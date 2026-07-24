"""Regression tests for telemetry_persistence.py (Sprint 6A.2)."""

from telemetry_persistence import (
    persist_connector_telemetry,
    _new_session_id,
    TELEMETRY_TABLE_NAME,
    _PERSISTED_CONNECTOR_FIELDS,
)


class _FakeTable:
    def __init__(self, store, table_name):
        self._store = store
        self._table_name = table_name
        self._pending_rows = None

    def insert(self, rows):
        self._pending_rows = rows
        return self

    def execute(self):
        self._store.setdefault(self._table_name, []).extend(self._pending_rows)
        return None


class _FakeSupabaseClient:
    """Records every table/rows insert call it receives — used to
    verify what this module WOULD have written, without touching a
    real database."""
    def __init__(self):
        self.store = {}
        self.tables_used = []

    def table(self, name):
        self.tables_used.append(name)
        return _FakeTable(self.store, name)


class _FailingSupabaseClient:
    def table(self, name):
        raise ConnectionError("simulated: could not reach Supabase")


def _sample_observability(connector_count=3):
    return {
        "scope": "current_collection_session",
        "overall_status": "completed",
        "connectors": [
            {
                "connector_name": f"Connector{i}", "connector_type": "Scientific literature",
                "execution_status": "Completed", "configuration_status": "Not required",
                "records_saved": i, "error_count": 0, "error_types": [], "error_messages": [],
                "cache_observability": "No repository-level cache detected.",
                "limitations": [],
            }
            for i in range(connector_count)
        ],
        "session_totals": {}, "limitations": [],
    }


# ---------------------------------------------------------------------
# 1. One telemetry row generated for every connector
# ---------------------------------------------------------------------
def test_one_row_generated_per_connector():
    observability = _sample_observability(connector_count=5)
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    assert len(client.store[TELEMETRY_TABLE_NAME]) == 5


# ---------------------------------------------------------------------
# 2. All rows in one collection session share one session_id
# ---------------------------------------------------------------------
def test_all_rows_in_one_session_share_one_session_id():
    observability = _sample_observability(connector_count=4)
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    session_ids = {row["session_id"] for row in client.store[TELEMETRY_TABLE_NAME]}
    assert len(session_ids) == 1


# ---------------------------------------------------------------------
# 3. Different collection sessions receive different session_ids
# ---------------------------------------------------------------------
def test_different_sessions_get_different_session_ids():
    observability = _sample_observability(connector_count=2)
    client1, client2 = _FakeSupabaseClient(), _FakeSupabaseClient()
    summary1 = persist_connector_telemetry(observability, supabase_client=client1)
    summary2 = persist_connector_telemetry(observability, supabase_client=client2)
    assert summary1["session_id"] != summary2["session_id"]


# ---------------------------------------------------------------------
# 4. Connector rows preserve Sprint 6A.1 fields
# ---------------------------------------------------------------------
def test_connector_rows_preserve_sprint_6a1_fields():
    observability = _sample_observability(connector_count=1)
    connector_entry = observability["connectors"][0]
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    row = client.store[TELEMETRY_TABLE_NAME][0]
    for field in _PERSISTED_CONNECTOR_FIELDS:
        assert row[field] == connector_entry[field]


# ---------------------------------------------------------------------
# 5. recorded_at is populated
# ---------------------------------------------------------------------
def test_recorded_at_is_populated():
    observability = _sample_observability(connector_count=1)
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    row = client.store[TELEMETRY_TABLE_NAME][0]
    assert row["recorded_at"]
    assert "T" in row["recorded_at"]  # ISO 8601 format


# ---------------------------------------------------------------------
# 6. Documentation identifies recorded_at as persistence time
# ---------------------------------------------------------------------
def test_documentation_identifies_recorded_at_as_persistence_time():
    with open("telemetry_persistence.py") as f:
        source = f.read()
    assert "recorded_at is the time this module wrote the row" in source
    assert "NOT when any" in source
    assert "connector executed" in source


# ---------------------------------------------------------------------
# 7. No execution timestamp fields exist
# ---------------------------------------------------------------------
def test_no_execution_timestamp_fields_exist():
    observability = _sample_observability(connector_count=1)
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    row = client.store[TELEMETRY_TABLE_NAME][0]
    for forbidden in ["execution_started_at", "execution_finished_at", "started_at", "finished_at"]:
        assert forbidden not in row


# ---------------------------------------------------------------------
# 8. No duration field exists
# ---------------------------------------------------------------------
def test_no_duration_field_exists():
    observability = _sample_observability(connector_count=1)
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    row = client.store[TELEMETRY_TABLE_NAME][0]
    assert "duration" not in row
    assert "execution_duration" not in row


# ---------------------------------------------------------------------
# 9. No uptime exists
# ---------------------------------------------------------------------
def test_no_uptime_field_exists():
    observability = _sample_observability(connector_count=1)
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    row = client.store[TELEMETRY_TABLE_NAME][0]
    assert "uptime" not in row
    assert "availability" not in row


# ---------------------------------------------------------------------
# 10. No success-rate exists
# ---------------------------------------------------------------------
def test_no_success_rate_or_attempt_count_fields_exist():
    observability = _sample_observability(connector_count=1)
    client = _FakeSupabaseClient()
    persist_connector_telemetry(observability, supabase_client=client)
    row = client.store[TELEMETRY_TABLE_NAME][0]
    for forbidden in ["success_rate", "attempt_count", "successful_attempt_count", "connector_version"]:
        assert forbidden not in row


# ---------------------------------------------------------------------
# 11. No connector files modified — verified structurally
# ---------------------------------------------------------------------
def test_module_imports_no_connector_files_or_collector():
    with open("telemetry_persistence.py") as f:
        source = f.read()
    assert "_connector import" not in source
    assert "import multi_source_collector" not in source
    assert "from multi_source_collector" not in source


# ---------------------------------------------------------------------
# 12. Telemetry persistence failure does not interrupt recommendations
# ---------------------------------------------------------------------
def test_persistence_failure_returns_gracefully_never_raises():
    observability = _sample_observability(connector_count=2)
    failing_client = _FailingSupabaseClient()
    summary = persist_connector_telemetry(observability, supabase_client=failing_client)
    assert summary["status"] == "unavailable"
    assert summary["rows_persisted"] == 0
    assert "simulated" not in summary["detail"]
    assert "ConnectionError" not in summary["detail"]


def test_persistence_failure_detail_is_safe_generic_text():
    failing_client = _FailingSupabaseClient()
    summary = persist_connector_telemetry(_sample_observability(1), supabase_client=failing_client)
    assert "Telemetry persistence unavailable" in summary["detail"]


# ---------------------------------------------------------------------
# Session identifier semantics
# ---------------------------------------------------------------------
def test_session_id_is_a_pure_grouping_key_not_derived_from_content():
    id1 = _new_session_id()
    id2 = _new_session_id()
    assert id1 != id2
    assert len(id1) == 36  # standard UUID4 string length


# ---------------------------------------------------------------------
# Empty / missing observability handled gracefully
# ---------------------------------------------------------------------
def test_empty_observability_persists_zero_rows_without_error():
    client = _FakeSupabaseClient()
    summary = persist_connector_telemetry({"connectors": []}, supabase_client=client)
    assert summary["rows_attempted"] == 0
    assert summary["status"] == "persisted"


def test_none_observability_does_not_crash():
    client = _FakeSupabaseClient()
    summary = persist_connector_telemetry(None, supabase_client=client)
    assert summary["rows_attempted"] == 0


# ---------------------------------------------------------------------
# Real Sprint 6A.1 integration — proves this module consumes the
# ACTUAL frozen output shape, not just a hand-built fixture
# ---------------------------------------------------------------------
def test_real_sprint_6a1_output_persists_correctly():
    from connector_session_observability import build_connector_session_observability

    collection_result = {
        "saved_records": [{"source": "PubMed"}] * 10,
        "errors": [{"source": "ChEMBL", "error": "Timed out after 50s (overall budget, not this source alone)."}],
        "sources_checked": ["PubMed", "ChEMBL"],
    }
    observability = build_connector_session_observability(collection_result)
    client = _FakeSupabaseClient()
    summary = persist_connector_telemetry(observability, supabase_client=client)

    assert summary["status"] == "persisted"
    assert summary["rows_persisted"] == len(observability["connectors"])

    rows_by_name = {r["connector_name"]: r for r in client.store[TELEMETRY_TABLE_NAME]}
    assert rows_by_name["PubMed"]["execution_status"] == "Completed"
    assert rows_by_name["PubMed"]["records_saved"] == 10
    assert rows_by_name["ChEMBL"]["execution_status"] == "Timed out"


# ---------------------------------------------------------------------
# 13-18: backward compatibility — this module has no import-time
# dependency on scoring, ranking, evidence, or regulatory code.
# ---------------------------------------------------------------------
def test_module_has_no_import_time_dependency_on_scoring_or_recommendation_code():
    with open("telemetry_persistence.py") as f:
        source = f.read()
    for forbidden_module in [
        "botanical_rd_candidate_engine", "structured_rationale",
        "comparative_rationale", "scoring_sensitivity_report",
    ]:
        assert f"import {forbidden_module}" not in source
        assert f"from {forbidden_module}" not in source


def test_ui_only_exposes_minimal_persistence_message():
    with open("step_evidence.py") as f:
        source = f.read()
    assert "Telemetry persisted successfully" in source
    assert "Telemetry persistence unavailable" in source
    assert "from telemetry_persistence import persist_connector_telemetry" in source
    # Must never expose database/SQL internals in the UI file.
    assert "supabase_client" not in source
    assert "SELECT" not in source
    assert "INSERT INTO" not in source
    # The table name must never appear as its own quoted literal (which
    # would indicate direct exposure) — its appearance as a substring of
    # the imported function name persist_connector_telemetry is fine.
    assert f'"{TELEMETRY_TABLE_NAME}"' not in source
    assert f"'{TELEMETRY_TABLE_NAME}'" not in source


if __name__ == "__main__":
    import sys

    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        this_module = sys.modules[__name__]
        test_fns = [
            getattr(this_module, name)
            for name in dir(this_module)
            if name.startswith("test_") and callable(getattr(this_module, name))
        ]
        passed, failed = [], []
        for fn in test_fns:
            try:
                fn()
            except AssertionError as exc:
                failed.append((fn.__name__, str(exc) or "assertion failed"))
            except Exception as exc:  # noqa: BLE001
                failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            else:
                passed.append(fn.__name__)
        print(f"\n{len(passed) + len(failed)} test(s) run.\n")
        for name in passed:
            print(f"  \u2705 {name}")
        if failed:
            print()
            for name, reason in failed:
                print(f"  \u274c {name}\n     -> {reason}")
            print(f"\n{len(failed)} FAILED, {len(passed)} passed.\n")
            sys.exit(1)
        print(f"\nALL TESTS PASSED ({len(passed)}/{len(passed)}).\n")
        sys.exit(0)
