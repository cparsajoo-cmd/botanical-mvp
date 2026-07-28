"""
Validation Architecture v3 — Phase 1: Reference Precedence.

WHAT THIS IS
Five independent, domain-specific reference hierarchies (Validation
Architecture v3 correction #1 — no single global hierarchy) plus the
conflict-resolution policy that picks a winner, or explicitly refuses
to, among references that have ALREADY passed check_applicability()
against the SAME ValidationUnit for the SAME domain
(applicability_check.py). This module never re-checks applicability —
resolve_precedence()'s caller is responsible for filtering to
applicable references first (v3 correction #6). A reference that
never passed applicability must never reach this function.

PRECAUTIONARY SAFETY PRECEDENCE — APPLIED ONLY AFTER APPLICABILITY
For the SAFETY domain, the most conservative (most severe) applicable
verdict wins, regardless of source rank — but this rule only ever
compares references that already passed applicability_check.py's
seven-dimension check against the ValidationUnit. A safety reference
for an inapplicable preparation/population/jurisdiction is never
allowed to override a genuinely applicable one just by being more
severe — severity-first logic is a tie-breaker AMONG applicable
references, never a bypass of applicability itself.

FIVE STRUCTURED RESOLUTION STATUSES (v3 correction #6 — exact set)
    SELECTED                — exactly one reference wins
    REFERENCE_CONFLICT      — 2+ equally-ranked applicable references
                               disagree (non-safety domains)
    NO_APPLICABLE_REFERENCE — zero references passed applicability
    INSUFFICIENT_METADATA   — an applicable reference's source_type
                               isn't in this domain's hierarchy, or a
                               safety reference has no parseable
                               severity — resolution cannot even be
                               attempted
    HUMAN_REVIEW_REQUIRED   — SAFETY domain specifically: a tied,
                               disagreeing severity that even the
                               domain's own fallback rank cannot
                               resolve. Deliberately a DIFFERENT status
                               from REFERENCE_CONFLICT: silently
                               picking a "first" winner among tied
                               safety verdicts by rank is exactly the
                               "auto-resolve" risk the precautionary
                               principle exists to prevent, so this
                               case is named and escalated distinctly,
                               never resolved automatically.

WHY THIS MODULE NEVER AVERAGES OR MERGES CONFLICTING VERDICTS
Per Validation Architecture v2's hard rule (preserved unchanged): two
conflicting results are never automatically averaged or combined into
one "reference truth" — REFERENCE_CONFLICT and HUMAN_REVIEW_REQUIRED
both report every conflicting reference_id, never silently pick a
blended answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from applicability_check import ReferenceDomain
from reference_descriptor import ReferenceDescriptor


class ResolutionStatus(str, Enum):
    SELECTED = "Selected"
    REFERENCE_CONFLICT = "Reference conflict"
    NO_APPLICABLE_REFERENCE = "No applicable reference"
    INSUFFICIENT_METADATA = "Insufficient metadata"
    HUMAN_REVIEW_REQUIRED = "Human review required"


@dataclass
class ReferenceVerdict:
    """The minimal per-reference verdict content resolve_precedence()
    needs — curated separately from ReferenceDescriptor's scope
    metadata (applicability_check.py never reads this; precedence
    never reads ReferenceDescriptor's scope fields). safety_severity
    is required for SAFETY-domain resolution; verdict_value is a
    generic categorical verdict (e.g. an eligibility label) used to
    detect disagreement in every domain."""
    reference_id: str
    safety_severity: Optional[str] = None  # "SERIOUS" | "MODERATE" | "MINOR" | "NONE"
    verdict_value: Optional[str] = None


@dataclass
class PrecedenceResolution:
    domain: ReferenceDomain
    status: ResolutionStatus
    selected_reference_id: Optional[str] = None
    conflicting_reference_ids: list = field(default_factory=list)
    detail: str = ""


_SEVERITY_ORDER = {"NONE": 0, "MINOR": 1, "MODERATE": 2, "SERIOUS": 3}

# Rank hierarchies — index 0 is HIGHEST priority. Deliberately five
# INDEPENDENT lists (v3 correction #1): a pharmacopoeia does not
# automatically outrank evidence sources for INDICATION_EVIDENCE, even
# though it is ranked first for IDENTITY_QUALITY and PREPARATION_SPEC.
_DOMAIN_HIERARCHIES = {
    ReferenceDomain.IDENTITY_QUALITY: [
        "PHARMACOPOEIA", "EMA_HMPC", "WHO_MONOGRAPH", "TAXONOMIC_AUTHORITY",
    ],
    ReferenceDomain.INDICATION_EVIDENCE: [
        "SYSTEMATIC_REVIEW", "EMA_HMPC", "WHO_MONOGRAPH",
        "ESCOP_MONOGRAPH", "COMMISSION_E",
    ],
    ReferenceDomain.REGULATORY_STATUS: [
        "NATIONAL_REGULATORY", "EMA_HMPC", "OTHER_NATIONAL_REGULATORY",
    ],
    ReferenceDomain.PREPARATION_SPEC: [
        "EMA_HMPC", "PHARMACOPOEIA", "WHO_MONOGRAPH", "ESCOP_MONOGRAPH",
    ],
    # SAFETY intentionally has no rank list here — severity always
    # decides first; _SAFETY_FALLBACK_RANK below is used ONLY to break
    # a tie among applicable references that share the same severity.
}

_SAFETY_FALLBACK_RANK = ["EMA_HMPC", "WHO_MONOGRAPH", "ESCOP_MONOGRAPH", "COMMISSION_E"]


def _rank_index(source_type: str, hierarchy: list) -> Optional[int]:
    return hierarchy.index(source_type) if source_type in hierarchy else None


def _resolve_safety(
    applicable: list,  # list[tuple[ReferenceDescriptor, ReferenceVerdict]]
) -> PrecedenceResolution:
    parsed = []
    for reference, verdict in applicable:
        if verdict.safety_severity not in _SEVERITY_ORDER:
            return PrecedenceResolution(
                domain=ReferenceDomain.SAFETY,
                status=ResolutionStatus.INSUFFICIENT_METADATA,
                detail=(
                    f"Reference {reference.reference_id!r} has no parseable "
                    f"safety_severity ({verdict.safety_severity!r})."
                ),
            )
        parsed.append((_SEVERITY_ORDER[verdict.safety_severity], reference, verdict))

    max_severity = max(p[0] for p in parsed)
    most_severe = [p for p in parsed if p[0] == max_severity]

    if len(most_severe) == 1:
        _, ref, _ = most_severe[0]
        return PrecedenceResolution(
            domain=ReferenceDomain.SAFETY,
            status=ResolutionStatus.SELECTED,
            selected_reference_id=ref.reference_id,
            detail="Most conservative (highest-severity) applicable reference selected.",
        )

    # Tie at the highest severity among applicable references. If they
    # all agree on verdict_value, the tie is harmless — select by
    # fallback rank. If they disagree, this is exactly the case
    # HUMAN_REVIEW_REQUIRED exists for — never silently pick one.
    verdict_values = {p[2].verdict_value for p in most_severe}
    if len(verdict_values) == 1:
        ranked = [
            (p, _rank_index(p[1].source_type, _SAFETY_FALLBACK_RANK)) for p in most_severe
        ]
        ranked = [r for r in ranked if r[1] is not None]
        if ranked:
            ranked.sort(key=lambda r: r[1])
            winner_ref = ranked[0][0][1]
            return PrecedenceResolution(
                domain=ReferenceDomain.SAFETY,
                status=ResolutionStatus.SELECTED,
                selected_reference_id=winner_ref.reference_id,
                detail="Tied severity, agreeing verdicts — resolved by fallback rank.",
            )
        # Agreeing verdicts but none of the tied references are in the
        # fallback rank list — arbitrary choice would be unprincipled.
        return PrecedenceResolution(
            domain=ReferenceDomain.SAFETY,
            status=ResolutionStatus.INSUFFICIENT_METADATA,
            conflicting_reference_ids=[p[1].reference_id for p in most_severe],
            detail="Tied severity, agreeing verdicts, but no fallback rank applies.",
        )

    return PrecedenceResolution(
        domain=ReferenceDomain.SAFETY,
        status=ResolutionStatus.HUMAN_REVIEW_REQUIRED,
        conflicting_reference_ids=[p[1].reference_id for p in most_severe],
        detail=(
            "Tied highest severity among applicable references, with "
            "disagreeing verdicts — precautionary policy forbids "
            "auto-resolving this by rank."
        ),
    )


def _resolve_ranked_domain(
    domain: ReferenceDomain,
    applicable: list,  # list[tuple[ReferenceDescriptor, ReferenceVerdict]]
) -> PrecedenceResolution:
    hierarchy = _DOMAIN_HIERARCHIES.get(domain)
    if hierarchy is None:
        return PrecedenceResolution(
            domain=domain,
            status=ResolutionStatus.INSUFFICIENT_METADATA,
            detail=f"No precedence hierarchy defined for domain {domain.value!r}.",
        )

    ranked = []
    for reference, verdict in applicable:
        idx = _rank_index(reference.source_type, hierarchy)
        if idx is None:
            return PrecedenceResolution(
                domain=domain,
                status=ResolutionStatus.INSUFFICIENT_METADATA,
                detail=(
                    f"Reference {reference.reference_id!r} has source_type "
                    f"{reference.source_type!r}, not recognized in the "
                    f"{domain.value} hierarchy."
                ),
            )
        ranked.append((idx, reference, verdict))

    min_rank = min(r[0] for r in ranked)
    top = [r for r in ranked if r[0] == min_rank]

    if len(top) == 1:
        _, ref, _ = top[0]
        return PrecedenceResolution(
            domain=domain,
            status=ResolutionStatus.SELECTED,
            selected_reference_id=ref.reference_id,
            detail="Single highest-ranked applicable reference selected.",
        )

    verdict_values = {t[2].verdict_value for t in top}
    if len(verdict_values) == 1:
        _, ref, _ = top[0]
        return PrecedenceResolution(
            domain=domain,
            status=ResolutionStatus.SELECTED,
            selected_reference_id=ref.reference_id,
            detail="Multiple equally-ranked references, but all agree — selected.",
        )

    return PrecedenceResolution(
        domain=domain,
        status=ResolutionStatus.REFERENCE_CONFLICT,
        conflicting_reference_ids=[t[1].reference_id for t in top],
        detail="Equally-ranked applicable references disagree.",
    )


def resolve_precedence(
    domain: ReferenceDomain,
    applicable_references: list,  # list[tuple[ReferenceDescriptor, ReferenceVerdict]]
) -> PrecedenceResolution:
    """The ONE function this module exists to provide. `applicable_references`
    must already be filtered to references that passed
    applicability_check.check_applicability() against the same
    ValidationUnit for this same domain (v3 correction #6) — this
    function does not re-check applicability and has no access to a
    ValidationUnit at all.

    Returns a PrecedenceResolution with exactly one of the five
    statuses documented in this module's docstring. Never averages or
    merges conflicting verdicts — see module docstring's hard rule.
    """
    if not applicable_references:
        return PrecedenceResolution(
            domain=domain,
            status=ResolutionStatus.NO_APPLICABLE_REFERENCE,
            detail="No references passed applicability for this domain.",
        )

    if domain == ReferenceDomain.SAFETY:
        return _resolve_safety(applicable_references)

    return _resolve_ranked_domain(domain, applicable_references)
