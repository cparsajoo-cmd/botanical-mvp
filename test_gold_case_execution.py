"""Tests for gold_case_execution.py (Validation Architecture v3, Phase 2).

Runs the REAL BotanicalRDCandidateEngine — no stubbing — same
convention as test_validation_protocol_execution.py's own end-to-end
tests. The most important test in this file
(test_safety_serious_case_actually_triggers_the_hard_safety_gate) is a
direct regression lock against the self-match bug this module's
docstring documents finding and fixing.
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
from gold_case import GoldCase, GoldCaseReference, ExpectedOutput, RiskStratum, DecisionDirection
from gold_case_execution import (
    execute_gold_case_against_engine,
    platform_output_for_gold_case,
    GoldCaseNotExecutableError,
    _GOLD_CASE_ANCHOR_TAXON,
)
from validation_unit import ValidationUnit, PreparationSpec


def _reset_engine_globals():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}


def _executable_case(taxon="TestTaxon", **overrides):
    defaults = dict(
        taxon=taxon,
        indication="TestIndication",
        preparation=PreparationSpec(dosage_form="Infusion"),
        jurisdiction="EU",
    )
    defaults.update(overrides)
    unit = ValidationUnit(**defaults)
    return GoldCase(case_id="test_case", validation_unit=unit, risk_strata=[RiskStratum.CLEAN_BASELINE])


# ---------------------------------------------------------------------
# GoldCaseNotExecutableError
# ---------------------------------------------------------------------

def test_missing_indication_raises():
    _reset_engine_globals()
    unit = ValidationUnit(taxon="X", preparation=PreparationSpec(dosage_form="Infusion"))
    case = GoldCase(case_id="c1", validation_unit=unit)
    try:
        execute_gold_case_against_engine(case)
        assert False, "should have raised"
    except GoldCaseNotExecutableError as e:
        assert "indication" in str(e)


def test_missing_dosage_form_raises():
    _reset_engine_globals()
    unit = ValidationUnit(taxon="X", indication="TestIndication")
    case = GoldCase(case_id="c1", validation_unit=unit)
    try:
        execute_gold_case_against_engine(case)
        assert False, "should have raised"
    except GoldCaseNotExecutableError as e:
        assert "dosage_form" in str(e)


def test_missing_preparation_entirely_raises():
    _reset_engine_globals()
    unit = ValidationUnit(taxon="X", indication="TestIndication")  # preparation=None
    case = GoldCase(case_id="c1", validation_unit=unit)
    try:
        execute_gold_case_against_engine(case)
        assert False, "should have raised"
    except GoldCaseNotExecutableError:
        pass


# ---------------------------------------------------------------------
# Real execution
# ---------------------------------------------------------------------

def test_executable_case_returns_exactly_one_row():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    assert len(result) == 1


def test_returned_row_uses_anchor_as_reference_and_taxon_as_alternative():
    # Direct regression lock for the self-match bug this module exists
    # to avoid — see module docstring.
    _reset_engine_globals()
    case = _executable_case(taxon="MyTestTaxon")
    result = execute_gold_case_against_engine(case)
    row = result.iloc[0]
    assert row["Reference_Plant"] == _GOLD_CASE_ANCHOR_TAXON
    assert row["Alternative_Plant"] == "MyTestTaxon"
    assert row["Reference_Plant"] != row["Alternative_Plant"]  # never a self-match


def test_safety_serious_case_actually_triggers_the_hard_safety_gate():
    # THE critical test: a hard-safety-triggering target must actually
    # produce GateStatus.FAILED and the "Safety concern" Decision_Class
    # — this is exactly what the self-match bug silently prevented.
    _reset_engine_globals()
    case = _executable_case(taxon="DangerousTestTaxon")
    result = execute_gold_case_against_engine(case, target="Lithogenic")
    output = platform_output_for_gold_case(result)
    assert output["decision_class"] == "Safety concern — not suitable without expert review"
    from data_contracts import GateStatus
    assert output["gate_results"]["safety"]["status"] == GateStatus.FAILED


def test_safety_gate_not_exempted_by_same_plant_logic():
    # Confirms the safety gate reason text is a REAL evaluation, not
    # the same_plant exemption text a self-match row would produce.
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    output = platform_output_for_gold_case(result)
    assert "matched to itself" not in output["gate_results"]["safety"]["reason"]


def test_clean_case_passes_safety_gate():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    output = platform_output_for_gold_case(result)
    from data_contracts import GateStatus
    assert output["gate_results"]["safety"]["status"] == GateStatus.PASSED


def test_regulatory_prohibition_also_triggers_correctly():
    _reset_engine_globals()
    case = _executable_case(taxon="ProhibitedTestTaxon")
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "ProhibitedTestTaxon",
        "Target_Indication": "TestIndication",
        "Notes": "This substance is prohibited and banned for sale in several jurisdictions.",
    }])
    result = execute_gold_case_against_engine(case, evidence_df=evidence_df)
    output = platform_output_for_gold_case(result)
    assert output["decision_class"] == "Regulatory prohibition — not suitable without regulatory review"


def test_plant_part_and_solvent_flow_into_extraction_method():
    _reset_engine_globals()
    case = _executable_case(plant_part="root", preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%"))
    result = execute_gold_case_against_engine(case)
    assert len(result) == 1  # doesn't raise, ran successfully with these fields set


def test_output_includes_grade_certainty_field():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    output = platform_output_for_gold_case(result)
    assert "grade_certainty" in output


# ---------------------------------------------------------------------
# platform_output_for_gold_case
# ---------------------------------------------------------------------

def test_platform_output_empty_dataframe_returns_empty_dict():
    assert platform_output_for_gold_case(pd.DataFrame()) == {}


def test_platform_output_none_returns_empty_dict():
    assert platform_output_for_gold_case(None) == {}


def test_platform_output_shape():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    output = platform_output_for_gold_case(result)
    assert set(output.keys()) == {
        "decision_class", "decision_class_ah", "gate_results",
        "grade_certainty", "rd_opportunity_score",
    }


# ---------------------------------------------------------------------
# Never touches the real engine's own code, never mutates it
# ---------------------------------------------------------------------

def test_module_never_modifies_botanical_rd_candidate_engine_output_columns():
    _reset_engine_globals()
    original_columns = list(eng.OUTPUT_COLUMNS)
    case = _executable_case()
    execute_gold_case_against_engine(case)
    assert list(eng.OUTPUT_COLUMNS) == original_columns
