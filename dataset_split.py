"""
Validation Architecture v3 — Phase 1: Dataset Split & Leakage Assessment.

WHAT CHANGED FROM v2 (v3 correction #7)
v2's design had leakage validation silently MOVE a case from
LOCKED_HOLDOUT to development when contamination was detected. v3
corrects this: assess_leakage() is a PURE, non-mutating function that
returns a structured assessment (VALID_FOR_HOLDOUT /
INVALID_FOR_HOLDOUT / QUARANTINED) — it never changes a GoldCase's
dataset_split itself. Moving a case to development is a SEPARATE,
explicit operation (move_to_development() below) that produces an
audit record and a new split value, never an implicit side effect of
assessment.

WHY THIS SEPARATION MATTERS
An assessment function that also mutates state makes it impossible to
answer "what would this check have found" without also acting on the
finding — exactly the kind of hidden side effect this platform's
established persistence modules (decision_record_persistence.py,
sign_off_persistence.py) already avoid by keeping "compute a status"
and "write a record" as two distinct steps. Here it matters even more:
a QUARANTINED case might need a curator's judgment call, not an
automatic demotion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DatasetSplit(str, Enum):
    DEVELOPMENT = "Development"
    VALIDATION = "Validation"
    LOCKED_HOLDOUT = "Locked holdout"


class LeakageAssessment(str, Enum):
    VALID_FOR_HOLDOUT = "Valid for holdout"
    INVALID_FOR_HOLDOUT = "Invalid for holdout"
    QUARANTINED = "Quarantined"


@dataclass
class LeakageControl:
    """Attached to a GoldCase to record whether/when its expected
    engine behavior was observed before the case was finalized, and
    whether the case was subsequently edited after that observation —
    the two conditions assess_leakage() below checks."""
    engine_output_observed_before_finalization: bool = False
    observed_at: Optional[datetime] = None
    case_modified_after_observation: bool = False


@dataclass
class LeakageAssessmentResult:
    case_id: str
    dataset_split: DatasetSplit
    assessment: LeakageAssessment
    reason: str


@dataclass
class AuditRecord:
    """Produced by move_to_development() below — never fabricated or
    inferred; always the explicit output of that one operation."""
    case_id: str
    previous_split: DatasetSplit
    new_split: DatasetSplit
    reason: str
    performed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def assess_leakage(case_id: str, dataset_split: DatasetSplit, leakage_control: LeakageControl) -> LeakageAssessmentResult:
    """Pure, non-mutating assessment (v3 correction #7) — never
    changes `dataset_split` itself, regardless of what it finds.

    Only LOCKED_HOLDOUT cases can fail this check by definition: a
    development/validation-split case observing engine output before
    "finalization" is normal iterative work, not leakage.
    """
    if dataset_split != DatasetSplit.LOCKED_HOLDOUT:
        return LeakageAssessmentResult(
            case_id=case_id,
            dataset_split=dataset_split,
            assessment=LeakageAssessment.VALID_FOR_HOLDOUT,
            reason="Not a locked-holdout case; leakage assessment is not applicable.",
        )

    if not leakage_control.engine_output_observed_before_finalization:
        return LeakageAssessmentResult(
            case_id=case_id,
            dataset_split=dataset_split,
            assessment=LeakageAssessment.VALID_FOR_HOLDOUT,
            reason="No engine output was observed before finalization.",
        )

    if leakage_control.case_modified_after_observation:
        return LeakageAssessmentResult(
            case_id=case_id,
            dataset_split=dataset_split,
            assessment=LeakageAssessment.INVALID_FOR_HOLDOUT,
            reason=(
                "Engine output was observed before finalization AND the "
                "case was modified afterward — classic leakage pattern. "
                "Never valid as a locked-holdout case."
            ),
        )

    # Output was observed, but the case was NOT modified afterward —
    # a softer signal than confirmed leakage, but not clean either;
    # a curator should look at it rather than either silently pass or
    # silently fail it.
    return LeakageAssessmentResult(
        case_id=case_id,
        dataset_split=dataset_split,
        assessment=LeakageAssessment.QUARANTINED,
        reason=(
            "Engine output was observed before finalization, but the case "
            "was not subsequently modified — cannot rule out leakage "
            "without curator judgment."
        ),
    )


def move_to_development(
    case_id: str, current_split: DatasetSplit, reason: str
) -> tuple:
    """The ONE explicit, separate operation that changes a case's
    dataset_split (v3 correction #7) — never a side effect of
    assess_leakage(). Returns (new_split, AuditRecord); the caller is
    responsible for actually updating its own GoldCase/store with the
    returned new_split — this function holds no state itself.
    """
    audit = AuditRecord(
        case_id=case_id,
        previous_split=current_split,
        new_split=DatasetSplit.DEVELOPMENT,
        reason=reason,
    )
    return DatasetSplit.DEVELOPMENT, audit
