from final_decision_policy import FinalDecisionStatus as S
from scientific_decision_validation import DecisionComparison
from validation_risk_metrics import (
    compute_high_risk_metrics,
    compute_high_risk_metrics_from_confusion_matrix,
    format_high_risk_metric,
)
from high_risk_validation_gate import evaluate_targeted_high_risk_regression_gate


def row(case_id, expected, actual):
    return DecisionComparison(case_id, expected, actual, actual is not None and expected == actual)


def test_serious_safety_reports_tp_fn_recall_precision_and_denominator():
    m = compute_high_risk_metrics([
        row("s1", S.NO_GO_SAFETY, S.NO_GO_SAFETY),
        row("s2", S.NO_GO_SAFETY, S.GO),
        row("n1", S.GO, S.NO_GO_SAFETY),
        row("n2", S.GO_WITH_CAUTION, S.GO_WITH_CAUTION),
    ]).serious_safety
    assert m.true_positives == 1
    assert m.false_negatives == 1
    assert m.false_positives == 1
    assert m.reference_positive_cases == 2
    assert m.recall == 0.5
    assert m.precision == 0.5
    assert m.status == "evaluable"


def test_zero_regulatory_reference_cases_are_not_evaluable_not_success():
    m = compute_high_risk_metrics([
        row("a", S.GO, S.GO),
        row("b", S.NO_GO_SAFETY, S.NO_GO_SAFETY),
    ]).regulatory
    assert m.reference_positive_cases == 0
    assert m.false_negatives == 0
    assert m.recall is None
    assert m.status == "not_evaluable"
    assert format_high_risk_metric(m).startswith("not evaluable")


def test_unscored_rows_are_explicitly_non_evaluable():
    m = compute_high_risk_metrics([
        row("s1", S.NO_GO_SAFETY, S.NO_GO_SAFETY),
        row("r1", S.NO_GO_REGULATORY, None),
    ])
    assert m.serious_safety.evaluable_cases == 1
    assert m.serious_safety.non_evaluable_cases == 1
    assert m.regulatory.reference_positive_cases == 0
    assert m.regulatory.status == "not_evaluable"


def test_matrix_adapter_preserves_denominators():
    labels = [x.value for x in S]
    matrix = {e: {a: 0 for a in labels} for e in labels}
    matrix[S.NO_GO_REGULATORY.value][S.NO_GO_REGULATORY.value] = 2
    matrix[S.GO.value][S.NO_GO_REGULATORY.value] = 1
    m = compute_high_risk_metrics_from_confusion_matrix(matrix, n_scored=3, n_total=4).regulatory
    assert m.true_positives == 2
    assert m.false_negatives == 0
    assert m.false_positives == 1
    assert m.recall == 1.0
    assert m.precision == 2 / 3
    assert m.non_evaluable_cases == 1


def test_targeted_regression_gate_is_zero_fn_strict_when_evaluable():
    metrics = compute_high_risk_metrics([
        row("s1", S.NO_GO_SAFETY, S.GO),
        row("n1", S.GO, S.GO),
    ])
    gate = evaluate_targeted_high_risk_regression_gate(metrics)
    assert not gate.passed
    assert gate.status == "fail"
    assert any("1/1 false negatives" in x for x in gate.blockers)
    assert any("Regulatory: not evaluable" in x for x in gate.notes)


def test_targeted_regression_gate_does_not_claim_success_with_no_targets():
    metrics = compute_high_risk_metrics([row("g1", S.GO, S.GO)])
    gate = evaluate_targeted_high_risk_regression_gate(metrics)
    assert not gate.passed
    assert gate.status == "not_evaluable"


def test_decision_holdout_v5_regression_reports_regulatory_as_not_evaluable():
    import json
    from pathlib import Path
    from validation_high_risk_report import build_report

    payload = json.loads(Path("gold_corpus/decision_holdout_v5/results.json").read_text())
    report = build_report(payload, source_result_path="gold_corpus/decision_holdout_v5/results.json")
    safety = report["high_risk_metrics"]["serious_safety"]
    regulatory = report["high_risk_metrics"]["regulatory"]
    assert safety["true_positives"] == 2
    assert safety["false_negatives"] == 0
    assert safety["reference_positive_cases"] == 2
    assert safety["recall"] == 1.0
    assert regulatory["false_negatives"] == 0
    assert regulatory["reference_positive_cases"] == 0
    assert regulatory["recall"] is None
    assert regulatory["status"] == "not_evaluable"


def test_sidecar_writer_refuses_to_overwrite_source(tmp_path):
    import json
    from validation_high_risk_report import write_sidecar
    p = tmp_path / "result.json"
    p.write_text(json.dumps({"metrics": {"confusion_matrix": {}}}))
    try:
        write_sidecar(p, p)
    except ValueError as exc:
        assert "Refusing to overwrite" in str(exc)
    else:
        raise AssertionError("source overwrite should be rejected")


def test_one_evaluable_high_risk_target_is_partial_pass_not_overall_success():
    metrics = compute_high_risk_metrics([
        row("s1", S.NO_GO_SAFETY, S.NO_GO_SAFETY),
        row("g1", S.GO, S.GO),
    ])
    gate = evaluate_targeted_high_risk_regression_gate(metrics)
    assert not gate.passed
    assert gate.status == "partial_pass"
