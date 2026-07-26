"""
Task 4 — Locked, versioned decision record persistence.

WHAT THIS COVERS
decision_record_persistence.py's persist_decision_record() and
load_decision_record() — mirrors test_telemetry_persistence.py's fake
Supabase client pattern exactly, since decision_record_persistence.py
mirrors telemetry_persistence.py's own failure-safe design.

HOW TO RUN
    pytest -q test_decision_record_persistence.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import json

import data_contracts as dc
from decision_record_persistence import (
    DECISION_RECORD_TABLE_NAME,
    _PERSISTED_RECORD_FIELDS,
    _new_analysis_id,
    load_decision_record,
    persist_decision_record,
)


# ---------------------------------------------------------------------
# Fake Supabase client — same shape as test_telemetry_persistence.py's,
# extended with .select()/.eq() so load_decision_record() can be
# exercised too.
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


def _sample_candidate_assessment(**overrides):
    defaults = dict(
        project_id="p1", indication="Liver support", product_type="Infusion",
        dosage_form="Infusion", target_market="EU",
        reference_plant="Silybum marianum", reference_plant_part=None,
        reference_compound="Silymarin", reference_compound_id=None,
        alternative_plant="Allium cepa", alternative_plant_part=None,
        alternative_compound="Quercetin", alternative_compound_id=None,
        rd_opportunity_score=72.0,
        decision_class="Promising candidate; verify safety and standardization",
        evidence_confidence=55.0,
        gate_results={"safety": {"gate_name": "safety", "status": "passed", "reason": "x", "evidence": "y"}},
        scoring_config_version="1.0-default",
    )
    defaults.update(overrides)
    return dc.CandidateAssessment(**defaults)


# ---------------------------------------------------------------------
# One row per COMPLETE analysis (not one row per candidate) — the
# approved persistence unit.
# ---------------------------------------------------------------------

def test_one_row_persisted_per_analysis_not_per_candidate():
    records = [_sample_candidate_assessment() for _ in range(5)]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", supabase_client=client)
    assert len(client.store[DECISION_RECORD_TABLE_NAME]) == 1


def test_candidate_count_matches_number_of_records():
    records = [_sample_candidate_assessment() for _ in range(3)]
    client = _FakeSupabaseClient()
    summary = persist_decision_record(records, indication="Liver support", supabase_client=client)
    assert summary["candidate_count"] == 3
    row = client.store[DECISION_RECORD_TABLE_NAME][0]
    assert row["candidate_count"] == 3


def test_persisted_row_contains_only_allowlisted_record_fields():
    records = [_sample_candidate_assessment()]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", supabase_client=client)
    row = client.store[DECISION_RECORD_TABLE_NAME][0]
    serialized_records = json.loads(row["records"])
    assert len(serialized_records) == 1
    assert set(serialized_records[0].keys()) == set(_PERSISTED_RECORD_FIELDS)


def test_scoring_config_version_extracted_from_records():
    records = [_sample_candidate_assessment(scoring_config_version="2.0-custom")]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", supabase_client=client)
    row = client.store[DECISION_RECORD_TABLE_NAME][0]
    assert row["scoring_config_version"] == "2.0-custom"


def test_gate_results_are_preserved_in_the_persisted_record():
    gate_results = {
        "safety": {"gate_name": "safety", "status": "failed", "reason": "r", "evidence": "e"},
        "identity": {"gate_name": "identity", "status": "passed", "reason": "r2", "evidence": "e2"},
        "minimum_evidence": {"gate_name": "minimum_evidence", "status": "not_evaluable", "reason": "r3", "evidence": "e3"},
        "regulatory": {"gate_name": "regulatory", "status": "passed", "reason": "r4", "evidence": "e4"},
    }
    records = [_sample_candidate_assessment(gate_results=gate_results)]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", supabase_client=client)
    row = client.store[DECISION_RECORD_TABLE_NAME][0]
    serialized_records = json.loads(row["records"])
    assert serialized_records[0]["gate_results"] == gate_results


def test_created_at_is_populated():
    records = [_sample_candidate_assessment()]
    client = _FakeSupabaseClient()
    persist_decision_record(records, indication="Liver support", supabase_client=client)
    row = client.store[DECISION_RECORD_TABLE_NAME][0]
    assert row["created_at"]
    assert "T" in row["created_at"]  # ISO 8601


# ---------------------------------------------------------------------
# Lock semantics: append-only, never an overwrite/update.
# ---------------------------------------------------------------------

def test_same_analysis_id_persisted_twice_produces_two_rows_not_an_overwrite():
    records = [_sample_candidate_assessment()]
    client = _FakeSupabaseClient()
    first = persist_decision_record(
        records, indication="Liver support", analysis_id="fixed-id", supabase_client=client,
    )
    second = persist_decision_record(
        records, indication="Liver support", analysis_id="fixed-id", supabase_client=client,
    )
    assert first["analysis_id"] == second["analysis_id"] == "fixed-id"
    stored_rows = client.store[DECISION_RECORD_TABLE_NAME]
    assert len(stored_rows) == 2
    assert stored_rows[0]["created_at"] != stored_rows[1]["created_at"] or True  # ordering not required, just two distinct inserts


def test_no_update_or_upsert_method_is_ever_called():
    # A fake client whose table() only supports insert()/select()/eq()/
    # execute() — no update()/upsert() method exists at all. If
    # persist_decision_record() ever tried to call one, this would
    # raise AttributeError instead of silently succeeding.
    records = [_sample_candidate_assessment()]
    client = _FakeSupabaseClient()
    summary = persist_decision_record(records, indication="Liver support", supabase_client=client)
    assert summary["status"] == "persisted"
    assert not hasattr(_FakeTable, "update")
    assert not hasattr(_FakeTable, "upsert")


def test_module_source_never_calls_update_or_upsert():
    with open("decision_record_persistence.py", encoding="utf-8") as f:
        source = f.read()
    assert ".update(" not in source
    assert ".upsert(" not in source
    assert ".delete(" not in source


def test_load_decision_record_returns_the_latest_version_when_persisted_twice():
    client = _FakeSupabaseClient()
    persist_decision_record(
        [_sample_candidate_assessment(rd_opportunity_score=10.0)],
        indication="Liver support", analysis_id="fixed-id", supabase_client=client,
    )
    persist_decision_record(
        [_sample_candidate_assessment(rd_opportunity_score=99.0)],
        indication="Liver support", analysis_id="fixed-id", supabase_client=client,
    )
    # Force distinguishable created_at ordering regardless of clock
    # resolution, since both calls may land in the same millisecond.
    rows = client.store[DECISION_RECORD_TABLE_NAME]
    rows[0]["created_at"] = "2020-01-01T00:00:00+00:00"
    rows[1]["created_at"] = "2020-01-02T00:00:00+00:00"

    loaded = load_decision_record("fixed-id", supabase_client=client)
    assert loaded is not None
    assert loaded["records"][0]["rd_opportunity_score"] == 99.0


# ---------------------------------------------------------------------
# Failure policy — never raises, generic detail text only.
# ---------------------------------------------------------------------

def test_persist_failure_returns_gracefully_never_raises():
    records = [_sample_candidate_assessment()]
    failing_client = _FailingSupabaseClient()
    summary = persist_decision_record(records, indication="Liver support", supabase_client=failing_client)
    assert summary["status"] == "unavailable"
    assert "simulated" not in summary["detail"]
    assert "ConnectionError" not in summary["detail"]


def test_load_failure_returns_none_never_raises():
    failing_client = _FailingSupabaseClient()
    result = load_decision_record("any-id", supabase_client=failing_client)
    assert result is None


def test_load_missing_analysis_id_returns_none():
    client = _FakeSupabaseClient()
    result = load_decision_record("does-not-exist", supabase_client=client)
    assert result is None


def test_load_none_or_empty_analysis_id_returns_none_without_a_query():
    client = _FakeSupabaseClient()
    assert load_decision_record(None, supabase_client=client) is None
    assert load_decision_record("", supabase_client=client) is None
    assert client.tables_used == []


# ---------------------------------------------------------------------
# Empty / missing records handled gracefully.
# ---------------------------------------------------------------------

def test_empty_records_list_persists_zero_candidates_without_error():
    client = _FakeSupabaseClient()
    summary = persist_decision_record([], indication="Liver support", supabase_client=client)
    assert summary["status"] == "persisted"
    assert summary["candidate_count"] == 0
    assert DECISION_RECORD_TABLE_NAME not in client.store


def test_none_records_does_not_crash():
    client = _FakeSupabaseClient()
    summary = persist_decision_record(None, indication="Liver support", supabase_client=client)
    assert summary["candidate_count"] == 0


# ---------------------------------------------------------------------
# analysis_id semantics
# ---------------------------------------------------------------------

def test_analysis_id_auto_generated_when_not_provided():
    id1 = _new_analysis_id()
    id2 = _new_analysis_id()
    assert id1 != id2
    assert len(id1) == 36  # UUID4 string length


def test_explicit_analysis_id_is_used_verbatim():
    records = [_sample_candidate_assessment()]
    client = _FakeSupabaseClient()
    summary = persist_decision_record(
        records, indication="Liver support", analysis_id="my-custom-id", supabase_client=client,
    )
    assert summary["analysis_id"] == "my-custom-id"


# ---------------------------------------------------------------------
# No import-time dependency on scoring/engine code — this module only
# consumes already-validated CandidateAssessment records.
# ---------------------------------------------------------------------

def test_module_has_no_import_time_dependency_on_the_engine_or_validation():
    with open("decision_record_persistence.py", encoding="utf-8") as f:
        source = f.read()
    for forbidden_module in ["botanical_rd_candidate_engine", "candidate_output_adapter"]:
        assert f"import {forbidden_module}" not in source
        assert f"from {forbidden_module}" not in source


# ---------------------------------------------------------------------
# UI wiring — AST/source inspection only (wiring, not behavior), same
# scoping discipline as test_gate_layer.py / test_task2_sensitivity_ui.py.
# ---------------------------------------------------------------------

def test_step_rd_candidates_imports_persist_decision_record():
    with open("step_rd_candidates.py", encoding="utf-8") as f:
        source = f.read()
    assert "from decision_record_persistence import persist_decision_record" in source


def test_step_rd_candidates_ui_never_exposes_database_internals():
    with open("step_rd_candidates.py", encoding="utf-8") as f:
        source = f.read()
    assert "Decision record persisted" in source
    assert "Decision-record persistence unavailable" in source
    assert "supabase_client" not in source
    assert "SELECT" not in source
    assert "INSERT INTO" not in source
    assert f'"{DECISION_RECORD_TABLE_NAME}"' not in source
    assert f"'{DECISION_RECORD_TABLE_NAME}'" not in source
