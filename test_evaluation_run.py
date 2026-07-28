"""Tests for evaluation_run.py (Validation Architecture v3, Phase 2).

Runs the REAL engine (via gold_case_execution.py) — no stubbing.
"""

import botanical_rd_candidate_engine as eng
from dataset_split import DatasetSplit, LeakageControl
from gold_case import GoldCase, RiskStratum, ExpectedOutput, DecisionDirection
from evaluation_run import (
    build_evaluation_run, EvaluationRunError, EvaluationRun,
    _derive_direction_from_decision_class,
)
from metric_report import MetricStatus
from validation_unit import ValidationUnit, PreparationSpec


def _reset_engine_globals():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}


def _holdout_case(case_id, taxon, expected_direction, risk_strata=None, executable=True):
    unit_kwargs = dict(taxon=taxon, indication="TestIndication", jurisdiction="EU")
    if executable:
        unit_kwargs["preparation"] = PreparationSpec(dosage_form="Infusion")
    return GoldCase(
        case_id=case_id,
        validation_unit=ValidationUnit(**unit_kwargs),
        risk_strata=risk_strata or [RiskStratum.CLEAN_BASELINE],
        expected_output=ExpectedOutput(expected_decision_direction=expected_direction),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=False),
    )


# ---------------------------------------------------------------------
# _derive_direction_from_decision_class
# ---------------------------------------------------------------------

def test_derive_direction_positive():
    assert _derive_direction_from_decision_class("Strong R&D candidate") == DecisionDirection.POSITIVE
    assert _derive_direction_from_decision_class("Early-stage candidate; more evidence needed") == DecisionDirection.POSITIVE


def test_derive_direction_negative():
    assert _derive_direction_from_decision_class("Safety concern — not suitable without expert review") == DecisionDirection.NEGATIVE
    assert _derive_direction_from_decision_class("Regulatory prohibition — not suitable without regulatory review") == DecisionDirection.NEGATIVE


def test_derive_direction_hold():
    assert _derive_direction_from_decision_class("Low priority / insufficient data") == DecisionDirection.HOLD


def test_derive_direction_unrecognized_returns_none():
    assert _derive_direction_from_decision_class("Something made up") is None
    assert _derive_direction_from_decision_class(None) is None


# ---------------------------------------------------------------------
# Guardrails: only LOCKED_HOLDOUT, leakage-clean cases accepted
# ---------------------------------------------------------------------

def test_raises_on_non_holdout_case():
    _reset_engine_globals()
    case = GoldCase(case_id="dev1", validation_unit=ValidationUnit(taxon="X"), dataset_split=DatasetSplit.DEVELOPMENT)
    try:
        build_evaluation_run([case])
        assert False, "should have raised"
    except EvaluationRunError as e:
        assert "LOCKED_HOLDOUT" in str(e)


def test_raises_on_validation_split_case():
    _reset_engine_globals()
    case = GoldCase(case_id="val1", validation_unit=ValidationUnit(taxon="X"), dataset_split=DatasetSplit.VALIDATION)
    try:
        build_evaluation_run([case])
        assert False, "should have raised"
    except EvaluationRunError:
        pass


def test_raises_on_leakage_tainted_case():
    _reset_engine_globals()
    case = GoldCase(
        case_id="tainted1", validation_unit=ValidationUnit(taxon="X"),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=True),
    )
    try:
        build_evaluation_run([case])
        assert False, "should have raised"
    except EvaluationRunError as e:
        assert "leakage" in str(e).lower()


def test_raises_on_quarantined_case():
    _reset_engine_globals()
    case = GoldCase(
        case_id="quarantined1", validation_unit=ValidationUnit(taxon="X"),
        dataset_split=DatasetSplit.LOCKED_HOLDOUT,
        leakage_control=LeakageControl(engine_output_observed_before_finalization=True, case_modified_after_observation=False),
    )
    try:
        build_evaluation_run([case])
        assert False, "should have raised"
    except EvaluationRunError:
        pass


def test_empty_case_list_does_not_raise():
    _reset_engine_globals()
    run = build_evaluation_run([])
    assert run.case_count == 0


# ---------------------------------------------------------------------
# Real execution and metric computation
# ---------------------------------------------------------------------

def test_evaluation_run_has_reproducibility_metadata():
    _reset_engine_globals()
    case = _holdout_case("c1", "Taxon1", DecisionDirection.HOLD)
    run = build_evaluation_run([case], gold_set_version="v1.0")
    assert run.evaluation_run_id
    assert run.engine_version == eng.DECISION_ENGINE_VERSION
    assert run.gold_set_version == "v1.0"
    assert run.dataset_split_used == "Locked holdout"
    assert len(run.dataset_snapshot_hash) == 64


def test_two_runs_on_same_input_get_different_run_ids_but_same_hash():
    _reset_engine_globals()
    case = _holdout_case("c1", "Taxon1", DecisionDirection.HOLD)
    run_a = build_evaluation_run([case])
    run_b = build_evaluation_run([case])
    assert run_a.evaluation_run_id != run_b.evaluation_run_id
    assert run_a.dataset_snapshot_hash == run_b.dataset_snapshot_hash


def test_clean_agreeing_case_produces_full_agreement():
    _reset_engine_globals()
    # No hazard signal -> engine produces HOLD (Low priority/insufficient
    # data) for a bare taxon+indication with no evidence -> matches
    # expected HOLD.
    case = _holdout_case("c1", "PlainTaxon", DecisionDirection.HOLD)
    run = build_evaluation_run([case])
    direction_metric = next(m for m in run.results if m.metric_name == "decision_direction_agreement")
    assert direction_metric.status == MetricStatus.COMPUTED
    assert direction_metric.proportion.numerator == 1
    assert direction_metric.proportion.denominator == 1


def test_inexecutable_case_is_recorded_not_silently_dropped():
    _reset_engine_globals()
    case = _holdout_case("c1", "NoPrepTaxon", DecisionDirection.HOLD, executable=False)
    run = build_evaluation_run([case])
    assert "c1" in run.inexecutable_case_ids
    assert run.case_count == 1


def test_inexecutable_case_excluded_from_metric_denominator():
    _reset_engine_globals()
    executable_case = _holdout_case("c1", "Taxon1", DecisionDirection.HOLD)
    inexecutable_case = _holdout_case("c2", "Taxon2", DecisionDirection.HOLD, executable=False)
    run = build_evaluation_run([executable_case, inexecutable_case])
    direction_metric = next(m for m in run.results if m.metric_name == "decision_direction_agreement")
    assert direction_metric.proportion.denominator == 1  # only the executable one counted


def test_safety_serious_metric_zero_denominator_when_no_safety_serious_cases():
    _reset_engine_globals()
    case = _holdout_case("c1", "Taxon1", DecisionDirection.HOLD, risk_strata=[RiskStratum.CLEAN_BASELINE])
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
