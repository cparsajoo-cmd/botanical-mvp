"""
Validation Architecture v3 — Phase 1: Synthetic Validation Fixtures.

WHAT THIS IS — AND, CRITICALLY, WHAT IT IS NOT
Every GoldCase built here is ENTIRELY SYNTHETIC — invented plant
names, invented reference content, invented severities — built only
to exercise the Phase 1 pipeline (applicability -> precedence ->
leakage assessment -> metric reporting) end to end. NONE of this has
been curated from a real EMA/HMPC, WHO, ESCOP, or Commission E
monograph, and NONE of it should ever be read as, cited as, or
confused with a scientifically curated Gold Set (Validation
Architecture v2 Layer 3 / Phase 2's real Gold Set).

This directory is named synthetic_validation_fixtures/ specifically
(v3 correction #4) — not gold_set/ or gold_cases/ — so that anyone
who lists the repository's contents cannot mistake it for the real
thing. Every case_id below is prefixed "synthetic_" for the same
reason, mirroring benchmark_harness.py's own "SYNTHETIC smoke-test
fixture ... not scientific validation" disclosure pattern.

WHAT THIS COVERS
One illustrative case per major risk stratum, enough for
pipeline-integration tests to exercise every ResolutionStatus and
LeakageAssessment value at least once — not remotely enough to be a
representative Gold Set (Phase 2's real Gold Set will need dozens of
cases per stratum per the sample sizes already approved in Validation
Architecture v2).
"""

from __future__ import annotations

from datetime import date

from applicability_check import ReferenceDomain
from dataset_split import DatasetSplit, LeakageControl
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, RiskStratum, DecisionDirection
from reference_descriptor import ReferenceDescriptor
from reference_precedence import ReferenceVerdict
from validation_unit import PreparationSpec, ValidationUnit


def _clean_baseline_case() -> GoldCase:
    """Single-reference, single-domain-applicable, no conflict —
    control-group case."""
    unit = ValidationUnit(
        taxon="Synthetica exampla",
        plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="Adults",
        jurisdiction="Germany",
        indication="Synthetic test indication A",
        route_of_administration="Oral",
    )
    reference = ReferenceDescriptor(
        reference_id="synthetic_ref_clean_1",
        source_type="EMA_HMPC",
        version="v1-synthetic",
        document_date=date(2020, 1, 1),
        jurisdiction=None,
        plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),
        population="general",
    )
    gold_ref = GoldCaseReference(
        reference=reference,
        verdict=ReferenceVerdict(reference_id=reference.reference_id, safety_severity="NONE", verdict_value="supported"),
    )
    return GoldCase(
        case_id="synthetic_clean_baseline_001",
        validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
        references=[gold_ref],
        expected_output=ExpectedOutput(
            expected_decision_direction=DecisionDirection.POSITIVE,
            expected_gate_results={"safety": "PASSED", "regulatory": "PASSED"},
        ),
        dataset_split=DatasetSplit.DEVELOPMENT,
    )


def _safety_serious_case() -> GoldCase:
    """Two applicable safety references, differing severity — the
    higher-severity one must win precedence, regardless of rank."""
    unit = ValidationUnit(
        taxon="Synthetica periculosa",
        plant_part="leaf",
        preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%"),
        population="Pregnant",
        jurisdiction="EU",
        indication="Synthetic test indication B",
        route_of_administration="Oral",
    )
    ref_minor = ReferenceDescriptor(
        reference_id="synthetic_ref_safety_minor",
        source_type="ESCOP_MONOGRAPH", version="v1-synthetic",
        plant_part="leaf", preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%"),
        population="general",
    )
    ref_serious = ReferenceDescriptor(
        reference_id="synthetic_ref_safety_serious",
        source_type="EMA_HMPC", version="v1-synthetic",
        plant_part="leaf", preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%"),
        population="general",
    )
    return GoldCase(
        case_id="synthetic_safety_serious_001",
        validation_unit=unit,
        risk_strata=[RiskStratum.SAFETY_SERIOUS, RiskStratum.VULNERABLE_POPULATION],
        references=[
            GoldCaseReference(
                reference=ref_minor,
                verdict=ReferenceVerdict(reference_id=ref_minor.reference_id, safety_severity="MINOR", verdict_value="caution"),
            ),
            GoldCaseReference(
                reference=ref_serious,
                verdict=ReferenceVerdict(reference_id=ref_serious.reference_id, safety_severity="SERIOUS", verdict_value="contraindicated"),
            ),
        ],
        expected_output=ExpectedOutput(
            expected_decision_direction=DecisionDirection.NEGATIVE,
            expected_gate_results={"safety": "FAILED"},
            expected_warnings=["Synthetic contraindication in pregnancy"],
        ),
        dataset_split=DatasetSplit.DEVELOPMENT,
    )


def _preparation_mismatch_case() -> GoldCase:
    """The only available reference is for a DIFFERENT preparation —
    must be INAPPLICABLE, not silently treated as supporting evidence."""
    unit = ValidationUnit(
        taxon="Synthetica mismatch",
        plant_part="root",
        preparation=PreparationSpec(dosage_form="Tincture", solvent="ethanol 45%"),
        population="Adults",
        jurisdiction="Germany",
        indication="Synthetic test indication C",
    )
    reference = ReferenceDescriptor(
        reference_id="synthetic_ref_prep_mismatch",
        source_type="EMA_HMPC", version="v1-synthetic",
        plant_part="root",
        preparation=PreparationSpec(dosage_form="Infusion", solvent="water"),  # different preparation
        population="general",
    )
    return GoldCase(
        case_id="synthetic_preparation_mismatch_001",
        validation_unit=unit,
        risk_strata=[RiskStratum.PREPARATION_MISMATCH],
        references=[GoldCaseReference(reference=reference)],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.ABSTAIN, expected_abstention_reason="No applicable reference for this preparation."),
        correct_abstention_expected=True,
        dataset_split=DatasetSplit.DEVELOPMENT,
    )


def _conflicting_evidence_case() -> GoldCase:
    """Two equally-ranked, applicable, non-safety-domain references
    that disagree — must resolve to REFERENCE_CONFLICT, never averaged."""
    unit = ValidationUnit(
        taxon="Synthetica disputata",
        plant_part="flower",
        population="Adults",
        jurisdiction="EU",
        indication="Synthetic test indication D",
    )
    ref_a = ReferenceDescriptor(reference_id="synthetic_ref_conflict_a", source_type="WHO_MONOGRAPH", version="v1-synthetic", plant_part="flower", population="general")
    ref_b = ReferenceDescriptor(reference_id="synthetic_ref_conflict_b", source_type="WHO_MONOGRAPH", version="v2-synthetic", plant_part="flower", population="general")
    return GoldCase(
        case_id="synthetic_conflicting_evidence_001",
        validation_unit=unit,
        risk_strata=[RiskStratum.CONFLICTING_EVIDENCE],
        references=[
            GoldCaseReference(reference=ref_a, verdict=ReferenceVerdict(reference_id=ref_a.reference_id, verdict_value="supports")),
            GoldCaseReference(reference=ref_b, verdict=ReferenceVerdict(reference_id=ref_b.reference_id, verdict_value="does_not_support")),
        ],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.HOLD),
        dataset_split=DatasetSplit.DEVELOPMENT,
    )


def _no_reference_case() -> GoldCase:
    """No reference attached at all — must resolve to
    NO_APPLICABLE_REFERENCE, and the platform must abstain, not guess."""
    unit = ValidationUnit(
        taxon="Synthetica ignota",
        population="Adults",
        jurisdiction="EU",
        indication="Synthetic test indication E",
    )
    return GoldCase(
        case_id="synthetic_no_reference_001",
        validation_unit=unit,
        risk_strata=[RiskStratum.NO_REFERENCE, RiskStratum.CORRECT_ABSTENTION],
        references=[],
        expected_output=ExpectedOutput(
            expected_decision_direction=DecisionDirection.ABSTAIN,
            expected_abstention_reason="No authoritative reference available.",
        ),
        correct_abstention_expected=True,
        dataset_split=DatasetSplit.DEVELOPMENT,
    )


def _locked_holdout_clean_case() -> GoldCase:
    """A LOCKED_HOLDOUT case with clean leakage_control — used to
    exercise assess_leakage()'s VALID_FOR_HOLDOUT path in pipeline
    tests."""
    unit = ValidationUnit(taxon="Synthetica holdouta", jurisdiction="EU", indication="Synthetic test indication F", population="Adults")
    reference = ReferenceDescriptor(reference_id="synthetic_ref_holdout", source_type="EMA_HMPC", version="v1-synthetic", population="general")
    return GoldCase(
        case_id="synthetic_locked_holdout_clean_001",
        validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
        references=[GoldCaseReference(reference=reference, verdict=ReferenceVerdict(reference_id=reference.reference_id, safety_severity="NONE", verdict_value="supported"))],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=False),
    )


def _locked_holdout_leaked_case() -> GoldCase:
    """A LOCKED_HOLDOUT case with a confirmed leakage pattern — used to
    exercise assess_leakage()'s INVALID_FOR_HOLDOUT path."""
    unit = ValidationUnit(taxon="Synthetica leaked", jurisdiction="EU", indication="Synthetic test indication G", population="Adults")
    return GoldCase(
        case_id="synthetic_locked_holdout_leaked_001",
        validation_unit=unit,
        risk_strata=[RiskStratum.CLEAN_BASELINE],
        references=[],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.ABSTAIN),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(
            engine_output_observed_before_finalization=True,
            case_modified_after_observation=True,
        ),
    )


def build_synthetic_gold_cases() -> list:
    """Returns the full set of synthetic fixture cases — the ONLY
    entry point pipeline tests should use (never construct fixtures
    ad hoc inline in a test if one of these already covers the
    scenario)."""
    return [
        _clean_baseline_case(),
        _safety_serious_case(),
        _preparation_mismatch_case(),
        _conflicting_evidence_case(),
        _no_reference_case(),
        _locked_holdout_clean_case(),
        _locked_holdout_leaked_case(),
    ]
