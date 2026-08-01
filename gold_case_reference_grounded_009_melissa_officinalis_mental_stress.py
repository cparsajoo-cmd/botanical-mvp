"""
Corrected Reference-Grounded Gold Case 009.

Melissa officinalis L., folium — traditional-use mental-stress indication.

This file replaces the earlier non-canonical Case 009. The governing
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


_SOURCE_ID = 'EMA_HMPC_310761_2013_melissae_folium_summary'
_SOURCE_VERSION = 'EMA HMPC summary for the public; first published 16 June 2014'
_SOURCE_LOCATOR = 'EMA/HMPC/310761/2013, Melissa leaf — Summary for the public, HMPC conclusions on medicinal uses'
_EVIDENCE = 'The HMPC concluded that, on the basis of its long-standing use, melissa leaf can be used for the relief of mild symptoms of mental stress and to aid sleep.'

_PREPARATION = PreparationSpec(dosage_form="Herbal tea", solvent="water", source_status="traditional")

def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon='Melissa officinalis L.',
        plant_part='folium',
        preparation=_PREPARATION,
        population='Adolescents over 12 years of age, adults and elderly',
        route_of_administration='Oral',
        indication='Mental stress and mood disorders',
        jurisdiction="EU",
    )

def _build_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_SOURCE_ID,
        source_type="EMA_HMPC",
        version=_SOURCE_VERSION,
        document_date=date(2014, 6, 16),
        jurisdiction="EU",
        taxon='Melissa officinalis L.',
        plant_part='folium',
        preparation=_PREPARATION,
        population='Adolescents over 12 years of age, adults and elderly',
        claim_type='traditional-use',
        indication_scope=['Mental stress and mood disorders'],
        route_scope=['Oral'],
        retracted_or_superseded=False,
    )

def _build_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject='relief of mild symptoms of mental stress',
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

def build_gold_case_refgrounded_009_melissa_officinalis_mental_stress() -> GoldCase:
    unit = _build_unit()
    reference = _build_reference()
    claim = _build_claim()
    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        reference, unit, ReferenceDomain.INDICATION_EVIDENCE
    )
    case = GoldCase(
        case_id="refgrounded_009_melissa_officinalis_mental_stress",
        validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
        references=[gref],
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case

if __name__ == "__main__":
    case = build_gold_case_refgrounded_009_melissa_officinalis_mental_stress()
    print(case.case_id)
    for outcome in case.resolved_outcomes:
        print(outcome.domain, outcome.resolution_status, outcome.selected_reference_id, outcome.assertion_state)
