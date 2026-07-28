"""Regression tests for validation_protocol_persistence.py. Reuses the
same fake-Supabase-client pattern already established in
test_sign_off_persistence.py / test_decision_record_persistence.py.
"""

from datetime import date

from validation_case_protocol import (
    ValidationCaseProtocol, DecisionContext, LockedCandidateSet,
    CandidateEligibilityRule, ReferenceEvidenceCorpus, ExpertPanel,
    ExpertPanelMember, lock_protocol,
)
from validation_protocol_persistence import (
    VALIDATION_PROTOCOL_TABLE_NAME,
    persist_protocol,
    load_protocol,
    load_protocol_history,
)


# ---------------------------------------------------------------------
# Fake Supabase client — same shape as test_sign_off_persistence.py's.
# ---------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, store, table_name):
        self._store = store
        self._table_name = table_name
        self._pending_row = None
        self._filters = {}

    def insert(self, row):
        self._pending_row = row
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field, value):
        self._filters[field] = value
        return self

    def execute(self):
        if self._pending_row is not None:
            self._store.setdefault(self._table_name, []).append(self._pending_row)
            self._pending_row = None
            return _FakeResponse(None)

        rows = self._store.get(self._table_name, [])
        if self._filters:
            rows = [
                r for r in rows
                if all(r.get(k) == v for k, v in self._filters.items())
            ]
        return _FakeResponse(rows)


class _FakeSupabaseClient:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _FakeTable(self.store, name)


class _FailingSupabaseClient:
    def table(self, name):
        raise ConnectionError("simulated: could not reach Supabase")


def _draft_protocol(**overrides):
    defaults = dict(case_name="Draft case", decision_context=DecisionContext(population="Adults"))
    defaults.update(overrides)
    return ValidationCaseProtocol(**defaults)


def _fully_locked_protocol(**overrides):
    protocol = ValidationCaseProtocol(
        case_name="Locked case",
        decision_context=DecisionContext(
            population="Adults", route_of_administration="Oral",
            dosage_form="Capsule", jurisdiction="EU",
        ),
        candidate_set=LockedCandidateSet(
            candidates=["Plant A"],
            eligibility_rules=[CandidateEligibilityRule("Documented use")],
        ),
        reference_corpus=ReferenceEvidenceCorpus(
            description="desc", built_independently_of_platform=True,
            sources=["PubMed"], search_strategy="strategy",
            evidence_cutoff_date=date(2026, 1, 1),
        ),
        expert_panel=ExpertPanel(
            members=[ExpertPanelMember("Pharmacognosist")],
            review_protocol="protocol", independence_statement="statement",
        ),
    )
    for k, v in overrides.items():
        setattr(protocol, k, v)
    return lock_protocol(protocol)


# ---------------------------------------------------------------------
# persist_protocol — allowed at ANY readiness, unlike sign-off persistence
# ---------------------------------------------------------------------

def test_persist_draft_protocol_succeeds():
    client = _FakeSupabaseClient()
    result = persist_protocol(_draft_protocol(), supabase_client=client)
    assert result["status"] == "persisted"
    assert result["readiness"] == "Not validation-ready"
    assert len(client.store[VALIDATION_PROTOCOL_TABLE_NAME]) == 1


def test_persist_completely_empty_protocol_succeeds():
    client = _FakeSupabaseClient()
    empty = ValidationCaseProtocol(case_name="Empty")
    result = persist_protocol(empty, supabase_client=client)
    assert result["status"] == "persisted"
    assert result["readiness"] == "Not started"


def test_persist_locked_protocol_succeeds():
    client = _FakeSupabaseClient()
    result = persist_protocol(_fully_locked_protocol(), supabase_client=client)
    assert result["status"] == "persisted"
    assert result["readiness"] == "Locked"


def test_persist_assigns_new_protocol_id_on_first_save():
    client = _FakeSupabaseClient()
    protocol = _draft_protocol()
    assert protocol.protocol_id is None
    result = persist_protocol(protocol, supabase_client=client)
    assert result["protocol_id"] is not None
    assert len(result["protocol_id"]) > 0


def test_persist_reuses_existing_protocol_id():
    client = _FakeSupabaseClient()
    protocol = _draft_protocol()
    result1 = persist_protocol(protocol, supabase_client=client)
    protocol.protocol_id = result1["protocol_id"]
    result2 = persist_protocol(protocol, supabase_client=client)
    assert result2["protocol_id"] == result1["protocol_id"]


def test_persist_two_saves_append_not_overwrite():
    client = _FakeSupabaseClient()
    protocol = _draft_protocol()
    result1 = persist_protocol(protocol, supabase_client=client)
    protocol.protocol_id = result1["protocol_id"]
    persist_protocol(protocol, supabase_client=client)
    assert len(client.store[VALIDATION_PROTOCOL_TABLE_NAME]) == 2


def test_persist_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    result = persist_protocol(_draft_protocol(), supabase_client=client)
    assert result["status"] == "unavailable"
    assert "unavailable" in result["detail"].lower()


def test_persist_failure_detail_never_leaks_raw_exception_text():
    client = _FailingSupabaseClient()
    result = persist_protocol(_draft_protocol(), supabase_client=client)
    assert "simulated" not in result["detail"]
    assert "ConnectionError" not in result["detail"]


def test_persist_failure_still_returns_a_protocol_id():
    # Even on a database failure, a protocol_id is generated and
    # returned so the caller can keep it for a retry.
    client = _FailingSupabaseClient()
    result = persist_protocol(_draft_protocol(), supabase_client=client)
    assert result["protocol_id"] is not None


# ---------------------------------------------------------------------
# load_protocol
# ---------------------------------------------------------------------

def test_load_returns_none_when_nothing_persisted():
    client = _FakeSupabaseClient()
    assert load_protocol("nonexistent-id", supabase_client=client) is None


def test_load_returns_none_for_empty_protocol_id():
    client = _FakeSupabaseClient()
    assert load_protocol("", supabase_client=client) is None
    assert load_protocol(None, supabase_client=client) is None


def test_load_reconstructs_the_saved_protocol():
    client = _FakeSupabaseClient()
    protocol = _draft_protocol()
    result = persist_protocol(protocol, supabase_client=client)
    loaded = load_protocol(result["protocol_id"], supabase_client=client)
    assert loaded is not None
    assert loaded.case_name == "Draft case"
    assert loaded.decision_context.population == "Adults"


def test_load_reconstructs_a_fully_locked_protocol_with_nested_data():
    client = _FakeSupabaseClient()
    locked = _fully_locked_protocol()
    result = persist_protocol(locked, supabase_client=client)
    loaded = load_protocol(result["protocol_id"], supabase_client=client)
    assert loaded.locked is True
    assert loaded.candidate_set.candidates == ["Plant A"]
    assert loaded.candidate_set.eligibility_rules[0].rule == "Documented use"
    assert loaded.reference_corpus.evidence_cutoff_date == date(2026, 1, 1)
    assert loaded.expert_panel.members[0].role == "Pharmacognosist"


def test_load_returns_most_recent_version():
    client = _FakeSupabaseClient()
    protocol = _draft_protocol()
    result1 = persist_protocol(protocol, supabase_client=client)
    protocol.protocol_id = result1["protocol_id"]
    protocol.candidate_set = LockedCandidateSet(
        candidates=["New Plant"], eligibility_rules=[CandidateEligibilityRule("r")],
    )
    persist_protocol(protocol, supabase_client=client)

    loaded = load_protocol(result1["protocol_id"], supabase_client=client)
    assert loaded.candidate_set.candidates == ["New Plant"]


def test_load_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    assert load_protocol("some-id", supabase_client=client) is None


# ---------------------------------------------------------------------
# load_protocol_history
# ---------------------------------------------------------------------

def test_history_empty_when_nothing_persisted():
    client = _FakeSupabaseClient()
    assert load_protocol_history("nonexistent-id", supabase_client=client) == []


def test_history_returns_empty_list_for_missing_identifier():
    client = _FakeSupabaseClient()
    assert load_protocol_history("", supabase_client=client) == []
    assert load_protocol_history(None, supabase_client=client) == []


def test_history_contains_every_saved_version_most_recent_first():
    client = _FakeSupabaseClient()
    protocol = _draft_protocol()
    result1 = persist_protocol(protocol, supabase_client=client)
    pid = result1["protocol_id"]
    protocol.protocol_id = pid

    protocol.candidate_set = LockedCandidateSet(
        candidates=["Plant A"], eligibility_rules=[CandidateEligibilityRule("r")],
    )
    persist_protocol(protocol, supabase_client=client)

    protocol.candidate_set = LockedCandidateSet(
        candidates=["Plant A", "Plant B"], eligibility_rules=[CandidateEligibilityRule("r")],
    )
    persist_protocol(protocol, supabase_client=client)

    history = load_protocol_history(pid, supabase_client=client)
    assert len(history) == 3
    assert history[0].candidate_set.candidates == ["Plant A", "Plant B"]
    assert history[-1].candidate_set.candidates == []


def test_history_only_includes_matching_protocol_id():
    client = _FakeSupabaseClient()
    p1 = _draft_protocol(case_name="Case 1")
    p2 = _draft_protocol(case_name="Case 2")
    r1 = persist_protocol(p1, supabase_client=client)
    persist_protocol(p2, supabase_client=client)

    history = load_protocol_history(r1["protocol_id"], supabase_client=client)
    assert len(history) == 1
    assert history[0].case_name == "Case 1"


def test_history_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    assert load_protocol_history("some-id", supabase_client=client) == []
