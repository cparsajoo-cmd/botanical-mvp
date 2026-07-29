"""
Reference-Grounded Validation — Severity Assignment Policy.

WHAT THIS IS
An explicit, versioned, repository-level rule for assigning
ReferenceClaim.severity (assertion_vocabulary.SeverityLevel) to a
documented SAFETY-domain contraindication or interaction claim.

WHY THIS EXISTS
reference_precedence.py's SAFETY resolution logic (_resolve_safety())
requires every applicable reference to already carry a parseable
severity before it will resolve at all — but nothing in this
repository previously defined HOW a severity gets assigned to a claim
in the first place. Case 006 initially filled that gap with an ad hoc,
case-specific paragraph of curator reasoning, which was correctly
rejected as not being "a documented repository rule." This module is
that rule: named, versioned, and available to every future SAFETY
case, not re-derived per case.

WHAT THIS RULE COVERS
A CONTRAINDICATION or INTERACTION claim whose contraindicated/
interacting substance(s) fall into one or more of the
HighRiskInteractionDrugClass values below is assigned
SeverityLevel.SERIOUS. These classes were chosen because reduced or
altered plasma concentrations of any of them carry a recognized risk
of serious, potentially life-threatening clinical consequences (organ
transplant rejection, thromboembolic events, antiretroviral treatment
failure, chemotherapy under/over-exposure).

WHAT THIS RULE DELIBERATELY DOES NOT COVER
- Any drug class not in HighRiskInteractionDrugClass. An unrecognized
  or empty class set returns None (no rule applies) — never a guessed
  severity.
- MODERATE/MINOR assignment. This policy currently formalizes only the
  SERIOUS case, which is what motivated it; a future revision may add
  rules for other severities, but none is invented here.
- Dose-gated or otherwise CONDITIONAL contraindications (e.g.
  "contraindicated only above a stated threshold"). This function
  assumes the caller is applying it to an unconditional claim; a
  dose-gated claim is a separate curator judgment this policy does
  not resolve.

VERSIONING
SEVERITY_ASSIGNMENT_RULE_VERSION follows the same convention as
subject_normalization.SUBJECT_NORMALIZATION_RULE_VERSION and
resolved_expected_outcome.py's translation/policy version constants —
bump it whenever HighRiskInteractionDrugClass or the logic below
changes, so a claim's provenance can always name the exact rule
version that assigned its severity.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Optional

from assertion_vocabulary import AssertionType, SeverityLevel

SEVERITY_ASSIGNMENT_RULE_VERSION = "1.0.0"


class HighRiskInteractionDrugClass(str, Enum):
    """Controlled vocabulary for the drug classes this policy
    recognizes. A curator selects from these explicit values, never a
    free string, so applying this rule stays checkable rather than
    becoming a re-litigated judgment call per case."""
    NARROW_THERAPEUTIC_INDEX = "Narrow therapeutic index medicine"
    TRANSPLANT_IMMUNOSUPPRESSANT = "Transplant immunosuppressant"
    ANTICOAGULANT = "Anticoagulant"
    ANTIRETROVIRAL_THERAPY = "Antiretroviral therapy"
    CYTOTOXIC_AGENT = "Cytotoxic / chemotherapeutic agent"


# AssertionTypes this policy applies to. A claim about anything else
# (e.g. SUPPORTS_INDICATION) is out of scope for this rule regardless
# of drug_classes.
_APPLICABLE_ASSERTION_TYPES = frozenset({
    AssertionType.CONTRAINDICATION,
    AssertionType.INTERACTION,
})


def assign_contraindication_severity(
    assertion_type: AssertionType,
    drug_classes: FrozenSet["HighRiskInteractionDrugClass"],
) -> Optional[SeverityLevel]:
    """The ONE function this policy exists to provide.

    Returns SeverityLevel.SERIOUS iff `assertion_type` is
    CONTRAINDICATION or INTERACTION AND `drug_classes` contains at
    least one HighRiskInteractionDrugClass member. Otherwise returns
    None — no rule applies, and this function never guesses a
    severity it cannot justify by the explicit table above.

    Pure and deterministic: same inputs always produce the same
    output, no randomness, no external lookup.
    """
    if assertion_type not in _APPLICABLE_ASSERTION_TYPES:
        return None
    if not drug_classes:
        return None
    if not set(drug_classes).issubset(set(HighRiskInteractionDrugClass)):
        # Defensive: a caller passing something outside the controlled
        # vocabulary gets no assignment, never a partial/best-effort
        # one silently computed from the recognized subset.
        return None
    return SeverityLevel.SERIOUS
