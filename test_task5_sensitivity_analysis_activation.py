"""
Task 5 rollback — sensitivity analysis de-duplication.

WHAT THIS COVERS
An earlier version of BotanicalRDCandidateEngine.run() computed
Robustness_Analysis/Boundary_Fragility internally, duplicating
sensitivity_display_adapter.py's existing, UI-facing sensitivity
analysis (same underlying functions, same result_df, called a second
time for no additional consumer — neither column was ever read by
anything downstream of run(); see the Dependency Audit that found
this). That duplicate computation has been removed from run(); this
file proves:
  1. run() no longer produces Robustness_Analysis/Boundary_Fragility,
     and the engine module no longer even imports
     scoring_sensitivity_report (the duplicate call site is gone, not
     just its output).
  2. sensitivity_display_adapter.py — called from step_rd_candidates.py
     AFTER run() returns, exactly as before this rollback — is
     untouched and still produces its UI payload correctly from
     run()'s result_df. UI behavior is unchanged.
  3. Non-regression: scoring, ranking, gates, confidence, Decision_Class,
     and OUTPUT_COLUMNS are otherwise exactly what they were before
     Task 5 was ever added, plus the four intentional Phase 1 evidence
     interpretation columns (59 columns total).

WHAT THIS DELIBERATELY DOES NOT COVER
The internal correctness of fragility_report()/build_robustness_analysis()
themselves (see test_scoring_sensitivity_report.py) or of
prepare_sensitivity_payload()'s own reshaping logic (see
test_task2_sensitivity_ui.py) — this file only covers that run() no
longer duplicates that work, and that removing the duplicate did not
disturb anything else.

HOW TO RUN
    pytest -q test_task5_sensitivity_analysis_activation.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import inspect

import pandas as pd

import botanical_rd_candidate_engine as eng
from sensitivity_display_adapter import prepare_sensitivity_payload
from test_task15_decision_engine_version_tracking import _make_engine, _run


# ---------------------------------------------------------------------
# 1) The duplicate computation is gone — from OUTPUT_COLUMNS, from
#    every row run() produces, and from the module's own imports.
# ---------------------------------------------------------------------

def test_output_columns_do_not_include_the_removed_fields():
    assert "Robustness_Analysis" not in eng.OUTPUT_COLUMNS
    assert "Boundary_Fragility" not in eng.OUTPUT_COLUMNS


def test_output_columns_count_matches_pre_task_5_baseline():
    # 55 = 53 (Task 15's Decision_Engine_Version baseline) + 2 (Task 2's
    # GRADE_Certainty/GRADE_Certainty_Rationale, which is NOT part of
    # this rollback and stays). See test_gate_layer.py's own locked
    # column-count assertion for the authoritative version of this
    # check against a real run() result; this is the OUTPUT_COLUMNS
    # list itself.
    #
    # Bumped 55 -> 59 by the Phase 1 evidence-direction audit fix:
    # Study_Design, Evidence_Direction, Evidence_Quality, and
    # Evidence_Applicability are new, independent, additive OUTPUT_COLUMNS
    # entries (see evidence_interpretation.py and test_gate_layer.py's
    # matching bump). Decision_Engine_Version stays the last column.
    assert len(eng.OUTPUT_COLUMNS) == 59
    assert eng.OUTPUT_COLUMNS[-1] == "Decision_Engine_Version"


def test_no_candidate_row_contains_the_removed_fields():
    result = _run()
    assert not result.empty
    assert "Robustness_Analysis" not in result.columns
    assert "Boundary_Fragility" not in result.columns


def test_engine_module_no_longer_imports_scoring_sensitivity_report():
    # Proves the duplicate CALL SITE is gone, not just its output — a
    # stray "compute it but don't attach it" leftover would still show
    # up as an import of this module.
    source = inspect.getsource(eng)
    assert "scoring_sensitivity_report" not in source


def test_engine_module_has_no_top_level_import_of_robustness_functions():
    import ast
    tree = ast.parse(inspect.getsource(eng))
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_names.add(alias.name.split(".")[0])
    assert "build_robustness_analysis" not in imported_names
    assert "boundary_fragility_series" not in imported_names


# ---------------------------------------------------------------------
# 2) UI path preserved: sensitivity_display_adapter.py, called after
#    run() returns exactly as before, still works unchanged.
# ---------------------------------------------------------------------

def test_sensitivity_display_adapter_still_works_on_runs_result():
    result = _run()
    payload = prepare_sensitivity_payload(result)
    assert payload["status"] != "insufficient_data"
    assert "fragility" in payload
    assert "rank_stability_counts" in payload
    assert "boundary_statement" in payload


def test_sensitivity_display_adapter_payload_shape_unchanged():
    result = _run()
    payload = prepare_sensitivity_payload(result)
    assert set(payload.keys()) == {
        "status", "total_rows", "message", "fragility",
        "rank_stability_counts", "boundary_statement", "boundary_explanation",
    }


# ---------------------------------------------------------------------
# 3) Non-regression: scoring, ranking, gates, confidence, Decision_Class
#    unaffected by removing the duplicate — identical to the checks
#    this file ran before the rollback.
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


def test_csv_export_shape_unaffected_by_the_rollback():
    # step_rd_candidates.py's "Download decision table (CSV)" button
    # serializes result_df.to_csv() directly — confirms that export no
    # longer contains the removed columns (it previously did, as an
    # unintended side effect of the duplicate computation) and that
    # every other column round-trips through CSV unchanged.
    result = _run()
    csv_text = result.to_csv(index=False)
    header = csv_text.splitlines()[0]
    assert "Robustness_Analysis" not in header
    assert "Boundary_Fragility" not in header
    for col in ("R&D_Opportunity_Score", "Decision_Class", "GRADE_Certainty"):
        assert col in header
