"""
Reference-Grounded Validation — Phase 3B/3C, Case 003.

WHAT THIS IS
The second real (kind=GoldCaseKind.REFERENCE_GROUNDED) case built under
VALIDATION_PROTOCOL.md v0.2 / VALIDATION_CASE_TEMPLATE.md v0.2. Unlike
Case 001 (Melissa officinalis, governed by EMA/HMPC), this case's
Ground Truth traces to a real, accessible SYSTEMATIC_REVIEW — a
deliberate, protocol-driven test of whether Section 6's precedence
rule (SYSTEMATIC_REVIEW outranks EMA_HMPC for INDICATION_EVIDENCE) is
actually implemented and followed consistently, not just asserted.

CASE SCOPE (Protocol §4)
Taxon:      Matricaria chamomilla L. (Chamomile)
Domain:     ReferenceDomain.INDICATION_EVIDENCE
Assertion:  AssertionType.SUPPORTS_INDICATION, subject="sleep"
Protocol Version (Case Template row 2 — no native field): v0.2.
Scientific Question (Case Template row 3 — no native field):
    "Does the reference-grounded resolved outcome for Matricaria
    chamomilla L. in domain Indication/Evidence (Supports indication)
    for 'sleep', under population Adults / route Oral / preparation
    Infusion (water) / jurisdiction EU, agree with the decision the
    engine produces when given equivalent, independently
    curator-supplied evidence?"

SOURCE-PRECEDENCE CHECK (Protocol §6/§9.3 — documented before any
engine output; also before any Ground Truth extraction, since this
determines WHICH document to extract from)
Two 2024 systematic reviews specific to chamomile and sleep/anxiety
were located and evaluated:

  1. Kazemi, Shojaei-Zarghani, Eskandarzadeh, Hashempur (2024),
     "Effects of chamomile (Matricaria chamomilla L.) on sleep: A
     systematic review and meta-analysis of clinical trials,"
     Complementary Therapies in Medicine 84:103071,
     DOI 10.1016/j.ctim.2024.103071. Specifically and exclusively
     about chamomile and SLEEP (not bundled with an unrelated
     condition) — the closest possible match to this case's primary
     assertion. ACCESSIBILITY VERIFIED two independent ways before
     selection: (a) ScienceDirect's own indexed abstract/conclusion
     snippet, (b) an independently-hosted full-text mirror showing
     matching journal pagination, PRISMA flow diagram, results tables,
     and a limitations section — i.e., not a single unconfirmed
     snippet (contrast with the Passiflora Case 002 access failure,
     where no such cross-verification was ever achieved).
  2. Hieu, Dibas, Surber, Tran (2019), "Therapeutic efficacy and
     safety of chamomile for state anxiety, generalized anxiety
     disorder, insomnia, and sleep quality: A systematic review and
     meta-analysis," Phytotherapy Research 33:1604-1615. Real,
     accessible, but bundles sleep together with state/generalized
     anxiety as co-primary outcomes, and is five years older than
     Kazemi et al. 2024's literature-search cutoff (August 2023) —
     less precisely on-topic for a sleep-only primary assertion.

Result: Kazemi et al. 2024 selected as the governing source —
SYSTEMATIC_REVIEW, correctly outranking EMA_HMPC (Section 6) for this
case, unlike Case 001 where no qualifying review existed. EMA_HMPC is
NOT used here and was never a candidate once a qualifying review was
confirmed accessible and extractable.

VERBATIM EXTRACTION AND ITS OWN DISCLOSED WORDING VARIANCE
The exact sentence below was cross-checked against TWO independently
retrieved renderings of this paper: ScienceDirect's own in-text
"In conclusion, chamomile was found to improve sleep..." sentence, and
an independently-hosted full-text mirror's structured-abstract
"Conclusion:" field, worded slightly differently ("Chamomile improved
sleep..." vs "...was found to improve..."). This is an ordinary,
expected difference between a paper's structured-abstract Conclusion
field and its Discussion section's own concluding sentence — not a
sign of an unreliable source. The VERBATIM excerpt below is taken from
the structured-abstract "Conclusion:" field specifically (the more
precisely locatable of the two), not a blend of both.

WHY assertion_state=CONDITIONAL, NOT PRESENT
The review's own conclusion is a genuinely MIXED finding: chamomile
improved SOME sleep measures (awakenings/staying asleep) but explicitly
did NOT improve others (sleep duration, sleep-efficiency percentage,
daytime functioning). Forcing this into AssertionState.PRESENT would
misrepresent a nuanced, partial result as an unqualified positive
finding. AssertionState.CONDITIONAL is used instead, and the full
mixed finding is preserved verbatim in evidence_text rather than
summarized down to just its positive half.

APPLICABILITY LIMITATIONS — RECORDED HONESTLY, NOT RESOLVED (per
explicit instruction)
1. PREPARATION HETEROGENEITY: the review pools ten trials using
   different chamomile preparations (tea, capsules, extracts, and
   aromatherapy) — it does not report a preparation-specific WMD for
   infusion/tea alone. ReferenceDescriptor.preparation is therefore
   left None (unspecified), which passes applicability_check.py's
   permissive null-handling for that dimension by default, not
   because preparation-specific equivalence to this case's
   Infusion/water ValidationUnit has actually been verified. This is a
   PASS-BY-ABSENCE, not a verified preparation match — flagged here so
   it is never mistaken for one.
2. POPULATION HETEROGENEITY: the ten pooled trials span markedly
   different populations (elderly institutionalized patients,
   postnatal women, heart failure patients, healthy adults) — the
   review's own limitations section states participant characteristics
   "were not similar across studies." ReferenceDescriptor.population
   is set to "general" (matching the abstract's own "healthy or
   diseased adults" framing), which is honest about breadth but does
   not resolve the underlying heterogeneity.
3. ROUTE: the pooled studies are predominantly oral, but the review
   title/abstract also references aromatherapy (an inhalation-route
   arm) among the included preparations. route_scope is set to
   ["Oral"] to reflect this case's own claim scope, not a claim that
   every included study was oral.
None of these three limitations are resolved or worked around here —
they are recorded as real, disclosed constraints on how strongly this
case's Ground Truth should be read.

PASS-BY-ABSENCE IS NOT EVIDENCE OF EQUIVALENCE (permanent principle,
not specific to this one case)
applicability_check.py's null-handling convention — an unspecified
field on the reference side is treated as "covers the general
category" and therefore PASSES that applicability dimension — is a
structural default, not a scientific finding. This case's
applicability_result.applicable == True for INDICATION_EVIDENCE holds
because preparation and population were left unspecified on the
reference, NOT because Infusion/water or "Adults" was verified against
the governing review's pooled data. Any later stage of this validation
program — the Execution Readiness Guard's DimensionAssessment values,
a curator's engine-evidence scope-equivalence judgment, or a future
reviewer reading this case's applicability=True result — must treat
this pass as "no documented mismatch," never as "confirmed match."
Concretely: this case's eventual ScopeEquivalence for preparation and
population should be assessed as UNKNOWN, never EXACT, purely on the
strength of this reference's applicability check having passed.

WHAT THIS FILE DELIBERATELY DOES NOT DO (per explicit instruction)
- Does not construct or infer any EngineEvidenceInput.
- Does not call gold_case_execution.execute_gold_case_against_engine()
  or execute_gold_case_with_readiness_gate(), and does not run or
  instantiate BotanicalRDCandidateEngine.
- Does not call lock_gold_case().
- Does not modify botanical_rd_candidate_engine.py or any other
  existing file.
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

# --- Real reference-source metadata (Kazemi et al. 2024) -------------------
_SR_REFERENCE_ID = "CTM_2024_Kazemi_chamomile_sleep_SR"
_SR_CITATION = (
    "Kazemi A, Shojaei-Zarghani S, Eskandarzadeh P, Hashempur MH (2024). "
    "Effects of chamomile (Matricaria chamomilla L.) on sleep: A systematic "
    "review and meta-analysis of clinical trials. Complementary Therapies "
    "in Medicine 84:103071. DOI 10.1016/j.ctim.2024.103071."
)
_SR_DOCUMENT_DATE = date(2024, 8, 4)
_SR_LOCATOR = "Abstract, 'Conclusion' field — Complementary Therapies in Medicine 84 (2024) 103071"
# Fixed, explicit extraction date — never date.today() (see Case 001's
# provenance-determinism correction; the same rule applies here).
_EXTRACTION_DATE = date(2026, 7, 29)

# Verbatim, complete sentence from the structured abstract's
# "Conclusion:" field — the mixed finding is preserved whole, not
# trimmed to only its positive half. See module docstring's
# "WHY assertion_state=CONDITIONAL" note.
_SR_CONCLUSION_VERBATIM = (
    "Chamomile improved sleep, especially the number of awakenings "
    "after sleep or staying asleep; however, it did not lead to an "
    "improvement in the duration of sleep, percentage of sleep "
    "efficiency, and daytime functioning measures."
)


def _chamomile_infusion_preparation() -> PreparationSpec:
    """This CASE's own claimed preparation scope (Infusion/water) —
    NOT a preparation the governing systematic review verified in
    isolation. See module docstring's Applicability Limitation #1.
    Named/shared the same way Case 001 shares one PreparationSpec
    between its ValidationUnit and (there) its ReferenceDescriptor;
    here the ReferenceDescriptor deliberately does NOT use this helper
    — see _build_reference_descriptor()'s own comment."""
    return PreparationSpec(dosage_form="Infusion", solvent="water")


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_SR_REFERENCE_ID,
        source_type="SYSTEMATIC_REVIEW",
        version=_SR_CITATION,
        document_date=_SR_DOCUMENT_DATE,
        jurisdiction=None,  # international literature synthesis, not jurisdiction-bound
        taxon="Matricaria chamomilla L.",
        plant_part=None,  # not isolated by the review; see Limitation #1
        # Preparation deliberately left UNSPECIFIED (None) — the review
        # pools tea/capsule/extract/aromatheropy studies without a
        # preparation-specific pooled result. This PASSES
        # applicability_check.py's permissive null-handling by
        # default; it is not a verified match. See module docstring's
        # Applicability Limitation #1 for the full disclosure.
        preparation=None,
        population="general",  # honest breadth, not resolved heterogeneity — Limitation #2
        claim_type=None,  # not a regulatory traditional-use/well-established-use source
        indication_scope=["Sleep and relaxation"],
        route_scope=["Oral"],  # this case's claim scope — Limitation #3
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
            "Verbatim excerpt taken from the structured-abstract 'Conclusion:' "
            "field, cross-verified against an independently-hosted full-text "
            "mirror showing matching journal pagination and structure. A "
            "second, differently-worded rendering of the same conclusion "
            "('In conclusion, chamomile was found to improve sleep...') was "
            "also found in ScienceDirect's own in-text Discussion sentence — "
            "an ordinary abstract-vs-discussion wording variance, disclosed "
            "here, not concealed. This excerpt is the abstract field's exact "
            "wording, not a blend of the two."
        ),
        extractor_type="hybrid",  # AI-located/extracted, human-directed and confirmed — see Case 001's identical convention
        extractor_version="claude-assisted-extraction-v1",
    )
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="sleep",
        # CONDITIONAL, not PRESENT — see module docstring's dedicated
        # explanation. A genuinely mixed/partial finding must not be
        # collapsed into an unqualified positive.
        assertion_state=AssertionState.CONDITIONAL,
        severity=None,
        source_reference_id=reference.reference_id,
        source_locator=_SR_LOCATOR,
        evidence_text=evidence_text,
        extraction_confidence=extraction_confidence,
    )


def _build_case_provenance() -> list:
    """Case-level FieldProvenance entries — same convention as Case
    001. curator is left None deliberately (no ReviewerRole value
    confirmed for this case)."""
    return [
        FieldProvenance(
            document_id=_SR_REFERENCE_ID,
            document_version=_SR_CITATION,
            locator=_SR_LOCATOR,
            supported_field="resolved_outcomes[domain=Indication/Evidence, subject='sleep']",
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
        FieldProvenance(
            document_id=_SR_REFERENCE_ID,
            document_version=_SR_CITATION,
            locator=(
                "Abstract Methods + Discussion/Limitations — pooled preparation "
                "and population heterogeneity across the ten included trials"
            ),
            supported_field=(
                "gold_case.references[0].reference.preparation (left None) / "
                ".population ('general') — disclosed heterogeneity, not resolved"
            ),
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
    ]


def build_gold_case_refgrounded_003_matricaria_chamomilla_sleep() -> GoldCase:
    """Builds the case through resolved_outcomes only — see module
    docstring's 'WHAT THIS FILE DELIBERATELY DOES NOT DO'. Returns an
    UNLOCKED GoldCase (locked=False); lock_gold_case() is intentionally
    never called here. EngineEvidenceInput collection is a separate,
    later, independently-decided step (Leakage Rule 9.1), not started
    in this file.
    """
    unit = ValidationUnit(
        taxon="Matricaria chamomilla L.",
        plant_part="flower",
        preparation=_chamomile_infusion_preparation(),
        population="Adults",
        route_of_administration="Oral",
        # Platform-vocabulary mapping, not a term drawn from the
        # governing systematic review itself.
        indication="Sleep and relaxation",
        jurisdiction="EU",
    )

    reference = _build_reference_descriptor()
    claim = _build_reference_claim(reference)

    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.INDICATION_EVIDENCE] = check_applicability(
        reference, unit, ReferenceDomain.INDICATION_EVIDENCE,
    )

    case = GoldCase(
        case_id="refgrounded_003_matricaria_chamomilla_sleep",
        validation_unit=unit,
        # NO RiskStratum applied. On review, none of the eleven
        # existing values correctly describe "one source reports an
        # internally mixed/partial finding" — CONFLICTING_EVIDENCE
        # specifically denotes disagreement BETWEEN evidence/sources,
        # not a single systematic review's own qualified conclusion
        # (which is exactly what AssertionState.CONDITIONAL already
        # exists to represent — see module docstring). Force-fitting
        # CONFLICTING_EVIDENCE here would misclassify the case for
        # anyone filtering/reporting by risk stratum later. Left empty
        # deliberately, not omitted by oversight.
        risk_strata=[],
        references=[gref],
        case_provenance=_build_case_provenance(),
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        # engine_evidence intentionally left empty; engine_evidence_origin
        # intentionally left None — Engine Evidence collection is a
        # separate step, not started in this file.
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


if __name__ == "__main__":
    built_case = build_gold_case_refgrounded_003_matricaria_chamomilla_sleep()
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
