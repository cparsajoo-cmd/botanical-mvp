"""
Reference-Grounded Validation — Phase 4, Case 004.

WHAT THIS IS
The third real (kind=GoldCaseKind.REFERENCE_GROUNDED) case built under
VALIDATION_PROTOCOL.md v0.3. First case in this program targeting a
domain OTHER than the sleep-tea family (cognitive impairment, not
sleep), first case using EMA_HMPC's WELL-ESTABLISHED-USE column rather
than traditional-use, and first case whose governing systematic review
was published (2026) after the cutoff of this file's own construction
date.

CASE SCOPE (Protocol §4)
Taxon:      Ginkgo biloba L. (Ginkgo leaf)
Domain:     ReferenceDomain.INDICATION_EVIDENCE
Assertion:  AssertionType.SUPPORTS_INDICATION, subject="cognitive impairment"
Protocol Version (Case Template row 2 — no native field): v0.3.
Scientific Question (Case Template row 3 — no native field):
    "Does the reference-grounded resolved outcome for Ginkgo biloba L.
    in domain Indication/Evidence (Supports indication) for 'cognitive
    impairment', under population Adults and elderly / route Oral /
    preparation Extract (DER 35-67:1, acetone 60% m/m) / jurisdiction
    EU, agree with the decision the engine produces when given
    equivalent, independently curator-supplied evidence?"

SOURCE-PRECEDENCE CHECK (Protocol §6/§9.3 — documented before any
engine output; also before Ground Truth extraction, since it
determines WHICH document governs)
Two real, accessible systematic reviews were identified and compared:

  1. Wieland LS, Ludeman E, Chi Y, Feinberg TM, Chen I-H, Chen K-H, Zhu
     Y, Wolverson E, Amri H (2026). "Ginkgo biloba for cognitive
     impairment and dementia." Cochrane Database of Systematic
     Reviews, Issue 2. Art. No. CD013661. DOI 10.1002/14651858.
     CD013661.pub2. Published 5 February 2026. 82 RCTs, 10,613
     participants, evidence current to November 2024, GRADE-rated
     certainty per outcome, produced by the Cochrane Dementia and
     Cognitive Improvement Group. VERIFIED DIRECTLY: the full Key
     Messages, Main Results (broken out by four clinical subgroups),
     and Authors' Conclusions sections were fetched in full from
     Cochrane's own freely accessible evidence page (not paywalled —
     the "what are the benefits and risks" plain-language page, distinct
     from the technical review behind Cochrane Library's institutional
     login) — not inferred from secondary press coverage.
  2. Chan E, et al. (~2014), a smaller systematic review/meta-analysis
     specific to the standardized extract EGb761 (9 trials, 2,561
     participants), concluding a more uniformly positive effect on
     cognition/function/behavior at 22-26 weeks. Real and PubMed-
     abstract-accessible. NOT selected as governing: it is older, an
     order of magnitude smaller (9 vs 82 trials), predates the most
     recent decade of trial evidence entirely, and does not
     GRADE-rate certainty per outcome the way the 2026 Cochrane review
     does. This is a resolvable preference on stated methodological
     grounds (recency, comprehensiveness, review-group rigor) — not an
     unresolved precedence conflict. Protocol §6 does not currently
     name an explicit tiebreaker between two same-rank systematic
     reviews; this case's resolution is documented here as a reasoned
     judgment, not as a claim that no judgment was required.

Result: Wieland et al. 2026 selected as the governing source —
SYSTEMATIC_REVIEW, correctly outranking EMA_HMPC (Section 6), the same
structural pattern as Case 003.

WHY subject="cognitive impairment", NOT "dementia" OR THE COMBINED EMA
INDICATION
EMA/HMPC/321097/2012's well-established-use indication text combines
TWO conditions in one sentence: "(age-associated) cognitive
impairment" AND "quality of life in mild dementia." The governing
systematic review does NOT treat these as one undifferentiated
population — it reports four separate, clearly distinguished clinical
subgroups (subjective cognitive complaints; multiple-sclerosis-related
impairment; mild cognitive impairment; dementia), each with its own
result and certainty rating. Per Protocol §4 ("exactly one primary
assertion... never several claims bundled into one case"), this case
targets ONLY the "cognitive impairment" component — matching the
review's own "Mild cognitive impairment" subgroup, moderate-certainty
evidence, its most confidently-rated subgroup after the dementia
result — not the review's separate "dementia" subgroup finding, and
not an averaged/blended reading across both. This choice was made
because "cognitive impairment" is the first-named, primary condition
in the EMA indication text and because the MCI subgroup carries the
review's clearest, most certain single-direction verdict — not because
of which AssertionState it happens to produce (see next section).

VERBATIM EXTRACTION — GOVERNING SOURCE
Reference claim's evidence_text is the exact "Authors' conclusions"
sentence for the MCI subgroup, copied verbatim from the review's own
freely accessible Cochrane evidence page (fetched directly, in full,
not paraphrased): "In people with MCI, ginkgo probably has little or
no effect at six months on global status, cognition, or ADLs."

WHY assertion_state=ABSENT
The review's MCI-subgroup Main Results state, at moderate-certainty
evidence, no meaningful difference from placebo on global clinical
status, cognition, or activities-of-daily-living measures — a clean,
single-direction (not internally mixed, unlike Case 003's chamomile
finding) negative result. AssertionState.ABSENT is used rather than
CONDITIONAL because this is not a partial/qualified finding on
multiple different outcome types pointing different directions — it is
one consistent "little or no effect" verdict across all three
MCI-subgroup outcomes measured. This was the honestly-reasoned
consequence of the subject selection above, not a criterion used to
choose that subject — see the "WHY subject=" note: the choice of MCI
over dementia was made on primacy/certainty-of-evidence grounds before
either subgroup's resulting AssertionState was used as a selection
criterion.

APPLICABILITY LIMITATIONS — RECORDED HONESTLY, NOT RESOLVED
1. PREPARATION IS NOT AN INFUSION, UNLIKE CASES 001/003: the
   well-established-use pathway is EXCLUSIVELY a standardized dry
   extract (DER 35-67:1, acetone 60% m/m extraction solvent, per Ph.
   Eur. monograph 1827/1828) — there is no infusion/tea option for
   this indication (that only exists under the monograph's SEPARATE
   traditional-use indication, which is for circulatory symptoms, not
   cognition, and is therefore out of scope for this claim).
   ReferenceDescriptor.preparation is set to this exact extract
   specification, not to Infusion/water.
2. INDICATION SCOPE-MATCHING JUDGMENT: as documented above, this case
   targets one of four subgroups the governing review itself
   distinguishes. A future curator reading only the EMA monograph's
   combined indication text, without also reading the governing
   review's own subgroup structure, could reasonably assume "cognitive
   impairment" and "mild dementia" are addressed identically — they
   are not, per the review's own data. This is a real scope-precision
   requirement this case exists partly to surface, not a resolved
   non-issue.
3. PASS-BY-ABSENCE PRINCIPLE (established in Case 003, applies here
   too): where any applicability dimension passes because a reference
   field was left unspecified rather than because equivalence was
   verified, that pass must never later be read as a confirmed match.

WHAT THIS FILE DELIBERATELY DOES NOT DO (per explicit instruction)
- Does not construct or infer any EngineEvidenceInput.
- Does not call gold_case_execution.execute_gold_case_against_engine()
  or execute_gold_case_with_readiness_gate(), and does not run or
  instantiate BotanicalRDCandidateEngine.
- Does not call lock_gold_case().
- Does not modify botanical_rd_candidate_engine.py or any other
  existing file, and does not touch Cases 001-003.

DOCUMENTED EXECUTION STATUS: DEFERRED — 2026-07-29
Same convention as Cases 001/003: Ground Truth complete and valid;
execution deferred because no independent Engine Evidence has been
drafted yet. Re-evaluate for execution only once Engine Evidence is
independently sourced and dimension-assessed, per Protocol §9.1/§14.6.
"""

from __future__ import annotations

from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus,
    ExtractionConfidenceLevel, GoldCaseKind, TransformationType,
)
from field_provenance import FieldProvenance, VerificationStatus
from gold_case import GoldCase, GoldCaseReference
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit

# --- Real reference-source metadata (Wieland et al. 2026) -------------------
_SR_REFERENCE_ID = "COCHRANE_CD013661_2026_Wieland_ginkgo_cognitive"
_SR_CITATION = (
    "Wieland LS, Ludeman E, Chi Y, Feinberg TM, Chen I-H, Chen K-H, Zhu Y, "
    "Wolverson E, Amri H (2026). Ginkgo biloba for cognitive impairment and "
    "dementia. Cochrane Database of Systematic Reviews, Issue 2. Art. No. "
    "CD013661. DOI 10.1002/14651858.CD013661.pub2."
)
_SR_DOCUMENT_DATE = date(2026, 2, 5)
_SR_LOCATOR = (
    "Authors' conclusions, Mild cognitive impairment subgroup sentence — "
    "Wieland et al. 2026, Cochrane Database of Systematic Reviews, "
    "Issue 2, Art. No. CD013661"
)
_EXTRACTION_DATE = date(2026, 7, 29)

# Verbatim, complete sentence from the review's own Authors' Conclusions
# section, MCI subgroup — fetched directly from Cochrane's freely
# accessible evidence page, not paraphrased.
_SR_MCI_CONCLUSION_VERBATIM = (
    "In people with MCI, ginkgo probably has little or no effect at "
    "six months on global status, cognition, or ADLs."
)

# --- Real reference-source metadata (EMA/HMPC/321097/2012) -----------------
_EMA_REFERENCE_ID = "EMA_HMPC_321097_2012_ginkgo_biloba_folium"
_EMA_DOCUMENT_TITLE = "European Union herbal monograph on Ginkgo biloba L., folium"
_EMA_DOCUMENT_VERSION = "Final, adopted by HMPC 28 January 2015 (EMA/HMPC/321097/2012)"
_EMA_DOCUMENT_DATE = date(2015, 1, 28)
_EMA_INDICATION_LOCATOR = (
    "Section 4.1 'Therapeutic indications', Well-established use column — "
    "EMA/HMPC/321097/2012, p.2/8"
)


def _ginkgo_extract_preparation() -> PreparationSpec:
    """The well-established-use pathway's ONLY preparation — a
    standardized dry extract, not an infusion. Shared between the
    ReferenceDescriptor and ValidationUnit so they cannot silently
    diverge (same convention established for Case 001)."""
    return PreparationSpec(
        dosage_form="Extract",
        solvent="acetone 60% m/m",
        der_min=35.0,
        der_max=67.0,
        source_status="concentrated",
    )


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_SR_REFERENCE_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_SR_CITATION,
        document_date=_SR_DOCUMENT_DATE,
        jurisdiction=None,  # international literature synthesis, not jurisdiction-bound
        taxon="Ginkgo biloba L.",
        plant_part="leaf",
        preparation=_ginkgo_extract_preparation(),
        population="Adults and elderly",
        claim_type="well-established-use",
        indication_scope=["Cognitive decline / Alzheimer's support"],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim(reference: ReferenceDescriptor) -> ReferenceClaim:
    evidence_text = NormalizedEvidenceText(
        original_text=_SR_MCI_CONCLUSION_VERBATIM,
        normalized_text=_SR_MCI_CONCLUSION_VERBATIM,
        transformation_type=TransformationType.VERBATIM,
        transformation_version="verbatim-extraction-v1",
        source_locator=_SR_LOCATOR,
    )
    extraction_confidence = ExtractionConfidence(
        level=ExtractionConfidenceLevel.HIGH,
        basis=(
            "Verbatim excerpt taken directly from the 'Authors' conclusions' "
            "section of Cochrane's own freely accessible evidence page for "
            "CD013661 (not the paywalled full technical review, and not a "
            "secondary press paraphrase) — full Key Messages, Main Results by "
            "subgroup, and Authors' Conclusions were fetched and read in full "
            "before this excerpt was selected."
        ),
        extractor_type="hybrid",
        extractor_version="claude-assisted-extraction-v1",
    )
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="cognitive impairment",
        assertion_state=AssertionState.ABSENT,
        severity=None,
        source_reference_id=reference.reference_id,
        source_locator=_SR_LOCATOR,
        evidence_text=evidence_text,
        extraction_confidence=extraction_confidence,
    )


def _build_case_provenance() -> list:
    return [
        FieldProvenance(
            document_id=_SR_REFERENCE_ID,
            document_version=_SR_CITATION,
            locator=_SR_LOCATOR,
            supported_field="resolved_outcomes[domain=Indication/Evidence, subject='cognitive impairment']",
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
        FieldProvenance(
            document_id=_EMA_REFERENCE_ID,
            document_version=_EMA_DOCUMENT_VERSION,
            locator=_EMA_INDICATION_LOCATOR,
            supported_field=(
                "validation_unit.preparation (Extract, DER 35-67:1, acetone "
                "60% m/m) and .population ('Adults and elderly') — the EMA "
                "monograph's own well-established-use posology, not the "
                "governing Ground Truth claim itself"
            ),
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
    ]


def build_gold_case_refgrounded_004_ginkgo_biloba_cognitive() -> GoldCase:
    """Builds the case through resolved_outcomes only. Returns an
    UNLOCKED GoldCase (locked=False); lock_gold_case() is intentionally
    never called here. EngineEvidenceInput collection is a separate,
    later, independently-decided step (Leakage Rule 9.1), not started
    in this file.
    """
    unit = ValidationUnit(
        taxon="Ginkgo biloba L.",
        plant_part="leaf",
        preparation=_ginkgo_extract_preparation(),
        population="Adults and elderly",
        route_of_administration="Oral",
        # Platform-vocabulary mapping, not a term drawn from either
        # source verbatim.
        indication="Cognitive decline / Alzheimer's support",
        jurisdiction="EU",
    )

    reference = _build_reference_descriptor()
    claim = _build_reference_claim(reference)

    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        reference, unit, ReferenceDomain.INDICATION_EVIDENCE,
    )

    case = GoldCase(
        case_id="refgrounded_004_ginkgo_biloba_cognitive",
        validation_unit=unit,
        risk_strata=[],  # no RiskStratum value cleanly fits a clean-negative single-subgroup finding; see Case 003's precedent for not force-fitting one
        references=[gref],
        case_provenance=_build_case_provenance(),
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        # engine_evidence intentionally left empty; engine_evidence_origin
        # intentionally left None.
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


if __name__ == "__main__":
    built_case = build_gold_case_refgrounded_004_ginkgo_biloba_cognitive()
    print(f"case_id: {built_case.case_id}")
    print(f"locked: {built_case.locked}")
    for outcome in built_case.resolved_outcomes:
        print(
            f"domain={outcome.domain.value!r} subject={outcome.subject!r} "
            f"assertion_type={outcome.assertion_type.value!r} "
            f"resolution_status={outcome.resolution_status.value!r} "
            f"selected_reference_id={outcome.selected_reference_id!r} "
            f"assertion_state={outcome.assertion_state}"
        )
