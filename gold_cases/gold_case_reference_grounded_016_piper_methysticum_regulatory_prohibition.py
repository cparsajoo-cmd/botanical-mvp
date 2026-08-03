"""Gold Case 016 — Piper methysticum G.Forst., REGULATORY_STATUS.

Governing source: UK Medicines and Healthcare products Regulatory Agency
(MHRA), "Banned and restricted herbal ingredients for medicinal use",
current official guidance linked to The Medicines for Human Use (Kava-kava)
(Prohibition) Order 2002 (SI 2002/3170).

The case evaluates one narrow UK regulatory claim: medicines for human use
containing Piper methysticum (Kava-kava), or an extract from it, are not
permitted for sale, supply, or importation except when exclusively for
external use.  It does not generalize this UK medicinal-product prohibition
to foods, food supplements, cosmetics, other jurisdictions, or every external
preparation.
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
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_REFERENCE_ID = "UK_MHRA_SI_2002_3170_piper_methysticum_prohibition"
_REFERENCE_VERSION = (
    "MHRA, Banned and restricted herbal ingredients for medicinal use; "
    "legal provision: The Medicines for Human Use (Kava-kava) "
    "(Prohibition) Order 2002, SI 2002/3170"
)
_DOCUMENT_DATE = date(2014, 12, 18)  # MHRA guidance publication date
_SOURCE_LOCATOR = (
    "MHRA 'Banned and restricted herbal ingredients' table, row "
    "'Piper methysticum | Kava-kava | SI 3170', and legislation summary "
    "for The Medicines for Human Use (Kava-kava) (Prohibition) Order 2002"
)
_EVIDENCE_EXCERPT = (
    "Not permitted in unlicensed medicines, except those exclusively for external use"
)


def _build_validation_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Piper methysticum G.Forst.",
        taxon_synonyms=[],
        plant_part=None,  # prohibition covers the plant, any part, or an extract
        preparation=None,
        route_of_administration="Oral",
        indication=None,
        population="General population",
        jurisdiction="UK",
    )


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_REFERENCE_ID,
        source_type="NATIONAL_REGULATORY",
        version=_REFERENCE_VERSION,
        document_date=_DOCUMENT_DATE,
        jurisdiction="UK",
        taxon="Piper methysticum G.Forst.",
        plant_part=None,
        preparation=None,
        population="General population",
        claim_type=None,
        indication_scope=[],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.REGULATORY_STATUS,
        assertion_type=AssertionType.PROHIBITION,
        subject=(
            "sale, supply or importation of oral medicines containing "
            "Piper methysticum in the UK"
        ),
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_REFERENCE_ID,
        source_locator=_SOURCE_LOCATOR,
        evidence_text=NormalizedEvidenceText(
            original_text=_EVIDENCE_EXCERPT,
            normalized_text=(
                "UK regulation prohibits sale, supply or importation of oral "
                "medicines containing Piper methysticum or its extracts; "
                "external-use-only medicines are excluded from the prohibition."
            ),
            transformation_type=TransformationType.NORMALIZED_TERMINOLOGY,
            transformation_version="case016-kava-regulatory-v1",
            source_locator=_SOURCE_LOCATOR,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "Direct current MHRA regulatory table linked to a named UK "
                "statutory instrument, with taxon, medicinal-product scope and "
                "external-use exception stated explicitly."
            ),
            extractor_type="human_curator",
            extractor_version="case016-v1",
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
                "assertion_type=Prohibition, subject='sale, supply or "
                "importation of oral medicines containing Piper methysticum "
                "in the UK']"
            ),
            extraction_date=date(2026, 8, 1),
            curator=None,
            verification_status=VerificationStatus.CURATOR_VERIFIED,
        )
    ]


def build_gold_case_refgrounded_016_piper_methysticum_regulatory_prohibition() -> GoldCase:
    unit = _build_validation_unit()
    descriptor = _build_reference_descriptor()
    claim = _build_reference_claim()

    gref = GoldCaseReference(reference=descriptor, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.REGULATORY_STATUS] = check_applicability(
        descriptor, unit, ReferenceDomain.REGULATORY_STATUS
    )

    case = GoldCase(
        case_id="refgrounded_016_piper_methysticum_regulatory_prohibition",
        validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
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
    case = build_gold_case_refgrounded_016_piper_methysticum_regulatory_prohibition()
    print(case.case_id)
    for outcome in case.resolved_outcomes:
        print(
            outcome.domain.value,
            outcome.assertion_type.value,
            outcome.assertion_state,
            outcome.resolution_status.value,
            outcome.selected_reference_id,
        )
