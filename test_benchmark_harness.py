"""
Task 5 — Benchmark harness tests.

READ benchmark_harness.py's module docstring first: the bundled fixture
(benchmark_cases/smoke_cases.json) is a SYNTHETIC, engineer-authored
smoke set proving the harness's own mechanics work — loading, running
cases through the unmodified engine, and comparing against a recorded
expected outcome. It is NOT scientific validation, benchmark
calibration, or domain validation, and this test file makes no such
claim either. When a real, expert-curated case file exists, this same
CI-enforced test (test_smoke_fixture_agreement_rate_is_100_percent)
is the template for wrapping it as a permanent regression guardrail —
see benchmark_harness.py's own docstring for that separation of
concerns.

HOW TO RUN
    pytest -q test_benchmark_harness.py
"""

import json
import os

import pandas as pd
import pytest

from benchmark_harness import (
    compare_to_expected,
    load_benchmark_cases,
    main,
    run_benchmark,
)

SMOKE_FIXTURE_PATH = os.path.join("benchmark_cases", "smoke_cases.json")


# ---------------------------------------------------------------------
# load_benchmark_cases
# ---------------------------------------------------------------------

def test_load_benchmark_cases_parses_the_bundled_smoke_fixture():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    assert isinstance(cases, list)
    assert len(cases) == 3
    assert {c["case_id"] for c in cases} == {
        "smoke_safety_exclusion",
        "smoke_no_evidence_low_priority",
        "smoke_direct_evidence_present",
    }


def test_load_benchmark_cases_every_case_has_a_non_scientific_note():
    # Each bundled case must self-document that it is not a real
    # historical/expert-curated case — the honesty discipline this
    # harness's docstring requires is not optional per-case.
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    for case in cases:
        assert case.get("note"), f"{case['case_id']} is missing its 'note' field"
        assert "synthetic" in case["note"].lower() or "not" in case["note"].lower()


def test_load_benchmark_cases_rejects_non_list_json(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"not": "a list"}))
    with pytest.raises(ValueError):
        load_benchmark_cases(str(bad_file))


def test_load_benchmark_cases_empty_list_is_valid(tmp_path):
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("[]")
    assert load_benchmark_cases(str(empty_file)) == []


# ---------------------------------------------------------------------
# run_benchmark — reuses the UNMODIFIED engine via make_engine(), no
# scoring/gating logic reimplemented here.
# ---------------------------------------------------------------------

def test_run_benchmark_produces_one_row_per_output_pair():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    results_df = run_benchmark(cases)
    # 2 pairs (safety case) + 2 pairs (no-evidence case) + 1 pair
    # (direct-evidence case, single reference plant only) = 5.
    assert len(results_df) == 5
    assert set(results_df.columns) == {
        "case_id", "reference_plant", "alternative_plant",
        "decision_class", "decision_class_ah", "gate_results", "run_error",
    }


def test_run_benchmark_captures_real_gate_results_not_reinterpreted():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    results_df = run_benchmark(cases)
    safety_case_rows = results_df[results_df["case_id"] == "smoke_safety_exclusion"]
    alt_row = safety_case_rows[safety_case_rows["alternative_plant"] == "AltPlant"].iloc[0]
    assert isinstance(alt_row["gate_results"], dict)
    assert set(alt_row["gate_results"].keys()) == {"safety", "identity", "minimum_evidence", "regulatory"}


def test_run_benchmark_handles_a_case_that_fails_to_run_without_crashing():
    broken_case = [{
        "case_id": "broken_case",
        "rows": None,  # make_engine()'s list(rows) raises TypeError on None
        "run_params": {"indication": "X", "dosage_form": "Y", "market": "EU"},
    }]
    results_df = run_benchmark(broken_case)
    assert len(results_df) == 1
    assert results_df.iloc[0]["run_error"] is not None
    assert "TypeError" in results_df.iloc[0]["run_error"]


def test_run_benchmark_empty_case_list_returns_empty_dataframe():
    results_df = run_benchmark([])
    assert results_df.empty
    assert list(results_df.columns) == [
        "case_id", "reference_plant", "alternative_plant",
        "decision_class", "decision_class_ah", "gate_results", "run_error",
    ]


# ---------------------------------------------------------------------
# compare_to_expected
# ---------------------------------------------------------------------

def test_compare_to_expected_all_agree_on_the_bundled_fixture():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    results_df = run_benchmark(cases)
    report = compare_to_expected(results_df, cases)
    assert report["disagreements"] == []
    assert report["missing_pairs"] == []
    assert report["agreement_rate"] == 1.0
    assert report["total_pairs_checked"] == 5


def test_compare_to_expected_detects_a_decision_class_disagreement():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    # Corrupt one case's expected decision_class so the comparison must
    # report a disagreement, not silently pass.
    cases[1]["expected"]["pairs"][0]["decision_class"] = "Strong R&D candidate"
    results_df = run_benchmark(cases)
    report = compare_to_expected(results_df, cases)
    assert len(report["disagreements"]) >= 1


def test_compare_to_expected_all_agree_on_decision_class_ah():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    for case in cases:
        for pair in case["expected"]["pairs"]:
            assert "decision_class_ah" in pair
    results_df = run_benchmark(cases)
    report = compare_to_expected(results_df, cases)
    assert report["disagreements"] == []


def test_compare_to_expected_detects_a_decision_class_ah_disagreement():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    cases[1]["expected"]["pairs"][0]["decision_class_ah"] = "A — Verified commercial route"
    results_df = run_benchmark(cases)
    report = compare_to_expected(results_df, cases)
    assert len(report["disagreements"]) >= 1


def test_compare_to_expected_detects_a_gate_status_disagreement():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    for pair in cases[0]["expected"]["pairs"]:
        if pair["alternative_plant"] == "AltPlant":
            pair["gate_status"]["safety"] = "passed"  # actual value is "failed"
    results_df = run_benchmark(cases)
    report = compare_to_expected(results_df, cases)
    assert len(report["disagreements"]) >= 1


def test_compare_to_expected_reports_a_missing_pair():
    cases = load_benchmark_cases(SMOKE_FIXTURE_PATH)
    cases[0]["expected"]["pairs"].append({
        "reference_plant": "PlantThatDoesNotExist",
        "alternative_plant": "AlsoDoesNotExist",
        "decision_class": "Strong R&D candidate",
    })
    results_df = run_benchmark(cases)
    report = compare_to_expected(results_df, cases)
    assert len(report["missing_pairs"]) == 1


def test_compare_to_expected_empty_results_and_cases_does_not_crash():
    report = compare_to_expected(pd.DataFrame(columns=[
        "case_id", "reference_plant", "alternative_plant",
        "decision_class", "decision_class_ah", "gate_results", "run_error",
    ]), [])
    assert report["total_pairs_checked"] == 0
    assert report["agreement_rate"] is None


# ---------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------

def test_cli_exits_zero_on_full_agreement(capsys):
    exit_code = main(["run", SMOKE_FIXTURE_PATH])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Agreement rate: 100%" in captured.out
    assert "not scientific validation" in captured.out.lower()


def test_cli_exits_nonzero_on_missing_arguments(capsys):
    exit_code = main([])
    assert exit_code != 0


def test_cli_exits_nonzero_on_unknown_subcommand(capsys):
    exit_code = main(["not-run", SMOKE_FIXTURE_PATH])
    assert exit_code != 0


# ---------------------------------------------------------------------
# This is a standalone tool, not production/UI code — never imported
# by app.py or any step_*.py page, same discipline as
# repo_dependency_audit.py.
# ---------------------------------------------------------------------

def test_benchmark_harness_not_imported_by_any_production_page():
    import glob
    for path in glob.glob("step_*.py") + ["app.py"]:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            source = f.read()
        assert "benchmark_harness" not in source, f"{path} must not import benchmark_harness"


def test_benchmark_harness_never_reimplements_scoring_or_gating():
    with open("benchmark_harness.py", encoding="utf-8") as f:
        source = f.read()
    assert "_score_candidate" not in source
    assert "_evaluate_gates" not in source
    assert "_decision_class" not in source


def test_module_never_claims_scientific_validation_without_caveat():
    with open("benchmark_harness.py", encoding="utf-8") as f:
        source = f.read()
    normalized = " ".join(source.split())
    assert "NOT scientific validation" in normalized
    assert "NOT benchmark calibration" in normalized
    assert "NOT domain validation" in normalized
