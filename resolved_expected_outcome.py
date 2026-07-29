"""
Reference-Grounded Validation — ResolvedExpectedOutcome.

WHAT THIS IS
The FINAL expected answer for one (domain, assertion_type,
normalized_subject) identity — never a raw ReferenceClaim.
evaluation_run.py compares engine output against THESE, never against
an arbitrary per-reference claim directly.

derive_reference_verdict_from_claim() IS THE ONLY BRIDGE TO
reference_precedence.py — that module is completely unmodified by this
work; this function projects a ReferenceClaim down to the lightweight
(reference_id, safety_severity, verdict_value) shape
reference_precedence.resolve_precedence() already expects, using the
severity/assertion values a ReferenceClaim already carries in
controlled-vocabulary form.

GROUPING BY ASSERTION IDENTITY (v4 correction #5)
group_claims_by_assertion_identity() groups by
(domain, assertion_type, normalized_subject) — NOT by domain alone.
Two claims about DIFFERENT subjects (e.g. "pregnancy" vs "hepatic
impairment") must never be compared against each other in the same
precedence operation, even if both are SAFETY-domain contraindication
claims. subject_normalization.normalize_subject() collapses surface-
form variants ("pregnancy" / "pregnant women" / "use in pregnancy")
onto one canonical subject before grouping — see that module's own
docstring for why and how this is versioned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from applicability_check import ReferenceDomain
from assertion_vocabulary import AssertionState, AssertionType, SeverityLevel
from reference_claim import ReferenceClaim
from reference_precedence import ReferenceVerdict, resolve_precedence, ResolutionStatus
from subject_normalization import normalize_subject, SUBJECT_NORMALIZATION_RULE_VERSION

# v4 correction #5/#10 — every ResolvedExpectedOutcome this module
# produces stores the exact policy/rule versions used to derive it.
# Bump these whenever the corresponding translation/policy logic
# changes, so an already-locked outcome's provenance always names the
# exact version that produced it.
TRANSLATION_RULE_ID = "claim_to_resolved_outcome_v1"
TRANSLATION_RULE_VERSION = "1.0.0"
APPLICABILITY_POLICY_VERSION = "1.0.0"  # applicability_check.py's current dimension set
PRECEDENCE_POLICY_VERSION = "1.0.0"     # reference_precedence.py's current hierarchy set


@dataclass
class ResolvedExpectedOutcome:
    domain: ReferenceDomain
    subject: str  # the NORMALIZED subject — the grouping identity itself
    assertion_type: AssertionType
    assertion_state: Optional[AssertionState]
    severity: Optional[SeverityLevel] = None
    resolution_status: ResolutionStatus = ResolutionStatus.NO_APPLICABLE_REFERENCE
    selected_reference_id: Optional[str] = None
    conflicting_reference_ids: list = field(default_factory=list)
    translation_rule_id: str = TRANSLATION_RULE_ID
    translation_rule_version: str = TRANSLATION_RULE_VERSION
    precedence_policy_version: str = PRECEDENCE_POLICY_VERSION
    applicability_policy_version: str = APPLICABILITY_POLICY_VERSION
    subject_normalization_rule_version: str = SUBJECT_NORMALIZATION_RULE_VERSION


def derive_reference_verdict_from_claim(claim: ReferenceClaim) -> ReferenceVerdict:
    """The ONLY bridge to reference_precedence.py — see module
    docstring. reference_precedence.py itself is never modified by
    this work."""
    verdict_value = f"{claim.assertion_type.value}:{claim.assertion_state.value}"
    return ReferenceVerdict(
        reference_id=claim.source_reference_id,
        safety_severity=claim.severity.value if claim.severity else None,
        verdict_value=verdict_value,
    )


def group_claims_by_assertion_identity(gold_case_references: list) -> dict:
    """Groups every claim across every GoldCaseReference by
    (domain, assertion_type, normalized_subject) — v4 correction #5.
    Returns dict[(ReferenceDomain, AssertionType, str), list[tuple]]
    where each tuple is (gold_case_reference, claim)."""
    groups: dict = {}
    for gref in gold_case_references:
        for claim in gref.claims:
            key = (claim.domain, claim.assertion_type, normalize_subject(claim.subject))
            groups.setdefault(key, []).append((gref, claim))
    return groups


def resolve_expected_outcomes(gold_case) -> list:
    """Produces the full list of ResolvedExpectedOutcome for a
    GoldCase — one per (domain, assertion_type, normalized_subject)
    identity found across all of its references' claims.

    For each identity group:
      1. Filter to (reference, claim) pairs whose reference is
         APPLICABLE for that exact domain (per
         gref.applicability_by_domain[domain].applicable) — a claim
         from an inapplicable reference is excluded before precedence
         ever sees it, exactly like the engine's own precautionary
         safety precedence only ever compares already-applicable
         references.
      2. If no applicable claims remain: resolution_status =
         NO_APPLICABLE_REFERENCE (via reference_precedence.py itself,
         called with an empty list — consistent single source of
         truth for that status).
      3. Otherwise: derive a ReferenceVerdict per applicable claim and
         call reference_precedence.resolve_precedence() — completely
         unmodified.
      4. Translate the resolution into a ResolvedExpectedOutcome:
         when status == SELECTED, assertion_state/severity are taken
         from the SELECTED claim; for any other status, assertion_state
         is None (there is no single answer to translate) and the
         resolution_status itself carries the meaning.

    Never mutates gold_case or any of its references/claims — pure
    function, same convention as assess_leakage().
    """
    outcomes = []
    groups = group_claims_by_assertion_identity(gold_case.references)

    for (domain, assertion_type, normalized_subject), pairs in groups.items():
        applicable_pairs = []
        for gref, claim in pairs:
            applicability = gref.applicability_by_domain.get(domain)
            if applicability is not None and applicability.applicable:
                applicable_pairs.append((gref, claim))

        if not applicable_pairs:
            resolution = resolve_precedence(domain, [])
        else:
            verdict_pairs = [
                (gref.reference, derive_reference_verdict_from_claim(claim))
                for gref, claim in applicable_pairs
            ]
            resolution = resolve_precedence(domain, verdict_pairs)

        assertion_state = None
        severity = None
        if resolution.status == ResolutionStatus.SELECTED:
            selected_claim = next(
                (claim for gref, claim in applicable_pairs
                 if gref.reference.reference_id == resolution.selected_reference_id),
                None,
            )
            if selected_claim is not None:
                assertion_state = selected_claim.assertion_state
                severity = selected_claim.severity

        outcomes.append(ResolvedExpectedOutcome(
            domain=domain,
            subject=normalized_subject,
            assertion_type=assertion_type,
            assertion_state=assertion_state,
            severity=severity,
            resolution_status=resolution.status,
            selected_reference_id=resolution.selected_reference_id,
            conflicting_reference_ids=list(resolution.conflicting_reference_ids),
        ))

    return outcomes
