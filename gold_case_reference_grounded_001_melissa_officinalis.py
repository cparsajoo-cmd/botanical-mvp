"""
Reference-Grounded Validation — Phase 3B, Case 001.

WHAT THIS IS
The first REAL (kind=GoldCaseKind.REFERENCE_GROUNDED) case built under
VALIDATION_PROTOCOL.md v0.2 / VALIDATION_CASE_TEMPLATE.md v0.2. Ground
Truth for this case traces to an authoritative, currently-published
EMA/HMPC community herbal monograph — no invented content, no
curator-summarized text anywhere in this file.

CASE SCOPE (Protocol §4 — exactly one primary assertion, one domain)
Taxon:      Melissa officinalis L. (Melissa leaf / lemon balm)
Domain:     ReferenceDomain.INDICATION_EVIDENCE
Assertion:  AssertionType.SUPPORTS_INDICATION, subject="sleep"
Scientific Question (Case Template row 3 — no native GoldCase field,
documented here instead):
    "Does the reference-grounded resolved outcome for Melissa
    officinalis L. in domain Indication/Evidence (Supports indication)
    for the sleep component of EMA/HMPC/196745/2012's Indication 1),
    under population 'Adolescents over 12 years of age, adults and
    elderly' / route Oral / preparation Infusion (water) / jurisdiction
    EU, agree with the decision the engine produces when given
    equivalent, independently curator-supplied evidence?"
Protocol Version (Case Template row 2 — no native field): v0.2.

WHY subject="sleep" AND NOT "sleep and mental stress"
EMA/HMPC/196745/2012's Indication 1) is written as one combined
traditional-use statement covering two symptom-relief effects (mild
mental stress AND sleep). Protocol §4 requires exactly one primary
assertion per case. The VERBATIM excerpt below is preserved complete
(including the mental-stress wording) because splitting the source
sentence itself would violate the VERBATIM transformation rule
(Protocol §8) — but the claim's `subject` and this case's Scientific
Question target the sleep component only. A future, separate case may
target "mental stress" as its own primary assertion; that would be a
different case with a different governing source (see the
source-precedence note below), not a re-use of this one.

WHY indication="Sleep and relaxation" ON THE VALIDATION UNIT
This is a PLATFORM-VOCABULARY MAPPING (step_inputs.INDICATIONS), not a
verbatim EMA term — EMA/HMPC/196745/2012 never uses this exact phrase.
It is the closest existing engine-recognized indication label to the
sleep component of Indication 1). Recorded explicitly here so this
mapping is never mistaken for source text.

SOURCE-PRECEDENCE CHECK (Protocol §6/§9.3 — documented before any
engine output was observed)
INDICATION_EVIDENCE ranks SYSTEMATIC_REVIEW above EMA_HMPC. Two
candidate systematic reviews were located and evaluated before EMA_HMPC
was accepted as the governing source for THIS claim:

  1. Ghazizadeh et al. 2021, "The effects of lemon balm (Melissa
     officinalis L.) on depression and anxiety in clinical trials: a
     systematic review and meta-analysis," Phytotherapy Research
     35(12):6690-6705 (DOI 10.1002/ptr.7252). Real, peer-reviewed,
     Melissa-monotherapy-focused. REJECTED for this claim: its primary
     assertion is depression/anxiety, not sleep — a different primary
     assertion than this case targets (Protocol §6's rule compares
     "same taxon, indication, and primary assertion," not just same
     taxon).
  2. "Effectiveness of Lesser Known Herbal Sedatives for Insomnia"
     (medRxiv preprint, PROSPERO CRD420251101795). This review DOES
     include Melissa officinalis studied sometimes as monotherapy and
     sometimes in combination, and reports a Melissa-specific subgroup
     analysis — it is NOT rejected for lacking a Melissa-specific
     result (an earlier draft of this record incorrectly said so; that
     was factually wrong and is corrected here). It is REJECTED
     because it is a non-peer-reviewed preprint, and Protocol §7
     explicitly places "non-peer-reviewed preprints" in the
     Non-Permitted Sources list regardless of topical fit.

  Result: no systematic review qualifies as the governing source for
  the sleep-specific claim. EMA_HMPC is retained on that basis, not
  because it was the first source proposed.

PREPARATION APPLICABILITY (demonstrated, not assumed)
Section 4.1 alone only establishes the indication. Section 4.2
(Posology), same document, explicitly ties an "Herbal tea ... as a
herbal infusion" (water-based) preparation to "Indications 1) and 2)"
for the population "Adolescents over 12 years of age, adults and
elderly" — see _EMA_PREPARATION_LOCATOR below. This is the basis for
PreparationSpec(dosage_form="Infusion", solvent="water").

WHAT THIS FILE DELIBERATELY DOES NOT DO (per explicit instruction)
- Does not construct or infer any EngineEvidenceInput.
- Does not call gold_case_execution.execute_gold_case_against_engine()
  or otherwise run BotanicalRDCandidateEngine.
- Does not call lock_gold_case() — this case is left in DRAFT-adjacent,
  unlocked state (curation_status=REFERENCE_CURATED, locked=False).
  Per Leakage Rule 9.1's mandatory ordering, EngineEvidenceInput is a
  separate, later, independently-decided step.
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
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit

# --- Real reference-source metadata (EMA/HMPC/196745/2012) ----------------
_EMA_REFERENCE_ID = "EMA_HMPC_196745_2012_melissa_officinalis_folium"
_EMA_DOCUMENT_TITLE = "Community herbal monograph on Melissa officinalis L., folium"
_EMA_DOCUMENT_VERSION = "Final, adopted by HMPC 14 May 2013 (EMA/HMPC/196745/2012)"
_EMA_DOCUMENT_DATE = date(2013, 5, 14)
_EMA_INDICATION_LOCATOR = (
    "Section 4.1 'Therapeutic indications', Indication 1) "
    "(Traditional use column) — EMA/HMPC/196745/2012, p.3/7"
)
_EMA_PREPARATION_LOCATOR = (
    "Section 4.2 'Posology and method of administration', "
    "'Indications 1) and 2)', point a) Herbal tea — "
    "EMA/HMPC/196745/2012, p.3/7"
)
# Verbatim, complete sentence — includes the mental-stress wording on
# purpose (see module docstring's "WHY subject=sleep" note). Never
# truncated or paraphrased.
_EMA_INDICATION_1_VERBATIM = (
    "Traditional herbal medicinal product for relief of mild symptoms "
    "of mental stress and to aid sleep."
)
# Fixed, explicit date this source extraction was actually performed —
# deliberately NOT date.today(). A Gold Case's provenance must not
# change merely because its builder is executed on a different day
# (it will later be locked/serialized/hashed, and a nondeterministic
# field would make that hash unreproducible).
_EXTRACTION_DATE = date(2026, 7, 29)


def _melissa_infusion_preparation() -> PreparationSpec:
    """The ONE PreparationSpec both the ReferenceDescriptor (what the
    source document covers) and the ValidationUnit (what the case
    evaluates) use — see _EMA_PREPARATION_LOCATOR. Sharing one helper
    prevents the two objects silently diverging (e.g. one carrying
    source_status="native" and the other omitting it)."""
    return PreparationSpec(dosage_form="Infusion", solvent="water", source_status="native")


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_EMA_REFERENCE_ID,
        source_type="EMA_HMPC",
        version=_EMA_DOCUMENT_VERSION,
        document_date=_EMA_DOCUMENT_DATE,
        jurisdiction="EU",
        taxon="Melissa officinalis L.",
        plant_part="leaf",
        preparation=_melissa_infusion_preparation(),
        # EMA-grounded population, verbatim from Section 4.2 Posology —
        # never "Adults" alone; the monograph explicitly names three
        # age bands and this case must not be later described as
        # adult-only.
        population="Adolescents over 12 years of age, adults and elderly",
        claim_type="traditional-use",
        indication_scope=["Sleep and relaxation"],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim(reference: ReferenceDescriptor) -> ReferenceClaim:
    evidence_text = NormalizedEvidenceText(
        original_text=_EMA_INDICATION_1_VERBATIM,
        normalized_text=_EMA_INDICATION_1_VERBATIM,
        transformation_type=TransformationType.VERBATIM,
        transformation_version="verbatim-extraction-v1",
        source_locator=_EMA_INDICATION_LOCATOR,
    )
    extraction_confidence = ExtractionConfidence(
        level=ExtractionConfidenceLevel.HIGH,
        basis=(
            "Verbatim excerpt copied directly from the official EMA-"
            "published final monograph PDF (EMA/HMPC/196745/2012, "
            "adopted 14 May 2013), Section 4.1, Indication 1)."
        ),
        # Honest attribution: the text was located and extracted by
        # Claude, human-directed and confirmed by the curator — not a
        # human-only extraction. See module docstring's provenance note.
        extractor_type="hybrid",
        extractor_version="claude-assisted-extraction-v1",
    )
    return ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE,
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="sleep",
        assertion_state=AssertionState.PRESENT,
        severity=None,
        source_reference_id=reference.reference_id,
        source_locator=_EMA_INDICATION_LOCATOR,
        evidence_text=evidence_text,
        extraction_confidence=extraction_confidence,
    )


def _build_case_provenance() -> list:
    """Case-level FieldProvenance entries (Case Template row 14/15's
    suggested home for reviewer/documentation metadata until a native
    field exists). `curator` is left None deliberately — no
    ReviewerRole value was confirmed for this case, and inventing one
    would misrepresent who actually reviewed it."""
    return [
        FieldProvenance(
            document_id=_EMA_REFERENCE_ID,
            document_version=_EMA_DOCUMENT_VERSION,
            locator=_EMA_INDICATION_LOCATOR,
            supported_field="resolved_outcomes[domain=Indication/Evidence, subject='sleep']",
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
        FieldProvenance(
            document_id=_EMA_REFERENCE_ID,
            document_version=_EMA_DOCUMENT_VERSION,
            locator=_EMA_PREPARATION_LOCATOR,
            supported_field="validation_unit.preparation (Infusion/water)",
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
    ]


def build_gold_case_refgrounded_001_melissa_officinalis_sleep() -> GoldCase:
    """Builds the case through resolved_outcomes only — see module
    docstring's "WHAT THIS FILE DELIBERATELY DOES NOT DO". Returns an
    UNLOCKED GoldCase (locked=False); lock_gold_case() is intentionally
    never called here.
    """
    unit = ValidationUnit(
        taxon="Melissa officinalis L.",
        plant_part="leaf",
        preparation=_melissa_infusion_preparation(),
        population="Adolescents over 12 years of age, adults and elderly",
        route_of_administration="Oral",
        # Platform-vocabulary mapping, not a verbatim EMA term — see
        # module docstring.
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
        case_id="refgrounded_001_melissa_officinalis_sleep",
        validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
        references=[gref],
        case_provenance=_build_case_provenance(),
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        # engine_evidence intentionally left empty; engine_evidence_origin
        # intentionally left None — see module docstring.
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


if __name__ == "__main__":
    built_case = build_gold_case_refgrounded_001_melissa_officinalis_sleep()
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
