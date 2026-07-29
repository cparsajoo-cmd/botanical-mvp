"""
Reference-Grounded Validation — controlled vocabulary.

WHY THIS IS ONE SHARED MODULE
Every enum here is used by at least two of reference_claim.py,
resolved_expected_outcome.py, gold_case.py, and evaluation_run.py —
putting them in one place avoids a circular-import tangle and gives
one canonical definition each vocabulary term can be traced back to.
"""

from __future__ import annotations

from enum import Enum


class AssertionState(str, Enum):
    """Replaces a bare boolean expected_value (v4 correction #2) — a
    boolean cannot distinguish "the source explicitly says this does
    NOT apply" from "the source never mentions this at all," which are
    scientifically very different claims."""
    PRESENT = "Present"
    ABSENT = "Absent"
    NOT_STATED = "Not stated"
    CONDITIONAL = "Conditional"
    INSUFFICIENT = "Insufficient"


class AssertionType(str, Enum):
    """Controlled vocabulary replacing free-text assertion_type (v4
    correction #3)."""
    CONTRAINDICATION = "Contraindication"
    PROHIBITION = "Prohibition"
    SUPPORTS_INDICATION = "Supports indication"
    DOES_NOT_SUPPORT_INDICATION = "Does not support indication"
    INTERACTION = "Interaction"
    RESTRICTION = "Restriction"
    IDENTITY_CONFIRMATION = "Identity confirmation"
    PREPARATION_SPECIFICATION = "Preparation specification"


class SeverityLevel(str, Enum):
    """Same four values reference_precedence.py's _SEVERITY_ORDER
    already keys on — formalized as an Enum here without changing
    reference_precedence.py itself (its dict keys are plain strings
    that equal these Enum values' .value)."""
    NONE = "NONE"
    MINOR = "MINOR"
    MODERATE = "MODERATE"
    SERIOUS = "SERIOUS"


class TransformationType(str, Enum):
    """How evidence text was derived from its source (v4 correction
    #4 references this for the SYNTHETIC-only restriction on
    SUMMARIZED_BY_CURATOR)."""
    VERBATIM = "Verbatim excerpt"
    NORMALIZED_TERMINOLOGY = "Normalized terminology"
    TRANSLATED = "Translated"
    SUMMARIZED_BY_CURATOR = "Summarized by curator"


class ExtractionConfidenceLevel(str, Enum):
    """Honest categorical model — no uncalibrated pseudo-precise
    probability (approved architecture, correction #11 from the prior
    revision)."""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class GoldCaseKind(str, Enum):
    """Explicit, stored field — never inferred from case_id string
    prefix (v4 correction #4)."""
    SYNTHETIC = "Synthetic"
    REFERENCE_GROUNDED = "Reference grounded"


class CurationStatus(str, Enum):
    """Workflow status — a genuine LOCK PREREQUISITE (v4 correction
    #1), but never sufficient by itself; see gold_case.is_lockable()
    for the full invariant set this must be combined with."""
    DRAFT = "Draft"
    REFERENCE_CURATED = "Reference-curated"
    INTERNALLY_REVIEWED = "Internally reviewed"
    EXPERT_ADJUDICATED = "Expert adjudicated"


# Explicit set, not an ordering comparison (v4 correction #1: "Do not
# use string-enum ordering. Use an explicit set or capability
# function."). DRAFT is deliberately absent — a case in DRAFT must
# never be lockable, regardless of any other invariant.
LOCK_ELIGIBLE_CURATION_STATUSES = frozenset({
    CurationStatus.REFERENCE_CURATED,
    CurationStatus.INTERNALLY_REVIEWED,
    CurationStatus.EXPERT_ADJUDICATED,
})


def is_curation_status_lock_eligible(status: CurationStatus) -> bool:
    """The one function anything checking this should call — never a
    direct set/ordering comparison inlined elsewhere."""
    return status in LOCK_ELIGIBLE_CURATION_STATUSES


class ValidationScope(str, Enum):
    """v4 correction #6 — replaces the free-text validation_scope
    field. Phase 2 may only ever produce PROVIDED_EVIDENCE; END_TO_END
    is a real, reserved value for the future Corpus/Retrieval
    Validation phase, not a placeholder that "can never" be used —
    see evaluation_run.py's own enforcement of this restriction."""
    PROVIDED_EVIDENCE = "provided-evidence"
    END_TO_END = "end-to-end"
