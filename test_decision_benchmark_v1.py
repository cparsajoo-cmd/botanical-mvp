from final_decision_policy import FinalDecisionStatus
from scientific_decision_validation import DecisionComparison
from decision_benchmark_v1 import (
    BENCHMARK_VERSION,
    BenchmarkCohort,
    DEVELOPMENT_CASE_NUMBERS,
    compute_metrics,
    discover_reference_grounded_cases,
    split_cases,
    validate_no_holdout_leakage,
)


def test_v1_split_is_disjoint_and_uses_only_existing_cases():
    cases = discover_reference_grounded_cases(".")
    assert len(cases) == 22
    split = split_cases(cases)
    dev_ids = {c.case_id for c in split[BenchmarkCohort.DEVELOPMENT]}
    holdout_ids = {c.case_id for c in split[BenchmarkCohort.PROSPECTIVE_HOLDOUT]}
    assert len(dev_ids) == 7
    assert len(holdout_ids) == 15
    assert dev_ids.isdisjoint(holdout_ids)
    assert len(dev_ids | holdout_ids) == 22
    assert {int(x.split("_", 2)[1]) for x in dev_ids} == DEVELOPMENT_CASE_NUMBERS


def test_holdout_has_no_case_used_in_prior_remediation():
    cases = discover_reference_grounded_cases(".")
    split = split_cases(cases)
    dev_ids = {c.case_id for c in split[BenchmarkCohort.DEVELOPMENT]}
    holdout_ids = {c.case_id for c in split[BenchmarkCohort.PROSPECTIVE_HOLDOUT]}
    validate_no_holdout_leakage(dev_ids, holdout_ids)


def test_decision_metrics_capture_safety_regulatory_and_abstention_errors():
    rows = [
        DecisionComparison("a", FinalDecisionStatus.NO_GO_SAFETY, FinalDecisionStatus.GO, False),
        DecisionComparison("b", FinalDecisionStatus.NO_GO_REGULATORY, FinalDecisionStatus.GO_WITH_CAUTION, False),
        DecisionComparison("c", FinalDecisionStatus.GO, FinalDecisionStatus.NO_GO_SAFETY, False),
        DecisionComparison("d", FinalDecisionStatus.GO, FinalDecisionStatus.EXPERT_REVIEW_REQUIRED, False),
        DecisionComparison("e", FinalDecisionStatus.INSUFFICIENT_EVIDENCE, FinalDecisionStatus.GO_WITH_CAUTION, False),
    ]
    m = compute_metrics(rows)
    assert m.n_scored == 5
    assert m.serious_safety_false_negatives == 1
    assert m.regulatory_false_negatives == 1
    assert m.false_no_go == 1
    assert m.expert_review_overuse == 1
    assert m.insufficient_evidence_miss == 1


def test_unscored_rows_do_not_inflate_metrics():
    rows = [DecisionComparison("pending", FinalDecisionStatus.GO, None, False)]
    m = compute_metrics(rows)
    assert m.n_scored == 0
    assert m.accuracy is None
    assert m.macro_f1 is None


def test_benchmark_version_is_frozen_v1():
    assert BENCHMARK_VERSION == "1.0.0"


def test_blind_packet_and_manifest_do_not_expose_engine_or_derived_decision_labels():
    import json
    from pathlib import Path
    # Builder artifacts are checked as part of the benchmark contract.
    import build_decision_benchmark_v1 as builder
    builder.main()
    out = Path("gold_corpus/decision_benchmark_v1")
    manifest_text = (out / "manifest.json").read_text(encoding="utf-8")
    packet = json.loads((out / "blind_expert_adjudication_packet.json").read_text(encoding="utf-8"))
    assert "truth_commitment_sha256" not in manifest_text
    assert "expected_reference_curated" not in manifest_text
    for row in packet:
        forbidden = {"actual_engine", "expected_reference_curated", "resolved_outcomes", "engine_decision"}
        assert forbidden.isdisjoint(row)
        assert row["reviewer_1_decision"] == ""
        assert row["reviewer_2_decision"] == ""
        assert row["adjudicated_decision"] == ""
