"""Structured final scientific decision policy.

Combines the pre-scoring safety/regulatory EligibilityDecision with a
record-level scientific-evidence signal.  This is deliberately separate from
eligibility_gate.py: eligibility remains the source of truth for safety and
regulatory admissibility, while this module owns the final six-class decision
used by scientific decision validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from interaction_severity_classifier import (
    InteractionSeverityTier, classify_interaction_assertion,
)

from eligibility_gate import EligibilityDecision, EligibilityStatus
from evidence_interpretation import (
    interpret_evidence,
    DIRECTION_POSITIVE, DIRECTION_NEGATIVE, DIRECTION_NULL,
    DIRECTION_MIXED, DIRECTION_UNCLEAR,
)




class AssessmentDomain(str, Enum):
    THERAPEUTIC = "therapeutic"
    PREPARATION_SPEC = "preparation_spec"
    IDENTITY_QUALITY = "identity_quality"
    SAFETY = "safety"


def assessment_domain_from_indication(indication: object) -> AssessmentDomain:
    """Map explicit non-therapeutic assessment labels to decision domains.

    This is intentionally narrow: ordinary therapeutic indications remain
    THERAPEUTIC.  The labels are the public domain names used by the
    validation/question layer, not plant- or case-specific values.
    """
    n = " ".join(str(indication or "").strip().lower().replace("_", " ").split())
    if n in {"preparation specification", "preparation spec"}:
        return AssessmentDomain.PREPARATION_SPEC
    if n in {"identity/quality", "identity quality", "identity and quality"}:
        return AssessmentDomain.IDENTITY_QUALITY
    if n == "safety":
        return AssessmentDomain.SAFETY
    return AssessmentDomain.THERAPEUTIC


def _has_domain_evidence(records: Iterable[Mapping]) -> bool:
    return any(
        str(rec.get("assertion_text") or rec.get("text") or "").strip()
        for rec in records
    )


def _safety_domain_requires_review(records: Iterable[Mapping]) -> bool:
    for rec in records:
        text = str(rec.get("assertion_text") or rec.get("text") or "")
        result = classify_interaction_assertion(text)
        if result.tier in {
            InteractionSeverityTier.PRECAUTION_CAUTION,
            InteractionSeverityTier.MODERATE_INTERACTION,
            InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION,
            InteractionSeverityTier.SERIOUS_CONTRAINDICATION,
        }:
            return True
    return False


class ScientificEvidenceSignal(str, Enum):
    SUPPORTIVE = "supportive"
    SUPPORTIVE_WITH_CAUTION = "supportive_with_caution"
    CONFLICT = "conflict"
    INSUFFICIENT = "insufficient"
    UNRESOLVED = "unresolved"


class FinalDecisionStatus(str, Enum):
    GO = "GO"
    GO_WITH_CAUTION = "GO WITH CAUTION"
    EXPERT_REVIEW_REQUIRED = "EXPERT REVIEW REQUIRED"
    NO_GO_SAFETY = "NO GO SAFETY"
    NO_GO_REGULATORY = "NO GO REGULATORY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT EVIDENCE"


# Existing INDICATION_EVIDENCE precedence order from reference_precedence.py.
# Kept here as a production-facing immutable projection so production code does
# not depend on validation dataclasses.  Any change must be mirrored by a test
# against reference_precedence's public behavior.
_INDICATION_SOURCE_RANK = {
    "SYSTEMATIC_REVIEW": 0,
    "EMA_HMPC": 1,
    "WHO_MONOGRAPH": 2,
    "ESCOP_MONOGRAPH": 3,
    "COMMISSION_E": 4,
}


@dataclass(frozen=True)
class ScientificEvidenceResolution:
    signal: ScientificEvidenceSignal
    reason: str
    top_rank_source_types: tuple[str, ...] = ()
    directions: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinalDecision:
    status: FinalDecisionStatus
    reason: str


def resolve_scientific_evidence(records: Iterable[Mapping]) -> ScientificEvidenceResolution:
    """Resolve only record-level indication evidence, never pooled text.

    The highest-ranked recognized indication source tier governs. Equally
    ranked records that disagree are escalated instead of averaged. A top-tier
    negative/null finding means the efficacy evidence is insufficient for GO;
    completely unclassified text stays UNRESOLVED and does not manufacture a
    negative decision.
    """
    interpreted = []
    for rec in records:
        source_type = str(rec.get("source_type") or "").strip().upper()
        rank = _INDICATION_SOURCE_RANK.get(source_type)
        if rank is None:
            continue
        text = str(rec.get("assertion_text") or rec.get("text") or "")
        direction = interpret_evidence(text).evidence_direction
        # Narrow final-decision-only interpretation of explicit review
        # conclusions.  The calibrated scoring classifier remains untouched;
        # this layer only prevents clear conclusion language from becoming an
        # accidental GO/INSUFFICIENT fall-through at the final decision stage.
        _n = " ".join(text.lower().split())
        if direction == DIRECTION_UNCLEAR:
            if any(phrase in _n for phrase in (
                "insufficient evidence to support",
                "insufficient evidence for",
                "evidence is insufficient to support",
                "evidence was insufficient to support",
                "little to no benefit", "little or no benefit",
                "no clear benefit", "inconclusive",
            )):
                direction = DIRECTION_NULL
            elif (
                any(phrase in _n for phrase in (
                    "appears efficacious", "appeared efficacious",
                    "appears effective", "appeared effective",
                    "showed reductions", "reported reductions",
                    "showed improvement", "reported improvement",
                    "showed improvements", "reported improvements",
                    "evidence suggesting", "evidence suggests",
                ))
                and any(token in _n for token in (
                    "efficacious", "effective", "reduction", "improvement",
                    "improv", "benefit", "efficacy",
                ))
            ):
                direction = DIRECTION_POSITIVE

        # Preserve uncertainty that is explicitly stated by the evidence itself.
        # This is semantic, not plant-specific: a supportive conclusion that is
        # materially hedged (e.g. "may be beneficial", "requires confirmation")
        # is not equivalent to an unconditional positive finding.  Conversely,
        # explicit statements that the evidence remains uncertain/insufficient
        # for firm conclusions cannot be promoted to GO merely because the same
        # sentence mentions a possible benefit.
        _firm_uncertainty_phrases = (
            "evidence remains uncertain",
            "evidence is uncertain",
            "evidence was uncertain",
            "insufficient for firm conclusions",
            "insufficient to draw firm conclusions",
            "insufficient to draw conclusions",
            "cannot draw firm conclusions",
            "no firm conclusions",
        )
        _cautionary_support_phrases = (
            "may be beneficial",
            "might be beneficial",
            "could be beneficial",
            "requires confirmation",
            "require confirmation",
            "needs confirmation",
            "need confirmation",
            "further high-quality trials",
            "further high quality trials",
            "further studies are needed",
            "further studies are required",
            "additional studies are needed",
            "additional studies are required",
            "more research is needed",
            "more research is required",
        )
        if any(phrase in _n for phrase in _firm_uncertainty_phrases):
            direction = DIRECTION_NULL
        elif direction == DIRECTION_POSITIVE and any(phrase in _n for phrase in (
            "evidence varied across studies",
            "results varied across studies",
            "findings varied across studies",
            "mixed findings",
            "mixed results",
            "inconsistent findings",
            "inconsistent results",
            *_cautionary_support_phrases,
        )):
            direction = DIRECTION_MIXED
        interpreted.append((rank, source_type, direction))

    if not interpreted:
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.UNRESOLVED,
            "No recognized indication-evidence source tier was available for record-level resolution.",
        )

    best_rank = min(x[0] for x in interpreted)
    top = [x for x in interpreted if x[0] == best_rank]
    directions = tuple(sorted({x[2] for x in top}))
    source_types = tuple(sorted({x[1] for x in top}))
    ds = set(directions)

    # A single governing tier that is internally mixed but not contradicted by
    # a separate same-rank positive-vs-null/negative source supports a cautious
    # decision rather than either an unconditional GO or an expert-conflict
    # escalation.  Cross-record disagreement remains a true CONFLICT.
    if DIRECTION_POSITIVE in ds and bool(ds & {DIRECTION_NEGATIVE, DIRECTION_NULL}):
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.CONFLICT,
            "Equally ranked governing indication sources contain opposing efficacy directions; automatic averaging is prohibited.",
            source_types, directions,
        )
    if DIRECTION_MIXED in ds:
        non_mixed = ds - {DIRECTION_MIXED, DIRECTION_UNCLEAR}
        if non_mixed & {DIRECTION_NEGATIVE, DIRECTION_NULL}:
            return ScientificEvidenceResolution(
                ScientificEvidenceSignal.CONFLICT,
                "Governing indication evidence is mixed and is accompanied by an equally ranked negative/null direction; expert review is required.",
                source_types, directions,
            )
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION,
            "The governing indication-evidence tier is supportive but explicitly mixed/inconsistent; a cautious GO is warranted.",
            source_types, directions,
        )
    if DIRECTION_POSITIVE in ds:
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.SUPPORTIVE,
            "The governing indication-evidence tier contains a supportive efficacy direction without an equally ranked contradiction.",
            source_types, directions,
        )
    if ds & {DIRECTION_NEGATIVE, DIRECTION_NULL}:
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.INSUFFICIENT,
            "The governing indication-evidence tier is negative/null and therefore does not support a GO decision.",
            source_types, directions,
        )
    return ScientificEvidenceResolution(
        ScientificEvidenceSignal.UNRESOLVED,
        "The governing indication-evidence tier could not be assigned a usable efficacy direction.",
        source_types, directions,
    )


def decide_final(
    eligibility: EligibilityDecision,
    scientific: ScientificEvidenceResolution,
    *,
    assessment_domain: AssessmentDomain = AssessmentDomain.THERAPEUTIC,
    records: Iterable[Mapping] = (),
) -> FinalDecision:
    if eligibility.status == EligibilityStatus.NO_GO_REGULATORY:
        return FinalDecision(FinalDecisionStatus.NO_GO_REGULATORY, eligibility.gate_reason)
    if eligibility.status == EligibilityStatus.NO_GO_SAFETY:
        return FinalDecision(FinalDecisionStatus.NO_GO_SAFETY, eligibility.gate_reason)
    if eligibility.status == EligibilityStatus.EXPERT_REVIEW_REQUIRED:
        return FinalDecision(FinalDecisionStatus.EXPERT_REVIEW_REQUIRED, eligibility.gate_reason)

    # Non-therapeutic scientific questions must not silently inherit the
    # therapeutic efficacy decision path.  Preparation and identity/quality
    # evidence confirms a domain claim, but does not by itself justify an
    # automatic product-development GO in this six-class decision framework.
    # Route an evidenced claim to expert review; absent evidence remains
    # insufficient.  This is domain-generic and independent of plant identity.
    if assessment_domain in {AssessmentDomain.PREPARATION_SPEC, AssessmentDomain.IDENTITY_QUALITY}:
        if _has_domain_evidence(records):
            return FinalDecision(
                FinalDecisionStatus.EXPERT_REVIEW_REQUIRED,
                f"{assessment_domain.value} evidence is present and requires domain-specific expert verification before a development GO.",
            )
        return FinalDecision(
            FinalDecisionStatus.INSUFFICIENT_EVIDENCE,
            f"No usable {assessment_domain.value} evidence was available for domain-specific assessment.",
        )

    # A Safety-domain question is itself asking whether a safety finding needs
    # action.  Explicit interaction precaution/moderate-or-higher language
    # therefore routes to expert review even when it is not severe enough to
    # become a therapeutic hard NO-GO.  Hard NO-GO states above remain
    # authoritative and take precedence.
    if assessment_domain == AssessmentDomain.SAFETY and _safety_domain_requires_review(records):
        return FinalDecision(
            FinalDecisionStatus.EXPERT_REVIEW_REQUIRED,
            "Safety-domain evidence contains an explicit interaction precaution or stronger interaction assertion requiring expert review.",
        )
    if scientific.signal == ScientificEvidenceSignal.CONFLICT:
        return FinalDecision(FinalDecisionStatus.EXPERT_REVIEW_REQUIRED, scientific.reason)
    if scientific.signal == ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION:
        return FinalDecision(FinalDecisionStatus.GO_WITH_CAUTION, scientific.reason)
    if eligibility.status == EligibilityStatus.INCOMPLETE:
        return FinalDecision(FinalDecisionStatus.INSUFFICIENT_EVIDENCE, eligibility.gate_reason)
    if scientific.signal == ScientificEvidenceSignal.INSUFFICIENT:
        return FinalDecision(FinalDecisionStatus.INSUFFICIENT_EVIDENCE, scientific.reason)
    if eligibility.status == EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS:
        return FinalDecision(FinalDecisionStatus.GO_WITH_CAUTION, eligibility.gate_reason)
    return FinalDecision(FinalDecisionStatus.GO, "Safety/regulatory eligibility passed and no governing scientific evidence requires abstention.")


def final_status_from_engine_row(row: Mapping) -> FinalDecisionStatus:
    """Read the six-class final state from existing production outputs.

    Eligibility_Status remains authoritative for safety/regulatory outcomes;
    Decision_Class carries scientific conflict/insufficiency abstentions.
    This keeps the public engine output contract stable while still allowing a
    structured benchmark comparison.
    """
    structured_status = str(row.get("Final_Decision_Status") or "").strip()
    if structured_status:
        try:
            return FinalDecisionStatus(structured_status)
        except ValueError:
            pass

    eligibility = str(row.get("Eligibility_Status") or "")
    decision_class = str(row.get("Decision_Class") or "").lower()
    if eligibility == EligibilityStatus.NO_GO_REGULATORY.value:
        return FinalDecisionStatus.NO_GO_REGULATORY
    if eligibility == EligibilityStatus.NO_GO_SAFETY.value:
        return FinalDecisionStatus.NO_GO_SAFETY
    if eligibility == EligibilityStatus.EXPERT_REVIEW_REQUIRED.value:
        return FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
    if "expert review required" in decision_class:
        return FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
    if ("insufficient evidence" in decision_class or "insufficient data" in decision_class
            or decision_class.startswith("incomplete")):
        return FinalDecisionStatus.INSUFFICIENT_EVIDENCE
    if "go with caution" in decision_class:
        return FinalDecisionStatus.GO_WITH_CAUTION
    if eligibility == EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS.value:
        return FinalDecisionStatus.GO_WITH_CAUTION
    return FinalDecisionStatus.GO
