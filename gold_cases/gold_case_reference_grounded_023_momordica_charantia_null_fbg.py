"""Gold Case 023 — Momordica charantia, standalone null human evidence.

Coverage objective
------------------
Close the standalone NULL_HUMAN_EVIDENCE gap with one real, independently
verified systematic review/meta-analysis, without changing production logic.

Critical source
---------------
Laczkó-Zöld E, Csupor-Löffler B, Kolcsár E-B, et al. The metabolic effect of
Momordica charantia cannot be determined based on the available clinical
evidence: a systematic review and meta-analysis of randomized clinical trials.
Front Nutr. 2024;10:1200801. PMID 38274207. PMCID PMC10808600.
DOI 10.3389/fnut.2023.1200801.

Scope discipline
----------------
The source reports multiple metabolic outcomes. This Gold Case deliberately
benchmarks only fasting blood glucose (FBG), where the change-score meta-analysis
reported no statistically significant effect versus placebo (MD -0.03; 95% CI
-0.38 to 0.31). It does not generalize that null result to every metabolic
endpoint, dose, preparation, or population.

Assertion semantics
-------------------
The repository has no dedicated NULL AssertionState. For an INDICATION_EVIDENCE
claim phrased as SUPPORTS_INDICATION, a statistically null result is represented
as AssertionState.ABSENT. The benchmark metadata separately labels this case as
NULL_STATISTICAL_RESULT so it is not conflated with evidence of harm or a
negative-direction effect.
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

_SUBJECT = "reduction of fasting blood glucose"
_SR_ID = "PUBMED_38274207_LACZKO_ZOLD_2024_MOMORDICA_FBG_META"
_SR_CITATION = (
    "Laczkó-Zöld E, Csupor-Löffler B, Kolcsár E-B, Ferenci T, Nan M, Tóth B, Csupor D. "
    "The metabolic effect of Momordica charantia cannot be determined based on the available clinical evidence: "
    "a systematic review and meta-analysis of randomized clinical trials. Front Nutr. 2024;10:1200801. "
    "PMID:38274207. PMCID:PMC10808600. DOI:10.3389/fnut.2023.1200801."
)
# Short source excerpt kept below 25 words; quantitative details are recorded in
# the locator/confidence basis rather than expanding the verbatim quotation.
_SR_VERBATIM = (
    "no significant effect could be observed for bitter melon treatment over placebo on fasting blood glucose level"
)


def _build_unit() -> ValidationUnit:
    return ValidationUnit(
        taxon="Momordica charantia L.",
        taxon_synonyms=["bitter melon"],
        plant_part=None,
        preparation=None,
        dose=None,
        duration=None,
        route_of_administration=None,
        indication=_SUBJECT,
        population=None,
        jurisdiction=None,
    )


def _build_reference() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_SR_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_SR_CITATION,
        document_date=date(2024, 1, 11),
        jurisdiction=None,
        taxon="Momordica charantia L.",
        plant_part=None,
        preparation=None,
        population=None,
        claim_type=None,
        indication_scope=[_SUBJECT],
        route_scope=[],
        retracted_or_superseded=False,
    )


def _build_claim() -> ReferenceClaim:
    locator = (
        "PubMed PMID 38274207, abstract Results, fasting blood glucose change-score meta-analysis; "
        "MD -0.03, 95% CI -0.38 to 0.31"
    )
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject=_SUBJECT,
        assertion_state=AssertionState.ABSENT,
        severity=None,
        source_reference_id=_SR_ID,
        source_locator=locator,
        evidence_text=NormalizedEvidenceText(
            original_text=_SR_VERBATIM,
            normalized_text=(
                "The meta-analysis found no statistically significant fasting-blood-glucose benefit "
                "of Momordica charantia over placebo."
            ),
            transformation_type=TransformationType.VERBATIM,
            transformation_version="case023-null-fbg-verbatim-v1",
            source_locator=locator,
        ),
        extraction_confidence=ExtractionConfidence(
            level=ExtractionConfidenceLevel.HIGH,
            basis=(
                "PubMed PMID 38274207 identifies the article as a systematic review/meta-analysis of randomized "
                "human trials and reports the fasting-blood-glucose change-score estimate as MD -0.03 with "
                "95% CI -0.38 to 0.31 versus placebo. No dose, preparation, plant part, or population detail is "
                "invented for this benchmark."
            ),
            extractor_type="human_curator",
            extractor_version="case023-null-human-evidence-curation-v1",
        ),
    )


def build_gold_case_refgrounded_023_momordica_charantia_null_fbg() -> GoldCase:
    unit = _build_unit()
    ref = _build_reference()
    gref = GoldCaseReference(reference=ref, claims=[_build_claim()])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        ref, unit, ReferenceDomain.INDICATION_EVIDENCE
    )

    case = GoldCase(
        case_id="refgrounded_023_momordica_charantia_null_fbg",
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
    c = build_gold_case_refgrounded_023_momordica_charantia_null_fbg()
    print(c.case_id)
    for o in c.resolved_outcomes:
        print(o.domain.value, o.assertion_type.value, o.assertion_state, o.resolution_status.value, o.selected_reference_id)
