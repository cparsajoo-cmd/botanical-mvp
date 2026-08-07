"""Gold Case 022 — Valeriana officinalis, cross-rank indication precedence.

Coverage objective
------------------
Exercise a real cross-rank precedence decision in INDICATION_EVIDENCE without
changing production logic. Two independently verified, applicable references
address valerian for insomnia/sleep disorders but carry different source ranks:

1) Stevinson & Ernst (2000), SYSTEMATIC_REVIEW — nine randomized,
   placebo-controlled, double-blind trials; conclusion: evidence for valerian
   as a treatment for insomnia is inconclusive.
2) EMA/HMPC/150848/2015, EMA_HMPC — European Union herbal monograph for
   Valeriana officinalis L., radix; recognizes well-established use for relief
   of sleep disorders.

The repository's existing INDICATION_EVIDENCE hierarchy ranks
SYSTEMATIC_REVIEW above EMA_HMPC. Therefore the systematic-review verdict must
be selected even though the EMA monograph is newer. This case tests source-rank
precedence itself; it is not a same-rank conflict case.

Scope discipline
----------------
No preparation or dose is invented. The ValidationUnit is limited to
Valeriana officinalis L. radix and insomnia. The systematic-review abstract
uses "insomnia"; EMA uses the broader "sleep disorders" wording. The case
records the shared clinical overlap as insomnia and does not claim that every
sleep disorder is equivalent to insomnia.
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
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit

_SUBJECT = "insomnia"

_SR_ID = "PUBMED_10767649_STEVINSON_ERNST_2000_VALERIAN_INSOMNIA_SR"
_SR_CITATION = (
    "Stevinson C, Ernst E. Valerian for insomnia: a systematic review of randomized "
    "clinical trials. Sleep Med. 2000;1(2):91-99. PMID:10767649. "
    "DOI:10.1016/S1389-9457(99)00015-5."
)
_SR_VERBATIM = (
    "The evidence for valerian as a treatment for insomnia is inconclusive. "
    "There is a need for rigorous trials to determine its efficacy."
)

_EMA_ID = "EMA_HMPC_150848_2015_VALERIANA_RADIX_SLEEP"
_EMA_CITATION = (
    "European Medicines Agency, Committee on Herbal Medicinal Products. "
    "European Union herbal monograph on Valeriana officinalis L., radix. "
    "EMA/HMPC/150848/2015. Adopted 2 February 2016."
)
_EMA_VERBATIM = "For relief of sleep disorders"


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Valeriana officinalis L.",
        taxon_synonyms=[],
        plant_part="radix",
        preparation=None,
        dose=None,
        duration=None,
        route_of_administration=None,
        indication=_SUBJECT,
        population=None,
        jurisdiction=None,
    )


def _build_sr_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_SR_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_SR_CITATION,
        document_date=date(2000, 4, 1),
        jurisdiction=None,
        taxon="Valeriana officinalis L.",
        # PubMed abstract does not make plant-part identity load-bearing.
        plant_part=None,
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[_SUBJECT],
        route_scope=[],
        retracted_or_superseded=False,
    )


def _build_ema_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_EMA_ID,
        source_type="EMA_HMPC",
        version=_EMA_CITATION,
        document_date=date(2016, 2, 2),
        jurisdiction="EU",
        taxon="Valeriana officinalis L.",
        plant_part="radix",
        preparation=None,
        population=None,
        claim_type="well-established-use",
        # Normalized to the case's narrower insomnia question. The source's
        # own wording is preserved verbatim in the claim below.
        indication_scope=[_SUBJECT],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_sr_claim() -> ReferenceClaim:
    locator = "PubMed PMID 10767649, abstract conclusion"
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject=_SUBJECT,
        assertion_state=AssertionState.INSUFFICIENT,
        severity=None,
        source_reference_id=_SR_ID,
        source_locator=locator,
        evidence_text=NormalizedEvidenceText(
            original_text=_SR_VERBATIM,
            normalized_text="Evidence for valerian as a treatment for insomnia is inconclusive.",
            transformation_type=TransformationType.VERBATIM,
            transformation_version="case022-sr-verbatim-v1",
            source_locator=locator,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "PubMed directly identifies the publication as a systematic review of randomized, "
                "placebo-controlled, double-blind trials and provides the quoted conclusion."
            ),
            extractor_type="human_curator",
            extractor_version="case022-cross-rank-curation-v1",
        ),
    )


def _build_ema_claim() -> ReferenceClaim:
    locator = (
        "EMA/HMPC/150848/2015, section 4.2 (well-established use), sleep-disorder posology; "
        "EMA Valerianae radix public page"
    )
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject=_SUBJECT,
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_EMA_ID,
        source_locator=locator,
        evidence_text=NormalizedEvidenceText(
            original_text=_EMA_VERBATIM,
            normalized_text="EMA/HMPC recognizes Valeriana officinalis radix for relief of sleep disorders, overlapping the insomnia question.",
            transformation_type=TransformationType.VERBATIM,
            transformation_version="case022-ema-verbatim-v1",
            source_locator=locator,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "The official EMA monograph and EMA public page identify Valeriana officinalis L., radix "
                "and recognize use for sleep disorders. The case narrows the benchmark question to insomnia."
            ),
            extractor_type="human_curator",
            extractor_version="case022-cross-rank-curation-v1",
        ),
    )


def build_gold_case_refgrounded_022_valeriana_cross_rank_precedence() -> GoldCase:
    unit = _build_unit()

    sr = _build_sr_reference()
    sr_gref = GoldCaseReference(reference=sr, claims=[_build_sr_claim()])
    sr_gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        sr, unit, ReferenceDomain.INDICATION_EVIDENCE
    )

    ema = _build_ema_reference()
    ema_gref = GoldCaseReference(reference=ema, claims=[_build_ema_claim()])
    ema_gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        ema, unit, ReferenceDomain.INDICATION_EVIDENCE
    )

    case = GoldCase(
        case_id="refgrounded_022_valeriana_cross_rank_precedence",
        validation_unit=unit,
        references=[sr_gref, ema_gref],
        engine_evidence=[],
        engine_evidence_origin=None,
        risk_strata=[],
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        locked=False,
    )
    return replace(case, resolved_outcomes=resolve_expected_outcomes(case))


if __name__ == "__main__":
    c = build_gold_case_refgrounded_022_valeriana_cross_rank_precedence()
    print(c.case_id)
    for o in c.resolved_outcomes:
        print(
            o.domain.value,
            o.assertion_type.value,
            o.assertion_state,
            o.resolution_status.value,
            o.selected_reference_id,
            o.conflicting_reference_ids,
        )
