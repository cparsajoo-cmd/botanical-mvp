"""Gold Case 021 — Serenoa repens, genuine same-rank systematic-review conflict.

Coverage objective
------------------
Close the corpus gap for a REAL multi-reference precedence conflict without
changing production logic. Two independently published SYSTEMATIC_REVIEW
sources address the same clinical question and reach opposing conclusions.

Critical sources
----------------
1) Wilt TJ, Ishani A, Stark G, MacDonald R, Lau J, Mulrow C. Saw palmetto
   extracts for treatment of benign prostatic hyperplasia: a systematic
   review. JAMA. 1998;280(18):1604-1609. PMID 9820264.
   DOI 10.1001/jama.280.18.1604.
   The review reported improvement in urinary symptoms/flow measures.

2) Franco JVA, Trivisonno L, Sgarbossa NJ, et al. Serenoa repens for the
   treatment of lower urinary tract symptoms due to benign prostatic
   enlargement. Cochrane Database Syst Rev. 2023;6:CD001423.
   DOI 10.1002/14651858.CD001423.pub4.
   The review concluded that Serenoa repens alone provides little to no
   benefit for lower urinary tract symptoms.

Both are represented as SYSTEMATIC_REVIEW because that is the repository's
approved precedence vocabulary for indication evidence. Neither source is
marked retracted or formally superseded. The architecture therefore must not
silently select one: equally-ranked applicable references with opposing
verdicts resolve to REFERENCE_CONFLICT.

Scope discipline
----------------
The case does not invent a standardized preparation, dose, route, or duration.
The ValidationUnit is intentionally broad enough to match the overlap actually
supported by both reviews: Serenoa repens in men with lower urinary tract
symptoms due to benign prostatic enlargement.
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

_SUBJECT = "lower urinary tract symptoms due to benign prostatic enlargement"

_WILT_ID = "PUBMED_9820264_WILT_1998_SERENOA_BPH_SR"
_WILT_CITATION = (
    "Wilt TJ, Ishani A, Stark G, MacDonald R, Lau J, Mulrow C. "
    "Saw palmetto extracts for treatment of benign prostatic hyperplasia: "
    "a systematic review. JAMA. 1998;280(18):1604-1609. "
    "DOI:10.1001/jama.280.18.1604. PMID:9820264."
)
_WILT_EXCERPT = "The evidence suggests that S repens improves urologic symptoms and flow measures."

_FRANCO_ID = "COCHRANE_CD001423_2023_FRANCO_SERENOA_LUTS"
_FRANCO_CITATION = (
    "Franco JVA, Trivisonno L, Sgarbossa NJ, Alvez GA, Fieiras C, "
    "Escobar Liquitay CM, Jung JH. Serenoa repens for the treatment of "
    "lower urinary tract symptoms due to benign prostatic enlargement. "
    "Cochrane Database Syst Rev. 2023;6:CD001423. "
    "DOI:10.1002/14651858.CD001423.pub4."
)
_FRANCO_EXCERPT = (
    "Serenoa repens alone provides little to no benefits for men with lower urinary tract symptoms "
    "due to benign prostatic enlargement."
)


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Serenoa repens",
        taxon_synonyms=["Sabal serrulatum"],
        plant_part="berry",
        preparation=None,
        dose=None,
        duration=None,
        route_of_administration=None,
        indication=_SUBJECT,
        population="Men with lower urinary tract symptoms due to benign prostatic enlargement",
        jurisdiction=None,
    )


def _build_wilt_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_WILT_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_WILT_CITATION,
        document_date=date(1998, 11, 11),
        jurisdiction=None,
        taxon="Serenoa repens",
        # The PubMed abstract does not itself provide a load-bearing plant-part
        # field; leave it unspecified rather than borrowing the newer review's
        # explicit berry wording.
        plant_part=None,
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[_SUBJECT],
        route_scope=[],
        retracted_or_superseded=False,
    )


def _build_franco_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_FRANCO_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_FRANCO_CITATION,
        document_date=date(2023, 6, 22),
        jurisdiction=None,
        taxon="Serenoa repens",
        plant_part="berry",
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[_SUBJECT],
        route_scope=[],
        retracted_or_superseded=False,
    )


def _build_wilt_claim() -> ReferenceClaim:
    locator = "PubMed PMID 9820264, abstract conclusion"
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject=_SUBJECT,
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=_WILT_ID,
        source_locator=locator,
        evidence_text=NormalizedEvidenceText(
            original_text=_WILT_EXCERPT,
            normalized_text="Serenoa repens supports improvement of urinary symptoms in symptomatic BPH.",
            transformation_type=TransformationType.VERBATIM,
            transformation_version="case021-wilt-verbatim-v1",
            source_locator=locator,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "Bibliographic metadata and the short conclusion excerpt were verified against "
                "the PubMed record for PMID 9820264. The case does not infer a specific dose or preparation."
            ),
            extractor_type="human_curator",
            extractor_version="case021-conflict-curation-v1",
        ),
    )


def _build_franco_claim() -> ReferenceClaim:
    locator = (
        "Cochrane evidence page for CD001423, Authors' conclusions; "
        "https://www.cochrane.org/evidence/CD001423_serenoa-repens-benign-prostatic-hyperplasia"
    )
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject=_SUBJECT,
        assertion_state=AssertionState.ABSENT,
        severity=None,
        source_reference_id=_FRANCO_ID,
        source_locator=locator,
        evidence_text=NormalizedEvidenceText(
            original_text=_FRANCO_EXCERPT,
            normalized_text="Serenoa repens does not provide clinically meaningful benefit for LUTS due to benign prostatic enlargement.",
            transformation_type=TransformationType.VERBATIM,
            transformation_version="case021-franco-verbatim-v1",
            source_locator=locator,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "The Cochrane public evidence page directly states the review question, study population, "
                "high/moderate certainty for Serenoa repens alone, and the quoted authors' conclusion."
            ),
            extractor_type="human_curator",
            extractor_version="case021-conflict-curation-v1",
        ),
    )


def build_gold_case_refgrounded_021_serenoa_repens_reference_conflict() -> GoldCase:
    unit = _build_unit()

    wilt = _build_wilt_reference()
    wilt_gref = GoldCaseReference(reference=wilt, claims=[_build_wilt_claim()])
    wilt_gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        wilt, unit, ReferenceDomain.INDICATION_EVIDENCE
    )

    franco = _build_franco_reference()
    franco_gref = GoldCaseReference(reference=franco, claims=[_build_franco_claim()])
    franco_gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        franco, unit, ReferenceDomain.INDICATION_EVIDENCE
    )

    case = GoldCase(
        case_id="refgrounded_021_serenoa_repens_reference_conflict",
        validation_unit=unit,
        references=[wilt_gref, franco_gref],
        engine_evidence=[],
        engine_evidence_origin=None,
        risk_strata=[],
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        locked=False,
    )
    return replace(case, resolved_outcomes=resolve_expected_outcomes(case))


if __name__ == "__main__":
    c = build_gold_case_refgrounded_021_serenoa_repens_reference_conflict()
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
