"""Regression tests for sign_off_persistence.py (Task 8 — Structured
Expert Sign-Off Persistence). Reuses the same fake-Supabase-client
pattern already established in test_decision_record_persistence.py /
test_telemetry_persistence.py.
"""

from datetime import datetime, timedelta

from expert_sign_off import ExpertSignOff, SignOffDisposition, IncompleteSignOffError
from sign_off_persistence import (
    SIGN_OFF_TABLE_NAME, persist_sign_off, load_sign_offs_for_candidate,
)


# ---------------------------------------------------------------------
# Fake Supabase client — same shape as test_decision_record_persistence.py's
# _FakeSupabaseClient/_FakeTable/_FakeResponse.
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
        self.tables_used = []

    def table(self, name):
        self.tables_used.append(name)
        return _FakeTable(self.store, name)


class _FailingSupabaseClient:
    def table(self, name):
        raise ConnectionError("simulated: could not reach Supabase")


def _meaningful_sign_off(**overrides):
    start = datetime(2026, 1, 1, 10, 0, 0)
    defaults = dict(
        analysis_id="a1", reference_plant="RefPlant", alternative_plant="AltPlant",
        reviewer_role="Pharmacognosist", evidence_access_confirmed=True,
        review_started_at=start, review_completed_at=start + timedelta(minutes=10),
        disposition=SignOffDisposition.APPROVED,
        disposition_notes="Evidence base is solid and directly applicable.",
    )
    defaults.update(overrides)
    return ExpertSignOff(**defaults)


# ---------------------------------------------------------------------
# persist_sign_off — the hard refusal for incomplete sign-offs
# ---------------------------------------------------------------------

def test_persist_raises_on_incomplete_sign_off_and_writes_nothing():
    client = _FakeSupabaseClient()
    incomplete = ExpertSignOff(
        analysis_id="a1", reference_plant="RefPlant", alternative_plant="AltPlant",
    )
    try:
        persist_sign_off(incomplete, supabase_client=client)
        assert False, "should have raised"
    except IncompleteSignOffError:
        pass
    assert client.store == {}


def test_persist_succeeds_on_meaningful_sign_off():
    client = _FakeSupabaseClient()
    sign_off = _meaningful_sign_off()
    result = persist_sign_off(sign_off, supabase_client=client)
    assert result["status"] == "persisted"
    assert result["reference_plant"] == "RefPlant"
    assert result["disposition"] == "Approved"
    assert len(client.store[SIGN_OFF_TABLE_NAME]) == 1


def test_persisted_row_contains_recorded_at():
    client = _FakeSupabaseClient()
    persist_sign_off(_meaningful_sign_off(), supabase_client=client)
    row = client.store[SIGN_OFF_TABLE_NAME][0]
    assert "recorded_at" in row
    assert row["recorded_at"]


def test_persist_two_sign_offs_for_same_candidate_appends_not_overwrites():
    client = _FakeSupabaseClient()
    persist_sign_off(_meaningful_sign_off(), supabase_client=client)
    persist_sign_off(
        _meaningful_sign_off(disposition=SignOffDisposition.REJECTED,
                              disposition_notes="Second reviewer disagrees."),
        supabase_client=client,
    )
    assert len(client.store[SIGN_OFF_TABLE_NAME]) == 2


def test_persist_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    result = persist_sign_off(_meaningful_sign_off(), supabase_client=client)
    assert result["status"] == "unavailable"
    assert "unavailable" in result["detail"].lower()


def test_persist_failure_detail_never_leaks_raw_exception_text():
    client = _FailingSupabaseClient()
    result = persist_sign_off(_meaningful_sign_off(), supabase_client=client)
    assert "simulated" not in result["detail"]
    assert "ConnectionError" not in result["detail"]


def test_persist_still_raises_incomplete_error_even_with_failing_client():
    # The completeness check happens BEFORE any database access, so a
    # failing client must not change this from a raise into a status dict.
    client = _FailingSupabaseClient()
    incomplete = ExpertSignOff(
        analysis_id="a1", reference_plant="RefPlant", alternative_plant="AltPlant",
    )
    try:
        persist_sign_off(incomplete, supabase_client=client)
        assert False, "should have raised"
    except IncompleteSignOffError:
        pass


# ---------------------------------------------------------------------
# load_sign_offs_for_candidate
# ---------------------------------------------------------------------

def test_load_returns_empty_list_when_nothing_persisted():
    client = _FakeSupabaseClient()
    result = load_sign_offs_for_candidate("a1", "RefPlant", "AltPlant", supabase_client=client)
    assert result == []


def test_load_returns_persisted_sign_off():
    client = _FakeSupabaseClient()
    persist_sign_off(_meaningful_sign_off(), supabase_client=client)
    result = load_sign_offs_for_candidate("a1", "RefPlant", "AltPlant", supabase_client=client)
    assert len(result) == 1
    assert result[0]["disposition"] == "Approved"


def test_load_filters_by_exact_candidate_identity():
    client = _FakeSupabaseClient()
    persist_sign_off(_meaningful_sign_off(), supabase_client=client)
    persist_sign_off(
        _meaningful_sign_off(reference_plant="OtherRef", alternative_plant="OtherAlt"),
        supabase_client=client,
    )
    result = load_sign_offs_for_candidate("a1", "RefPlant", "AltPlant", supabase_client=client)
    assert len(result) == 1
    assert result[0]["reference_plant"] == "RefPlant"


def test_load_multiple_sign_offs_sorted_most_recent_first():
    client = _FakeSupabaseClient()
    persist_sign_off(_meaningful_sign_off(disposition_notes="First review."), supabase_client=client)
    persist_sign_off(
        _meaningful_sign_off(
            disposition=SignOffDisposition.REJECTED,
            disposition_notes="Second review, later.",
        ),
        supabase_client=client,
    )
    result = load_sign_offs_for_candidate("a1", "RefPlant", "AltPlant", supabase_client=client)
    assert len(result) == 2
    # Most recent (the second persisted) must come first.
    assert result[0]["disposition"] == "Rejected"
    assert result[1]["disposition"] == "Approved"


def test_load_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    result = load_sign_offs_for_candidate("a1", "RefPlant", "AltPlant", supabase_client=client)
    assert result == []


def test_load_returns_empty_list_on_missing_identifiers():
    client = _FakeSupabaseClient()
    assert load_sign_offs_for_candidate("", "RefPlant", "AltPlant", supabase_client=client) == []
    assert load_sign_offs_for_candidate("a1", "", "AltPlant", supabase_client=client) == []
    assert load_sign_offs_for_candidate("a1", "RefPlant", "", supabase_client=client) == []
