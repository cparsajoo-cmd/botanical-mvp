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
import re
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




class EvidenceLimitationTier(str, Enum):
    NONE = "none"
    CAUTION = "caution"
    FIRM_UNCERTAINTY = "firm_uncertainty"


def _evidence_limitation_tier(text: str) -> EvidenceLimitationTier:
    """Decision-layer certainty semantics derived only from supplied evidence text.

    This deliberately does not infer hidden limitations from plant identity or
    benchmark labels.  It recognizes publication-level language that explicitly
    limits certainty, generalisability, durability, or stand-alone use.
    """
    n = " ".join(str(text or "").lower().replace("–", "-").replace("—", "-").split())
    if not n:
        return EvidenceLimitationTier.NONE

    firm = (
        "evidence insufficient to establish",
        "evidence is insufficient to establish",
        "insufficient to establish clear clinical benefit",
        "insufficient to establish clinical benefit",
        "not adequately corroborated",
        "evidence remains uncertain",
        "evidence is uncertain",
        "insufficient for firm conclusions",
        "insufficient to draw firm conclusions",
        "cannot draw firm conclusions",
        "no firm conclusions",
    )
    if any(x in n for x in firm):
        return EvidenceLimitationTier.FIRM_UNCERTAINTY

    caution = (
        "more evidence is needed",
        "more evidence is required",
        "further evidence is needed",
        "further evidence is required",
        "further high-quality trials",
        "further high quality trials",
        "further rigorous trials",
        "more rigorous trials",
        "additional rigorous trials",
        "larger trials are needed",
        "large-scale trial is justified",
        "large scale trial is justified",
        "long-term effects",
        "long term effects",
        "long-term efficacy",
        "long term efficacy",
        "high heterogeneity",
        "very high heterogeneity",
        "substantial heterogeneity",
        "extremely high heterogeneity",
        "risk of bias",
        "high risk of bias",
        "methodological weakness",
        "methodological weaknesses",
        "methodological limitations",
        "remaining uncertainties",
        "remain uncertain",
        "effects varying",
        "effect varying",
        "effects varied",
        "effect varied",
        "variability in diagnostic criteria",
        "variability in outcome measures",
        "variability in preparations",
        "small trials",
        "small studies",
        "only four studies",
        "limited number of studies",
        "adjunctive",
        "alongside lipid-lowering therapy",
        "alongside standard therapy",
        "potentially effective",
    )
    if any(x in n for x in caution):
        return EvidenceLimitationTier.CAUTION

    # General linguistic forms of the same certainty limitations.  These are
    # deliberately concept-based rather than plant/indication phrases.
    caution_patterns = (
        r"\bheterogeneity\b.{0,28}\b(high|very high|substantial|considerable|remain|remains|present)\b",
        r"\b(high|very high|substantial|considerable)\b.{0,28}\bheterogeneity\b",
        r"\b(certainty|quality)\b.{0,24}\b(low|very low|limited|variable|varied)\b",
        r"\b(studies|trials)\b.{0,18}\b(were|are)?\s*(small|limited|few)\b",
        r"\b(reporting|methodological|study)\s+quality\b.{0,24}\b(varied|variable|low|limited)\b",
        r"\bfurther\b.{0,36}\b(trials|studies|research|investigation)\b.{0,24}\b(needed|required|warranted|essential)\b",
        r"\b(cautious|careful)\s+interpretation\b",
        r"\b(populations|interventions|preparations|outcomes|results|findings)\b.{0,28}\b(varied|variable|heterogeneous)\b",
    )
    return EvidenceLimitationTier.CAUTION if any(re.search(pat, n) for pat in caution_patterns) else EvidenceLimitationTier.NONE


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


def _parse_publication_year(rec: Mapping) -> int | None:
    """Best-effort publication year for freshness checks."""
    for key in ("source_year", "publication_year", "year", "Source_Year", "Publication_Year", "Year"):
        value = rec.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if len(text) >= 4 and text[:4].isdigit():
            year = int(text[:4])
            if 1800 <= year <= 2200:
                return year
    return None


def _explicit_conflict_language(text: str) -> bool:
    n = " ".join(str(text or "").lower().split())
    phrases = (
        "matter of debate",
        "remains a matter of debate",
        "evidence is conflicting",
        "evidence remains conflicting",
        "conflicting evidence",
        "conflicting results",
        "results are conflicting",
        "findings are conflicting",
        "not definitive",
        "not conclusive",
        "remains inconclusive",
        "evidence remains inconclusive",
        "controversial evidence",
    )
    return any(phrase in n for phrase in phrases)


def _final_decision_direction(text: str) -> str:
    """Decision-layer semantic direction without changing calibrated scoring."""
    direction = interpret_evidence(text).evidence_direction
    n = " ".join(str(text or "").lower().split())
    if direction == DIRECTION_UNCLEAR:
        if any(phrase in n for phrase in (
            "insufficient evidence to support", "insufficient evidence for",
            "evidence is insufficient to support", "evidence was insufficient to support",
            "little to no benefit", "little or no benefit", "no clear benefit",
            "inconclusive", "trivial-to-small effects", "trivial to small effects",
            "minimal effect", "minimal effects", "little effect", "little effects",
            "little to no difference", "little or no difference",
            "no significant beneficial effect", "no meaningful difference",
        )):
            direction = DIRECTION_NULL
        elif (
            any(phrase in n for phrase in (
                "appears efficacious", "appeared efficacious", "appears effective",
                "appeared effective", "showed reductions", "reported reductions",
                "showed improvement", "reported improvement", "showed improvements",
                "reported improvements", "evidence suggesting", "evidence suggests",
                "significant benefit", "significant benefits", "provided significant benefit",
                "strong scientific evidence", "can reduce", "reduced symptoms", "improved symptoms",
                "support benefit", "supports benefit", "supporting efficacy",
                "evidence of benefit", "beneficial effects", "beneficial effect",
                "improved glycemic control", "improved clinical outcomes",
                "increased markedly", "good results",
                "therapeutic indications", "therapeutic indication",
                "prophylactic and restorative", "supporting mental and physical capacities",
            ))
            and any(token in n for token in (
                "efficacious", "effective", "reduction", "reduce", "improvement",
                "improv", "benefit", "efficacy", "therapeutic",
                "prophylactic", "restorative", "supporting",
            ))
        ):
            direction = DIRECTION_POSITIVE

    firm_uncertainty_phrases = (
        "evidence remains uncertain", "evidence is uncertain", "evidence was uncertain",
        "insufficient for firm conclusions", "insufficient to draw firm conclusions",
        "insufficient to draw conclusions", "cannot draw firm conclusions",
        "no firm conclusions",
    )
    cautionary_support_phrases = (
        "may be beneficial", "might be beneficial", "could be beneficial",
        "requires confirmation", "require confirmation", "needs confirmation",
        "need confirmation", "further high-quality trials", "further high quality trials",
        "further studies are needed", "further studies are required",
        "additional studies are needed", "additional studies are required",
        "more research is needed", "more research is required",
    )
    limitation_tier = _evidence_limitation_tier(n)

    # Active-comparator trials often report no between-group difference while
    # explicitly stating that both interventions were effective.  The latter is
    # a positive efficacy statement; it must not be flattened to a null merely
    # because the two active arms were similar to each other.
    if any(phrase in n for phrase in (
        "both effective", "both were effective", "both treatments were effective",
        "both interventions were effective", "both groups improved",
    )) and not any(phrase in n for phrase in (
        "no benefit", "no clinical benefit", "ineffective", "failed to improve",
    )):
        direction = DIRECTION_POSITIVE

    # Common synthesis wording that carries a usable direction even when the
    # calibrated phrase classifier is deliberately conservative.
    if direction == DIRECTION_UNCLEAR and (
        any(phrase in n for phrase in (
            "all included trials positive", "all trials positive",
            "positive outcomes", "beneficial findings", "potentially effective",
            "significantly improved", "significantly reduced",
            "significant improvement", "significant improvements",
            "significant reduction", "significant reductions",
        ))
        or ("significant" in n and any(token in n for token in ("reduction", "reduced", "improvement", "improved")))
    ):
        direction = DIRECTION_POSITIVE

    # Explicitly insufficient clinical-benefit conclusions are null for
    # decision purposes.  This is stronger than a routine limitations sentence.
    if limitation_tier == EvidenceLimitationTier.FIRM_UNCERTAINTY and any(phrase in n for phrase in (
        "evidence insufficient to establish", "evidence is insufficient to establish",
        "insufficient to establish clear clinical benefit",
        "insufficient to establish clinical benefit",
    )):
        direction = DIRECTION_NULL
    elif any(phrase in n for phrase in firm_uncertainty_phrases):
        direction = DIRECTION_NULL
    elif direction == DIRECTION_POSITIVE and (
        limitation_tier == EvidenceLimitationTier.CAUTION
        or any(phrase in n for phrase in (
            "evidence varied across studies", "results varied across studies",
            "findings varied across studies", "mixed findings", "mixed results",
            "inconsistent findings", "inconsistent results", *cautionary_support_phrases,
        ))
    ):
        direction = DIRECTION_MIXED

    # Endpoint-level split conclusions are mixed, not a hard null: e.g. one
    # glycaemic endpoint improves while another is non-significant.
    if direction in {DIRECTION_POSITIVE, DIRECTION_NULL, DIRECTION_UNCLEAR} and (
        any(x in n for x in ("beneficial", "improved", "reduced", "positive"))
        and any(x in n for x in ("not significant", "not statistically significant", "non-significant", "nonsignificant"))
    ):
        direction = DIRECTION_MIXED
    return direction


def resolve_scientific_evidence(records: Iterable[Mapping]) -> ScientificEvidenceResolution:
    """Resolve record-level indication evidence with conflict/freshness safeguards.

    The highest-ranked recognized indication tier still governs.  Two narrow
    safeguards prevent false certainty: (1) explicit controversy language in
    a governing source escalates rather than being flattened to GO, and (2) a
    directly relevant clinical study published after the newest governing
    review can challenge a supportive conclusion when its direction is null or
    negative.  This does not make lower-tier studies co-equal with reviews; it
    only prevents an older synthesis from pretending later contradictory data
    do not exist.
    """
    interpreted = []
    challengers = []
    for rec in records:
        source_type = str(rec.get("source_type") or "").strip().upper()
        text = str(rec.get("assertion_text") or rec.get("text") or "")
        direction = _final_decision_direction(text)
        year = _parse_publication_year(rec)
        explicit_conflict = _explicit_conflict_language(text)
        limitation_tier = _evidence_limitation_tier(text)
        rank = _INDICATION_SOURCE_RANK.get(source_type)
        if rank is not None:
            interpreted.append((rank, source_type, direction, year, explicit_conflict, limitation_tier))
            continue
        study_design = str(rec.get("study_design") or "").strip().lower()
        if source_type in {"CLINICAL_TRIAL", "RANDOMIZED_CONTROLLED_TRIAL", "RANDOMISED_CONTROLLED_TRIAL", "RCT"} or any(
            token in study_design for token in ("clinical trial", "randomized", "randomised", "rct")
        ):
            challengers.append((source_type or "CLINICAL_TRIAL", direction, year))

    if not interpreted:
        direct_directions = {x[1] for x in challengers}
        if DIRECTION_POSITIVE in direct_directions and not (direct_directions & {DIRECTION_NEGATIVE, DIRECTION_NULL}):
            return ScientificEvidenceResolution(
                ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION,
                "Supportive direct clinical evidence is available, but no higher-tier synthesis/monograph governs the indication; a cautious GO is warranted rather than full certainty.",
                tuple(sorted({x[0] for x in challengers})),
                tuple(sorted(direct_directions)),
            )
        if DIRECTION_POSITIVE in direct_directions and (direct_directions & {DIRECTION_NEGATIVE, DIRECTION_NULL}):
            return ScientificEvidenceResolution(
                ScientificEvidenceSignal.CONFLICT,
                "Direct clinical evidence contains opposing efficacy directions and no higher-tier synthesis resolves the conflict.",
                tuple(sorted({x[0] for x in challengers})),
                tuple(sorted(direct_directions)),
            )
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.UNRESOLVED,
            "No recognized indication-evidence source tier was available for record-level resolution.",
        )

    best_rank = min(x[0] for x in interpreted)
    top = [x for x in interpreted if x[0] == best_rank]
    directions = tuple(sorted({x[2] for x in top}))
    source_types = tuple(sorted({x[1] for x in top}))
    ds = set(directions)

    if any(x[4] for x in top):
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.CONFLICT,
            "A governing indication source explicitly characterizes the evidence as debated, conflicting, inconclusive, or not definitive; automatic GO is prohibited.",
            source_types, directions,
        )

    if DIRECTION_POSITIVE in ds and bool(ds & {DIRECTION_NEGATIVE, DIRECTION_NULL}):
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.CONFLICT,
            "Equally ranked governing indication sources contain opposing efficacy directions; automatic averaging is prohibited.",
            source_types, directions,
        )
    # Equally ranked positive + unresolved evidence is not the same as clean
    # confirmation.  Preserve the unresolved component as decision uncertainty.
    if DIRECTION_POSITIVE in ds and DIRECTION_UNCLEAR in ds:
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION,
            "Equally ranked governing evidence contains a positive direction plus an unresolved/uncertain component; unconditional GO would overstate certainty.",
            source_types, directions,
        )

    if DIRECTION_MIXED in ds:
        non_mixed = ds - {DIRECTION_MIXED, DIRECTION_UNCLEAR}
        if non_mixed & {DIRECTION_NEGATIVE, DIRECTION_NULL}:
            # A mixed synthesis already encodes endpoint/study variability.  A
            # second positive or null component within the same top tier is not
            # automatically a hard contradiction unless a source is explicitly
            # conflict/firm-insufficiency language (handled above/below).
            if DIRECTION_POSITIVE not in non_mixed:
                return ScientificEvidenceResolution(
                    ScientificEvidenceSignal.CONFLICT,
                    "Governing indication evidence is mixed and is accompanied by an equally ranked negative/null direction; expert review is required.",
                    source_types, directions,
                )
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION,
            "The governing indication-evidence tier is supportive but explicitly mixed/inconsistent or limitation-qualified; a cautious GO is warranted.",
            source_types, directions,
        )

    # A governing synthesis may be too cautious to claim efficacy on its own,
    # yet a lower-tier direct trial can provide supportive corroboration.  That
    # combination warrants caution rather than either a full GO or a hard
    # insufficiency decision.
    if ds <= {DIRECTION_UNCLEAR} and any(
        x[5] in {EvidenceLimitationTier.CAUTION, EvidenceLimitationTier.FIRM_UNCERTAINTY}
        for x in top
    ):
        supportive_challengers = [
            x for x in challengers if x[1] in {DIRECTION_POSITIVE, DIRECTION_MIXED}
        ]
        if supportive_challengers:
            challenger_types = tuple(sorted({x[0] for x in supportive_challengers}))
            return ScientificEvidenceResolution(
                ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION,
                "The governing synthesis is limitation-qualified while direct clinical evidence is supportive; a cautious GO is warranted rather than full certainty.",
                tuple(sorted(set(source_types) | set(challenger_types))),
                tuple(sorted(set(directions) | {x[1] for x in supportive_challengers})),
            )

    if DIRECTION_POSITIVE in ds:
        # A positive governing synthesis is not equivalent to high-certainty
        # evidence.  If any equally ranked governing source explicitly carries
        # a caution-level limitation (heterogeneity, risk of bias, small/limited
        # studies, need for confirmation, etc.), preserve that uncertainty in
        # the decision rather than flattening the tier to unconditional support.
        if any(x[5] == EvidenceLimitationTier.CAUTION for x in top):
            return ScientificEvidenceResolution(
                ScientificEvidenceSignal.SUPPORTIVE_WITH_CAUTION,
                "The governing indication-evidence tier is positive but at least one equally ranked source explicitly reports material certainty limitations; a cautious GO is warranted.",
                source_types, directions,
            )
        if any(x[5] == EvidenceLimitationTier.FIRM_UNCERTAINTY for x in top):
            return ScientificEvidenceResolution(
                ScientificEvidenceSignal.CONFLICT,
                "The governing indication-evidence tier contains a positive direction but also firm uncertainty language; automatic GO is not justified.",
                source_types, directions,
            )
        top_years = [x[3] for x in top if x[3] is not None]
        newest_top_year = max(top_years) if top_years else None
        if newest_top_year is not None:
            newer_contradictions = [
                (stype, direction, year) for stype, direction, year in challengers
                if year is not None and year > newest_top_year
                and direction in {DIRECTION_NEGATIVE, DIRECTION_NULL}
            ]
            if newer_contradictions:
                challenger_types = tuple(sorted({x[0] for x in newer_contradictions}))
                return ScientificEvidenceResolution(
                    ScientificEvidenceSignal.CONFLICT,
                    "A directly relevant clinical study published after the newest governing review reports a null/negative direction; the older synthesis is no longer sufficient for an automatic GO and expert review is required.",
                    tuple(sorted(set(source_types) | set(challenger_types))),
                    tuple(sorted(set(directions) | {x[1] for x in newer_contradictions})),
                )
        return ScientificEvidenceResolution(
            ScientificEvidenceSignal.SUPPORTIVE,
            "The governing indication-evidence tier contains a supportive efficacy direction without an equally ranked or newer direct contradiction.",
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
    if eligibility.status == EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS:
        return FinalDecision(FinalDecisionStatus.GO_WITH_CAUTION, eligibility.gate_reason)
    if scientific.signal in {
        ScientificEvidenceSignal.INSUFFICIENT,
        ScientificEvidenceSignal.UNRESOLVED,
    }:
        return FinalDecision(FinalDecisionStatus.INSUFFICIENT_EVIDENCE, scientific.reason)
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
