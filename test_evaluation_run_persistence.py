"""Tests for evaluation_run_persistence.py (Validation Architecture v3, Phase 2)."""

import botanical_rd_candidate_engine as eng
from dataset_split import DatasetSplit, LeakageControl
from gold_case import GoldCase, RiskStratum, ExpectedOutput, DecisionDirection
from evaluation_run import build_evaluation_run
from evaluation_run_persistence import (
    EVALUATION_RUN_TABLE_NAME, persist_evaluation_run, load_evaluation_run_summary,
)
from validation_unit import ValidationUnit, PreparationSpec



def _reset_engine_globals():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}


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
            rows = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
        return _FakeResponse(rows)


class _FakeSupabaseClient:
    def __init__(self):
        self.store = {}

    def table(self, name):
        return _FakeTable(self.store, name)


class _FailingSupabaseClient:
    def table(self, name):
        raise ConnectionError("simulated: could not reach Supabase")


def _sample_run():
    from synthetic_validation_fixtures.fixtures import build_synthetic_gold_cases
    cases = {c.case_id: c for c in build_synthetic_gold_cases()}
    locked_holdout_case = cases["synthetic_locked_holdout_clean_001"]
    assert locked_holdout_case.locked is True
    return build_evaluation_run([locked_holdout_case], gold_set_version="test-v1")


def test_persist_succeeds():
    _reset_engine_globals()
    client = _FakeSupabaseClient()
    run = _sample_run()
    result = persist_evaluation_run(run, supabase_client=client)
    assert result["status"] == "persisted"
    assert len(client.store[EVALUATION_RUN_TABLE_NAME]) == 1


def test_persist_degrades_gracefully_on_connection_failure():
    _reset_engine_globals()
    client = _FailingSupabaseClient()
    run = _sample_run()
    result = persist_evaluation_run(run, supabase_client=client)
    assert result["status"] == "unavailable"
    assert "simulated" not in result["detail"]


def test_two_runs_produce_two_separate_rows():
    _reset_engine_globals()
    client = _FakeSupabaseClient()
    run_a = _sample_run()
    run_b = _sample_run()
    persist_evaluation_run(run_a, supabase_client=client)
    persist_evaluation_run(run_b, supabase_client=client)
    assert len(client.store[EVALUATION_RUN_TABLE_NAME]) == 2


def test_load_returns_none_when_not_found():
    client = _FakeSupabaseClient()
    assert load_evaluation_run_summary("nonexistent", supabase_client=client) is None


def test_load_returns_none_for_empty_id():
    client = _FakeSupabaseClient()
    assert load_evaluation_run_summary("", supabase_client=client) is None


def test_load_reconstructs_persisted_summary():
    _reset_engine_globals()
    client = _FakeSupabaseClient()
    run = _sample_run()
    persist_evaluation_run(run, supabase_client=client)
    summary = load_evaluation_run_summary(run.evaluation_run_id, supabase_client=client)
    assert summary["evaluation_run_id"] == run.evaluation_run_id
    assert summary["gold_set_version"] == "test-v1"
    assert len(summary["results"]) == 2


def test_load_summary_includes_metric_reports():
    _reset_engine_globals()
    client = _FakeSupabaseClient()
    run = _sample_run()
    persist_evaluation_run(run, supabase_client=client)
    summary = load_evaluation_run_summary(run.evaluation_run_id, supabase_client=client)
    metric_names = {r["metric_name"] for r in summary["results"]}
    assert metric_names == {"decision_direction_agreement", "safety_serious_false_negative_rate"}


def test_load_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    assert load_evaluation_run_summary("some-id", supabase_client=client) is None
