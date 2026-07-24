"""Regression tests for connector_session_observability.py (Sprint 6A.1)."""

from connector_session_observability import (
    build_connector_session_observability,
    _classify_error,
    _connector_type,
    _cache_observability,
    _configuration_status,
    _derive_overall_status,
    PUBMED_OBSERVABILITY_LIMITATION,
    SESSION_LIMITATIONS,
)


# ---------------------------------------------------------------------
# 1. Deterministic output for fixed input
# ---------------------------------------------------------------------
def test_deterministic_output_for_fixed_input():
    collection_result = {
        "saved_records": [{"source": "PubMed"}], "errors": [],
        "sources_checked": ["PubMed", "ChEMBL"],
    }
    result1 = build_connector_session_observability(collection_result)
    result2 = build_connector_session_observability(collection_result)
    assert result1 == result2


# ---------------------------------------------------------------------
# 2. Completed with records
# ---------------------------------------------------------------------
def test_completed_with_records():
    collection_result = {
        "saved_records": [{"source": "PubMed"}, {"source": "PubMed"}],
        "errors": [], "sources_checked": ["PubMed"],
    }
    obj = build_connector_session_observability(collection_result)
    entry = obj["connectors"][0]
    assert entry["execution_status"] == "Completed"
    assert entry["records_saved"] == 2


# ---------------------------------------------------------------------
# 3. Completed with zero records
# ---------------------------------------------------------------------
def test_completed_with_zero_records():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": ["ChEMBL"]}
    obj = build_connector_session_observability(collection_result)
    entry = obj["connectors"][0]
    assert entry["execution_status"] == "Completed — no records"
    assert entry["records_saved"] == 0
    assert entry["error_type"] is None  # distinct from failure


# ---------------------------------------------------------------------
# 4. Timeout detection from existing error-message patterns
# ---------------------------------------------------------------------
def test_timeout_detection_from_real_error_message_pattern():
    error_message = "Timed out after 50s (overall budget, not this source alone)."
    assert _classify_error(error_message) == "timeout"

    collection_result = {
        "saved_records": [], "errors": [{"source": "OpenAlex", "error": error_message}],
        "sources_checked": ["OpenAlex"],
    }
    obj = build_connector_session_observability(collection_result)
    assert obj["connectors"][0]["execution_status"] == "Timed out"


# ---------------------------------------------------------------------
# 5. Not-configured detection
# ---------------------------------------------------------------------
def test_not_configured_detection():
    error_message = "Set EPO_OPS_KEY and EPO_OPS_SECRET (free registration at https://developers.epo.org/) to enable patent search."
    assert _classify_error(error_message) == "configuration_missing"

    collection_result = {
        "saved_records": [], "errors": [{"source": "Patent Landscape", "error": error_message}],
        "sources_checked": ["Patent Landscape"],
    }
    obj = build_connector_session_observability(collection_result)
    entry = obj["connectors"][0]
    assert entry["execution_status"] == "Not configured"
    assert entry["configuration_status"] == "Not configured"


# ---------------------------------------------------------------------
# 6. Generic failure classification
# ---------------------------------------------------------------------
def test_generic_failure_classification():
    error_message = "ConnectionResetError: [Errno 104] Connection reset by peer"
    assert _classify_error(error_message) == "generic_failure"
    collection_result = {
        "saved_records": [], "errors": [{"source": "CrossRef", "error": error_message}],
        "sources_checked": ["CrossRef"],
    }
    obj = build_connector_session_observability(collection_result)
    assert obj["connectors"][0]["execution_status"] == "Failed"
    assert obj["connectors"][0]["error_type"] == "generic_failure"


# ---------------------------------------------------------------------
# 7. Not-attempted connector
# ---------------------------------------------------------------------
def test_not_attempted_connector_reported_separately():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": ["PubMed"]}
    obj = build_connector_session_observability(collection_result)
    names = {c["connector_name"]: c["execution_status"] for c in obj["connectors"]}
    assert names["PubMed"] == "Completed — no records"
    not_attempted = [n for n, s in names.items() if s == "Not attempted"]
    assert len(not_attempted) > 0
    assert "PubMed" not in not_attempted
    assert obj["session_totals"]["sources_attempted"] == 1


# ---------------------------------------------------------------------
# 8. Unknown fallback
# ---------------------------------------------------------------------
def test_unknown_fallback_for_empty_error_message():
    assert _classify_error("") == "unknown"
    assert _classify_error(None) == "unknown"


# ---------------------------------------------------------------------
# 9. Correct status precedence
# ---------------------------------------------------------------------
def test_status_precedence_configuration_missing_beats_generic_wording_overlap():
    error_message = "Request failed: missing credentials for this API."
    assert _classify_error(error_message) == "configuration_missing"


def test_status_precedence_timeout_not_misclassified_as_generic():
    assert _classify_error("Timed out after 50s (overall budget, not this source alone).") == "timeout"


# ---------------------------------------------------------------------
# 10. Source-registry category reuse
# ---------------------------------------------------------------------
def test_connector_type_reuses_source_registry_category():
    assert _connector_type("PubMed") == "Scientific literature"
    assert _connector_type("ChEMBL") is not None


# ---------------------------------------------------------------------
# 11. "Unclassified" fallback without name-based guessing
# ---------------------------------------------------------------------
def test_unclassified_fallback_for_unregistered_source_name():
    assert _connector_type("SomeNewConnectorNobodyRegisteredYet") == "Unclassified"


# ---------------------------------------------------------------------
# 12. Session-scoped record counts
# ---------------------------------------------------------------------
def test_session_scoped_record_counts_per_source():
    collection_result = {
        "saved_records": [
            {"source": "PubMed"}, {"source": "PubMed"}, {"source": "PubMed"},
            {"source": "ChEMBL"},
        ],
        "errors": [], "sources_checked": ["PubMed", "ChEMBL"],
    }
    obj = build_connector_session_observability(collection_result)
    counts = {c["connector_name"]: c["records_saved"] for c in obj["connectors"]}
    assert counts["PubMed"] == 3
    assert counts["ChEMBL"] == 1


# ---------------------------------------------------------------------
# 13. Correct session totals
# ---------------------------------------------------------------------
def test_session_totals_correct_across_mixed_outcomes():
    collection_result = {
        "saved_records": [{"source": "PubMed"}, {"source": "PubMed"}],
        "errors": [
            {"source": "ChEMBL", "error": "Timed out after 50s (overall budget, not this source alone)."},
            {"source": "Patent Landscape", "error": "Set EPO_OPS_KEY and EPO_OPS_SECRET to enable patent search."},
            {"source": "CrossRef", "error": "Some other network error"},
        ],
        "sources_checked": ["PubMed", "ChEMBL", "Patent Landscape", "CrossRef", "ChEBI"],
    }
    obj = build_connector_session_observability(collection_result)
    totals = obj["session_totals"]
    assert totals["sources_attempted"] == 5
    assert totals["sources_completed"] == 1
    assert totals["sources_completed_no_records"] == 1
    assert totals["sources_timed_out"] == 1
    assert totals["sources_not_configured"] == 1
    assert totals["sources_failed"] == 1
    assert totals["records_saved"] == 2


# ---------------------------------------------------------------------
# 14. EMA cache observability
# ---------------------------------------------------------------------
def test_ema_cache_observability_states_the_real_lru_cache():
    result = _cache_observability("EMA/WHO/ESCOP Regulatory")
    assert "Repository-level cache detected" in result
    assert "lru_cache" in result
    assert "not observable" in result.lower()


# ---------------------------------------------------------------------
# 15. Conservative cache wording for non-EMA connectors
# ---------------------------------------------------------------------
def test_non_ema_cache_wording_is_conservative_not_absolute():
    result = _cache_observability("PubMed")
    assert "No repository-level cache detected" in result
    assert "does not imply" in result


# ---------------------------------------------------------------------
# 16. Configuration status values
# ---------------------------------------------------------------------
def test_configuration_status_values_are_conservative():
    assert _configuration_status("Patent Landscape", "configuration_missing") == "Not configured"
    assert _configuration_status("ChEMBL", None) == "Not required"
    assert _configuration_status("PubMed", None) == "Not observable"
    assert _configuration_status("Semantic Scholar", None) == "Not observable"
    forbidden = {"Valid", "Invalid", "Authenticated"}
    for source in ["PubMed", "ChEMBL", "Semantic Scholar", "Patent Landscape"]:
        assert _configuration_status(source, None) not in forbidden


# ---------------------------------------------------------------------
# 17. PubMed observability limitation
# ---------------------------------------------------------------------
def test_pubmed_limitation_present_and_worded_correctly():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": ["PubMed"]}
    obj = build_connector_session_observability(collection_result)
    entry = obj["connectors"][0]
    assert PUBMED_OBSERVABILITY_LIMITATION in entry["limitations"]
    assert "Biopython" in entry["limitations"][0]
    assert "Entrez" in entry["limitations"][0]


def test_pubmed_email_value_never_appears_anywhere_in_output():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": ["PubMed"]}
    obj = build_connector_session_observability(collection_result)
    output_text = str(obj)
    assert "@" not in output_text


# ---------------------------------------------------------------------
# 18. Explicit limitations about non-persistence
# ---------------------------------------------------------------------
def test_session_limitations_state_non_persistence_explicitly():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": []}
    obj = build_connector_session_observability(collection_result)
    assert obj["limitations"] == SESSION_LIMITATIONS
    assert any("not persisted" in lim for lim in obj["limitations"])
    assert any("current collection session only" in lim for lim in obj["limitations"])


# ---------------------------------------------------------------------
# 19-20. No last_success / last_failure fields anywhere
# ---------------------------------------------------------------------
def test_no_last_success_or_last_failure_fields_anywhere():
    collection_result = {
        "saved_records": [{"source": "PubMed"}], "errors": [{"source": "ChEMBL", "error": "x"}],
        "sources_checked": ["PubMed", "ChEMBL"],
    }
    obj = build_connector_session_observability(collection_result)
    output_text = str(obj).lower()
    assert "last_success" not in output_text
    assert "last_failure" not in output_text
    assert "last success" not in output_text
    assert "last failure" not in output_text


# ---------------------------------------------------------------------
# 21. No connector_version claim
# ---------------------------------------------------------------------
def test_no_connector_version_field_anywhere():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": ["PubMed"]}
    obj = build_connector_session_observability(collection_result)
    for connector in obj["connectors"]:
        assert "connector_version" not in connector
        assert "version" not in connector


# ---------------------------------------------------------------------
# 22. No execution-duration claim
# ---------------------------------------------------------------------
def test_no_execution_duration_field_anywhere():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": ["PubMed"]}
    obj = build_connector_session_observability(collection_result)
    for connector in obj["connectors"]:
        assert "duration" not in connector
        assert "last_duration" not in connector


# ---------------------------------------------------------------------
# 23. No freshness claim
# ---------------------------------------------------------------------
def test_no_freshness_or_timestamp_fields_anywhere():
    collection_result = {"saved_records": [], "errors": [], "sources_checked": ["PubMed"]}
    obj = build_connector_session_observability(collection_result)
    output_text = str(obj).lower()
    for forbidden_term in ["last_refresh", "data_age", "freshness", "last updated", "last_updated"]:
        assert forbidden_term not in output_text


# ---------------------------------------------------------------------
# Overall status derivation
# ---------------------------------------------------------------------
def test_overall_status_not_started_when_nothing_attempted():
    assert _derive_overall_status({
        "sources_attempted": 0, "sources_completed": 0, "sources_completed_no_records": 0,
        "sources_failed": 0, "sources_timed_out": 0, "sources_not_configured": 0, "records_saved": 0,
    }) == "not_started"


def test_overall_status_completed_when_all_clean():
    assert _derive_overall_status({
        "sources_attempted": 2, "sources_completed": 1, "sources_completed_no_records": 1,
        "sources_failed": 0, "sources_timed_out": 0, "sources_not_configured": 0, "records_saved": 5,
    }) == "completed"


def test_overall_status_completed_with_errors_when_mixed():
    assert _derive_overall_status({
        "sources_attempted": 2, "sources_completed": 1, "sources_completed_no_records": 0,
        "sources_failed": 1, "sources_timed_out": 0, "sources_not_configured": 0, "records_saved": 2,
    }) == "completed_with_errors"


def test_overall_status_failed_when_nothing_completed_cleanly():
    assert _derive_overall_status({
        "sources_attempted": 2, "sources_completed": 0, "sources_completed_no_records": 0,
        "sources_failed": 1, "sources_timed_out": 1, "sources_not_configured": 0, "records_saved": 0,
    }) == "failed"


# ---------------------------------------------------------------------
# Backward compatibility / robustness
# ---------------------------------------------------------------------
def test_handles_empty_collection_result_gracefully():
    obj = build_connector_session_observability({})
    assert obj["overall_status"] == "not_started"
    assert obj["session_totals"]["sources_attempted"] == 0


def test_handles_none_collection_result_gracefully():
    obj = build_connector_session_observability(None)
    assert obj["overall_status"] == "not_started"


def test_handles_malformed_record_missing_source_field():
    collection_result = {"saved_records": [{}], "errors": [{}], "sources_checked": ["PubMed"]}
    obj = build_connector_session_observability(collection_result)
    assert obj is not None


# ---------------------------------------------------------------------
# 24. UI consumes structured object rather than recomputing logic
# ---------------------------------------------------------------------
def test_step_evidence_ui_imports_and_uses_the_shared_function_not_a_duplicate():
    with open("step_evidence.py") as f:
        source = f.read()
    assert "from connector_session_observability import build_connector_session_observability" in source
    assert "build_connector_session_observability(research_output)" in source
    # No local re-implementation of the classification patterns this
    # module owns — the UI must never define its own copy of these.
    assert "_classify_error" not in source
    assert "_CONFIG_MISSING_PATTERNS" not in source
    assert "_TIMEOUT_PATTERNS" not in source


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
