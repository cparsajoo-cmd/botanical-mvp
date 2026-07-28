"""Regression tests for validation_protocol_execution.py — the bridge
between a locked ValidationCaseProtocol and the real,
BotanicalRDCandidateEngine. Runs the ACTUAL engine (no stubbing), same
pattern as test_task5_sensitivity_analysis_activation.py and
test_grade_certainty_persistence.py's end-to-end tests.
"""

from datetime import date

import pandas as pd

import botanical_rd_candidate_engine as eng
from validation_case_protocol import (
    ValidationCaseProtocol, DecisionContext, LockedCandidateSet,
    CandidateEligibilityRule, ReferenceEvidenceCorpus, ExpertPanel,
    ExpertPanelMember, lock_protocol,
)
from validation_protocol_execution import (
    execute_protocol_against_engine,
    summarize_platform_output,
    ProtocolNotLockedError,
)


def _reset_engine_globals():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}


def _locked_protocol(candidates=("PlantA", "PlantB"), indication="TestIndication", **overrides):
    protocol = ValidationCaseProtocol(
        case_name="Test case",
        decision_context=DecisionContext(
            population="Adults", route_of_administration="Oral",
            dosage_form="Infusion", jurisdiction="EU", indication=indication,
        ),
        candidate_set=LockedCandidateSet(
            candidates=list(candidates),
            eligibility_rules=[CandidateEligibilityRule("Documented traditional use")],
        ),
        reference_corpus=ReferenceEvidenceCorpus(
            description="d", built_independently_of_platform=True, sources=["x"],
            search_strategy="s", evidence_cutoff_date=date(2026, 1, 1),
        ),
        expert_panel=ExpertPanel(
            members=[ExpertPanelMember("Pharmacognosist")],
            review_protocol="rp", independence_statement="is",
        ),
    )
    for k, v in overrides.items():
        setattr(protocol.decision_context, k, v) if hasattr(protocol.decision_context, k) else setattr(protocol, k, v)
    return lock_protocol(protocol)


def _sample_plant_compounds_df():
    return pd.DataFrame([
        dict(scientific_name="PlantA", compound_name="CompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantB", compound_name="CompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantC", compound_name="CompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ])


# ---------------------------------------------------------------------
# ProtocolNotLockedError — the hard refusal
# ---------------------------------------------------------------------

def test_unlocked_protocol_raises():
    _reset_engine_globals()
    unlocked = ValidationCaseProtocol(case_name="Not locked")
    try:
        execute_protocol_against_engine(unlocked, _sample_plant_compounds_df())
        assert False, "should have raised"
    except ProtocolNotLockedError:
        pass


def test_conditionally_ready_protocol_still_raises():
    _reset_engine_globals()
    protocol = ValidationCaseProtocol(
        case_name="Conditionally ready only",
        decision_context=DecisionContext(
            population="Adults", route_of_administration="Oral",
            dosage_form="Infusion", jurisdiction="EU", indication="TestIndication",
        ),
    )
    assert protocol.locked is False
    try:
        execute_protocol_against_engine(protocol, _sample_plant_compounds_df())
        assert False, "should have raised"
    except ProtocolNotLockedError:
        pass


# ---------------------------------------------------------------------
# Missing indication
# ---------------------------------------------------------------------

def test_missing_indication_raises_value_error():
    _reset_engine_globals()
    protocol = ValidationCaseProtocol(
        case_name="No indication",
        decision_context=DecisionContext(
            population="Adults", route_of_administration="Oral",
            dosage_form="Infusion", jurisdiction="EU",
        ),
        candidate_set=LockedCandidateSet(
            candidates=["PlantA"], eligibility_rules=[CandidateEligibilityRule("r")],
        ),
        reference_corpus=ReferenceEvidenceCorpus(
            description="d", built_independently_of_platform=True, sources=["x"],
            search_strategy="s", evidence_cutoff_date=date(2026, 1, 1),
        ),
        expert_panel=ExpertPanel(
            members=[ExpertPanelMember("P")], review_protocol="rp",
            independence_statement="is",
        ),
    )
    locked = lock_protocol(protocol)
    assert locked.decision_context.indication is None
    try:
        execute_protocol_against_engine(locked, _sample_plant_compounds_df())
        assert False, "should have raised"
    except ValueError as e:
        assert "indication" in str(e)


# ---------------------------------------------------------------------
# plant_compounds_df validation
# ---------------------------------------------------------------------

def test_missing_scientific_name_column_raises():
    _reset_engine_globals()
    protocol = _locked_protocol()
    bad_df = pd.DataFrame([{"wrong_column": "PlantA"}])
    try:
        execute_protocol_against_engine(protocol, bad_df)
        assert False, "should have raised"
    except ValueError as e:
        assert "scientific_name" in str(e)


def test_no_matching_candidates_raises():
    _reset_engine_globals()
    protocol = _locked_protocol(candidates=["GhostPlant"])
    try:
        execute_protocol_against_engine(protocol, _sample_plant_compounds_df())
        assert False, "should have raised"
    except ValueError as e:
        assert "GhostPlant" in str(e)


# ---------------------------------------------------------------------
# Real execution against the real engine
# ---------------------------------------------------------------------

def test_execution_returns_a_real_result_dataframe():
    _reset_engine_globals()
    protocol = _locked_protocol()
    result_df = execute_protocol_against_engine(protocol, _sample_plant_compounds_df())
    assert isinstance(result_df, pd.DataFrame)
    assert not result_df.empty
    assert "Decision_Class" in result_df.columns
    assert "R&D_Opportunity_Score" in result_df.columns


def test_execution_only_includes_locked_candidates_not_the_full_background():
    _reset_engine_globals()
    protocol = _locked_protocol(candidates=["PlantA", "PlantB"])
    result_df = execute_protocol_against_engine(protocol, _sample_plant_compounds_df())
    all_plants = set(result_df["Reference_Plant"]) | set(result_df["Alternative_Plant"])
    assert "PlantC" not in all_plants
    assert all_plants == {"PlantA", "PlantB"}


def test_execution_output_includes_grade_and_gate_columns_untouched():
    # Confirms this module doesn't strip or alter anything the engine
    # itself already produces (GRADE_Certainty, Gate_Results, etc.).
    _reset_engine_globals()
    protocol = _locked_protocol()
    result_df = execute_protocol_against_engine(protocol, _sample_plant_compounds_df())
    assert "GRADE_Certainty" in result_df.columns
    assert "Gate_Results" in result_df.columns
    assert list(result_df.columns) == eng.OUTPUT_COLUMNS


def test_execution_result_matches_calling_the_engine_directly():
    # The bridge must not alter engine behavior in any way — running
    # the engine directly on the same filtered data must produce an
    # identical result.
    _reset_engine_globals()
    protocol = _locked_protocol()
    df = _sample_plant_compounds_df()
    bridged_result = execute_protocol_against_engine(protocol, df)

    _reset_engine_globals()
    filtered = df[df["scientific_name"].isin(["PlantA", "PlantB"])]
    direct_engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=filtered, compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(), evidence_df=pd.DataFrame(),
        use_live_search=False,
    )
    direct_result = direct_engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    pd.testing.assert_frame_equal(
        bridged_result.reset_index(drop=True), direct_result.reset_index(drop=True)
    )


# ---------------------------------------------------------------------
# summarize_platform_output
# ---------------------------------------------------------------------

def test_summarize_platform_output_shape():
    _reset_engine_globals()
    protocol = _locked_protocol()
    result_df = execute_protocol_against_engine(protocol, _sample_plant_compounds_df())
    summary = summarize_platform_output(result_df)
    assert len(summary) == len(result_df)
    for entry in summary:
        assert set(entry.keys()) == {
            "reference_plant", "alternative_plant", "platform_decision_class",
            "platform_decision_class_ah", "platform_rd_opportunity_score",
            "platform_grade_certainty",
        }


def test_summarize_platform_output_never_uses_expected_or_validated_language():
    # Guards the module's own core honesty claim: nothing in the
    # returned keys implies this is a validated/expected result.
    _reset_engine_globals()
    protocol = _locked_protocol()
    result_df = execute_protocol_against_engine(protocol, _sample_plant_compounds_df())
    summary = summarize_platform_output(result_df)
    for entry in summary:
        for key in entry:
            assert "expected" not in key.lower()
            assert "validated" not in key.lower()


def test_summarize_platform_output_empty_dataframe():
    assert summarize_platform_output(pd.DataFrame()) == []


def test_summarize_platform_output_none_input():
    assert summarize_platform_output(None) == []
