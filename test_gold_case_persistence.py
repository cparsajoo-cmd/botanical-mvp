"""Tests for gold_case_persistence.py (Validation Architecture v3, Phase 2)."""

from dataset_split import DatasetSplit
from gold_case import GoldCase
from gold_case_persistence import (
    GOLD_CASE_TABLE_NAME, persist_gold_case, load_gold_case, load_gold_cases_by_split,
)
from synthetic_validation_fixtures.fixtures import build_synthetic_gold_cases
from validation_unit import ValidationUnit


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


def test_persist_draft_case_succeeds():
    client = _FakeSupabaseClient()
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"))
    result = persist_gold_case(case, supabase_client=client)
    assert result["status"] == "persisted"
    assert len(client.store[GOLD_CASE_TABLE_NAME]) == 1


def test_persist_two_saves_append_not_overwrite():
    client = _FakeSupabaseClient()
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"))
    persist_gold_case(case, supabase_client=client)
    persist_gold_case(case, supabase_client=client)
    assert len(client.store[GOLD_CASE_TABLE_NAME]) == 2


def test_persist_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"))
    result = persist_gold_case(case, supabase_client=client)
    assert result["status"] == "unavailable"
    assert "simulated" not in result["detail"]


def test_load_returns_none_when_not_found():
    client = _FakeSupabaseClient()
    assert load_gold_case("nonexistent", supabase_client=client) is None


def test_load_returns_none_for_empty_id():
    client = _FakeSupabaseClient()
    assert load_gold_case("", supabase_client=client) is None


def test_load_reconstructs_persisted_case():
    client = _FakeSupabaseClient()
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="Valeriana officinalis"))
    persist_gold_case(case, supabase_client=client)
    loaded = load_gold_case("c1", supabase_client=client)
    assert loaded.validation_unit.taxon == "Valeriana officinalis"


def test_load_returns_most_recent_version():
    client = _FakeSupabaseClient()
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="First"))
    persist_gold_case(case, supabase_client=client)
    case.validation_unit = ValidationUnit(taxon="Second")
    persist_gold_case(case, supabase_client=client)
    loaded = load_gold_case("c1", supabase_client=client)
    assert loaded.validation_unit.taxon == "Second"


def test_load_by_split_returns_only_matching_split():
    client = _FakeSupabaseClient()
    for c in build_synthetic_gold_cases():
        persist_gold_case(c, supabase_client=client)
    holdout = load_gold_cases_by_split(DatasetSplit.LOCKED_HOLDOUT.value, supabase_client=client)
    dev = load_gold_cases_by_split(DatasetSplit.DEVELOPMENT.value, supabase_client=client)
    assert len(holdout) == 2
    assert len(dev) == 5
    assert all(c.dataset_split == DatasetSplit.LOCKED_HOLDOUT for c in holdout)


def test_load_by_split_uses_latest_version_only():
    client = _FakeSupabaseClient()
    case = GoldCase(case_id="c1", validation_unit=ValidationUnit(taxon="X"), dataset_split=DatasetSplit.DEVELOPMENT)
    persist_gold_case(case, supabase_client=client)
    case.dataset_split = DatasetSplit.LOCKED_HOLDOUT
    persist_gold_case(case, supabase_client=client)

    dev_results = load_gold_cases_by_split(DatasetSplit.DEVELOPMENT.value, supabase_client=client)
    holdout_results = load_gold_cases_by_split(DatasetSplit.LOCKED_HOLDOUT.value, supabase_client=client)
    assert len(dev_results) == 0  # superseded version must not count
    assert len(holdout_results) == 1


def test_load_by_split_degrades_gracefully_on_connection_failure():
    client = _FailingSupabaseClient()
    assert load_gold_cases_by_split(DatasetSplit.LOCKED_HOLDOUT.value, supabase_client=client) == []
