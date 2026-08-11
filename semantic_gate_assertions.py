"""Semantic safety/regulatory assertion contracts for hard-gate evidence.

This module is deliberately *not* a decision engine.  It turns structured
semantic extraction output into auditable assertion objects.  Final GO/NO-GO
policy remains deterministic in ``eligibility_gate.py``.

Design invariants
-----------------
* record-level provenance is mandatory for production use;
* an LLM can add concern/review signals but cannot erase deterministic hazards;
* extraction confidence is distinct from source/evidence strength;
* supporting text must be a verbatim span from the source record;
* regulatory state and market-access effect are distinct concepts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Tuple

from assertion_vocabulary import SeverityLevel
from safety_assertion_engine import (
    AssertionPolarity,
    SafetyAssertion,
    SafetyAssertionType,
    SafetyConfidence,
)

SEMANTIC_GATE_ASSERTION_VERSION = "1.0.0"


class SemanticCertainty(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class RegulatoryAction(str, Enum):
    PROHIBITED = "prohibited"
    AUTHORIZATION_REQUIRED = "authorization_required"
    AUTHORIZED = "authorized"
    AUTHORIZED_WITH_CONDITIONS = "authorized_with_conditions"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"
    SUSPENDED = "suspended"
    PENDING = "pending"
    RESTRICTED = "restricted"
    NOT_AUTHORIZED = "not_authorized"
    TERMINATED = "terminated"
    UNCLEAR = "unclear"


class MarketAccessEffect(str, Enum):
    BLOCKS_MARKET_ACCESS = "blocks_market_access"
    CONDITIONAL_ACCESS = "conditional_access"
    NO_BLOCK = "no_block"
    UNCLEAR = "unclear"


@dataclass(frozen=True)
class SemanticRegulatoryAssertion:
    action: RegulatoryAction
    market_access_effect: MarketAccessEffect
    jurisdiction: str = ""
    authority: str = ""
    ingredient: str = ""
    plant_part: str = ""
    preparation: str = ""
    route: str = ""
    product_category: str = ""
    conditions: str = ""
    effective_date: str = ""
    supporting_text: str = ""
    evidence_record_id: str = ""
    source_url: str = ""
    extraction_confidence: float = 0.0
    context_applicability: str = "unknown"  # relevant | irrelevant | unknown
    classifier_version: str = SEMANTIC_GATE_ASSERTION_VERSION

    @property
    def blocking(self) -> bool:
        return self.market_access_effect == MarketAccessEffect.BLOCKS_MARKET_ACCESS


# Generic semantic labels map into the existing SafetyAssertion vocabulary so
# the current eligibility/final-decision architecture stays intact.
_SAFETY_TYPE_MAP = {
    "fatal_adverse_event": SafetyAssertionType.FATAL_ADVERSE_EVENT,
    "serious_adverse_event": SafetyAssertionType.SERIOUS_ADVERSE_EVENT,
    "organ_toxicity": SafetyAssertionType.ORGAN_TOXICITY,
    "contraindication": SafetyAssertionType.CONTRAINDICATION,
    "serious_drug_interaction": SafetyAssertionType.SERIOUS_DRUG_INTERACTION,
    "pregnancy": SafetyAssertionType.PREGNANCY,
    "lactation": SafetyAssertionType.LACTATION,
    "pediatric_restriction": SafetyAssertionType.PEDIATRIC_RESTRICTION,
    "qt_prolongation": SafetyAssertionType.QT_PROLONGATION,
    "bleeding_risk": SafetyAssertionType.BLEEDING_RISK,
    "allergic_risk": SafetyAssertionType.ALLERGIC_RISK,
    "carcinogenicity": SafetyAssertionType.CARCINOGENICITY,
    "genotoxicity": SafetyAssertionType.GENOTOXICITY,
    "reproductive_toxicity": SafetyAssertionType.REPRODUCTIVE_TOXICITY,
    "major_regulatory_safety_warning": SafetyAssertionType.MAJOR_REGULATORY_SAFETY_WARNING,
    "warning": SafetyAssertionType.WARNING,
    "precaution": SafetyAssertionType.PRECAUTION,
    "reassurance": SafetyAssertionType.REASSURANCE,
}


def _confidence_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _authority_to_evidence_strength(authority_score: float) -> SafetyConfidence:
    """Map *source authority*, never model confidence, to legacy strength.

    This preserves backward compatibility with SafetyAssertion while keeping
    semantic extraction confidence in its own field.
    """
    try:
        score = float(authority_score)
    except (TypeError, ValueError):
        score = 0.0
    if score >= 0.85:
        return SafetyConfidence.HIGH
    if score >= 0.65:
        return SafetyConfidence.MODERATE
    if score > 0:
        return SafetyConfidence.LOW
    return SafetyConfidence.INSUFFICIENT


def validate_supporting_span(source_text: str, supporting_text: str) -> bool:
    """A semantic assertion is auditable only if its quote exists verbatim."""
    source = str(source_text or "")
    span = str(supporting_text or "").strip()
    return bool(span and span in source)


def safety_assertion_from_semantic(
    data: Mapping[str, Any],
    *,
    source_text: str,
    evidence_record_id: str = "",
    authority: str = "Unknown Source",
    authority_score: float = 0.5,
    source_url: str = "",
) -> SafetyAssertion | None:
    """Convert one validated semantic safety extraction to SafetyAssertion.

    Invalid/non-verbatim spans fail closed by returning ``None``.  The caller
    can then route extraction disagreement/invalidity to review without ever
    clearing an existing deterministic signal.
    """
    span = str(data.get("supporting_text") or "").strip()
    if not validate_supporting_span(source_text, span):
        return None

    severity_raw = str(data.get("seriousness") or "unknown").strip().lower()
    polarity_raw = str(data.get("polarity") or "risk_present").strip().lower()
    hazard_type = str(data.get("hazard_type") or "warning").strip().lower()

    severity = {
        "serious": SeverityLevel.SERIOUS,
        "moderate": SeverityLevel.MODERATE,
        "minor": SeverityLevel.MINOR,
        "none": SeverityLevel.NONE,
        "reassuring": SeverityLevel.NONE,
    }.get(severity_raw, SeverityLevel.NONE)

    polarity = {
        "risk_present": AssertionPolarity.RISK_PRESENT,
        "risk_absent": AssertionPolarity.RISK_ABSENT,
        "conditional": AssertionPolarity.CONDITIONAL,
        "mechanistic_only": AssertionPolarity.MECHANISTIC_ONLY,
    }.get(polarity_raw, AssertionPolarity.RISK_PRESENT)

    if polarity == AssertionPolarity.RISK_ABSENT:
        assertion_type = SafetyAssertionType.REASSURANCE
    else:
        assertion_type = _SAFETY_TYPE_MAP.get(hazard_type)
        if assertion_type is None:
            # Unknown vocabulary must still preserve a semantically asserted
            # serious risk instead of reproducing the regex vocabulary gap.
            assertion_type = (
                SafetyAssertionType.SERIOUS_ADVERSE_EVENT
                if severity == SeverityLevel.SERIOUS
                else SafetyAssertionType.WARNING
            )

    populations = data.get("affected_population") or []
    if isinstance(populations, str):
        populations = [populations] if populations.strip() else []

    extraction_confidence = _confidence_float(data.get("extraction_confidence"))
    return SafetyAssertion(
        assertion_type=assertion_type,
        severity=severity,
        polarity=polarity,
        evidence_strength=_authority_to_evidence_strength(authority_score),
        applicability=str(data.get("context_applicability") or "unknown"),
        affected_population=tuple(str(x).strip().lower() for x in populations if str(x).strip()),
        preparation=str(data.get("preparation") or ""),
        dose_dependency=str(data.get("dose_dependency") or "unknown"),
        route=str(data.get("route") or ""),
        authority=authority,
        authority_score=float(authority_score or 0.0),
        evidence_record_id=str(evidence_record_id or ""),
        source_url=str(source_url or ""),
        source_sentence=span,
        matched_language=str(data.get("reported_outcome") or data.get("hazard_type") or ""),
        classifier_version=f"semantic-gate/{SEMANTIC_GATE_ASSERTION_VERSION}",
        reason=(
            "Semantic record-level safety assertion; extraction confidence="
            f"{extraction_confidence:.2f}. Severity is source semantics; "
            "evidence_strength is derived independently from source authority."
        ),
        semantic_extraction_confidence=extraction_confidence,
        provenance="llm_semantic_gate",
    )


def regulatory_assertion_from_semantic(
    data: Mapping[str, Any],
    *,
    source_text: str,
    evidence_record_id: str = "",
    source_url: str = "",
) -> SemanticRegulatoryAssertion | None:
    span = str(data.get("supporting_text") or "").strip()
    if not validate_supporting_span(source_text, span):
        return None
    try:
        action = RegulatoryAction(str(data.get("action") or "unclear"))
    except ValueError:
        action = RegulatoryAction.UNCLEAR
    try:
        effect = MarketAccessEffect(str(data.get("market_access_effect") or "unclear"))
    except ValueError:
        effect = MarketAccessEffect.UNCLEAR
    return SemanticRegulatoryAssertion(
        action=action,
        market_access_effect=effect,
        jurisdiction=str(data.get("jurisdiction") or ""),
        authority=str(data.get("authority") or ""),
        ingredient=str(data.get("ingredient") or ""),
        plant_part=str(data.get("plant_part") or ""),
        preparation=str(data.get("preparation") or ""),
        route=str(data.get("route") or ""),
        product_category=str(data.get("product_category") or ""),
        conditions=str(data.get("conditions") or ""),
        effective_date=str(data.get("effective_date") or ""),
        supporting_text=span,
        evidence_record_id=str(evidence_record_id or ""),
        source_url=str(source_url or ""),
        extraction_confidence=_confidence_float(data.get("extraction_confidence")),
        context_applicability=str(data.get("context_applicability") or "unknown").lower(),
    )


def parse_semantic_gate_payload(
    payload: Mapping[str, Any],
    *,
    source_text: str,
    evidence_record_id: str = "",
    authority: str = "Unknown Source",
    authority_score: float = 0.5,
    source_url: str = "",
) -> tuple[Tuple[SafetyAssertion, ...], Tuple[SemanticRegulatoryAssertion, ...], Tuple[str, ...]]:
    """Validate one record payload and return assertions + audit warnings."""
    safety = []
    regulatory = []
    warnings = []
    for item in payload.get("safety_assertions") or []:
        assertion = safety_assertion_from_semantic(
            item,
            source_text=source_text,
            evidence_record_id=evidence_record_id,
            authority=authority,
            authority_score=authority_score,
            source_url=source_url,
        )
        if assertion is None:
            warnings.append("invalid_or_nonverbatim_safety_supporting_span")
        else:
            safety.append(assertion)
    for item in payload.get("regulatory_assertions") or []:
        assertion = regulatory_assertion_from_semantic(
            item,
            source_text=source_text,
            evidence_record_id=evidence_record_id,
            source_url=source_url,
        )
        if assertion is None:
            warnings.append("invalid_or_nonverbatim_regulatory_supporting_span")
        else:
            regulatory.append(assertion)
    return tuple(safety), tuple(regulatory), tuple(warnings)
