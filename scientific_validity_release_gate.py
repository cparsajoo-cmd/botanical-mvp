"""Scientific validity release gate for the six-class decision engine.

This module does NOT create scientific truth and does NOT tune production rules.
It defines, before a final benchmark is run, the finite conditions required to
call a decision-engine version "scientifically validated for v1 decision
support".

The gate deliberately requires independent human adjudication. A model,
developer, or benchmark author cannot substitute for external expert agreement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from final_decision_policy import FinalDecisionStatus
from decision_benchmark_v1 import DecisionMetrics


@dataclass(frozen=True)
class ValidationProtocol:
    benchmark_id: str
    reference_frozen_before_engine_run: bool
    engine_blinded_to_reference_labels: bool
    remediation_cases_excluded: bool
    adjudicator_count: int
    adjudicators_independent: bool
    inter_rater_agreement: float | None
    n_cases: int
    class_support: Mapping[str, int]


@dataclass(frozen=True)
class ScientificReleaseProfile:
    """Finite v1 acceptance profile; not a claim of universal clinical validity."""
    min_cases: int = 24
    min_cases_per_class: int = 3
    min_adjudicators: int = 2
    min_inter_rater_agreement: float = 0.70
    min_accuracy: float = 0.80
    min_macro_f1: float = 0.75
    min_go_precision: float = 0.85
    min_caution_recall: float = 0.75
    min_expert_review_recall: float = 0.70
    max_serious_safety_false_negatives: int = 0
    max_regulatory_false_negatives: int = 0
    max_insufficient_evidence_miss_rate: float = 0.20


@dataclass(frozen=True)
class ScientificReleaseDecision:
    releasable: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def _precision_for(label: str, matrix: Mapping[str, Mapping[str, int]]) -> float | None:
    tp = matrix.get(label, {}).get(label, 0)
    predicted = sum(row.get(label, 0) for row in matrix.values())
    return None if predicted == 0 else tp / predicted


def _support_for(label: str, matrix: Mapping[str, Mapping[str, int]]) -> int:
    return sum(matrix.get(label, {}).values())


def evaluate_scientific_release(
    protocol: ValidationProtocol,
    metrics: DecisionMetrics,
    profile: ScientificReleaseProfile = ScientificReleaseProfile(),
) -> ScientificReleaseDecision:
    blockers = []
    warnings = []

    # Study-design integrity / leakage controls.
    if not protocol.reference_frozen_before_engine_run:
        blockers.append("Reference labels were not frozen before engine execution.")
    if not protocol.engine_blinded_to_reference_labels:
        blockers.append("Engine was not blinded to reference labels.")
    if not protocol.remediation_cases_excluded:
        blockers.append("Cases used for remediation were reused in the final holdout.")
    if protocol.adjudicator_count < profile.min_adjudicators:
        blockers.append(
            f"Independent adjudicators={protocol.adjudicator_count}; require >= {profile.min_adjudicators}."
        )
    if not protocol.adjudicators_independent:
        blockers.append("Reference adjudicators were not independent.")
    if protocol.inter_rater_agreement is None:
        blockers.append("Inter-rater agreement was not measured.")
    elif protocol.inter_rater_agreement < profile.min_inter_rater_agreement:
        blockers.append(
            f"Inter-rater agreement={protocol.inter_rater_agreement:.3f}; "
            f"require >= {profile.min_inter_rater_agreement:.3f}."
        )

    # One finite, balanced benchmark rather than endless case-by-case tuning.
    if protocol.n_cases < profile.min_cases:
        blockers.append(f"Final holdout has {protocol.n_cases} cases; require >= {profile.min_cases}.")
    for status in FinalDecisionStatus:
        n = int(protocol.class_support.get(status.value, 0))
        if n < profile.min_cases_per_class:
            blockers.append(
                f"Class {status.value!r} has {n} reference cases; require >= {profile.min_cases_per_class}."
            )

    # Performance requirements.
    if metrics.n_scored != protocol.n_cases:
        blockers.append(
            f"Only {metrics.n_scored}/{protocol.n_cases} frozen cases were scored."
        )
    if metrics.accuracy is None or metrics.accuracy < profile.min_accuracy:
        blockers.append(
            f"Accuracy={metrics.accuracy}; require >= {profile.min_accuracy:.2f}."
        )
    if metrics.macro_f1 is None or metrics.macro_f1 < profile.min_macro_f1:
        blockers.append(
            f"Macro-F1={metrics.macro_f1}; require >= {profile.min_macro_f1:.2f}."
        )

    go = FinalDecisionStatus.GO.value
    go_precision = _precision_for(go, metrics.confusion_matrix)
    if go_precision is None or go_precision < profile.min_go_precision:
        blockers.append(
            f"GO precision={go_precision}; require >= {profile.min_go_precision:.2f}."
        )

    caution = metrics.per_class_recall.get(FinalDecisionStatus.GO_WITH_CAUTION.value)
    if caution is None or caution < profile.min_caution_recall:
        blockers.append(
            f"GO WITH CAUTION recall={caution}; require >= {profile.min_caution_recall:.2f}."
        )

    expert = metrics.per_class_recall.get(FinalDecisionStatus.EXPERT_REVIEW_REQUIRED.value)
    if expert is None or expert < profile.min_expert_review_recall:
        blockers.append(
            f"EXPERT REVIEW REQUIRED recall={expert}; require >= {profile.min_expert_review_recall:.2f}."
        )

    if metrics.serious_safety_false_negatives > profile.max_serious_safety_false_negatives:
        blockers.append(
            f"Serious safety false negatives={metrics.serious_safety_false_negatives}; zero tolerated."
        )
    if metrics.regulatory_false_negatives > profile.max_regulatory_false_negatives:
        blockers.append(
            f"Regulatory false negatives={metrics.regulatory_false_negatives}; zero tolerated."
        )

    insufficient_support = _support_for(
        FinalDecisionStatus.INSUFFICIENT_EVIDENCE.value, metrics.confusion_matrix
    )
    if insufficient_support:
        miss_rate = metrics.insufficient_evidence_miss / insufficient_support
        if miss_rate > profile.max_insufficient_evidence_miss_rate:
            blockers.append(
                f"INSUFFICIENT EVIDENCE miss rate={miss_rate:.3f}; "
                f"require <= {profile.max_insufficient_evidence_miss_rate:.2f}."
            )
    else:
        blockers.append("INSUFFICIENT EVIDENCE class has no scorable support.")

    # A passing v1 gate is a bounded claim: decision-support validity on the
    # frozen target domain, not universal clinical truth.
    if metrics.false_no_go:
        warnings.append(
            f"{metrics.false_no_go} false hard-NO-GO prediction(s) occurred; review specificity even if all release blockers pass."
        )

    return ScientificReleaseDecision(
        releasable=not blockers,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
