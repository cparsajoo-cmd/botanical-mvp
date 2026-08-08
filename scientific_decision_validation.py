"""Scientific final-decision benchmark over existing reference-grounded cases.

Ground truth is derived only from GoldCase.resolved_outcomes.  Engine output is
translated from the existing Eligibility_Status + Decision_Class production contract.  No case id, expected
label, or GoldCase object is ever passed into the production engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, SeverityLevel
from final_decision_policy import FinalDecisionStatus
from reference_precedence import ResolutionStatus


@dataclass(frozen=True)
class DecisionComparison:
    case_id: str
    expected: FinalDecisionStatus
    actual: FinalDecisionStatus | None
    match: bool


def derive_reference_final_decision(gold_case) -> FinalDecisionStatus:
    outcomes = list(gold_case.resolved_outcomes or [])

    # Any unresolved governing reference conflict is an explicit abstention.
    if any(o.resolution_status in {ResolutionStatus.REFERENCE_CONFLICT, ResolutionStatus.HUMAN_REVIEW_REQUIRED}
           for o in outcomes):
        return FinalDecisionStatus.EXPERT_REVIEW_REQUIRED

    selected = [o for o in outcomes if o.resolution_status == ResolutionStatus.SELECTED]

    # Regulatory legal status has first-class final-decision semantics.
    for o in selected:
        if o.domain == ReferenceDomain.REGULATORY_STATUS and o.assertion_state == AssertionState.PRESENT:
            if o.assertion_type == AssertionType.PROHIBITION:
                return FinalDecisionStatus.NO_GO_REGULATORY
            if o.assertion_type == AssertionType.RESTRICTION:
                return FinalDecisionStatus.GO_WITH_CAUTION

    # Serious applicable safety evidence is a hard stop.
    for o in selected:
        if (o.domain == ReferenceDomain.SAFETY and o.assertion_state == AssertionState.PRESENT
                and o.severity == SeverityLevel.SERIOUS):
            return FinalDecisionStatus.NO_GO_SAFETY

    indication = [o for o in selected if o.domain == ReferenceDomain.INDICATION_EVIDENCE]
    if indication:
        states = {o.assertion_state for o in indication}
        if AssertionState.INSUFFICIENT in states:
            return FinalDecisionStatus.INSUFFICIENT_EVIDENCE
        if AssertionState.PRESENT in states:
            return FinalDecisionStatus.GO
        if AssertionState.CONDITIONAL in states:
            return FinalDecisionStatus.GO_WITH_CAUTION
        return FinalDecisionStatus.INSUFFICIENT_EVIDENCE

    # A selected non-indication outcome with no hard stop is not enough to
    # manufacture efficacy. Conservatively require review rather than GO.
    return FinalDecisionStatus.EXPERT_REVIEW_REQUIRED


def build_confusion_matrix(comparisons: Iterable[DecisionComparison]) -> dict[str, dict[str, int]]:
    labels = [x.value for x in FinalDecisionStatus]
    matrix = {e: {a: 0 for a in labels} for e in labels}
    for row in comparisons:
        if row.actual is not None:
            matrix[row.expected.value][row.actual.value] += 1
    return matrix


def agreement(comparisons: Iterable[DecisionComparison]) -> tuple[int, int, float | None]:
    rows = [x for x in comparisons if x.actual is not None]
    if not rows:
        return 0, 0, None
    num = sum(x.match for x in rows)
    return num, len(rows), num / len(rows)
