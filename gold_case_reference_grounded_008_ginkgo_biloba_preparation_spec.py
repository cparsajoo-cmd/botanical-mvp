"""
Corrected Reference-Grounded Gold Case 008.

Ginkgo biloba L., folium — standardized dry-extract preparation specification.

This file replaces the earlier non-canonical Case 008. The governing
source is an official EMA/HMPC document represented by the protocol-recognized
source_type ``EMA_HMPC``. Applicability and precedence are computed by the
repository's production validation modules; no outcome is hard-coded.
EngineEvidenceInput is deliberately absent (Leakage Rule 9.1).
"""

from __future__ import annotations

from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus, ExtractionConfidenceLevel,
    GoldCaseKind, TransformationType,
)
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit


_SOURCE_ID = 'EMA_HMPC_321097_2012_ginkgo_folium'
_SOURCE_VERSION = 'Final European Union herbal monograph; first published 8 April 2015'
_SOURCE_LOCATOR = 'EMA/HMPC/321097/2012, section 2: Qualitative and quantitative composition, well-established use'
_EVIDENCE = 'Dry extract (DER 35-67:1), extraction solvent: acetone 60% (w/w).'

_PREPARATION = PreparationSpec(dosage_form="Dry extract", solvent="acetone 60% (w/w)", der_min=35.0, der_max=67.0, source_status="quantified")

def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon='Ginkgo biloba L.',
        plant_part='folium',
        preparation=_PREPARATION,
        population='Adults',
        route_of_administration='Oral',
        indication=None,
        jurisdiction="EU",
    )

def _build_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_SOURCE_ID,
        source_type="EMA_HMPC",
        version=_SOURCE_VERSION,
        document_date=date(2015, 4, 8),
        jurisdiction="EU",
        taxon='Ginkgo biloba L.',
        plant_part='folium',
        preparation=_PREPARATION,
        population='Adults',
        claim_type='well-established-use',
        indication_scope=[],
        route_scope=['Oral'],
        retracted_or_superseded=False,
    )

def _build_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.PREPARATION_SPEC,
        assertion_type=AssertionType.PREPARATION_SPECIFICATION,
        subject='dry extract DER 35-67:1, extraction solvent acetone 60% (w/w)',
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_SOURCE_ID,
        source_locator=_SOURCE_LOCATOR,
        evidence_text=NormalizedEvidenceText(
            original_text=_EVIDENCE,
            normalized_text=_EVIDENCE,
            transformation_type=TransformationType.VERBATIM,
            transformation_version="verbatim-v1",
            source_locator=_SOURCE_LOCATOR,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis="Direct extraction from an official EMA/HMPC monograph or official HMPC public summary.",
            extractor_type="human_curator",
            extractor_version="case-correction-2026-08-01",
        ),
    )

def build_gold_case_refgrounded_008_ginkgo_biloba_preparation_spec() -> GoldCase:
    unit = _build_unit()
    reference = _build_reference()
    claim = _build_claim()
    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.PREPARATION_SPEC] = check_applicability(
        reference, unit, ReferenceDomain.PREPARATION_SPEC
    )
    case = GoldCase(
        case_id="refgrounded_008_ginkgo_biloba_preparation_spec",
        validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
        references=[gref],
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case

if __name__ == "__main__":
    case = build_gold_case_refgrounded_008_ginkgo_biloba_preparation_spec()
    print(case.case_id)
    for outcome in case.resolved_outcomes:
        print(outcome.domain, outcome.resolution_status, outcome.selected_reference_id, outcome.assertion_state)
