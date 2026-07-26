"""
Task 3 — Externalized, versioned scoring weights (ScoringConfig).

WHAT THIS COVERS
botanical_rd_candidate_engine.ScoringConfig / DEFAULT_SCORING_CONFIG,
BotanicalRDCandidateEngine.__init__'s scoring_config parameter, and the
additive Scoring_Config_Version column produced through run(). The two
non-negotiable guarantees: (1) DEFAULT_SCORING_CONFIG reproduces
byte-identical scores to the pre-Task-3 hardcoded weights, and (2) a
custom config changes score in a predictable, single-component way —
nothing else about _score_candidate's control flow, rounding, or
clamping changes.

HOW TO RUN
    pytest -q test_scoring_config.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import dataclasses

import pandas as pd
import pytest

import botanical_rd_candidate_engine as eng
from test_botanical_rd_candidate_engine import make_engine


def _two_row_fixture():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="SharedCompound",
             indication="Other", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    return rows


# ---------------------------------------------------------------------
# DEFAULT_SCORING_CONFIG must reproduce byte-identical scores to the
# pre-Task-3 hardcoded weights.
# ---------------------------------------------------------------------

def test_default_scoring_config_reproduces_identical_scores_to_pre_task_hardcoded_values():
    engine = make_engine(_two_row_fixture())
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    result_sorted = result.sort_values(
        ["Reference_Plant", "Alternative_Plant"]
    ).reset_index(drop=True)
    alt_row = result_sorted[result_sorted["Alternative_Plant"] == "AltPlant"].iloc[0]
    self_row = result_sorted[result_sorted["Alternative_Plant"] == "RefPlant"].iloc[0]

    # Exact values recorded before ScoringConfig existed (see the
    # identical fixture and assertions in
    # test_gate_layer.py::test_deterministic_output_contract_locked_engineering_regression).
    assert alt_row["R&D_Opportunity_Score"] == 38.0
    assert alt_row["Decision_Class"] == "Low priority / insufficient data"
    assert self_row["R&D_Opportunity_Score"] == 23.0
    assert self_row["Decision_Class"] == "Low priority / insufficient data"


def test_default_scoring_config_field_values_match_documented_pre_task_weights():
    # Cross-check the dataclass defaults themselves against
    # _score_candidate's own "COMPLETE WEIGHTS TABLE" docstring values —
    # catches drift even in a fixture that wouldn't otherwise expose a
    # particular weight.
    config = eng.DEFAULT_SCORING_CONFIG
    assert config.chem_link_exact == 22
    assert config.chem_link_target_verified == 15
    assert config.chem_link_class_only == 5
    assert config.evidence_clinical == 24
    assert config.evidence_regulatory == 20
    assert config.evidence_preclinical == 12
    assert config.evidence_general_literature == 7
    assert config.evidence_none == 0
    assert config.product_fit_concentration_reported == 10
    assert config.product_fit_concentration_missing == 2
    assert config.product_fit_extraction_cap == 18
    assert config.product_fit_co_compound_per_item == 2
    assert config.product_fit_co_compound_cap == 8
    assert config.product_fit_target_identified == 8
    assert config.product_fit_target_missing == 1
    assert config.novelty_common == 0
    assert config.novelty_alternative == 10
    assert config.novelty_other == 2
    assert config.market_verified_marketed_product == 1
    assert config.market_regulatory_monograph_or_traditional_use == 2
    assert config.market_commercial_evidence_reported == 2
    assert config.market_no_verified_product_found == 6
    assert config.market_conflicting_evidence == -2
    assert config.market_search_incomplete == 3
    assert config.market_neutral_default == 3
    assert config.safety_flag_penalty == -14
    assert config.interaction_flag_penalty == -10
    assert config.same_plant_penalty == -15


# ---------------------------------------------------------------------
# A custom config changes score predictably: one changed weight moves
# ONE component's contribution and the total by exactly that amount;
# every other component is untouched.
# ---------------------------------------------------------------------

def test_custom_scoring_config_changes_only_the_targeted_component():
    engine_default = make_engine(_two_row_fixture())
    baseline = engine_default.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    baseline_alt = baseline[baseline["Alternative_Plant"] == "AltPlant"].iloc[0]

    custom_config = dataclasses.replace(
        eng.DEFAULT_SCORING_CONFIG,
        version="1.1-test-custom",
        chem_link_exact=eng.DEFAULT_SCORING_CONFIG.chem_link_exact + 10,
    )
    engine_custom = make_engine(_two_row_fixture())
    engine_custom.scoring_config = custom_config
    result = engine_custom.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    alt_row = result[result["Alternative_Plant"] == "AltPlant"].iloc[0]

    # Only the chemical-link weight changed, by +10 — the final score
    # (before any clamp) must move by exactly that amount.
    assert alt_row["R&D_Opportunity_Score"] == pytest.approx(baseline_alt["R&D_Opportunity_Score"] + 10, abs=0.01)
    assert alt_row["Scoring_Config_Version"] == "1.1-test-custom"


def test_scoring_config_is_frozen_and_cannot_be_mutated_in_place():
    with pytest.raises(dataclasses.FrozenInstanceError):
        eng.DEFAULT_SCORING_CONFIG.chem_link_exact = 999


def test_mutating_a_custom_config_instance_does_not_affect_default():
    custom = dataclasses.replace(eng.DEFAULT_SCORING_CONFIG, chem_link_exact=999, version="custom")
    assert eng.DEFAULT_SCORING_CONFIG.chem_link_exact == 22
    assert eng.DEFAULT_SCORING_CONFIG.version == "1.0-default"
    assert custom.chem_link_exact == 999


# ---------------------------------------------------------------------
# __init__ wiring: defaults to DEFAULT_SCORING_CONFIG, accepts an
# explicit override.
# ---------------------------------------------------------------------

def test_engine_defaults_to_default_scoring_config():
    engine = make_engine(_two_row_fixture())
    assert engine.scoring_config is eng.DEFAULT_SCORING_CONFIG
    assert engine.scoring_config.version == "1.0-default"


def test_engine_accepts_explicit_scoring_config_override():
    custom_config = dataclasses.replace(eng.DEFAULT_SCORING_CONFIG, version="2.0-custom")
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(_two_row_fixture()),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
        scoring_config=custom_config,
    )
    assert engine.scoring_config is custom_config
    assert engine.scoring_config.version == "2.0-custom"


# ---------------------------------------------------------------------
# Scoring_Config_Version populated end-to-end through run(), and
# survives the multi-compound merge (same value across an entire run —
# no per-row recomputation needed, unlike Task 1's Gate_Results).
# ---------------------------------------------------------------------

def test_scoring_config_version_populated_end_to_end_through_run():
    engine = make_engine(_two_row_fixture())
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    assert "Scoring_Config_Version" in result.columns
    assert (result["Scoring_Config_Version"] == "1.0-default").all()


def test_scoring_config_version_survives_multi_compound_merge():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="CompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="RefPlant", compound_name="CompoundB",
             indication="TestIndication", target="Diuretic",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="CompoundA",
             indication="Other", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="CompoundB",
             indication="Other", target="Diuretic",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    alt_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlant")
    ]
    assert not alt_row.empty
    assert alt_row.iloc[0]["Scoring_Config_Version"] == "1.0-default"


# ---------------------------------------------------------------------
# Backward compatibility: existing candidate_output_adapter validation
# still accepts rows with the new column, and exposes it on
# CandidateAssessment.
# ---------------------------------------------------------------------

def test_candidate_assessment_includes_scoring_config_version():
    import data_contracts as dc
    cand = dc.CandidateAssessment(
        project_id="p1", indication="Liver support", product_type="Infusion",
        dosage_form="Infusion", target_market="EU",
        reference_plant="Silybum marianum", reference_plant_part=None,
        reference_compound="Silymarin", reference_compound_id=None,
        alternative_plant="Allium cepa", alternative_plant_part=None,
        alternative_compound="Quercetin", alternative_compound_id=None,
        scoring_config_version="1.0-default",
    )
    assert cand.scoring_config_version == "1.0-default"


def test_validate_result_df_passes_through_scoring_config_version():
    from candidate_output_adapter import validate_result_df
    engine = make_engine(_two_row_fixture())
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    records, errors_df = validate_result_df(result, indication="TestIndication", project_id="p1")
    assert len(records) == len(result)
    assert all(r.scoring_config_version == "1.0-default" for r in records)
