"""
Reference-Grounded Validation — Synthetic Validation Fixtures (v4).

WHAT THIS IS — AND WHAT IT IS NOT
Every GoldCase built here is ENTIRELY SYNTHETIC and explicitly marked
kind=GoldCaseKind.SYNTHETIC — invented plant names, invented reference
content, invented severities — built only to exercise the pipeline
(claims -> applicability -> precedence -> resolved outcomes -> locking
-> engine execution) end to end. NONE of this has been curated from a
real EMA/HMPC, WHO, ESCOP, or Commission E monograph, and NONE of it
should ever be read as, cited as, or confused with a scientifically
curated Gold Set.

BREAKING CHANGE FROM THE PRIOR (v3) FIXTURES
The prior version of this module used ReferenceVerdict-only cases with
no ReferenceClaim/ResolvedExpectedOutcome/locking pipeline at all. This
is a deliberate, disclosed rewrite — GoldCase's schema changed
materially (v4 Reference-Grounded Validation architecture) and the old
fixture shapes no longer reflect how a real case is built. Every
case_id below is prefixed "synthetic_" for the same reason the prior
version used, but kind=SYNTHETIC is now the authoritative,
machine-checked signal (never inferred from the case_id string — see
gold_case.is_lockable()'s own enforcement of this).

WHAT THIS COVERS
One illustrative case per major scenario the v4 pipeline needs to be
exercised against: a clean, locked REFERENCE_CURATED case; a
Safety-Serious case whose resolved outcome actually drives a real
engine safety-gate failure; a Preparation-Mismatch case that correctly
fails to lock (NO_APPLICABLE_REFERENCE); a Conflicting-Evidence case
that correctly fails to lock (REFERENCE_CONFLICT); a No-Reference case
with zero references; and two LOCKED_HOLDOUT cases (one leakage-clean,
one leakage-tainted) for exercising assess_leakage().
"""

from __future__ import annotations

from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus, ExtractionConfidenceLevel,
    GoldCaseKind, SeverityLevel, TransformationType,
)
from dataset_split import DatasetSplit, LeakageControl
from engine_evidence_input import EngineEvidenceInput, EngineEvidenceOrigin
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, RiskStratum, DecisionDirection, lock_gold_case
from reference_claim import ReferenceClaim, NormalizedEvidenceText, ExtractionConfidence
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit


def _synthetic_evidence_text(text: str, locator: str) -> NormalizedEvidenceText:
    """SUMMARIZED_BY_CURATOR is only ever permitted for SYNTHETIC
    cases (v4 correction #4) — this is exactly where that permission
    is used, since nothing here traces to a real document."""
    return NormalizedEvidenceText(
        original_text=text, normalized_text=text,
        transformation_type=TransformationType.SUMMARIZED_BY_CURATOR,
        transformation_version="synthetic-fixture-v1", source_locator=locator,
    )


def _synthetic_confidence() -> ExtractionConfidence:
    return ExtractionConfidence(
        level=ExtractionConfidenceLevel.HIGH, basis="Synthetic fixture — not a real extraction",
        extractor_type="human_curator", extractor_version="synthetic-fixture-v1",
    )


def _apply_applicability(gref: GoldCaseReference, unit: ValidationUnit, domains: list) -> None:
    for domain in domains:
        gref.applicability_by_domain[domain] = check_applicability(gref.reference, unit, domain)


def _clean_baseline_case() -> GoldCase:
    """Single reference, single applicable claim, resolves and locks
    cleanly — the control-group case."""
    unit = ValidationUnit(
        taxon="Synthetica exampla", plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="Adults", jurisdiction="Germany",
        indication="Synthetic test indication A", route_of_administration="Oral",
    )
    reference = ReferenceDescriptor(
        reference_id="synthetic_ref_clean_1", source_type="EMA_HMPC",
        version="v1-synthetic", document_date=date(2020, 1, 1),
        plant_part="root", preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="general",
    )
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.ABSENT, severity=SeverityLevel.NONE,
        source_reference_id=reference.reference_id, source_locator="synthetic section 1",
        evidence_text=_synthetic_evidence_text("No contraindication documented.", "synthetic section 1"),
        extraction_confidence=_synthetic_confidence(),
    )
    gref = GoldCaseReference(reference=reference, claims=[claim])
    _apply_applicability(gref, unit, [ReferenceDomain.SAFETY])

    case = GoldCase(
        case_id="synthetic_clean_baseline_001", validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE], references=[gref],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE),
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
        engine_evidence=[EngineEvidenceInput(
            scientific_name=unit.taxon, target_indication=unit.indication,
            notes="No documented safety concerns for this preparation.",
        )],
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def _safety_serious_case() -> GoldCase:
    """One reference with a SERIOUS pregnancy contraindication claim —
    this is the case that exercises the real end-to-end Safety-Serious
    data path: the resolved outcome (evaluator-only) expects a serious
    flag, and engine_evidence (structurally separate) carries a
    preclassified structured activity-target ("Lithogenic") that makes
    the REAL engine's Hard Safety Gate independently fail this
    candidate.

    CORRECTION (v4 correction #2): an earlier version of this
    docstring said the "natural-text + structured activity-target
    signal" together made the engine detect this. Characterization
    disproved that — SAFETY_TERMS (what free text is scanned against)
    and HARD_SAFETY_TERMS (what actually forces the hard stop) are
    disjoint vocabularies, so notes below contributes nothing to the
    gate outcome; only compound_activity_targets does. See
    test_gold_case_execution.py's capability-boundary tests. notes is
    kept here for narrative realism (what a curator would also see in
    the source text) — it is deliberately NOT what triggers the gate.
    "Lithogenic" is a deliberately preclassified synthetic engine
    input chosen to exercise gate behavior, not an extracted
    scientific conclusion — see engine_evidence_origin below."""
    unit = ValidationUnit(
        taxon="Synthetica periculosa", plant_part="leaf",
        preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%"),
        population="Pregnant", jurisdiction="EU",
        indication="Synthetic test indication B", route_of_administration="Oral",
    )
    reference = ReferenceDescriptor(
        reference_id="synthetic_ref_safety_serious", source_type="EMA_HMPC",
        version="v1-synthetic", plant_part="leaf",
        preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%"),
        population="general",
    )
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnant women", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.SERIOUS,
        source_reference_id=reference.reference_id, source_locator="synthetic section 4.3",
        evidence_text=_synthetic_evidence_text(
            "Documented lithogenic activity; contraindicated in pregnancy.", "synthetic section 4.3",
        ),
        extraction_confidence=_synthetic_confidence(),
    )
    gref = GoldCaseReference(reference=reference, claims=[claim])
    _apply_applicability(gref, unit, [ReferenceDomain.SAFETY])

    case = GoldCase(
        case_id="synthetic_safety_serious_001", validation_unit=unit,
        risk_strata=[RiskStratum.SAFETY_SERIOUS, RiskStratum.VULNERABLE_POPULATION],
        references=[gref],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.NEGATIVE),
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
        # engine_evidence is STRUCTURALLY SEPARATE from the claim above
        # (see gold_case.py's own docstring on this separation) — it
        # happens to describe the same underlying fact here (expected
        # in real curation too), but the engine only ever sees this,
        # never the ReferenceClaim/ResolvedExpectedOutcome objects.
        # "Lithogenic" below is typed in by hand, matching the claim's
        # evidence_text by fixture-author choice, NOT computed from
        # claim/reference/expected_output — see engine_evidence_origin.
        engine_evidence=[EngineEvidenceInput(
            scientific_name=unit.taxon, target_indication=unit.indication,
            notes="Case reports describe kidney stone formation associated with prolonged use of this preparation.",
            compound_activity_targets=("Lithogenic",),
        )],
        engine_evidence_origin=EngineEvidenceOrigin.MANUAL_TEST_FIXTURE,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def _preparation_mismatch_case() -> GoldCase:
    """The only available reference is for a DIFFERENT preparation —
    applicability correctly fails, so the resolved outcome is
    NO_APPLICABLE_REFERENCE and the case correctly CANNOT lock."""
    unit = ValidationUnit(
        taxon="Synthetica mismatch", plant_part="root",
        preparation=PreparationSpec(dosage_form="Tincture", solvent="ethanol 45%"),
        population="Adults", jurisdiction="Germany",
        indication="Synthetic test indication C",
    )
    reference = ReferenceDescriptor(
        reference_id="synthetic_ref_prep_mismatch", source_type="EMA_HMPC",
        version="v1-synthetic", plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),  # different preparation
        population="general",
    )
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.ABSENT, severity=SeverityLevel.NONE,
        source_reference_id=reference.reference_id, source_locator="synthetic section 1",
        evidence_text=_synthetic_evidence_text("No contraindication for infusion.", "synthetic section 1"),
        extraction_confidence=_synthetic_confidence(),
    )
    gref = GoldCaseReference(reference=reference, claims=[claim])
    _apply_applicability(gref, unit, [ReferenceDomain.SAFETY])

    case = GoldCase(
        case_id="synthetic_preparation_mismatch_001", validation_unit=unit,
        risk_strata=[RiskStratum.PREPARATION_MISMATCH], references=[gref],
        expected_output=ExpectedOutput(
            expected_decision_direction=DecisionDirection.ABSTAIN,
            expected_abstention_reason="No applicable reference for this preparation.",
        ),
        correct_abstention_expected=True,
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def _conflicting_evidence_case() -> GoldCase:
    """Two equally-ranked, applicable, non-safety-domain references
    that disagree — must resolve to REFERENCE_CONFLICT, and the case
    correctly CANNOT lock."""
    unit = ValidationUnit(
        taxon="Synthetica disputata", plant_part="flower",
        population="Adults", jurisdiction="EU", indication="Synthetic test indication D",
    )
    reference_a = ReferenceDescriptor(
        reference_id="synthetic_ref_conflict_a", source_type="WHO_MONOGRAPH",
        version="v1-synthetic", plant_part="flower", population="general",
    )
    reference_b = ReferenceDescriptor(
        reference_id="synthetic_ref_conflict_b", source_type="WHO_MONOGRAPH",
        version="v2-synthetic", plant_part="flower", population="general",
    )
    claim_a = ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE, assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="synthetic test indication d", assertion_state=AssertionState.PRESENT,
        source_reference_id=reference_a.reference_id, source_locator="synthetic section 2",
        evidence_text=_synthetic_evidence_text("Supports the indication.", "synthetic section 2"),
        extraction_confidence=_synthetic_confidence(),
    )
    claim_b = ReferenceClaim(
        domain=ReferenceDomain.INDICATION_EVIDENCE, assertion_type=AssertionType.SUPPORTS_INDICATION,
        subject="synthetic test indication d", assertion_state=AssertionState.ABSENT,
        source_reference_id=reference_b.reference_id, source_locator="synthetic section 3",
        evidence_text=_synthetic_evidence_text("Does not support the indication.", "synthetic section 3"),
        extraction_confidence=_synthetic_confidence(),
    )
    gref_a = GoldCaseReference(reference=reference_a, claims=[claim_a])
    gref_b = GoldCaseReference(reference=reference_b, claims=[claim_b])
    _apply_applicability(gref_a, unit, [ReferenceDomain.INDICATION_EVIDENCE])
    _apply_applicability(gref_b, unit, [ReferenceDomain.INDICATION_EVIDENCE])

    case = GoldCase(
        case_id="synthetic_conflicting_evidence_001", validation_unit=unit,
        risk_strata=[RiskStratum.CONFLICTING_EVIDENCE], references=[gref_a, gref_b],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.HOLD),
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def _no_reference_case() -> GoldCase:
    """No reference attached at all — resolved_outcomes stays empty,
    correctly cannot lock."""
    unit = ValidationUnit(
        taxon="Synthetica ignota", population="Adults",
        jurisdiction="EU", indication="Synthetic test indication E",
    )
    case = GoldCase(
        case_id="synthetic_no_reference_001", validation_unit=unit,
        risk_strata=[RiskStratum.NO_REFERENCE, RiskStratum.CORRECT_ABSTENTION],
        references=[],
        expected_output=ExpectedOutput(
            expected_decision_direction=DecisionDirection.ABSTAIN,
            expected_abstention_reason="No authoritative reference available.",
        ),
        correct_abstention_expected=True,
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


def _locked_holdout_clean_case() -> GoldCase:
    """A fully lockable, LOCKED_HOLDOUT case with clean leakage_control
    — exercises assess_leakage()'s VALID_FOR_HOLDOUT path and
    build_evaluation_run()'s happy path."""
    unit = ValidationUnit(
        taxon="Synthetica holdouta", jurisdiction="EU",
        indication="Synthetic test indication F", population="Adults",
        preparation=PreparationSpec(dosage_form="Infusion"),
    )
    reference = ReferenceDescriptor(
        reference_id="synthetic_ref_holdout", source_type="EMA_HMPC",
        version="v1-synthetic", population="general",
    )
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.ABSENT, severity=SeverityLevel.NONE,
        source_reference_id=reference.reference_id, source_locator="synthetic section 1",
        evidence_text=_synthetic_evidence_text("No contraindication documented.", "synthetic section 1"),
        extraction_confidence=_synthetic_confidence(),
    )
    gref = GoldCaseReference(reference=reference, claims=[claim])
    _apply_applicability(gref, unit, [ReferenceDomain.SAFETY])

    case = GoldCase(
        case_id="synthetic_locked_holdout_clean_001", validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE], references=[gref],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=False),
        kind=GoldCaseKind.SYNTHETIC, curation_status=CurationStatus.REFERENCE_CURATED,
        engine_evidence=[EngineEvidenceInput(
            scientific_name=unit.taxon, target_indication=unit.indication,
            notes="No documented safety concerns for this preparation.",
        )],
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return lock_gold_case(case)


def _locked_holdout_leaked_case() -> GoldCase:
    """A LOCKED_HOLDOUT case with a confirmed leakage pattern —
    exercises assess_leakage()'s INVALID_FOR_HOLDOUT path. Left
    unlocked deliberately (locking is orthogonal to the leakage check
    itself, and build_evaluation_run() would reject this case on the
    leakage check before ever looking at .locked)."""
    unit = ValidationUnit(
        taxon="Synthetica leaked", jurisdiction="EU",
        indication="Synthetic test indication G", population="Adults",
    )
    case = GoldCase(
        case_id="synthetic_locked_holdout_leaked_001", validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE], references=[],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.ABSTAIN),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(
            engine_output_observed_before_finalization=True,
            case_modified_after_observation=True,
        ),
        kind=GoldCaseKind.SYNTHETIC,
    )
    return case


def build_synthetic_gold_cases() -> list:
    """Returns the full set of synthetic fixture cases — the ONLY
    entry point pipeline tests should use."""
    return [
        _clean_baseline_case(),
        _safety_serious_case(),
        _preparation_mismatch_case(),
        _conflicting_evidence_case(),
        _no_reference_case(),
        _locked_holdout_clean_case(),
        _locked_holdout_leaked_case(),
    ]
