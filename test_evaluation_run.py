"""Tests for evaluation_run.py (Reference-Grounded Validation, v4).

Runs the REAL engine (via gold_case_execution.py) — no stubbing.
"""

from datetime import date

import botanical_rd_candidate_engine as eng
from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, SeverityLevel, CurationStatus, ValidationScope,
    TransformationType,
)
from dataset_split import DatasetSplit, LeakageControl
from engine_evidence_input import EngineEvidenceInput
from evaluation_run import (
    build_evaluation_run, EvaluationRunError, InvalidValidationScopeError,
    EvaluationRun, _derive_direction_from_decision_class,
)
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, DecisionDirection, lock_gold_case
from metric_report import MetricStatus
from reference_claim import ReferenceClaim, NormalizedEvidenceText
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import ValidationUnit, PreparationSpec


def _reset_engine_globals():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}


def _locked_clean_case(case_id="c1", taxon="Taxon1"):
    """A fully locked, LOCKED_HOLDOUT case with no safety concern
    expected (a NONE/ABSENT claim) — the engine should agree."""
    unit = ValidationUnit(
        taxon=taxon, indication="TestIndication", jurisdiction="EU",
        preparation=PreparationSpec(dosage_form="Infusion"),
    )
    ref = ReferenceDescriptor(reference_id=f"{case_id}_ref", source_type="EMA_HMPC", version="v1")
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.ABSENT, severity=SeverityLevel.NONE,
        source_reference_id=ref.reference_id, source_locator="sec 1",
        evidence_text=NormalizedEvidenceText("x", "y", TransformationType.VERBATIM, "1.0", "sec 1"),
    )
    gref = GoldCaseReference(reference=ref, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.SAFETY] = check_applicability(ref, unit, ReferenceDomain.SAFETY)

    case = GoldCase(
        case_id=case_id, validation_unit=unit, references=[gref],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.POSITIVE),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=False),
        curation_status=CurationStatus.REFERENCE_CURATED,
        engine_evidence=[EngineEvidenceInput(
            scientific_name=taxon, target_indication="TestIndication",
            notes="No documented safety concerns.",
        )],
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return lock_gold_case(case)


def _locked_safety_serious_case(case_id="safety1", taxon="DangerousTaxon"):
    """A fully locked case whose resolved outcome expects a SERIOUS
    safety flag, with matching engine_evidence that should make the
    real engine independently detect it."""
    unit = ValidationUnit(
        taxon=taxon, indication="TestIndication", jurisdiction="EU",
        preparation=PreparationSpec(dosage_form="Infusion"),
    )
    ref = ReferenceDescriptor(reference_id=f"{case_id}_ref", source_type="EMA_HMPC", version="v1")
    claim = ReferenceClaim(
        domain=ReferenceDomain.SAFETY, assertion_type=AssertionType.CONTRAINDICATION,
        subject="pregnancy", assertion_state=AssertionState.PRESENT, severity=SeverityLevel.SERIOUS,
        source_reference_id=ref.reference_id, source_locator="sec 4.3",
        evidence_text=NormalizedEvidenceText("x", "y", TransformationType.VERBATIM, "1.0", "sec 4.3"),
    )
    gref = GoldCaseReference(reference=ref, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.SAFETY] = check_applicability(ref, unit, ReferenceDomain.SAFETY)

    case = GoldCase(
        case_id=case_id, validation_unit=unit, references=[gref],
        expected_output=ExpectedOutput(expected_decision_direction=DecisionDirection.NEGATIVE),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=False),
        curation_status=CurationStatus.REFERENCE_CURATED,
        engine_evidence=[EngineEvidenceInput(
            scientific_name=taxon, target_indication="TestIndication",
            notes="Documented kidney stone formation with prolonged use.",
            compound_activity_targets=("Lithogenic",),
        )],
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return lock_gold_case(case)


# ---------------------------------------------------------------------
# _derive_direction_from_decision_class
# ---------------------------------------------------------------------

def test_derive_direction_positive():
    assert _derive_direction_from_decision_class("Strong R&D candidate") == DecisionDirection.POSITIVE


def test_derive_direction_negative():
    assert _derive_direction_from_decision_class("Safety concern — not suitable without expert review") == DecisionDirection.NEGATIVE


def test_derive_direction_hold():
    assert _derive_direction_from_decision_class("Low priority / insufficient data") == DecisionDirection.HOLD


def test_derive_direction_unrecognized_returns_none():
    assert _derive_direction_from_decision_class("Something made up") is None


# ---------------------------------------------------------------------
# ValidationScope enforcement (v4 correction #6/#8)
# ---------------------------------------------------------------------

def test_invalid_validation_scope_end_to_end_raises():
    from datetime import datetime, timezone
    try:
        EvaluationRun(
            evaluation_run_id="x", engine_version="1.0.0", gold_set_version="v1",
            execution_timestamp=datetime.now(timezone.utc), dataset_snapshot_hash="h",
            dataset_split_used="Locked holdout", validation_scope=ValidationScope.END_TO_END,
        )
        assert False, "should have raised"
    except InvalidValidationScopeError:
        pass


def test_build_evaluation_run_always_uses_provided_evidence_scope():
    _reset_engine_globals()
    run = build_evaluation_run([])
    assert run.validation_scope == ValidationScope.PROVIDED_EVIDENCE


# ---------------------------------------------------------------------
# Guardrails: LOCKED_HOLDOUT + locked=True + leakage-clean required
# ---------------------------------------------------------------------

def test_raises_on_non_holdout_case():
    _reset_engine_globals()
    case = GoldCase(case_id="dev1", validation_unit=ValidationUnit(taxon="X"), dataset_split=DatasetSplit.DEVELOPMENT)
    try:
        build_evaluation_run([case])
        assert False, "should have raised"
    except EvaluationRunError as e:
        assert "LOCKED_HOLDOUT" in str(e)


def test_raises_on_unlocked_holdout_split_case():
    # dataset_split is LOCKED_HOLDOUT but .locked is still False —
    # must be rejected (v4: locking is now a real prerequisite).
    _reset_engine_globals()
    case = GoldCase(
        case_id="unlocked1", validation_unit=ValidationUnit(taxon="X"),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
    )
    assert case.locked is False
    try:
        build_evaluation_run([case])
        assert False, "should have raised"
    except EvaluationRunError as e:
        assert "not locked" in str(e)


def test_raises_on_leakage_tainted_case():
    _reset_engine_globals()
    case = GoldCase(
        case_id="tainted1", validation_unit=ValidationUnit(taxon="X"),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT, locked=True,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=True),
    )
    try:
        build_evaluation_run([case])
        assert False, "should have raised"
    except EvaluationRunError as e:
        assert "leakage" in str(e).lower()


def test_empty_case_list_does_not_raise():
    _reset_engine_globals()
    run = build_evaluation_run([])
    assert run.case_count == 0


# ---------------------------------------------------------------------
# Real execution and metric computation
# ---------------------------------------------------------------------

def test_evaluation_run_has_reproducibility_metadata():
    _reset_engine_globals()
    case = _locked_clean_case()
    run = build_evaluation_run([case], gold_set_version="v1.0")
    assert run.evaluation_run_id
    assert run.engine_version == eng.DECISION_ENGINE_VERSION
    assert run.gold_set_version == "v1.0"
    assert run.dataset_split_used == "Locked holdout"
    assert len(run.dataset_snapshot_hash) == 64


def test_two_runs_on_same_input_get_different_run_ids_but_same_hash():
    _reset_engine_globals()
    case = _locked_clean_case()
    run_a = build_evaluation_run([case])
    run_b = build_evaluation_run([case])
    assert run_a.evaluation_run_id != run_b.evaluation_run_id
    assert run_a.dataset_snapshot_hash == run_b.dataset_snapshot_hash


def test_clean_case_produces_full_direction_agreement():
    _reset_engine_globals()
    case = _locked_clean_case()
    run = build_evaluation_run([case])
    direction_metric = next(m for m in run.results if m.metric_name == "decision_direction_agreement")
    assert direction_metric.status == MetricStatus.COMPUTED
    assert direction_metric.proportion.numerator == 1
    assert direction_metric.proportion.denominator == 1


def test_safety_serious_resolved_outcome_correctly_detected_zero_false_negatives():
    # THE key scientific test: a ResolvedExpectedOutcome (evaluator-only)
    # expects SERIOUS/PRESENT; engine_evidence (structurally separate)
    # supplies natural text + structured activity target; the REAL
    # engine independently produces the FAILED safety gate.
    _reset_engine_globals()
    case = _locked_safety_serious_case()
    run = build_evaluation_run([case])
    safety_metric = next(m for m in run.results if m.metric_name == "safety_serious_false_negative_rate")
    assert safety_metric.status == MetricStatus.COMPUTED
    assert safety_metric.proportion.numerator == 0
    assert safety_metric.proportion.denominator == 1


def test_safety_serious_metric_zero_denominator_when_no_such_outcomes():
    _reset_engine_globals()
    case = _locked_clean_case()  # ABSENT/NONE claim -> no SERIOUS/PRESENT outcome
    run = build_evaluation_run([case])
    safety_metric = next(m for m in run.results if m.metric_name == "safety_serious_false_negative_rate")
    assert safety_metric.status == MetricStatus.NOT_COMPUTABLE


def test_evaluation_run_results_always_has_two_metrics():
    _reset_engine_globals()
    run = build_evaluation_run([])
    names = {m.metric_name for m in run.results}
    assert names == {"decision_direction_agreement", "safety_serious_false_negative_rate"}


def test_explicit_evaluation_run_id_is_honored():
    _reset_engine_globals()
    run = build_evaluation_run([], evaluation_run_id="my-fixed-id")
    assert run.evaluation_run_id == "my-fixed-id"


def test_explicit_engine_version_override():
    _reset_engine_globals()
    run = build_evaluation_run([], engine_version="9.9.9-test")
    assert run.engine_version == "9.9.9-test"


def test_multiple_cases_produce_correct_aggregate_metrics():
    _reset_engine_globals()
    clean = _locked_clean_case(case_id="clean1", taxon="CleanTaxon1")
    safety = _locked_safety_serious_case(case_id="safety2", taxon="DangerousTaxon2")
    run = build_evaluation_run([clean, safety])
    assert run.case_count == 2
    direction_metric = next(m for m in run.results if m.metric_name == "decision_direction_agreement")
    assert direction_metric.proportion.denominator == 2
