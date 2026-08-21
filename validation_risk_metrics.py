"""High-risk validation metrics for safety and regulatory final decisions.

Validation/reporting only. This module does not alter production scoring,
ranking, eligibility, safety, regulatory, or final-decision logic.

The purpose is to make rare high-risk failure modes denominator-aware. A
reported zero false-negative count is not treated as evidence of success when
there are zero reference-positive cases for that target.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping, Optional

from final_decision_policy import FinalDecisionStatus
from scientific_decision_validation import DecisionComparison


@dataclass(frozen=True)
class HighRiskClassMetrics:
    target_label: str
    true_positives: int
    false_negatives: int
    false_positives: int
    reference_positive_cases: int
    evaluable_cases: int
    non_evaluable_cases: int
    recall: Optional[float]
    precision: Optional[float]
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class HighRiskValidationMetrics:
    serious_safety: HighRiskClassMetrics
    regulatory: HighRiskClassMetrics

    def to_dict(self) -> dict:
        return {
            "serious_safety": self.serious_safety.to_dict(),
            "regulatory": self.regulatory.to_dict(),
        }


def _safe_div(num: int, den: int) -> Optional[float]:
    return None if den == 0 else num / den


def _from_counts(
    *,
    target_label: str,
    tp: int,
    fn: int,
    fp: int,
    evaluable_cases: int,
    non_evaluable_cases: int,
) -> HighRiskClassMetrics:
    reference_positive_cases = tp + fn
    recall = _safe_div(tp, reference_positive_cases)
    precision = _safe_div(tp, tp + fp)
    status = "not_evaluable" if reference_positive_cases == 0 else "evaluable"
    return HighRiskClassMetrics(
        target_label=target_label,
        true_positives=tp,
        false_negatives=fn,
        false_positives=fp,
        reference_positive_cases=reference_positive_cases,
        evaluable_cases=evaluable_cases,
        non_evaluable_cases=non_evaluable_cases,
        recall=recall,
        precision=precision,
        status=status,
    )


def compute_high_risk_metrics(
    comparisons: Iterable[DecisionComparison],
) -> HighRiskValidationMetrics:
    """Compute denominator-aware safety/regulatory metrics from comparisons.

    Rows with ``actual is None`` are counted as non-evaluable and are excluded
    from TP/FN/FP calculations. They must not silently become false negatives.
    """
    rows = list(comparisons)
    evaluable = [r for r in rows if r.actual is not None]
    non_evaluable = len(rows) - len(evaluable)

    def one(target: FinalDecisionStatus) -> HighRiskClassMetrics:
        tp = sum(1 for r in evaluable if r.expected == target and r.actual == target)
        fn = sum(1 for r in evaluable if r.expected == target and r.actual != target)
        fp = sum(1 for r in evaluable if r.expected != target and r.actual == target)
        return _from_counts(
            target_label=target.value,
            tp=tp,
            fn=fn,
            fp=fp,
            evaluable_cases=len(evaluable),
            non_evaluable_cases=non_evaluable,
        )

    return HighRiskValidationMetrics(
        serious_safety=one(FinalDecisionStatus.NO_GO_SAFETY),
        regulatory=one(FinalDecisionStatus.NO_GO_REGULATORY),
    )


def compute_high_risk_metrics_from_confusion_matrix(
    matrix: Mapping[str, Mapping[str, int]],
    *,
    n_scored: Optional[int] = None,
    n_total: Optional[int] = None,
) -> HighRiskValidationMetrics:
    """Compute high-risk metrics when only a final-decision matrix is stored."""
    labels = [x.value for x in FinalDecisionStatus]
    inferred_scored = sum(int(matrix.get(e, {}).get(a, 0)) for e in labels for a in labels)
    evaluable_cases = inferred_scored if n_scored is None else int(n_scored)
    total = evaluable_cases if n_total is None else int(n_total)
    non_evaluable = max(0, total - evaluable_cases)

    def one(target: FinalDecisionStatus) -> HighRiskClassMetrics:
        t = target.value
        tp = int(matrix.get(t, {}).get(t, 0))
        fn = sum(int(matrix.get(t, {}).get(a, 0)) for a in labels if a != t)
        fp = sum(int(matrix.get(e, {}).get(t, 0)) for e in labels if e != t)
        return _from_counts(
            target_label=t,
            tp=tp,
            fn=fn,
            fp=fp,
            evaluable_cases=evaluable_cases,
            non_evaluable_cases=non_evaluable,
        )

    return HighRiskValidationMetrics(
        serious_safety=one(FinalDecisionStatus.NO_GO_SAFETY),
        regulatory=one(FinalDecisionStatus.NO_GO_REGULATORY),
    )


def format_high_risk_metric(metric: HighRiskClassMetrics) -> str:
    """Human-readable denominator-aware representation for reports."""
    if metric.status == "not_evaluable":
        return (
            "not evaluable "
            f"(0 reference-positive cases; {metric.evaluable_cases} evaluable total cases)"
        )
    recall = "n/a" if metric.recall is None else f"{metric.recall:.3f}"
    precision = "n/a" if metric.precision is None else f"{metric.precision:.3f}"
    return (
        f"TP={metric.true_positives}, FN={metric.false_negatives}, "
        f"recall={recall}, precision={precision}, "
        f"reference-positive={metric.reference_positive_cases}, "
        f"evaluable={metric.evaluable_cases}, non-evaluable={metric.non_evaluable_cases}"
    )
