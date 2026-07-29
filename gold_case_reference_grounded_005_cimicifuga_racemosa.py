"""
Reference-Grounded Validation — Phase 5, Case 005.

WHAT THIS IS
The fourth real (kind=GoldCaseKind.REFERENCE_GROUNDED) case built under
VALIDATION_PROTOCOL.md v0.3. First case in this program with
assertion_state=AssertionState.INSUFFICIENT — closing a real coverage
gap (INSUFFICIENT/NOT_STATED were previously untested by any Gold
Case), and first case whose source-suitability screening surfaced an
unresolved same-rank systematic-review conflict, a taxonomy caveat,
and a quantitative dose-unit discrepancy — all recorded honestly below
rather than smoothed over. This case does NOT produce a whole-case
decision_direction_agreement measurement (see "WHY NOT_ELIGIBLE" below)
and is not offered as one.

CASE SCOPE (Protocol §4)
Taxon:      Cimicifuga racemosa (L.) Nutt. (syn. Actaea racemosa L.) —
            black cohosh, rhizome
Domain:     ReferenceDomain.INDICATION_EVIDENCE
Assertion:  AssertionType.SUPPORTS_INDICATION, subject="menopausal symptoms"
Protocol Version (Case Template row 2 — no native field): v0.3.
Scientific Question (Case Template row 3 — no native field):
    "Does the reference-grounded resolved outcome for Cimicifuga
    racemosa (L.) Nutt. in domain Indication/Evidence (Supports
    indication) for 'menopausal symptoms', under population Female
    adults / route Oral / preparation Extract (DER 4.5-8.5:1, ethanol
    60% V/V) / jurisdiction EU, agree with the decision the engine
    produces when given equivalent, independently curator-supplied
    evidence?"
    NOTE: because assertion_state=INSUFFICIENT maps to no
    DecisionDirection (agreement_eligibility.map_assertion_state_to_
    direction() returns None for INSUFFICIENT), this Scientific
    Question is UNANSWERABLE by design under the current protocol —
    the case exists to verify the platform recognizes that honestly
    (NOT_ELIGIBLE, ASSERTION_STATE_UNMAPPED), not to produce an
    answer to it.

SOURCE-PRECEDENCE CHECK (Protocol §6/§9.3 — documented before any
engine output; also before Ground Truth extraction)
Real, accessible reviews compared (full search record and comparison
table produced during source-suitability screening; summarized here):

  1. Leach MJ, Moore V (2012). "Black cohosh (Cimicifuga spp.) for
     menopausal symptoms." Cochrane Database of Systematic Reviews,
     Issue 9. Art. No. CD007244. DOI 10.1002/14651858.CD007244.pub2.
     16 RCTs, 2027 women, search to March 2012. Eligibility restricted
     to orally administered MONOPREPARATIONS of black cohosh only
     (explicit exclusion of combination products) compared to placebo
     or active medication. VERIFIED DIRECTLY: the free plain-language
     evidence page (cochrane.org/evidence/CD007244_...) and the
     structured public abstract (search strategy, selection criteria,
     main results, authors' conclusions) were fetched in full — not
     the paywalled full technical review with its Characteristics of
     Included Studies table (see taxonomy/dose caveats below for what
     that gap means in practice).
  2. Sadahiro R, Matsuoka LN, Zeng BS, et al. (2023). "Black cohosh
     extracts in women with menopausal symptoms: an updated pairwise
     meta-analysis." Menopause 30(7):766-773. DOI 10.1097/GME.
     0000000000002196. 22 articles, 2310 women. Real, peer-reviewed,
     more recent and larger than CD007244, and finds a SIGNIFICANT
     POSITIVE effect on overall menopausal symptoms (Hedges' g=0.575,
     P<0.001) and hot flashes (g=0.315, P=0.003) — the opposite
     direction from Cochrane. NOT selected as governing, on a
     disclosed methodological ground, not recency or "Cochrane brand"
     alone: its own abstract states the pooled intervention is "black
     cohosh extract both alone OR COMBINED WITH OTHER RELATED ACTIVE
     INGREDIENTS" — i.e. combination products are pooled together with
     monotherapy, which is exactly the confound Cochrane's own
     eligibility criteria (monopreparations only) was designed to
     exclude. Because this case's taxon/claim is specifically about
     Cimicifuga racemosa alone, a review that cannot cleanly separate
     monotherapy effect from combination-product effect is weaker
     evidence for THIS specific claim, despite being larger and more
     recent. This is a documented, reasoned judgment on a genuine,
     UNRESOLVED same-rank conflict — not a claim that no real tension
     exists. A future case or protocol revision may reconsider this.
     I did not obtain Sadahiro et al.'s full text (behind Wolters
     Kluwer/Ovid paywall); only the public abstract was verified.
  3. Shams T et al. (2010, Altern Ther Health Med) and Borrelli F,
     Ernst E (2008, Pharmacol Res) — both predate CD007244's own
     search date and are effectively superseded by it on
     recency/comprehensiveness grounds (same logic as Case004's
     Chan-2014-vs-Wieland-2026 exclusion, applied in the opposite
     temporal direction). Not live same-rank competitors.
  4. Ismail R et al. (2015, Climacteric) — a systematic review of
     multiple different herbal preparations for menopausal symptom
     clusters, not black-cohosh-specific. Excluded on the same
     relevance ground Case 001 used to exclude Ghazizadeh 2021
     (Protocol §6 compares "same taxon, indication, and primary
     assertion" — this review's primary subject is multi-herb, not
     Cimicifuga racemosa alone).
  5. Beer AM et al. (2013, Gynecol Endocrinol) — a published critical
     commentary/reanalysis responding to CD007244, not an independent
     systematic review. Not same-rank; recorded only as evidence that
     real methodological disagreement about CD007244 exists in the
     literature.

Result: Cochrane CD007244 selected as governing — SYSTEMATIC_REVIEW,
outranking EMA_HMPC (Section 6), consistent with Cases 003/004 —
WITH THE SADAHIRO 2023 CONFLICT EXPLICITLY UNRESOLVED, not hidden.

WHY subject="menopausal symptoms" (umbrella), NOT "hot flushes"
Unlike Case004's Ginkgo review (which reported four separately-
concluded clinical subgroups), CD007244's Authors' Conclusions is ONE
undifferentiated sentence sitting on top of two separately-reported,
consistently null, same-direction quantitative outcomes (hot-flush
frequency: MD 0.07/day, P=0.79, 3 trials, 393 women; menopausal
symptom score: SMD -0.10, P=0.34, 4 trials, 357 women). Narrowing the
claim to "hot flushes" alone would require inventing an outcome-
specific conclusion sentence CD007244 never itself wrote as its
headline verdict — a fabrication this program does not permit.
"menopausal symptoms" is the level at which the review's own Authors'
Conclusions is actually stated.

VERBATIM EXTRACTION — GOVERNING SOURCE
Reference claim's evidence_text is the exact Authors' Conclusions
sentence, copied verbatim from Cochrane's own freely accessible
evidence page (fetched directly, in full, not paraphrased): "There is
currently insufficient evidence to support the use of black cohosh for
menopausal symptoms."

WHY assertion_state=INSUFFICIENT (not ABSENT, not CONDITIONAL)
This is CD007244's own stated epistemic verdict — "insufficient
evidence," not "evidence of no effect" (which would be ABSENT, as in
Case004) and not a partial/qualified finding pointing different
directions on different outcomes (which would be CONDITIONAL, as in
Case003). Both of CD007244's own pooled outcomes point the same
(null) direction, but the review characterizes this as inadequate
evidence quality/quantity to conclude either way, not as an
established negative finding — hence INSUFFICIENT.

WHY NOT_ELIGIBLE (Protocol v0.3 AssertionState mapping)
agreement_eligibility.map_assertion_state_to_direction() returns None
for AssertionState.INSUFFICIENT — deliberately, "nothing to map, the
source never gave a usable answer" (see that function's own
docstring). assess_agreement_eligibility() therefore returns
AgreementEligibility.NOT_ELIGIBLE with reason=
ASSERTION_STATE_UNMAPPED for this case. This is NOT this case "filling
an agreement gap" — it produces no whole-case decision-direction
agreement measurement at all. Its benchmark value is narrower and
different: verifying the platform's fail-closed mapping behavior and
its refusal to invent an expected direction where the source itself
did not supply one.

APPLICABILITY LIMITATIONS — RECORDED HONESTLY, NOT RESOLVED
1. DIRECT TAXONOMY COMPARABILITY: NO / UNVERIFIED AT TRIAL LEVEL.
   CD007244's own title uses the genus-level "Cimicifuga spp.", and
   its Objectives text restricts the definition to "Cimicifuga
   racemosa or Actaea racemosa" — but I could not fetch the paywalled
   Characteristics of Included Studies table to confirm all 16
   individual included trials actually used C. racemosa/A. racemosa
   material specifically (other Cimicifuga species, e.g. C. foetida,
   are independently studied elsewhere in the literature, so this is
   a real possibility, not a pedantic one). Per Case003's precedent
   and explicit instruction for this case, this is recorded as NO
   applicability-pass by verified equivalence — it is a genuine open
   item, not silently resolved by borrowing EMA's own (C. racemosa-
   only) taxonomy to narrow the review's scope after the fact.
2. PREPARATION EQUIVALENCE: UNVERIFIED. EMA/HMPC/48745/2017 well-
   established-use pathway defines THREE distinct extract
   preparations (DER 5-10:1 ethanol 58%; DER 4.5-8.5:1 ethanol 60%;
   DER 6-11:1 propan-2-ol 40%). ReferenceDescriptor.preparation below
   is set to the second of these (arbitrarily selected as the
   applicability-metadata anchor, not because it was shown to match
   what CD007244's trials used) — see TD-001, which this case
   reproduces in the same way Case004 did. CD007244 itself pooled
   trials using "various formulations" with no single declared DER;
   which (if any) of the three EMA preparations any given included
   trial used is NOT verified here.
3. DOSE EQUIVALENCE: PARTIALLY PLAUSIBLE AFTER DER CONVERSION, NOT
   CONFIRMED. The NIH ODS Health Professional Fact Sheet (an
   authoritative secondary source, fetched directly) states CD007244's
   16 trials used "various formulations of 8 to 160 mg/day black
   cohosh extract, with a median dose of 40 mg/day" — and separately
   notes this 40 mg figure for the commonly-used Remifemin product is
   expressed as "40 mg black cohosh root/rhizome" (crude-drug
   equivalent), not dry-extract mass. Converting each EMA preparation's
   dry-extract daily dose by its own stated DER range gives a rough
   crude-drug-equivalent band of roughly 28-56 mg/day for all three EMA
   preparations, which brackets the reported ~40 mg/day trial median.
   This makes the raw "40 mg vs 5-6.5 mg" figures look like they are
   largely a unit-of-expression artifact rather than proof of
   unrelated interventions. However: (a) the trials' actual 8-160
   mg/day RANGE is far wider than any single EMA DER conversion can
   cover, (b) NOT ALL of CD007244's pooled trials are established to
   have reported doses on a crude-drug-equivalent basis the way
   Remifemin's labeling does — I explicitly do NOT claim that all of
   CD007244's included doses were crude-drug equivalents, only that
   the commonly-cited Remifemin figure was, and (c) the individual
   per-trial DER/solvent data needed to confirm this systematically is
   in the paywalled full review. Recorded as PARTIALLY PLAUSIBLE, NOT
   CONFIRMED.
4. POPULATION EQUIVALENCE: UNVERIFIED. ValidationUnit.population
   ("Female adults") is EMA's own well-established-use posology
   language, not independently derived from CD007244's pooled trial
   population characteristics beyond the review's own general
   eligibility criterion ("perimenopausal and postmenopausal women").
5. ROUTE COMPARABILITY: Oral, on both sides — the one dimension with
   a clean, unqualified match (CD007244's eligibility criterion is
   explicitly "orally administered monopreparations"; EMA's route of
   administration is "Oral use").
6. INDICATION OVERLAP WITH EMA: PARTIAL, not equivalent. CD007244's
   own scope is the umbrella "menopausal symptoms." EMA/HMPC/48745/
   2017's indication text is narrower and more specific: "relief of
   menopausal complaints such as hot flushes and profuse sweating."
   The two overlap but are not coextensive; EMA's wording names a
   subset, not a synonym, of CD007244's broader scope.
7. EMA METADATA IS APPLICABILITY-ONLY, NEVER GROUND TRUTH. Every EMA-
   sourced field on this case's ReferenceDescriptor/ValidationUnit
   (preparation, population, indication wording) is provenance-tagged
   to EMA/HMPC/48745/2017 specifically, separately from the Cochrane-
   sourced Ground Truth provenance record. assertion_state,
   evidence_text, and selected_reference_id for the resolved outcome
   are 100% CD007244-derived; nothing from EMA enters the claim
   itself. This mirrors Case004/TD-001 exactly.
8. PASS-BY-ABSENCE PRINCIPLE (Case003/Case004 precedent, applies
   here too): where any applicability dimension passes because a
   reference field was left unspecified rather than because
   equivalence was actively verified, that pass must never later be
   read as a confirmed match.

WHAT THIS FILE DELIBERATELY DOES NOT DO (per explicit instruction)
- Does not construct or infer any EngineEvidenceInput.
- Does not call gold_case_execution.execute_gold_case_against_engine()
  or execute_gold_case_with_readiness_gate(), and does not run or
  instantiate BotanicalRDCandidateEngine.
- Does not call lock_gold_case().
- Does not modify botanical_rd_candidate_engine.py, VALIDATION_PROTOCOL.md,
  agreement_eligibility.py, or any other existing file, and does not
  touch Cases 001-004.
- Does not set GoldCase.expected_output.expected_decision_direction —
  there is no derivable direction for INSUFFICIENT (see "WHY
  NOT_ELIGIBLE" above); leaving it None is the honest state, not an
  oversight.

DOCUMENTED EXECUTION STATUS: DEFERRED — 2026-07-29
Ground Truth complete and valid; execution deferred because no
independent Engine Evidence has been drafted, and because this case's
own AssertionState makes whole-case decision-direction execution
inapplicable by design (see "WHY NOT_ELIGIBLE"). Re-evaluate only if a
future protocol revision changes how INSUFFICIENT/NOT_ELIGIBLE cases
are used in gate-level (not whole-case) evaluation, per Protocol
§9.1/§14.6.
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

# --- Real reference-source metadata (Leach & Moore, Cochrane CD007244) -----
_SR_REFERENCE_ID = "COCHRANE_CD007244_2012_Leach_black_cohosh_menopausal"
_SR_CITATION = (
    "Leach MJ, Moore V. Black cohosh (Cimicifuga spp.) for menopausal "
    "symptoms. Cochrane Database of Systematic Reviews 2012, Issue 9. "
    "Art. No.: CD007244. DOI: 10.1002/14651858.CD007244.pub2."
)
_SR_DOCUMENT_DATE = date(2012, 9, 12)
_SR_LOCATOR = (
    "Authors' conclusions section, free plain-language evidence page — "
    "cochrane.org/evidence/CD007244_black-cohosh-cimicifuga-spp-"
    "menopausal-symptoms (fetched directly; not the paywalled full "
    "technical review)"
)
# Verbatim Authors' Conclusions sentence — fetched directly from
# Cochrane's own freely accessible evidence page, not paraphrased.
_SR_CONCLUSION_VERBATIM = (
    "There is currently insufficient evidence to support the use of "
    "black cohosh for menopausal symptoms."
)

# --- Real reference-source metadata (EMA/HMPC/48745/2017) ------------------
_EMA_REFERENCE_ID = "EMA_HMPC_48745_2017_cimicifuga_racemosa_rhizoma"
_EMA_DOCUMENT_TITLE = (
    "European Union herbal monograph on Cimicifuga racemosa (L.) Nutt., rhizoma"
)
_EMA_DOCUMENT_VERSION = "Final, adopted by HMPC 27 March 2018 (EMA/HMPC/48745/2017, revision 1)"
_EMA_DOCUMENT_DATE = date(2018, 3, 27)
_EMA_INDICATION_LOCATOR = (
    "Section 4.1 'Therapeutic indications' and 4.2 'Posology', "
    "Well-established use column — EMA/HMPC/48745/2017, p.4-5/8"
)
_EXTRACTION_DATE = date(2026, 7, 29)


def _black_cohosh_ema_preparation_b() -> PreparationSpec:
    """One of THREE well-established-use preparations named in
    EMA/HMPC/48745/2017 (arbitrarily selected as the applicability-
    metadata anchor — see 'PREPARATION EQUIVALENCE: UNVERIFIED' above;
    this is not a claim that CD007244's trials used this specific
    preparation). Shared between the ReferenceDescriptor and
    ValidationUnit so they cannot silently diverge (Case001/Case004
    convention)."""
    return PreparationSpec(
        dosage_form="Extract",
        solvent="ethanol 60% (V/V)",
        der_min=4.5,
        der_max=8.5,
        source_status="concentrated",
    )


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_SR_REFERENCE_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_SR_CITATION,
        document_date=_SR_DOCUMENT_DATE,
        jurisdiction=None,  # international literature synthesis, not jurisdiction-bound
        taxon="Cimicifuga racemosa (L.) Nutt.",
        plant_part="rhizome",
        # NOTE: this PreparationSpec is EMA-sourced applicability
        # metadata, not something CD007244 itself specifies as a
        # single standardized preparation — see "PREPARATION
        # EQUIVALENCE: UNVERIFIED" in the module docstring and TD-001.
        preparation=_black_cohosh_ema_preparation_b(),
        population="Female adults",
        claim_type="well-established-use",
        indication_scope=["Menopause support"],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim(reference: ReferenceDescriptor) -> ReferenceClaim:
    evidence_text = NormalizedEvidenceText(
        original_text=_SR_CONCLUSION_VERBATIM,
        normalized_text=_SR_CONCLUSION_VERBATIM,
        transformation_type=TransformationType.VERBATIM,
        transformation_version="verbatim-extraction-v1",
        source_locator=_SR_LOCATOR,
    )
    extraction_confidence = ExtractionConfidence(
        level=ExtractionConfidenceLevel.HIGH,
        basis=(
            "Verbatim excerpt taken directly from the 'Authors' conclusions' "
            "section of Cochrane's own freely accessible evidence page for "
            "CD007244 (not the paywalled full technical review) — the full "
            "background, objectives, search strategy, main results, and "
            "authors' conclusions were fetched and read in full before this "
            "excerpt was selected. Extraction confidence is HIGH for the "
            "verbatim text itself; this is independent of the LOW/UNVERIFIED "
            "confidence recorded separately for taxonomy/preparation/dose "
            "applicability, which this field does not cover."
        ),
        extractor_type="hybrid",
        extractor_version="claude-assisted-extraction-v1",
    )
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="menopausal symptoms",
        assertion_state=AssertionState.INSUFFICIENT,
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
            supported_field="resolved_outcomes[domain=Indication/Evidence, subject='menopausal symptoms']",
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
        FieldProvenance(
            document_id=_EMA_REFERENCE_ID,
            document_version=_EMA_DOCUMENT_VERSION,
            locator=_EMA_INDICATION_LOCATOR,
            supported_field=(
                "validation_unit.preparation (Extract, DER 4.5-8.5:1, ethanol "
                "60% V/V — one of THREE EMA well-established-use preparations, "
                "arbitrarily selected) and .population ('Female adults') — "
                "the EMA monograph's own well-established-use posology, NOT "
                "the governing Ground Truth claim, and NOT verified as "
                "equivalent to what CD007244's included trials used"
            ),
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
    ]


def build_gold_case_refgrounded_005_cimicifuga_racemosa_menopausal() -> GoldCase:
    """Builds the case through resolved_outcomes only. Returns an
    UNLOCKED GoldCase (locked=False); lock_gold_case() is intentionally
    never called here. EngineEvidenceInput collection is a separate,
    later, independently-decided step (Leakage Rule 9.1), not started
    in this file. expected_output.expected_decision_direction is left
    at its default (None) — there is nothing to derive it from for
    AssertionState.INSUFFICIENT (see module docstring).
    """
    unit = ValidationUnit(
        taxon="Cimicifuga racemosa (L.) Nutt.",
        taxon_synonyms=["Actaea racemosa L.", "Cimicifuga racemosa (L.) Nutt."],
        plant_part="rhizome",
        preparation=_black_cohosh_ema_preparation_b(),
        population="Female adults",
        route_of_administration="Oral",
        # Platform-vocabulary mapping (step_inputs.INDICATIONS), not a
        # term drawn verbatim from either source — recorded explicitly
        # so it is never mistaken for source text (Case001 convention).
        indication="Menopause support",
        jurisdiction="EU",
    )

    reference = _build_reference_descriptor()
    claim = _build_reference_claim(reference)

    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        reference, unit, ReferenceDomain.INDICATION_EVIDENCE,
    )

    case = GoldCase(
        case_id="refgrounded_005_cimicifuga_racemosa_menopausal",
        validation_unit=unit,
        risk_strata=[],  # no RiskStratum value cleanly fits an insufficient-evidence verdict; see Case003/004 precedent for not force-fitting one
        references=[gref],
        case_provenance=_build_case_provenance(),
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        # engine_evidence intentionally left empty; engine_evidence_origin
        # intentionally left None. expected_output intentionally left at
        # its default (expected_decision_direction=None) — see docstring.
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


if __name__ == "__main__":
    built_case = build_gold_case_refgrounded_005_cimicifuga_racemosa_menopausal()
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
