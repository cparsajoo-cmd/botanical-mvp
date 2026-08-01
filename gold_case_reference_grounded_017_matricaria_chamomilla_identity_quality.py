"""Gold Case 017 — Matricaria chamomilla L., IDENTITY_QUALITY.

Governing source: Royal Botanic Gardens, Kew, Plants of the World Online
(POWO), accepted taxon LSID urn:lsid:ipni.org:names:154715-2.

POWO identifies Matricaria chamomilla L. as an accepted species.  It also
records Chamomilla recutita (L.) Rauschert as a synonym.  The case is limited
to taxonomic identity and synonym normalization; it makes no efficacy,
safety, preparation, or regulatory claim.
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
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_REFERENCE_ID = "KEW_POWO_154715_2_matricaria_chamomilla"
_POWO_VERSION = (
    "Plants of the World Online, Kew Names and Taxonomic Backbone; "
    "accepted taxon urn:lsid:ipni.org:names:154715-2; accessed 2026-08-01"
)


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Matricaria chamomilla L.",
        taxon_synonyms=[
            "Chamomilla recutita (L.) Rauschert",
            "Matricaria recutita L.",
        ],
        plant_part=None,
        preparation=None,
        route_of_administration=None,
        indication=None,
        population=None,
        jurisdiction="International",
    )


def _build_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_REFERENCE_ID,
        source_type="TAXONOMIC_AUTHORITY",
        version=_POWO_VERSION,
        document_date=date(2026, 8, 1),
        jurisdiction=None,
        taxon="Matricaria chamomilla L.",
        plant_part=None,
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[],
        route_scope=[],
        retracted_or_superseded=False,
    )


def _build_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.IDENTITY_QUALITY,
        assertion_type=AssertionType.IDENTITY_CONFIRMATION,
        subject="accepted taxonomic identity: Matricaria chamomilla L.",
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_REFERENCE_ID,
        source_locator=(
            "Kew Plants of the World Online (POWO), Matricaria chamomilla L., "
            "General Information and Synonyms sections, LSID "
            "urn:lsid:ipni.org:names:154715-2"
        ),
        evidence_text=NormalizedEvidenceText(
            original_text="This species is accepted.",
            normalized_text=(
                "Matricaria chamomilla L. is an accepted species; "
                "Chamomilla recutita (L.) Rauschert is a synonym."
            ),
            transformation_type=TransformationType.NORMALIZED_TERMINOLOGY,
            transformation_version="kew-taxonomy-normalization-v1",
            source_locator="POWO accepted-status line and synonyms section",
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "Direct accepted-status and synonym statements from the Kew "
                "Plants of the World Online taxonomic backbone."
            ),
            extractor_type="human_curator",
            extractor_version="case017-v1",
        ),
    )


def build_gold_case_refgrounded_017_matricaria_chamomilla_identity_quality() -> GoldCase:
    unit = _build_unit()
    descriptor = _build_reference()
    gref = GoldCaseReference(reference=descriptor, claims=[_build_claim()])
    gref.applicability_by_domain[ReferenceDomain.IDENTITY_QUALITY] = check_applicability(
        descriptor, unit, ReferenceDomain.IDENTITY_QUALITY
    )
    case = GoldCase(
        case_id="refgrounded_017_matricaria_chamomilla_identity_quality",
        validation_unit=unit,
        references=[gref],
        engine_evidence=[],
        engine_evidence_origin=None,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        locked=False,
    )
    return replace(case, resolved_outcomes=resolve_expected_outcomes(case))


if __name__ == "__main__":
    built = build_gold_case_refgrounded_017_matricaria_chamomilla_identity_quality()
    print(built.case_id)
    for outcome in built.resolved_outcomes:
        print(
            outcome.domain.value,
            outcome.assertion_type.value,
            outcome.assertion_state,
            outcome.resolution_status.value,
        )
