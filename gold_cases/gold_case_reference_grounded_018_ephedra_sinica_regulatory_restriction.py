"""Gold Case 018 — Ephedra sinica Stapf, REGULATORY_STATUS.

Governing source: UK Medicines and Healthcare products Regulatory Agency
(MHRA), "Banned and restricted herbal ingredients for medicinal use",
implementing Human Medicines Regulations 2012, Schedule 20, Parts II and III.

The case evaluates a narrow UK medicinal-product supply-channel restriction.
For herbal medicines supplied following a one-to-one consultation with a
practitioner outside registered pharmacy premises, Ephedra sinica is limited
to 600 mg per dose and 1800 mg per 24 hours. If either threshold is exceeded,
the medicine is not absolutely prohibited; it may only be supplied from
registered pharmacy premises by or under the supervision of a pharmacist.

The MHRA source describes this as "internal use". ValidationUnit currently has
no generic "internal use" route value, so this case maps internal medicinal use
to route_of_administration="Oral" for applicability. That mapping is explicit
and must not be read as a verbatim route statement from the source.

The case does not generalize this UK rule to foods, food supplements, external
use, other jurisdictions, or an absolute maximum dose across all lawful supply
channels.
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
    TransformationType,
)
from field_provenance import FieldProvenance, VerificationStatus
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_REFERENCE_ID = "UK_MHRA_HMR2012_S20_ephedra_sinica_dose_restriction"
_REFERENCE_VERSION = (
    "MHRA, Banned and restricted herbal ingredients for medicinal use; "
    "Human Medicines Regulations 2012, Schedule 20, Parts II and III"
)
_DOCUMENT_DATE = date(2014, 12, 18)
_SOURCE_LOCATOR = (
    "MHRA 'Banned and restricted herbal ingredients' table, row listing "
    "Ephedra sinica and related Ephedra species under SI 2130 Parts II and III"
)
_EVIDENCE_EXCERPT = "600 mg (MD), 1800 mg (MDD)"


def _build_validation_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Ephedra sinica Stapf",
        taxon_synonyms=[],
        plant_part=None,
        preparation=None,
        route_of_administration="Oral",
        indication=None,
        population=None,
        jurisdiction="UK",
    )


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_REFERENCE_ID,
        source_type="NATIONAL_REGULATORY",
        version=_REFERENCE_VERSION,
        document_date=_DOCUMENT_DATE,
        jurisdiction="UK",
        taxon="Ephedra sinica Stapf",
        plant_part=None,
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.REGULATORY_STATUS,
        assertion_type=AssertionType.RESTRICTION,
        subject=(
            "UK dose thresholds determining practitioner versus pharmacy "
            "supply of internal-use herbal medicines containing Ephedra sinica"
        ),
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_REFERENCE_ID,
        source_locator=_SOURCE_LOCATOR,
        evidence_text=NormalizedEvidenceText(
            original_text=_EVIDENCE_EXCERPT,
            normalized_text=(
                "In the UK, herbal medicines containing Ephedra sinica may be "
                "supplied following a one-to-one practitioner consultation at "
                "doses not exceeding 600 mg per dose and 1800 mg per 24 hours. "
                "If either threshold is exceeded, supply is limited to "
                "registered pharmacy premises by or under pharmacist supervision."
            ),
            transformation_type=TransformationType.NORMALIZED_TERMINOLOGY,
            transformation_version="case018-ephedra-regulatory-v1",
            source_locator=_SOURCE_LOCATOR,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "Direct current MHRA guidance names Ephedra sinica, gives the "
                "600 mg single-dose and 1800 mg daily-dose thresholds, and "
                "explains that exceeding the Part 2 thresholds changes the "
                "lawful supply channel to registered pharmacy premises rather "
                "than creating an absolute prohibition."
            ),
            extractor_type="human_curator",
            extractor_version="case018-v1",
        ),
    )


def _build_case_provenance() -> list[FieldProvenance]:
    return [
        FieldProvenance(
            document_id=_REFERENCE_ID,
            document_version=_REFERENCE_VERSION,
            locator=_SOURCE_LOCATOR,
            supported_field=(
                "resolved_outcomes[domain=Regulatory status, "
                "assertion_type=Restriction, subject='UK maximum-dose "
                "restriction for internal-use herbal medicines containing "
                "Ephedra sinica']"
            ),
            extraction_date=date(2026, 8, 1),
            curator=None,
            verification_status=VerificationStatus.CURATOR_VERIFIED,
        )
    ]


def build_gold_case_refgrounded_018_ephedra_sinica_regulatory_restriction() -> GoldCase:
    unit = _build_validation_unit()
    descriptor = _build_reference_descriptor()
    claim = _build_reference_claim()

    gref = GoldCaseReference(reference=descriptor, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.REGULATORY_STATUS] = check_applicability(
        descriptor, unit, ReferenceDomain.REGULATORY_STATUS
    )

    case = GoldCase(
        case_id="refgrounded_018_ephedra_sinica_regulatory_restriction",
        validation_unit=unit,
        risk_strata=[],
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
    case = build_gold_case_refgrounded_018_ephedra_sinica_regulatory_restriction()
    print(case.case_id)
    for outcome in case.resolved_outcomes:
        print(
            outcome.domain.value,
            outcome.assertion_type.value,
            outcome.assertion_state,
            outcome.resolution_status.value,
            outcome.selected_reference_id,
        )
