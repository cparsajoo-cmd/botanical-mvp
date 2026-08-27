"""Pharmaceutical-grade-oriented structured safety assertion layer.

This module converts evidence-record text into structured safety assertions.
Lexical matching is used only for extraction; gate decisions consume the
structured assertion objects, never raw keywords directly.

Design invariants:
- plant/case/PMID/document agnostic;
- negation/reassurance aware at sentence-unit level;
- explicit contraindication is SERIOUS even when no recognized interacting
  drug class is named (the previous false-negative gap);
- mechanism-only CYP/P-gp mentions do not become serious by themselves;
- positive and reassuring assertions are both retained so conflict can be
  surfaced rather than overwritten;
- source authority affects confidence, not the semantic severity asserted by
  the source; low-authority serious evidence can therefore trigger review but
  cannot silently become "safe".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, FrozenSet, Iterable, Tuple

from assertion_vocabulary import AssertionType, SeverityLevel
from interaction_severity_classifier import (
    classify_interaction_assertion,
    InteractionSeverityTier,
)

SAFETY_ASSERTION_ENGINE_VERSION = "1.0.0"
SAFETY_SEVERITY_RULE_VERSION = "pharma-safety-severity-v1"


class SafetyAssertionType(str, Enum):
    CONTRAINDICATION = "contraindication"
    SERIOUS_DRUG_INTERACTION = "serious_drug_interaction"
    MODERATE_INTERACTION = "moderate_interaction"
    PRECAUTION = "precaution"
    WARNING = "warning"
    PREGNANCY = "pregnancy"
    LACTATION = "lactation"
    PEDIATRIC_RESTRICTION = "pediatric_restriction"
    HEPATIC_IMPAIRMENT = "hepatic_impairment"
    RENAL_IMPAIRMENT = "renal_impairment"
    QT_PROLONGATION = "qt_prolongation"
    BLEEDING_RISK = "bleeding_risk"
    CYP_INDUCTION = "cyp_induction"
    CYP_INHIBITION = "cyp_inhibition"
    PGP_INTERACTION = "p_gp_interaction"
    ORGAN_TOXICITY = "organ_toxicity"
    PHOTOSENSITIVITY = "photosensitivity"
    ALLERGIC_RISK = "allergic_risk"
    NARROW_THERAPEUTIC_INDEX_INTERACTION = "narrow_therapeutic_index_interaction"
    GERIATRIC_RESTRICTION = "geriatric_restriction"
    HYPERTENSION = "hypertension"
    HYPOTENSION = "hypotension"
    DIABETES_INTERACTION = "diabetes_interaction"
    CNS_DEPRESSION = "cns_depression"
    SEROTONERGIC_TOXICITY = "serotonergic_toxicity"
    CARCINOGENICITY = "carcinogenicity"
    GENOTOXICITY = "genotoxicity"
    REPRODUCTIVE_TOXICITY = "reproductive_toxicity"
    MAJOR_REGULATORY_SAFETY_WARNING = "major_regulatory_safety_warning"
    SERIOUS_ADVERSE_EVENT = "serious_adverse_event"
    FATAL_ADVERSE_EVENT = "fatal_adverse_event"
    REASSURANCE = "reassurance"


class AssertionPolarity(str, Enum):
    RISK_PRESENT = "risk_present"
    RISK_ABSENT = "risk_absent"
    CONDITIONAL = "conditional"
    MECHANISTIC_ONLY = "mechanistic_only"


class SafetyConfidence(str, Enum):
    HIGH = "High"
    MODERATE = "Moderate"
    LOW = "Low"
    INSUFFICIENT = "Insufficient"


@dataclass(frozen=True)
class SafetyAssertion:
    assertion_type: SafetyAssertionType
    severity: SeverityLevel
    polarity: AssertionPolarity
    evidence_strength: SafetyConfidence
    applicability: str = "unknown"
    affected_population: Tuple[str, ...] = ()
    affected_drug_classes: Tuple[str, ...] = ()
    preparation: str = ""
    dose_dependency: str = "unknown"
    route: str = ""
    authority: str = "Unknown Source"
    authority_score: float = 0.5
    evidence_record_id: str = ""
    source_url: str = ""
    source_sentence: str = ""
    matched_language: str = ""
    severity_rule: str = SAFETY_SEVERITY_RULE_VERSION
    classifier_version: str = SAFETY_ASSERTION_ENGINE_VERSION
    reason: str = ""
    # Model certainty is deliberately separate from source/evidence strength.
    semantic_extraction_confidence: float | None = None
    provenance: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["assertion_type"] = self.assertion_type.value
        out["severity"] = self.severity.value
        out["polarity"] = self.polarity.value
        out["evidence_strength"] = self.evidence_strength.value
        return out


_UNIT_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+|\n+")


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _units(text: Any) -> Tuple[str, ...]:
    raw = str(text or "").strip()
    if not raw:
        return ()
    parts = tuple(x.strip() for x in _UNIT_SPLIT_RE.split(raw) if x.strip())
    return parts or (raw,)


def _has(text: str, patterns: Iterable[str]) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            return m.group(0)
    return ""


def _authority_confidence(score: float, explicitness: str) -> SafetyConfidence:
    # Authority controls confidence, not semantic severity. Explicit source
    # language can keep confidence moderate even for an unknown source, while
    # weak/mechanistic extraction never receives High confidence.
    if explicitness == "mechanistic":
        return SafetyConfidence.LOW if score >= 0.5 else SafetyConfidence.INSUFFICIENT
    if score >= 0.90:
        return SafetyConfidence.HIGH
    if score >= 0.60:
        return SafetyConfidence.MODERATE
    if score >= 0.35:
        return SafetyConfidence.LOW
    return SafetyConfidence.INSUFFICIENT


_CONTRA = (
    r"\bcontraindicat(?:ed|ion|ions)\b",
    r"\bmust not be (?:used|taken|administered|co-?administered|combined)\b",
    r"\bshould not be (?:used|taken|administered|co-?administered|combined)\b",
)
_REASSURANCE = (
    r"\bno (?:known |clinically relevant |significant )?(?:contraindication|interaction|safety concern|safety signal)s?\b",
    r"\bnot contraindicated\b",
    r"\bno increased risk\b",
    r"\bdid not (?:increase|prolong|affect)\b.{0,45}\b(?:bleeding|qt|liver|renal|kidney|interaction)\b",
    r"\bgenerally (?:considered )?safe\b",
    r"\bwell tolerated\b",
)
_PRECAUTION = (
    r"\buse with caution\b", r"\bcaution (?:is )?(?:advised|recommended|required)\b",
    r"\bmonitor(?:ing)? (?:is )?(?:recommended|advised|required)\b",
)
_WARNING = (r"\bwarning\b", r"\bshould be avoided\b", r"\bnot recommended\b")
_POPULATION = {
    SafetyAssertionType.PREGNANCY: (r"\bpregnan(?:cy|t)\b", r"\bgestation\b"),
    SafetyAssertionType.LACTATION: (r"\blactat(?:ion|ing)\b", r"\bbreast[- ]?feed(?:ing)?\b"),
    SafetyAssertionType.PEDIATRIC_RESTRICTION: (r"\bpa?ediatric\b", r"\bchildren\b", r"\binfants?\b"),
    SafetyAssertionType.HEPATIC_IMPAIRMENT: (r"\bhepatic impairment\b", r"\bliver disease\b"),
    SafetyAssertionType.RENAL_IMPAIRMENT: (r"\brenal impairment\b", r"\bkidney disease\b"),
    SafetyAssertionType.GERIATRIC_RESTRICTION: (r"\bgeriatric\b", r"\belderly\b", r"\bolder adults?\b"),
}
_RISK_PATTERNS = {
    SafetyAssertionType.QT_PROLONGATION: (r"\b(?:prolong(?:s|ed|ation)?|increase(?:s|d)?)\b.{0,35}\bqt(?:c)?\b", r"\btorsades de pointes\b"),
    SafetyAssertionType.BLEEDING_RISK: (r"\b(?:increase(?:s|d)?|elevat(?:e|es|ed))\b.{0,35}\bbleeding risk\b", r"\bhemorrhag(?:e|ic)\b"),
    SafetyAssertionType.PHOTOSENSITIVITY: (r"\bphotosensiti(?:vity|sation|zation)\b", r"\bphototoxic(?:ity)?\b"),
    SafetyAssertionType.ALLERGIC_RISK: (r"\banaphylaxis\b", r"\bsevere allergic reaction\b", r"\bhypersensitivity reaction\b"),
}
# Root-cause fix (Reference-Grounded Validation v1, Problem B): the
# causal-anchor pattern only matched the SINGULAR "liver injury"/"renal
# injury" (the same plural-form bug class fixed elsewhere via
# scientific_phrase_matcher — this module intentionally stays
# standard-library/dependency-light, so the fix is applied locally as an
# explicit (?:y|ies) alternation rather than importing that module) and
# used a narrow 55-character window, which real prose regularly exceeds
# when a causal verb is followed by a list of qualifiers before the
# organ-toxicity noun ("has caused multiple clinically apparent
# hepatocellular liver injuries..."). The window is widened and the
# plural form added; the standalone (no-causal-verb-required) tuple
# below is separately widened with additional organ/systemic-failure
# outcome nouns that are inherently harm outcomes regardless of which
# verb introduces them (see the module docstring's list-of-symptoms
# case: "...can cause seizures, coma, ..., acute hepatic necrosis,
# multiorgan failure and death" puts the causal verb far from several of
# its listed consequences).
# Root-cause fix (2026-08-10, RGV v2 regression against rgv2_018_datura_oral
# and rgv2_020_belladonna_oral): two further gaps in the same family as the
# fix above, found by testing the real failing evidence text directly
# against this regex, not by guessing.
#   1. Missing verb: "Belladonna poisoning can PRODUCE severe
#      neurotoxicity..." -- "produce(s|d)" was absent from the causal-verb
#      alternation, so a real, direct causal claim using that verb never
#      reached the (already-present) "neurotoxicity" noun.
#   2. Missing noun: "...can result in severe ANTICHOLINERGIC TOXICITY
#      with hallucinations, tachycardia, confusion..." -- the noun list
#      only covered organ-specific toxicity terms (hepato-/nephro-/cardio-/
#      neuro-), not toxicity syndromes named after their mechanism instead
#      of an organ (anticholinergic toxicity/syndrome is a well-established
#      serious poisoning syndrome, not a novel category).
#   Also added "seizures" and "coma" to the standalone (no-verb-required)
#   tuple below, since both are commonly listed as bare outcome nouns in an
#   enumeration ("...toxicity including seizures, coma and...") with no
#   single nearby causal verb governing them, the same structural pattern
#   already documented for "multiorgan failure"/"death" above.
_ORGAN_TOXICITY = (
    r"\b(?:caus(?:e|es|ed)|induc(?:e|es|ed)|produc(?:e|es|ed)|associated with|risk of|result(?:s|ed)? in|linked to)\b.{0,80}\b(?:hepatotoxicity|liver injur(?:y|ies)|nephrotoxicity|renal injur(?:y|ies)|cardiotoxicity|neurotoxicity|anticholinergic toxicity|anticholinergic syndrome)\b",
    r"\b(?:hepatotoxic|nephrotoxic|cardiotoxic|neurotoxic|hepatocellular liver injur(?:y|ies)|acute hepatic necrosis|hepatic necrosis|multiorgan failure|multi-organ failure|cardiovascular collapse|hepatic failure|renal failure|respiratory failure|status epilepticus|seizures|coma|anticholinergic toxicity|anticholinergic syndrome)\b",
)
_PROTECTIVE_CONTEXT = (
    r"\bprotect(?:s|ed|ive|ion)? against\b", r"\bprevent(?:s|ed|ion)?\b.{0,30}\b(?:toxicity|injury)\b",
    r"\battenuat(?:e|es|ed)\b.{0,30}\b(?:toxicity|injury)\b",
)
_MECHANISM = {
    SafetyAssertionType.CYP_INDUCTION: (r"\b(?:induces?|induction of)\b.{0,25}\bcyp\w+\b", r"\bcyp\w+\b.{0,25}\binduc(?:er|tion|es)\b"),
    SafetyAssertionType.CYP_INHIBITION: (r"\b(?:inhibits?|inhibition of)\b.{0,25}\bcyp\w+\b", r"\bcyp\w+\b.{0,25}\binhibit(?:or|ion|s)\b"),
    SafetyAssertionType.PGP_INTERACTION: (r"\bp[- ]?glycoprotein\b", r"\bp[- ]?gp\b"),
}
_NTI = (r"\bnarrow therapeutic (?:index|window)\b", r"\btherapeutic drug monitoring\b")

_DIRECT_SERIOUS_RISKS = {
    SafetyAssertionType.CARCINOGENICITY: (r"\b(?:carcinogenic(?:ity)?|causes? cancer|tumou?rigenic)\b",),
    SafetyAssertionType.GENOTOXICITY: (r"\b(?:genotoxic(?:ity)?|mutagenic(?:ity)?|chromosomal damage|dna damage)\b",),
    SafetyAssertionType.REPRODUCTIVE_TOXICITY: (r"\b(?:reproductive toxicity|embryotoxic(?:ity)?|fetotoxic(?:ity)?|teratogenic(?:ity)?)\b",),
    SafetyAssertionType.SEROTONERGIC_TOXICITY: (r"\b(?:serotonin syndrome|serotonergic toxicity)\b",),
    SafetyAssertionType.CNS_DEPRESSION: (r"\b(?:severe |profound )?(?:cns|central nervous system) depression\b",),
    SafetyAssertionType.HYPERTENSION: (r"\b(?:severe |marked |dangerous )?hypertension\b", r"\bhypertensive crisis\b"),
    SafetyAssertionType.HYPOTENSION: (r"\b(?:severe |marked |dangerous )?hypotension\b",),
    SafetyAssertionType.DIABETES_INTERACTION: (r"\b(?:antidiabetic|hypoglyc(?:a|e)mic)\b.{0,60}\b(?:interaction|potentiat|severe hypoglyc(?:a|e)mia)\b", r"\bsevere hypoglyc(?:a|e)mia\b"),
}
# Root-cause fix (Reference-Grounded Validation v1, Problem B): "have
# been reported" is the standard, plant-agnostic clinical-literature way
# of reporting an observed fatality ("fatalities have been reported"),
# distinct from and just as common as the explicit "death(s) caused
# by/associated with" wording already covered — neither was previously
# recognized. The causal-anchor pattern is also widened (50 -> 90 chars)
# and its verb made tense-flexible (caus(?:e|es|ed), not only "caused")
# so a list of consequences between the causal verb and "death" (as in
# "can cause seizures, coma, ..., multiorgan failure and death") is
# still captured.
_FATAL_AE = (
    r"\bfatal adverse events?\b",
    r"\bfatalit(?:y|ies)\b.{0,40}\b(?:reported|observed|documented|occurred)\b",
    r"\b(?:reported|observed|documented)\b.{0,40}\bfatalit(?:y|ies)\b",
    r"\bdeath(?:s)?\b.{0,50}\b(?:associated with|reported after|due to|caused by)\b",
    r"\b(?:associated with|caus(?:e|es|ed)|result(?:s|ed)? in)\b.{0,90}\bdeath(?:s)?\b",
)
_SERIOUS_AE = (
    r"\bserious adverse events?\b",
    r"\badverse events?\b.{0,50}\b(?:hospitali[sz]ation|life[- ]threatening|disability)\b",
    # Generic ICH-style seriousness/outcome language. These patterns are
    # deliberately consequence-based rather than botanical- or case-specific,
    # so severe harm can be recognized even when the prose never says the
    # literal words "adverse event" or "toxicity".
    r"\blife[- ]threatening\b.{0,60}\b(?:event|reaction|condition|hospitali[sz]ation|intervention)\b",
    r"\b(?:requires?|required|requiring)\b.{0,35}\b(?:hospitali[sz]ation|emergency (?:surgery|intervention)|intensive care)\b",
    r"\b(?:permanent|persistent|irreversible)\b.{0,35}\b(?:disability|impairment|blindness|vision loss|hearing loss|neurologic deficit)\b",
)
_REGULATORY_MAJOR = (r"\b(?:boxed|black box) warning\b", r"\b(?:fda|ema|mhra|tga|health canada)\b.{0,50}\b(?:safety warning|safety communication|serious risk)\b")


def _affected_populations(unit_norm: str) -> Tuple[str, ...]:
    out = []
    for kind, patterns in _POPULATION.items():
        if _has(unit_norm, patterns):
            out.append(kind.value)
    return tuple(out)


def _mk(*, kind: SafetyAssertionType, severity: SeverityLevel, polarity: AssertionPolarity,
        unit: str, matched: str, authority: str, authority_score: float,
        evidence_record_id: str, source_url: str, preparation: str, dose_dependency: str,
        route: str, affected_population: Tuple[str, ...] = (), drug_classes: Tuple[str, ...] = (),
        explicitness: str = "explicit", reason: str = "") -> SafetyAssertion:
    return SafetyAssertion(
        assertion_type=kind,
        severity=severity,
        polarity=polarity,
        evidence_strength=_authority_confidence(authority_score, explicitness),
        affected_population=affected_population,
        affected_drug_classes=drug_classes,
        preparation=preparation,
        dose_dependency=dose_dependency,
        route=route,
        authority=authority or "Unknown Source",
        authority_score=float(authority_score if authority_score is not None else 0.5),
        evidence_record_id=evidence_record_id or "",
        source_url=source_url or "",
        source_sentence=unit.strip(),
        matched_language=matched,
        reason=reason,
    )


def classify_safety_assertions(
    text: Any,
    *,
    evidence_record_id: str = "",
    authority: str = "Unknown Source",
    authority_score: float = 0.5,
    source_url: str = "",
    preparation: str = "",
    dose_dependency: str = "unknown",
    route: str = "",
    affected_population: Tuple[str, ...] = (),
) -> Tuple[SafetyAssertion, ...]:
    """Return all meaningful structured safety assertions in one record.

    Multiple assertions are intentionally retained; callers must not reduce a
    record to one winner because that would erase evidence conflict.
    """
    assertions: list[SafetyAssertion] = []
    for unit in _units(text):
        n = _norm(unit)
        populations = tuple(dict.fromkeys(tuple(affected_population) + _affected_populations(n)))

        reassurance = _has(n, _REASSURANCE)
        if reassurance:
            assertions.append(_mk(
                kind=SafetyAssertionType.REASSURANCE, severity=SeverityLevel.NONE,
                polarity=AssertionPolarity.RISK_ABSENT, unit=unit, matched=reassurance,
                authority=authority, authority_score=authority_score,
                evidence_record_id=evidence_record_id, source_url=source_url,
                preparation=preparation, dose_dependency=dose_dependency, route=route,
                affected_population=populations, reason="Explicit reassurance/absence-of-risk assertion retained for conflict analysis.",
            ))
            # An explicit reassurance sentence must not also be interpreted as
            # positive risk merely because it contains the hazard noun.
            continue

        contraindication = _has(n, _CONTRA)
        if contraindication:
            assertions.append(_mk(
                kind=SafetyAssertionType.CONTRAINDICATION, severity=SeverityLevel.SERIOUS,
                polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=contraindication,
                authority=authority, authority_score=authority_score,
                evidence_record_id=evidence_record_id, source_url=source_url,
                preparation=preparation, dose_dependency=dose_dependency, route=route,
                affected_population=populations,
                reason="Explicit contraindication language is a serious safety assertion; no drug-class whitelist is required.",
            ))
            for p in populations:
                kind = SafetyAssertionType(p)
                assertions.append(_mk(
                    kind=kind, severity=SeverityLevel.SERIOUS,
                    polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=contraindication,
                    authority=authority, authority_score=authority_score,
                    evidence_record_id=evidence_record_id, source_url=source_url,
                    preparation=preparation, dose_dependency=dose_dependency, route=route,
                    affected_population=populations,
                    reason=f"Explicit contraindication applies to affected population: {p}.",
                ))

        interaction = classify_interaction_assertion(unit)
        drug_classes = tuple(sorted(x.value for x in interaction.drug_classes))
        if interaction.tier in {InteractionSeverityTier.SERIOUS_CONTRAINDICATION, InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION}:
            kind = SafetyAssertionType.NARROW_THERAPEUTIC_INDEX_INTERACTION if _has(n, _NTI) else SafetyAssertionType.SERIOUS_DRUG_INTERACTION
            assertions.append(_mk(
                kind=kind, severity=SeverityLevel.SERIOUS, polarity=AssertionPolarity.RISK_PRESENT,
                unit=unit, matched=interaction.matched_language,
                authority=authority, authority_score=authority_score,
                evidence_record_id=evidence_record_id, source_url=source_url,
                preparation=preparation, dose_dependency=dose_dependency, route=route,
                affected_population=populations, drug_classes=drug_classes,
                reason=interaction.reason,
            ))
        elif interaction.tier == InteractionSeverityTier.MODERATE_INTERACTION and not contraindication:
            assertions.append(_mk(
                kind=SafetyAssertionType.MODERATE_INTERACTION, severity=SeverityLevel.MODERATE,
                polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=interaction.matched_language,
                authority=authority, authority_score=authority_score,
                evidence_record_id=evidence_record_id, source_url=source_url,
                preparation=preparation, dose_dependency=dose_dependency, route=route,
                affected_population=populations, drug_classes=drug_classes,
                reason=interaction.reason,
            ))

        precaution = _has(n, _PRECAUTION)
        warning = _has(n, _WARNING)
        if precaution:
            assertions.append(_mk(
                kind=SafetyAssertionType.PRECAUTION, severity=SeverityLevel.MINOR,
                polarity=AssertionPolarity.CONDITIONAL, unit=unit, matched=precaution,
                authority=authority, authority_score=authority_score,
                evidence_record_id=evidence_record_id, source_url=source_url,
                preparation=preparation, dose_dependency=dose_dependency, route=route,
                affected_population=populations, reason="Precaution/monitoring language.",
            ))
        if warning and not contraindication:
            assertions.append(_mk(
                kind=SafetyAssertionType.WARNING, severity=SeverityLevel.MODERATE,
                polarity=AssertionPolarity.CONDITIONAL, unit=unit, matched=warning,
                authority=authority, authority_score=authority_score,
                evidence_record_id=evidence_record_id, source_url=source_url,
                preparation=preparation, dose_dependency=dose_dependency, route=route,
                affected_population=populations, reason="Explicit warning/avoidance language without formal contraindication.",
            ))

        for kind, patterns in _RISK_PATTERNS.items():
            hit = _has(n, patterns)
            if hit:
                sev = SeverityLevel.SERIOUS if kind in {SafetyAssertionType.QT_PROLONGATION, SafetyAssertionType.BLEEDING_RISK} and ("torsades" in n or "hemorrhag" in n or "severe" in n) else SeverityLevel.MODERATE
                assertions.append(_mk(
                    kind=kind, severity=sev, polarity=AssertionPolarity.RISK_PRESENT,
                    unit=unit, matched=hit, authority=authority, authority_score=authority_score,
                    evidence_record_id=evidence_record_id, source_url=source_url,
                    preparation=preparation, dose_dependency=dose_dependency, route=route,
                    affected_population=populations, reason=f"Direct {kind.value} safety assertion.",
                ))

        # High-consequence safety outcomes use explicit causal/diagnostic
        # language. These are intentionally plant-agnostic and conservative.
        fatal_hit = _has(n, _FATAL_AE)
        serious_ae_hit = _has(n, _SERIOUS_AE)
        regulatory_hit = _has(n, _REGULATORY_MAJOR)
        if fatal_hit:
            assertions.append(_mk(kind=SafetyAssertionType.FATAL_ADVERSE_EVENT, severity=SeverityLevel.SERIOUS, polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=fatal_hit, authority=authority, authority_score=authority_score, evidence_record_id=evidence_record_id, source_url=source_url, preparation=preparation, dose_dependency=dose_dependency, route=route, affected_population=populations, reason="Fatal adverse-event/death safety assertion."))
        if serious_ae_hit:
            assertions.append(_mk(kind=SafetyAssertionType.SERIOUS_ADVERSE_EVENT, severity=SeverityLevel.SERIOUS, polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=serious_ae_hit, authority=authority, authority_score=authority_score, evidence_record_id=evidence_record_id, source_url=source_url, preparation=preparation, dose_dependency=dose_dependency, route=route, affected_population=populations, reason="Serious adverse-event safety assertion."))
        if regulatory_hit:
            assertions.append(_mk(kind=SafetyAssertionType.MAJOR_REGULATORY_SAFETY_WARNING, severity=SeverityLevel.SERIOUS, polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=regulatory_hit, authority=authority, authority_score=authority_score, evidence_record_id=evidence_record_id, source_url=source_url, preparation=preparation, dose_dependency=dose_dependency, route=route, affected_population=populations, reason="Major regulator/boxed safety warning."))
        if not _has(n, _PROTECTIVE_CONTEXT):
            for kind, patterns in _DIRECT_SERIOUS_RISKS.items():
                hit = _has(n, patterns)
                if hit:
                    # CNS depression / hypertension / hypotension are serious
                    # only when severe/marked/crisis language is present.
                    if kind in {SafetyAssertionType.CNS_DEPRESSION, SafetyAssertionType.HYPERTENSION, SafetyAssertionType.HYPOTENSION} and not re.search(r"\b(?:severe|profound|marked|dangerous|crisis)\b", n):
                        sev = SeverityLevel.MODERATE
                    else:
                        sev = SeverityLevel.SERIOUS
                    assertions.append(_mk(kind=kind, severity=sev, polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=hit, authority=authority, authority_score=authority_score, evidence_record_id=evidence_record_id, source_url=source_url, preparation=preparation, dose_dependency=dose_dependency, route=route, affected_population=populations, reason=f"Direct {kind.value} safety assertion."))

        if not _has(n, _PROTECTIVE_CONTEXT):
            tox = _has(n, _ORGAN_TOXICITY)
            if tox:
                assertions.append(_mk(
                    kind=SafetyAssertionType.ORGAN_TOXICITY, severity=SeverityLevel.SERIOUS,
                    polarity=AssertionPolarity.RISK_PRESENT, unit=unit, matched=tox,
                    authority=authority, authority_score=authority_score,
                    evidence_record_id=evidence_record_id, source_url=source_url,
                    preparation=preparation, dose_dependency=dose_dependency, route=route,
                    affected_population=populations, reason="Causal/direct organ-toxicity assertion; protective-context sentences are excluded.",
                ))

        # Population restriction without a formal contraindication remains
        # visible as a moderate restriction/warning, not a hard-stop guess.
        if populations and not contraindication and (warning or precaution):
            for p in populations:
                assertions.append(_mk(
                    kind=SafetyAssertionType(p), severity=SeverityLevel.MODERATE,
                    polarity=AssertionPolarity.CONDITIONAL, unit=unit, matched=warning or precaution,
                    authority=authority, authority_score=authority_score,
                    evidence_record_id=evidence_record_id, source_url=source_url,
                    preparation=preparation, dose_dependency=dose_dependency, route=route,
                    affected_population=populations, reason=f"Population-specific restriction/precaution: {p}.",
                ))

        # Mechanism-only signals are structured but explicitly non-blocking.
        for kind, patterns in _MECHANISM.items():
            hit = _has(n, patterns)
            if hit and interaction.tier not in {InteractionSeverityTier.SERIOUS_CONTRAINDICATION, InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION}:
                assertions.append(_mk(
                    kind=kind, severity=SeverityLevel.NONE,
                    polarity=AssertionPolarity.MECHANISTIC_ONLY, unit=unit, matched=hit,
                    authority=authority, authority_score=authority_score,
                    evidence_record_id=evidence_record_id, source_url=source_url,
                    preparation=preparation, dose_dependency=dose_dependency, route=route,
                    affected_population=populations, explicitness="mechanistic",
                    reason="Mechanism/transporter signal only; not upgraded to clinical severity without an asserted risk relationship.",
                ))

    # Stable de-duplication while preserving distinct evidence records/sentences.
    seen = set(); out = []
    for a in assertions:
        key = (a.assertion_type, a.severity, a.polarity, a.evidence_record_id, a.source_sentence, a.matched_language)
        if key not in seen:
            seen.add(key); out.append(a)
    return tuple(out)


# ---------------------------------------------------------------------
# Part 9 (this session) -- structured, candidate-level safety STATUS
# output. Reuses this module's own SafetyAssertion/AssertionPolarity
# vocabulary and summarize_safety_assertions() above; adds no new
# extraction logic and no new safety facts. Deliberately coarse and
# explicit about missing data: "no adverse events reported in one
# study" is STUDY_SPECIFIC_REASSURANCE_ONLY, never a general safety
# claim, and an empty assertion set is NO_SAFETY_EVIDENCE_RETRIEVED
# (not "safe").
#
# NAMING NOTE: the output key is "Safety_Assertion_Status", not the more
# obvious "Safety_Data_Status" -- indication_candidate_discovery.py
# already uses "Safety_Data_Status" for a DIFFERENT, pre-existing,
# lowercase snake_case vocabulary (not_assessed / source_excluded /
# adverse_signal_present / reassurance_reported / interaction_signal_
# present), produced by a different extraction path
# (safety_interaction_attribution.py) for the indication-centric
# discovery mode. That is a separate pipeline this change does not
# touch (Part 25: reuse, don't rewrite) -- reusing its exact column name
# for a structurally different vocabulary here would silently produce
# two incompatible value sets under one column name. "Safety_Assertion_
# Status" makes explicit which underlying mechanism (the structured
# SafetyAssertion objects) this status is derived from.
# ---------------------------------------------------------------------
SAFETY_STATUS_NO_EVIDENCE = "NO_SAFETY_EVIDENCE_RETRIEVED"
SAFETY_STATUS_REASSURANCE_ONLY = "STUDY_SPECIFIC_REASSURANCE_ONLY"
SAFETY_STATUS_CONCERN = "SAFETY_CONCERN_RETRIEVED"
SAFETY_STATUS_INTERACTION = "INTERACTION_SIGNAL_RETRIEVED"
SAFETY_STATUS_CONFLICTING = "CONFLICTING_SAFETY_EVIDENCE"
SAFETY_STATUS_INSUFFICIENT = "INSUFFICIENT_OR_UNKNOWN"

# Assertion types that are specifically INTERACTION signals (as opposed
# to a standalone safety concern like contraindication/organ toxicity/
# adverse event) -- kept as its own bucket because an interaction signal
# is actionable differently (co-administration risk) than a standalone
# concern.
_INTERACTION_ASSERTION_TYPES = frozenset({
    SafetyAssertionType.SERIOUS_DRUG_INTERACTION, SafetyAssertionType.MODERATE_INTERACTION,
    SafetyAssertionType.CYP_INDUCTION, SafetyAssertionType.CYP_INHIBITION,
    SafetyAssertionType.PGP_INTERACTION, SafetyAssertionType.NARROW_THERAPEUTIC_INDEX_INTERACTION,
})

_SEVERITY_RANK = {SeverityLevel.NONE: 0, SeverityLevel.MINOR: 1, SeverityLevel.MODERATE: 2, SeverityLevel.SERIOUS: 3}


def derive_structured_safety_status(assertions: Iterable[SafetyAssertion]) -> dict[str, Any]:
    """Returns {"Safety_Assertion_Status", "Safety_Concern_Level",
    "Safety_Evidence_IDs", "Safety_Rationale"} for one candidate, derived
    ONLY from the structured assertions already extracted upstream by
    classify_safety_assertions() -- never a new keyword scan, never an
    AI guess. Hard safety/regulatory gates (eligibility_gate.py) remain
    authoritative for any GO/NO-GO decision; this is a REPORTING layer
    on top of the same underlying assertions, not a second gate.
    """
    items = tuple(assertions or ())
    evidence_ids = tuple(dict.fromkeys(a.evidence_record_id for a in items if a.evidence_record_id))

    if not items:
        return {
            "Safety_Assertion_Status": SAFETY_STATUS_NO_EVIDENCE,
            "Safety_Concern_Level": "UNKNOWN",
            "Safety_Evidence_IDs": (),
            "Safety_Rationale": "No safety-relevant evidence was retrieved for this candidate.",
        }

    risks = tuple(a for a in items if a.polarity == AssertionPolarity.RISK_PRESENT)
    reassurances = tuple(a for a in items if a.polarity == AssertionPolarity.RISK_ABSENT)
    concern_level = (
        max((a.severity for a in risks), key=lambda s: _SEVERITY_RANK.get(s, 0)).value
        if risks else ("NONE" if reassurances else "UNKNOWN")
    )

    if risks and reassurances:
        return {
            "Safety_Assertion_Status": SAFETY_STATUS_CONFLICTING,
            "Safety_Concern_Level": concern_level,
            "Safety_Evidence_IDs": evidence_ids,
            "Safety_Rationale": (
                "Both risk-present and risk-absent safety assertions were retrieved for this "
                "candidate; this is an unresolved conflict, not evidence of safety."
            ),
        }
    if risks:
        if any(a.assertion_type in _INTERACTION_ASSERTION_TYPES for a in risks):
            return {
                "Safety_Assertion_Status": SAFETY_STATUS_INTERACTION,
                "Safety_Concern_Level": concern_level,
                "Safety_Evidence_IDs": evidence_ids,
                "Safety_Rationale": "An interaction-type safety signal (drug interaction / CYP / P-gp / narrow-therapeutic-index) was retrieved.",
            }
        return {
            "Safety_Assertion_Status": SAFETY_STATUS_CONCERN,
            "Safety_Concern_Level": concern_level,
            "Safety_Evidence_IDs": evidence_ids,
            "Safety_Rationale": "A safety concern (e.g. contraindication, adverse event, organ toxicity) was retrieved from the evidence.",
        }
    if reassurances:
        return {
            "Safety_Assertion_Status": SAFETY_STATUS_REASSURANCE_ONLY,
            "Safety_Concern_Level": concern_level,
            "Safety_Evidence_IDs": evidence_ids,
            "Safety_Rationale": (
                "Only study-specific reassurance (e.g. \"no adverse events reported\" in a "
                "specific study) was found. This does NOT establish general safety."
            ),
        }
    return {
        "Safety_Assertion_Status": SAFETY_STATUS_INSUFFICIENT,
        "Safety_Concern_Level": concern_level,
        "Safety_Evidence_IDs": evidence_ids,
        "Safety_Rationale": "Safety-relevant evidence exists but could not be classified as a concern or as reassurance.",
    }


def summarize_safety_assertions(assertions: Iterable[SafetyAssertion]) -> dict[str, Any]:
    items = tuple(assertions)
    risks = tuple(a for a in items if a.polarity == AssertionPolarity.RISK_PRESENT)
    reassurances = tuple(a for a in items if a.polarity == AssertionPolarity.RISK_ABSENT)
    serious = tuple(a for a in risks if a.severity == SeverityLevel.SERIOUS)
    conflict = bool(risks and reassurances)

    if not items:
        confidence = SafetyConfidence.INSUFFICIENT
    else:
        rank = {SafetyConfidence.INSUFFICIENT: 0, SafetyConfidence.LOW: 1, SafetyConfidence.MODERATE: 2, SafetyConfidence.HIGH: 3}
        relevant = serious or risks or items
        confidence = max((a.evidence_strength for a in relevant), key=lambda x: rank[x])

    return {
        "assertions": items,
        "serious_assertions": serious,
        "has_conflict": conflict,
        "confidence": confidence,
        "evidence_ids": tuple(dict.fromkeys(a.evidence_record_id for a in items if a.evidence_record_id)),
    }


def safety_assertion_from_dict(data: dict[str, Any]) -> SafetyAssertion:
    """Lossless reconstruction for row merge / persistence round-trips."""
    return SafetyAssertion(
        assertion_type=SafetyAssertionType(data["assertion_type"]),
        severity=SeverityLevel(data["severity"]),
        polarity=AssertionPolarity(data["polarity"]),
        evidence_strength=SafetyConfidence(data.get("evidence_strength", SafetyConfidence.INSUFFICIENT.value)),
        applicability=str(data.get("applicability", "unknown")),
        affected_population=tuple(data.get("affected_population") or ()),
        affected_drug_classes=tuple(data.get("affected_drug_classes") or ()),
        preparation=str(data.get("preparation") or ""),
        dose_dependency=str(data.get("dose_dependency") or "unknown"),
        route=str(data.get("route") or ""),
        authority=str(data.get("authority") or "Unknown Source"),
        authority_score=float(data.get("authority_score", 0.5) or 0.5),
        evidence_record_id=str(data.get("evidence_record_id") or ""),
        source_url=str(data.get("source_url") or ""),
        source_sentence=str(data.get("source_sentence") or ""),
        matched_language=str(data.get("matched_language") or ""),
        severity_rule=str(data.get("severity_rule") or SAFETY_SEVERITY_RULE_VERSION),
        classifier_version=str(data.get("classifier_version") or SAFETY_ASSERTION_ENGINE_VERSION),
        reason=str(data.get("reason") or ""),
        semantic_extraction_confidence=(
            float(data["semantic_extraction_confidence"])
            if data.get("semantic_extraction_confidence") is not None else None
        ),
        provenance=str(data.get("provenance") or "deterministic"),
    )
