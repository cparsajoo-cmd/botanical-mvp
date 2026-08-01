"""Corrected Gold Case 011 — Matricaria chamomilla L., INDICATION_EVIDENCE.

The previous Case 011 incorrectly represented a favourable tolerability
observation as a SAFETY-domain SUPPORTS_INDICATION claim.  This corrected
case uses a governing systematic review for the clinically scoped claim
"generalized anxiety disorder" and keeps the source's positive conclusion
without converting tolerability into a safety ontology assertion.

Governing source:
Hieu TH, Dibas M, Surya Dila KA, et al. Therapeutic efficacy and safety of
chamomile for state anxiety, generalized anxiety disorder, insomnia, and
sleep quality: a systematic review and meta-analysis. Phytother Res.
2019;33(6):1604-1615. DOI 10.1002/ptr.6349. PMID 31006899.
"""
from __future__ import annotations
from dataclasses import replace
from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus,
    ExtractionConfidenceLevel, GoldCaseKind, TransformationType,
)
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_REFERENCE_ID = "PUBMED_31006899_Hieu_2019_chamomile_GAD_SR"
_CITATION = (
    "Hieu TH, Dibas M, Surya Dila KA, et al. Therapeutic efficacy and safety "
    "of chamomile for state anxiety, generalized anxiety disorder, insomnia, "
    "and sleep quality. Phytother Res. 2019;33(6):1604-1615. "
    "DOI:10.1002/ptr.6349. PMID:31006899."
)
_SHORT_SOURCE_EXCERPT = "Chamomile appears to be efficacious and safe for sleep quality and GAD."


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Matricaria chamomilla L.",
        taxon_synonyms=["Matricaria recutita L."],
        plant_part="flower",
        route_of_administration="Oral",
        indication="generalized anxiety disorder",
        population="Adults",
        jurisdiction="International",
    )


def _build_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_REFERENCE_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_CITATION,
        document_date=date(2019, 4, 21),
        jurisdiction=None,
        taxon="Matricaria chamomilla L.",
        plant_part=None,
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=["generalized anxiety disorder"],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_claim() -> ReferenceClaim:
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="generalized anxiety disorder",
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_REFERENCE_ID,
        source_locator="PubMed PMID 31006899, abstract conclusion; DOI 10.1002/ptr.6349",
        evidence_text=NormalizedEvidenceText(
            original_text=_SHORT_SOURCE_EXCERPT,
            normalized_text="Chamomile supports generalized anxiety disorder symptom improvement.",
            transformation_type=TransformationType.NORMALIZED_TERMINOLOGY,
            transformation_version="identity-safe-normalization-v1",
            source_locator="PubMed PMID 31006899, abstract conclusion",
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis="Systematic review and meta-analysis of randomized and quasi-randomized trials; exact short conclusion excerpt verified on PubMed.",
            extractor_type="human_curator",
            extractor_version="case011-correction-v1",
        ),
    )


def build_gold_case_refgrounded_011_matricaria_chamomilla_indication_evidence() -> GoldCase:
    unit = _build_unit()
    descriptor = _build_reference()
    gref = GoldCaseReference(reference=descriptor, claims=[_build_claim()])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        descriptor, unit, ReferenceDomain.INDICATION_EVIDENCE
    )
    case = GoldCase(
        case_id="refgrounded_011_matricaria_chamomilla_indication_evidence",
        validation_unit=unit,
        references=[gref],
        engine_evidence=[],
        engine_evidence_origin=None,
        risk_strata=[],
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        locked=False,
    )
    return replace(case, resolved_outcomes=resolve_expected_outcomes(case))


if __name__ == "__main__":
    c = build_gold_case_refgrounded_011_matricaria_chamomilla_indication_evidence()
    print(c.case_id)
    for o in c.resolved_outcomes:
        print(o.domain.value, o.assertion_type.value, o.assertion_state, o.resolution_status.value)
