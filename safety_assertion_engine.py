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
}
_RISK_PATTERNS = {
    SafetyAssertionType.QT_PROLONGATION: (r"\b(?:prolong(?:s|ed|ation)?|increase(?:s|d)?)\b.{0,35}\bqt(?:c)?\b", r"\btorsades de pointes\b"),
    SafetyAssertionType.BLEEDING_RISK: (r"\b(?:increase(?:s|d)?|elevat(?:e|es|ed))\b.{0,35}\bbleeding risk\b", r"\bhemorrhag(?:e|ic)\b"),
    SafetyAssertionType.PHOTOSENSITIVITY: (r"\bphotosensiti(?:vity|sation|zation)\b", r"\bphototoxic(?:ity)?\b"),
    SafetyAssertionType.ALLERGIC_RISK: (r"\banaphylaxis\b", r"\bsevere allergic reaction\b", r"\bhypersensitivity reaction\b"),
}
_ORGAN_TOXICITY = (
    r"\b(?:caus(?:e|es|ed)|induc(?:e|es|ed)|associated with|risk of|result(?:s|ed)? in)\b.{0,55}\b(?:hepatotoxicity|liver injury|nephrotoxicity|renal injury|cardiotoxicity|neurotoxicity)\b",
    r"\b(?:hepatotoxic|nephrotoxic|cardiotoxic|neurotoxic)\b",
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
) -> Tuple[SafetyAssertion, ...]:
    """Return all meaningful structured safety assertions in one record.

    Multiple assertions are intentionally retained; callers must not reduce a
    record to one winner because that would erase evidence conflict.
    """
    assertions: list[SafetyAssertion] = []
    for unit in _units(text):
        n = _norm(unit)
        populations = _affected_populations(n)

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
    )
