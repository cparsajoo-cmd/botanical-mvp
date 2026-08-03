"""Gold Case 014 — Ginkgo biloba L., folium, SAFETY interaction.

Governing source: European Union herbal monograph on Ginkgo biloba L.,
folium, EMA/HMPC/321097/2012, adopted 28 January 2015.

The case evaluates one narrow, affirmative interaction claim for the
well-established-use dry extract: concomitant use with dabigatran etexilate
requires caution because Ginkgo biloba may inhibit intestinal P-glycoprotein
and increase dabigatran exposure. It does not generalize this claim to every
anticoagulant and does not convert a caution into a contraindication.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState,
    AssertionType,
    CurationStatus,
    ExtractionConfidenceLevel,
    GoldCaseKind,
    SeverityLevel,
    TransformationType,
)
from field_provenance import FieldProvenance, VerificationStatus
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit

_REFERENCE_ID = "EMA_HMPC_321097_2012_ginkgo_biloba_dabigatran_interaction"
_REFERENCE_VERSION = (
    "European Union herbal monograph on Ginkgo biloba L., folium, "
    "EMA/HMPC/321097/2012, final, adopted 28 January 2015"
)
_SOURCE_LOCATOR = (
    "EMA/HMPC/321097/2012, section 4.5 'Interactions with other medicinal "
    "products and other forms of interaction', page 4/8"
)
_EVIDENCE_EXCERPT = "Caution is advised if combining G. biloba and dabigatran."

_PREPARATION = PreparationSpec(
    dosage_form="Dry extract",
    solvent="acetone 60% m/m",
    der_min=35.0,
    der_max=67.0,
    source_status="concentrated",
)


def _build_validation_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Ginkgo biloba L.",
        plant_part="folium",
        preparation=_PREPARATION,
        route_of_administration="Oral",
        indication=None,
        population="Adults and elderly",
        jurisdiction="EU",
    )


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_REFERENCE_ID,
        source_type="EMA_HMPC",
        version=_REFERENCE_VERSION,
        document_date=date(2015, 1, 28),
        jurisdiction="EU",
        taxon="Ginkgo biloba L.",
        plant_part="folium",
        preparation=_PREPARATION,
        population="Adults and elderly",
        claim_type="well-established-use",
        indication_scope=[],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.SAFETY,
        assertion_type=AssertionType.INTERACTION,
        subject="concomitant use with dabigatran etexilate",
        assertion_state=AssertionState.PRESENT,
        severity=SeverityLevel.MODERATE,
        source_reference_id=_REFERENCE_ID,
        source_locator=_SOURCE_LOCATOR,
        evidence_text=NormalizedEvidenceText(
            original_text=_EVIDENCE_EXCERPT,
            normalized_text=(
                "Concomitant use of Ginkgo biloba dry extract with dabigatran "
                "etexilate requires caution because exposure may increase."
            ),
            transformation_type=TransformationType.NORMALIZED_TERMINOLOGY,
            transformation_version="case014-ginkgo-dabigatran-v1",
            source_locator=_SOURCE_LOCATOR,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "Direct interaction statement in the final EMA/HMPC monograph, "
                "with preparation, route, and interacting medicinal product specified."
            ),
            extractor_type="human_curator",
            extractor_version="case014-v1",
        ),
    )


def _build_case_provenance() -> list[FieldProvenance]:
    return [
        FieldProvenance(
            document_id=_REFERENCE_ID,
            document_version=_REFERENCE_VERSION,
            locator=_SOURCE_LOCATOR,
            supported_field=(
                "resolved_outcomes[domain=Safety, assertion_type=Interaction, "
                "subject='concomitant use with dabigatran etexilate']"
            ),
            extraction_date=date(2026, 8, 1),
            curator=None,
            verification_status=VerificationStatus.CURATOR_VERIFIED,
        )
    ]


def build_gold_case_refgrounded_014_ginkgo_biloba_safety_interaction() -> GoldCase:
    unit = _build_validation_unit()
    descriptor = _build_reference_descriptor()
    claim = _build_reference_claim()
    gref = GoldCaseReference(reference=descriptor, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.SAFETY] = check_applicability(
        descriptor, unit, ReferenceDomain.SAFETY
    )

    case = GoldCase(
        case_id="refgrounded_014_ginkgo_biloba_safety_interaction",
        validation_unit=unit,
        risk_strata=[RiskStratum.INTERACTION, RiskStratum.SAFETY_MODERATE],
        references=[gref],
        case_provenance=_build_case_provenance(),
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        engine_evidence=[],
        engine_evidence_origin=None,
        locked=False,
    )
    return replace(case, resolved_outcomes=resolve_expected_outcomes(case))


if __name__ == "__main__":
    case = build_gold_case_refgrounded_014_ginkgo_biloba_safety_interaction()
    print(case.case_id)
    for outcome in case.resolved_outcomes:
        print(
            outcome.domain.value,
            outcome.assertion_type.value,
            outcome.assertion_state,
            outcome.severity,
            outcome.resolution_status.value,
        )
