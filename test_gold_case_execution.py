"""Tests for gold_case_execution.py (Reference-Grounded Validation, v4).

Runs the REAL BotanicalRDCandidateEngine — no stubbing. Uses
EngineEvidenceInput exclusively; no bare target= kwarg exists anymore
(see test_structural_leakage_boundary.py for the interface-level
regression lock on that removal).
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
from data_contracts import GateStatus
from engine_evidence_input import EngineEvidenceInput
from gold_case import GoldCase
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
    return GoldCase(case_id="test_case", validation_unit=unit)


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
    unit = ValidationUnit(taxon="X", indication="TestIndication")
    case = GoldCase(case_id="c1", validation_unit=unit)
    try:
        execute_gold_case_against_engine(case)
        assert False, "should have raised"
    except GoldCaseNotExecutableError:
        pass


# ---------------------------------------------------------------------
# Real execution, no evidence
# ---------------------------------------------------------------------

def test_executable_case_returns_exactly_one_row():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    assert len(result) == 1


def test_returned_row_uses_anchor_as_reference_and_taxon_as_alternative():
    _reset_engine_globals()
    case = _executable_case(taxon="MyTestTaxon")
    result = execute_gold_case_against_engine(case)
    row = result.iloc[0]
    assert row["Reference_Plant"] == _GOLD_CASE_ANCHOR_TAXON
    assert row["Alternative_Plant"] == "MyTestTaxon"
    assert row["Reference_Plant"] != row["Alternative_Plant"]


def test_clean_case_passes_safety_gate():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    output = platform_output_for_gold_case(result)
    assert output["gate_results"]["safety"]["status"] == GateStatus.PASSED


def test_safety_gate_not_exempted_by_same_plant_logic():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case)
    output = platform_output_for_gold_case(result)
    assert "matched to itself" not in output["gate_results"]["safety"]["reason"]


def test_no_evidence_argument_defaults_to_empty_and_does_not_raise():
    _reset_engine_globals()
    case = _executable_case()
    result = execute_gold_case_against_engine(case, evidence=None)
    assert len(result) == 1


# ---------------------------------------------------------------------
# Structured Safety-Target Gate Validation (v4 correction #2)
#
# Real execution WITH EngineEvidenceInput, NO bare target= kwarg
# anywhere. The pair of tests below documents the CURRENT capability
# boundary, not an aspiration: compound_activity_targets (a
# preclassified structured hazard input) is the only channel that can
# activate the Hard Safety Gate. notes (natural text) is a real,
# independent production input to the engine, but it cannot reach
# HARD_SAFETY_TERMS — SAFETY_TERMS (what free text is scanned against)
# and HARD_SAFETY_TERMS (what forces the hard stop) are disjoint
# vocabularies by design. See engine_evidence_input.py's module
# docstring and botanical_rd_candidate_engine.py's SAFETY_TERMS /
# HARD_SAFETY_TERMS definitions. This file does NOT claim natural-text
# extraction of hard-safety concepts is implemented or validated.
# ---------------------------------------------------------------------

def test_structured_safety_target_gate_validation_fails_on_preclassified_hazard_target():
    """Validates: preclassified structured hazard input
    (compound_activity_targets) -> production plant_compounds_df["target"]
    column -> Hard Safety Gate. Does NOT demonstrate natural-text
    detection — see the companion capability-boundary test below,
    which shows the same hazard word in notes alone does not fire this
    gate."""
    _reset_engine_globals()
    case = _executable_case(taxon="DangerousTestTaxon")
    evidence = [EngineEvidenceInput(
        scientific_name="DangerousTestTaxon", target_indication="TestIndication",
        notes="Case reports describe kidney stone formation associated with prolonged use.",
        compound_activity_targets=("Lithogenic",),
    )]
    result = execute_gold_case_against_engine(case, evidence=evidence)
    output = platform_output_for_gold_case(result)
    assert output["decision_class"] == "Safety concern — not suitable without expert review"
    assert output["gate_results"]["safety"]["status"] == GateStatus.FAILED


def test_capability_boundary_notes_alone_cannot_trigger_hard_safety_gate():
    """Documents the current capability boundary: even hazard-adjacent
    language in notes — the literal word "lithogenic" plus
    "contraindicated" and "pregnancy" — does NOT activate the Hard
    Safety Gate when compound_activity_targets is empty. Free text is
    scanned only against SAFETY_TERMS (a disjoint, softer vocabulary);
    HARD_SAFETY_TERMS is reachable only via the structured target
    field — see the companion test above for the positive case. This
    is not a desired future capability being asserted; it is what the
    engine, unmodified, does today."""
    _reset_engine_globals()
    case = _executable_case(taxon="NotesOnlyHazardLanguageTaxon")
    evidence = [EngineEvidenceInput(
        scientific_name="NotesOnlyHazardLanguageTaxon", target_indication="TestIndication",
        notes=(
            "Documented lithogenic activity; case reports describe kidney "
            "stone formation. Contraindicated in pregnancy. Serious risk."
        ),
        compound_activity_targets=(),
    )]
    result = execute_gold_case_against_engine(case, evidence=evidence)
    output = platform_output_for_gold_case(result)
    assert output["gate_results"]["safety"]["status"] == GateStatus.PASSED
    assert "lithogenic" not in output["gate_results"]["safety"]["reason"].lower()


def test_regulatory_prohibition_triggers_via_natural_text_notes():
    _reset_engine_globals()
    case = _executable_case(taxon="ProhibitedTestTaxon")
    evidence = [EngineEvidenceInput(
        scientific_name="ProhibitedTestTaxon", target_indication="TestIndication",
        notes="This substance is prohibited and banned for sale in several jurisdictions.",
    )]
    result = execute_gold_case_against_engine(case, evidence=evidence)
    output = platform_output_for_gold_case(result)
    assert output["decision_class"] == "Regulatory prohibition — not suitable without regulatory review"


def test_evidence_for_a_different_taxon_does_not_affect_this_case():
    # Evidence keyed to a DIFFERENT scientific_name must not leak into
    # this taxon's row.
    _reset_engine_globals()
    case = _executable_case(taxon="InnocentTaxon")
    evidence = [EngineEvidenceInput(
        scientific_name="SomeOtherTaxon", target_indication="TestIndication",
        notes="Irrelevant evidence about a different plant.",
        compound_activity_targets=("Lithogenic",),
    )]
    result = execute_gold_case_against_engine(case, evidence=evidence)
    output = platform_output_for_gold_case(result)
    assert output["gate_results"]["safety"]["status"] == GateStatus.PASSED


def test_plant_part_and_solvent_flow_into_extraction_method():
    _reset_engine_globals()
    case = _executable_case(plant_part="root", preparation=PreparationSpec(dosage_form="Extract", solvent="ethanol 70%"))
    result = execute_gold_case_against_engine(case)
    assert len(result) == 1


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


def test_module_never_modifies_botanical_rd_candidate_engine_output_columns():
    _reset_engine_globals()
    original_columns = list(eng.OUTPUT_COLUMNS)
    case = _executable_case()
    execute_gold_case_against_engine(case)
    assert list(eng.OUTPUT_COLUMNS) == original_columns
