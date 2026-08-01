"""Gold Case 013 — Echinacea purpurea (L.) Moench, IDENTITY_QUALITY.

Governing source: Royal Botanic Gardens, Kew, Plants of the World Online
(POWO), taxon LSID urn:lsid:ipni.org:names:1174497-2.

POWO identifies Echinacea purpurea (L.) Moench as an accepted species and
lists Rudbeckia purpurea L. as a synonym.  The case deliberately evaluates
only taxonomic identity; it makes no efficacy, safety, preparation, or
regulatory claim.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus,
    ExtractionConfidenceLevel, GoldCaseKind, TransformationType,
)
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_REFERENCE_ID = "KEW_POWO_1174497_2_echinacea_purpurea"
_POWO_VERSION = (
    "Plants of the World Online, Kew Names and Taxonomic Backbone; "
    "taxon urn:lsid:ipni.org:names:1174497-2; accessed 2026-08-01"
)


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Echinacea purpurea (L.) Moench",
        taxon_synonyms=["Rudbeckia purpurea L."],
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
        taxon="Echinacea purpurea (L.) Moench",
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
        subject="accepted taxonomic identity: Echinacea purpurea (L.) Moench",
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_REFERENCE_ID,
        source_locator=(
            "Kew Plants of the World Online (POWO), Echinacea purpurea (L.) Moench, "
            "Taxonomy section, LSID urn:lsid:ipni.org:names:1174497-2"
        ),
        evidence_text=NormalizedEvidenceText(
            original_text="This species is accepted.",
            normalized_text="Echinacea purpurea (L.) Moench is an accepted species.",
            transformation_type=TransformationType.NORMALIZED_TERMINOLOGY,
            transformation_version="kew-taxonomy-normalization-v1",
            source_locator="POWO taxon page, status line and taxonomy section",
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis="Direct status statement from Kew Plants of the World Online taxonomic backbone.",
            extractor_type="human_curator",
            extractor_version="case013-v1",
        ),
    )


def build_gold_case_refgrounded_013_echinacea_purpurea_identity_quality() -> GoldCase:
    unit = _build_unit()
    descriptor = _build_reference()
    gref = GoldCaseReference(reference=descriptor, claims=[_build_claim()])
    gref.applicability_by_domain[ReferenceDomain.IDENTITY_QUALITY] = check_applicability(
        descriptor, unit, ReferenceDomain.IDENTITY_QUALITY
    )
    case = GoldCase(
        case_id="refgrounded_013_echinacea_purpurea_identity_quality",
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
    c = build_gold_case_refgrounded_013_echinacea_purpurea_identity_quality()
    print(c.case_id)
    for o in c.resolved_outcomes:
        print(o.domain.value, o.assertion_type.value, o.assertion_state, o.resolution_status.value)
