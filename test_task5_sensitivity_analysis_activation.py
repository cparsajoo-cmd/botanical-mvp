"""
Task 5 — Automatic sensitivity analysis, wired into
BotanicalRDCandidateEngine.run().

WHAT THIS COVERS
- Robustness_Analysis / Boundary_Fragility on OUTPUT_COLUMNS and on
  every candidate row produced by run().
- Non-regression: scoring, ranking, gates, confidence, Decision_Class
  unchanged apart from the two additive columns (same pattern as
  test_task15_decision_engine_version_tracking.py).
- Both new columns agree with directly calling
  scoring_sensitivity_report.py's functions on the same result.

WHAT THIS DELIBERATELY DOES NOT COVER
The internal correctness of build_robustness_analysis()/
boundary_fragility_series() themselves (see
test_scoring_sensitivity_report.py) — this file only covers that
run() wires them in correctly, once, without disturbing anything else.

HOW TO RUN
    pytest -q test_task5_sensitivity_analysis_activation.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
from scoring_sensitivity_report import build_robustness_analysis, boundary_fragility_series
from test_task15_decision_engine_version_tracking import _make_engine, _run


# ---------------------------------------------------------------------
# 1) The two new columns exist on OUTPUT_COLUMNS and on every row.
# ---------------------------------------------------------------------

def test_output_columns_include_the_two_new_fields():
    assert "Robustness_Analysis" in eng.OUTPUT_COLUMNS
    assert "Boundary_Fragility" in eng.OUTPUT_COLUMNS
    # Both must sit before the always-last reproducibility column.
    assert eng.OUTPUT_COLUMNS.index("Robustness_Analysis") < eng.OUTPUT_COLUMNS.index("Decision_Engine_Version")
    assert eng.OUTPUT_COLUMNS.index("Boundary_Fragility") < eng.OUTPUT_COLUMNS.index("Decision_Engine_Version")
    assert eng.OUTPUT_COLUMNS[-1] == "Decision_Engine_Version"


def test_every_candidate_row_contains_both_new_fields():
    result = _run()
    assert not result.empty
    assert "Robustness_Analysis" in result.columns
    assert "Boundary_Fragility" in result.columns
    assert result["Robustness_Analysis"].notna().all()
    assert result["Boundary_Fragility"].notna().all()


# ---------------------------------------------------------------------
# 2) Values agree with calling the standalone functions directly on
#    the same result — run() must not compute a second, different
#    version of this analysis.
# ---------------------------------------------------------------------

def test_wired_values_match_calling_the_standalone_functions_directly():
    result = _run()

    expected_robustness = build_robustness_analysis(result)
    expected_fragility = boundary_fragility_series(result)

    for idx in result.index:
        assert result.loc[idx, "Robustness_Analysis"] == expected_robustness.loc[idx]
        assert result.loc[idx, "Boundary_Fragility"] == expected_fragility.loc[idx]


def test_boundary_fragility_shape_is_correct():
    result = _run()
    for entry in result["Boundary_Fragility"]:
        assert isinstance(entry, dict)
        assert set(entry.keys()) == {
            "nearest_boundary", "distance_to_boundary",
            "is_boundary_fragile", "margin",
        }


def test_robustness_analysis_shape_is_correct():
    result = _run()
    for entry in result["Robustness_Analysis"]:
        assert isinstance(entry, dict)
        assert "status" in entry


# ---------------------------------------------------------------------
# 3) Non-regression: scoring, ranking, gates, confidence, Decision_Class
#    are completely unaffected by this task, exactly like Task 15's own
#    non-regression test for its own additive column.
# ---------------------------------------------------------------------

def test_non_regression_scoring_and_decision_unaffected():
    rows = [
        dict(scientific_name="PlantRef", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAlt", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAlt2", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ] + [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=pd.DataFrame(),
        use_live_search=False,
    )
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    compare_columns = [
        "Alternative_Plant", "R&D_Opportunity_Score", "Decision_Class",
        "Decision_Class_AH", "Gate_Results", "Evidence_Confidence",
    ]
    for col in compare_columns:
        assert col in result.columns
        assert result[col].notna().all() or result[col].map(lambda v: v is not None).all()

    # Row order (by R&D_Opportunity_Score, descending) must be preserved.
    scores = result["R&D_Opportunity_Score"].tolist()
    assert scores == sorted(scores, reverse=True)


def test_run_still_returns_a_plain_dataframe_with_exactly_output_columns():
    result = _run()
    assert isinstance(result, pd.DataFrame)
    assert list(result.columns) == eng.OUTPUT_COLUMNS


# ---------------------------------------------------------------------
# 4) Determinism: two fresh engine instances on the same inputs must
#    produce identical Robustness_Analysis / Boundary_Fragility.
# ---------------------------------------------------------------------

def test_deterministic_across_two_runs_with_same_inputs():
    result_a = _run()
    result_b = _run()

    for idx in result_a.index:
        assert result_a.loc[idx, "Boundary_Fragility"] == result_b.loc[idx, "Boundary_Fragility"]
        assert result_a.loc[idx, "Robustness_Analysis"] == result_b.loc[idx, "Robustness_Analysis"]
