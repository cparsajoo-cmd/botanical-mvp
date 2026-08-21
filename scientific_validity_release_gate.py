"""Reference-grounded scientific validity release gate.

This gate validates the decision engine against independently sourced,
pre-frozen scientific/regulatory reference evidence. It deliberately does NOT
claim human-expert agreement.

A passing result supports the bounded claim:
"reference-grounded validated for the frozen target domain and protocol."
It does not establish clinical efficacy, regulatory approval, or universal
expert agreement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from final_decision_policy import FinalDecisionStatus
from decision_benchmark_v1 import DecisionMetrics
from validation_risk_metrics import compute_high_risk_metrics_from_confusion_matrix


@dataclass(frozen=True)
class ReferenceValidationProtocol:
    benchmark_id: str
    reference_frozen_before_engine_run: bool
    engine_blinded_to_reference_labels: bool
    remediation_cases_excluded: bool
    reference_evidence_excluded_from_engine_input: bool
    provenance_complete: bool
    n_cases: int
    class_support: Mapping[str, int]
    reference_source_support: Mapping[str, int]


@dataclass(frozen=True)
class ReferenceGroundedReleaseProfile:
    min_cases: int = 24
    min_cases_per_class: int = 3
    min_reference_sources_per_case: int = 1
    min_accuracy: float = 0.80
    min_macro_f1: float = 0.75
    min_go_precision: float = 0.85
    min_caution_recall: float = 0.75
    min_expert_review_recall: float = 0.70
    max_serious_safety_false_negatives: int = 0
    max_regulatory_false_negatives: int = 0
    max_insufficient_evidence_miss_rate: float = 0.20


@dataclass(frozen=True)
class ReferenceGroundedReleaseDecision:
    releasable: bool
    claim: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def _precision_for(label: str, matrix: Mapping[str, Mapping[str, int]]) -> float | None:
    tp=matrix.get(label,{}).get(label,0)
    predicted=sum(row.get(label,0) for row in matrix.values())
    return None if predicted == 0 else tp/predicted


def _support_for(label: str, matrix: Mapping[str, Mapping[str, int]]) -> int:
    return sum(matrix.get(label,{}).values())


def evaluate_reference_grounded_release(
    protocol: ReferenceValidationProtocol,
    metrics: DecisionMetrics,
    profile: ReferenceGroundedReleaseProfile=ReferenceGroundedReleaseProfile(),
) -> ReferenceGroundedReleaseDecision:
    blockers=[]
    warnings=[]

    # Anti-leakage and provenance are mandatory.
    if not protocol.reference_frozen_before_engine_run:
        blockers.append("Reference decisions were not frozen before engine execution.")
    if not protocol.engine_blinded_to_reference_labels:
        blockers.append("Engine was not blinded to frozen reference decisions.")
    if not protocol.remediation_cases_excluded:
        blockers.append("Cases used to remediate this engine version were reused in the final holdout.")
    if not protocol.reference_evidence_excluded_from_engine_input:
        blockers.append("Reference-defining evidence leaked into engine input.")
    if not protocol.provenance_complete:
        blockers.append("Reference provenance is incomplete or non-traceable.")

    if protocol.n_cases < profile.min_cases:
        blockers.append(f"Final holdout has {protocol.n_cases} cases; require >= {profile.min_cases}.")

    for status in FinalDecisionStatus:
        n=int(protocol.class_support.get(status.value,0))
        if n < profile.min_cases_per_class:
            blockers.append(
                f"Class {status.value!r} has {n} cases; require >= {profile.min_cases_per_class}."
            )

    for case_id,n in protocol.reference_source_support.items():
        if int(n) < profile.min_reference_sources_per_case:
            blockers.append(f"Case {case_id!r} has no qualifying independent reference source.")

    if len(protocol.reference_source_support) != protocol.n_cases:
        blockers.append(
            f"Reference-source accounting covers {len(protocol.reference_source_support)}/{protocol.n_cases} cases."
        )

    if metrics.n_scored != protocol.n_cases:
        blockers.append(f"Only {metrics.n_scored}/{protocol.n_cases} frozen cases were scored.")
    if metrics.accuracy is None or metrics.accuracy < profile.min_accuracy:
        blockers.append(f"Accuracy={metrics.accuracy}; require >= {profile.min_accuracy:.2f}.")
    if metrics.macro_f1 is None or metrics.macro_f1 < profile.min_macro_f1:
        blockers.append(f"Macro-F1={metrics.macro_f1}; require >= {profile.min_macro_f1:.2f}.")

    go=FinalDecisionStatus.GO.value
    go_precision=_precision_for(go,metrics.confusion_matrix)
    if go_precision is None or go_precision < profile.min_go_precision:
        blockers.append(f"GO precision={go_precision}; require >= {profile.min_go_precision:.2f}.")

    caution=metrics.per_class_recall.get(FinalDecisionStatus.GO_WITH_CAUTION.value)
    if caution is None or caution < profile.min_caution_recall:
        blockers.append(f"GO WITH CAUTION recall={caution}; require >= {profile.min_caution_recall:.2f}.")

    review=metrics.per_class_recall.get(FinalDecisionStatus.EXPERT_REVIEW_REQUIRED.value)
    if review is None or review < profile.min_expert_review_recall:
        blockers.append(f"EXPERT REVIEW REQUIRED recall={review}; require >= {profile.min_expert_review_recall:.2f}.")

    high_risk = compute_high_risk_metrics_from_confusion_matrix(
        metrics.confusion_matrix, n_scored=metrics.n_scored, n_total=protocol.n_cases
    )

    safety = high_risk.serious_safety
    if safety.status == "not_evaluable":
        blockers.append(
            "Serious safety is not evaluable: the holdout contains zero NO GO SAFETY reference cases."
        )
    else:
        safety_fn = max(int(metrics.serious_safety_false_negatives), safety.false_negatives)
        if safety_fn > profile.max_serious_safety_false_negatives:
            blockers.append(
                f"Serious safety false negatives={safety_fn}/{safety.reference_positive_cases}; "
                "zero tolerated."
            )

    regulatory = high_risk.regulatory
    if regulatory.status == "not_evaluable":
        blockers.append(
            "Regulatory is not evaluable: the holdout contains zero NO GO REGULATORY reference cases."
        )
    else:
        regulatory_fn = max(int(metrics.regulatory_false_negatives), regulatory.false_negatives)
        if regulatory_fn > profile.max_regulatory_false_negatives:
            blockers.append(
                f"Regulatory false negatives={regulatory_fn}/{regulatory.reference_positive_cases}; "
                "zero tolerated."
            )

    insufficient=FinalDecisionStatus.INSUFFICIENT_EVIDENCE.value
    support=_support_for(insufficient,metrics.confusion_matrix)
    if not support:
        blockers.append("INSUFFICIENT EVIDENCE has no scorable reference support.")
    else:
        miss=metrics.insufficient_evidence_miss/support
        if miss > profile.max_insufficient_evidence_miss_rate:
            blockers.append(f"INSUFFICIENT EVIDENCE miss rate={miss:.3f}; require <= {profile.max_insufficient_evidence_miss_rate:.2f}.")

    if metrics.false_no_go:
        warnings.append(f"{metrics.false_no_go} false hard-NO-GO prediction(s); review specificity.")

    claim=(
        "REFERENCE-GROUNDED VALIDATED for the frozen benchmark/domain"
        if not blockers else
        "NOT YET REFERENCE-GROUNDED VALIDATED"
    )
    return ReferenceGroundedReleaseDecision(not blockers,claim,tuple(blockers),tuple(warnings))
