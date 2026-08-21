"""Minimal denominator-aware gates for targeted high-risk regression corpora.

These are engineering regression thresholds / internal scientific targets.
They are NOT claims of clinical validation, regulatory validation, or external
expert validation.
"""
from __future__ import annotations

from dataclasses import dataclass

from validation_risk_metrics import HighRiskClassMetrics, HighRiskValidationMetrics


@dataclass(frozen=True)
class HighRiskRegressionGateDecision:
    passed: bool
    status: str
    blockers: tuple[str, ...]
    notes: tuple[str, ...]


def _check_target(name: str, metric: HighRiskClassMetrics, blockers: list[str], notes: list[str]) -> None:
    if metric.status == "not_evaluable":
        notes.append(
            f"{name}: not evaluable because the corpus contains no reference-positive cases."
        )
        return
    if metric.false_negatives > 0:
        blockers.append(
            f"{name}: {metric.false_negatives}/{metric.reference_positive_cases} false negatives; "
            "targeted regression tolerance is 0."
        )


def evaluate_targeted_high_risk_regression_gate(
    metrics: HighRiskValidationMetrics,
) -> HighRiskRegressionGateDecision:
    """Apply zero-FN tolerance only where the targeted corpus is evaluable.

    A missing target class is explicitly NOT EVALUABLE, never a successful
    zero-FN result. This gate is intentionally narrow and is not a substitute
    for a sufficiently powered independent validation protocol.
    """
    blockers: list[str] = []
    notes: list[str] = []
    _check_target("Serious safety", metrics.serious_safety, blockers, notes)
    _check_target("Regulatory", metrics.regulatory, blockers, notes)

    evaluable_targets = sum(
        m.status == "evaluable" for m in (metrics.serious_safety, metrics.regulatory)
    )
    if evaluable_targets == 0:
        return HighRiskRegressionGateDecision(
            passed=False,
            status="not_evaluable",
            blockers=tuple(blockers),
            notes=tuple(notes),
        )
    if blockers:
        return HighRiskRegressionGateDecision(
            passed=False,
            status="fail",
            blockers=tuple(blockers),
            notes=tuple(notes),
        )
    if evaluable_targets < 2:
        return HighRiskRegressionGateDecision(
            passed=False,
            status="partial_pass",
            blockers=tuple(blockers),
            notes=tuple(notes),
        )
    return HighRiskRegressionGateDecision(
        passed=True,
        status="pass",
        blockers=tuple(blockers),
        notes=tuple(notes),
    )
