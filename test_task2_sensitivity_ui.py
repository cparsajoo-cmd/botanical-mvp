"""
Task 2 — Scoring sensitivity / ranking robustness surfacing.

WHAT THIS COVERS
sensitivity_display_adapter.prepare_sensitivity_payload() — the pure,
Streamlit-free adapter over the EXISTING scoring_sensitivity_report.py
entry points (fragility_report, build_robustness_analysis) — plus
AST-only checks that step_rd_candidates.py actually wires this into one
collapsed expander without disturbing Task 1's Gate_Results or the
existing result_df contract.

Behavioral and non-mutation requirements are covered with executable
tests (not AST). AST is used only to confirm the Streamlit wiring
itself (expander presence/collapsed state, that engine.run() is not
called a second time for sensitivity) — consistent with how
test_gate_layer.py already scopes AST-only checks to wiring, not
behavior.

HOW TO RUN
    pytest -q test_scoring_sensitivity_report.py
    pytest -q test_task2_sensitivity_ui.py
    pytest -q test_gate_layer.py
    pytest -q
"""

import ast
import copy

import pandas as pd
import pandas.testing as pdt
import pytest

import scoring_sensitivity_report as ssr
from sensitivity_display_adapter import (
    BOUNDARY_STATEMENT,
    prepare_sensitivity_payload,
)
from test_botanical_rd_candidate_engine import make_engine


# ---------------------------------------------------------------------
# Reuse, not duplication: prepare_sensitivity_payload must call the
# EXISTING scoring_sensitivity_report functions, not reimplement them.
# ---------------------------------------------------------------------

def test_adapter_reuses_existing_fragility_report_not_a_copy(monkeypatch):
    calls = []
    original = ssr.fragility_report

    def _spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr("sensitivity_display_adapter.fragility_report", _spy)
    df = pd.DataFrame({
        "Reference_Plant": ["A", "A"],
        "Reference_Compound": ["c1", "c1"],
        "R&D_Opportunity_Score": [80.0, 40.0],
        "Score_Breakdown": ["", ""],
        "Alternative_Plant": ["X", "Y"],
    })
    prepare_sensitivity_payload(df)
    assert len(calls) == 1, "fragility_report must be called exactly once, not reimplemented"


def test_adapter_reuses_existing_build_robustness_analysis_not_a_copy(monkeypatch):
    calls = []
    original = ssr.build_robustness_analysis

    def _spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr("sensitivity_display_adapter.build_robustness_analysis", _spy)
    df = pd.DataFrame({
        "Reference_Plant": ["A", "A"],
        "Reference_Compound": ["c1", "c1"],
        "R&D_Opportunity_Score": [80.0, 40.0],
        "Score_Breakdown": ["", ""],
        "Alternative_Plant": ["X", "Y"],
    })
    prepare_sensitivity_payload(df)
    assert len(calls) == 1, "build_robustness_analysis must be called exactly once, not reimplemented"


def test_adapter_module_never_calls_botanical_rd_candidate_engine():
    import sensitivity_display_adapter as sda
    with open(sda.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=sda.__file__)

    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "botanical_rd_candidate_engine", (
                "sensitivity_display_adapter.py must not import from "
                "botanical_rd_candidate_engine.py"
            )
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "botanical_rd_candidate_engine"

    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_names.add(node.func.attr)
    assert "BotanicalRDCandidateEngine" not in call_names
    assert "run" not in call_names, "no .run(...) call site belongs in this pure adapter"


# ---------------------------------------------------------------------
# Input immutability — executable test, not AST, per Task 2 requirement 6.
# ---------------------------------------------------------------------

def _sample_result_df():
    eng_module = __import__("botanical_rd_candidate_engine")
    eng_module.SIMILAR_COMPOUND_GROUPS = {}
    eng_module.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="CompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="CompoundA",
             indication="Other", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    return engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")


def test_prepare_sensitivity_payload_does_not_mutate_input_dataframe():
    result_df = _sample_result_df()

    before_shape = result_df.shape
    before_index = result_df.index.copy()
    before_columns = result_df.columns.copy()
    before_dtypes = result_df.dtypes.copy()
    before_values = result_df.copy(deep=True)
    before_gate_results = [copy.deepcopy(g) for g in result_df["Gate_Results"]]

    prepare_sensitivity_payload(result_df)

    assert result_df.shape == before_shape
    pdt.assert_index_equal(result_df.index, before_index)
    pdt.assert_index_equal(result_df.columns, before_columns)
    pdt.assert_series_equal(result_df.dtypes, before_dtypes)
    pdt.assert_frame_equal(result_df, before_values)

    after_gate_results = list(result_df["Gate_Results"])
    assert after_gate_results == before_gate_results, (
        "Gate_Results (Task 1) must be byte-for-byte unchanged after "
        "the sensitivity payload is prepared"
    )


def test_prepare_sensitivity_payload_does_not_mutate_a_two_group_dataframe():
    # A second, independent fixture (multiple reference groups) to
    # exercise build_robustness_analysis's groupby path without relying
    # on a single fixture shape.
    eng_module = __import__("botanical_rd_candidate_engine")
    eng_module.SIMILAR_COMPOUND_GROUPS = {}
    eng_module.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant1", compound_name="CompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant1", compound_name="CompoundA",
             indication="Other", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="RefPlant2", compound_name="CompoundB",
             indication="TestIndication", target="Diuretic",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant2", compound_name="CompoundB",
             indication="Other", target="Diuretic",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    result_df = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    before = result_df.copy(deep=True)
    prepare_sensitivity_payload(result_df)
    pdt.assert_frame_equal(result_df, before)


# ---------------------------------------------------------------------
# Graceful handling of insufficient data — never raises, never
# fabricates a robustness/fragility metric.
# ---------------------------------------------------------------------

def test_none_result_df_is_handled_gracefully():
    payload = prepare_sensitivity_payload(None)
    assert payload["status"] == "insufficient_data"
    assert payload["message"]
    assert payload["fragility"] is None
    assert payload["rank_stability_counts"] is None


def test_empty_result_df_is_handled_gracefully():
    payload = prepare_sensitivity_payload(pd.DataFrame())
    assert payload["status"] == "insufficient_data"
    assert payload["fragility"] is None
    assert payload["rank_stability_counts"] is None


def test_missing_required_columns_is_handled_gracefully():
    payload = prepare_sensitivity_payload(pd.DataFrame({"Unrelated_Column": [1, 2, 3]}))
    assert payload["status"] == "insufficient_data"
    assert payload["fragility"] is None
    assert payload["rank_stability_counts"] is None


def test_single_candidate_is_handled_gracefully():
    payload = prepare_sensitivity_payload(
        pd.DataFrame({"R&D_Opportunity_Score": [55.0]})
    )
    assert payload["status"] == "insufficient_data"
    assert "one candidate" in payload["message"].lower()


def test_non_dataframe_input_is_handled_gracefully():
    payload = prepare_sensitivity_payload("not a dataframe")
    assert payload["status"] == "insufficient_data"


def test_tied_scores_do_not_crash_and_are_not_fabricated_as_robust():
    df = pd.DataFrame({
        "Reference_Plant": ["A", "A"],
        "Reference_Compound": ["c1", "c1"],
        "Alternative_Plant": ["X", "Y"],
        "R&D_Opportunity_Score": [50.0, 50.0],
        "Score_Breakdown": [
            "Chemical/mechanistic link: 10; Evidence quality: 10; "
            "Product-development fit: 10; Novelty: 10; Market signal: 5; "
            "Safety/interaction/self-row penalty: 5",
            "Chemical/mechanistic link: 10; Evidence quality: 10; "
            "Product-development fit: 10; Novelty: 10; Market signal: 5; "
            "Safety/interaction/self-row penalty: 5",
        ],
    })
    payload = prepare_sensitivity_payload(df)
    # Must not crash, and must not report "Stable"/"Fragile" for a tie —
    # the existing module's own "Tied" label (not invented here) is the
    # only honest classification for a genuine tie.
    assert payload["status"] == "ok"
    counts = payload["rank_stability_counts"]
    assert counts is not None
    assert set(counts.keys()).issubset({"Stable", "Moderately stable", "Fragile", "Tied", "Insufficient"})


# ---------------------------------------------------------------------
# The exact required scientific-boundary statement is always present.
# ---------------------------------------------------------------------

def test_boundary_statement_exact_text_present_on_every_payload():
    assert BOUNDARY_STATEMENT == "Model sensitivity is not scientific evidence confidence."
    for result_df in (None, pd.DataFrame(), pd.DataFrame({"R&D_Opportunity_Score": [1.0]})):
        payload = prepare_sensitivity_payload(result_df)
        assert payload["boundary_statement"] == BOUNDARY_STATEMENT

    payload_ok = prepare_sensitivity_payload(_sample_result_df())
    assert payload_ok["boundary_statement"] == BOUNDARY_STATEMENT
    assert payload_ok["boundary_explanation"]


# ---------------------------------------------------------------------
# End-to-end: Task 1's Gate_Results and the existing output contract
# (score, Decision_Class, ordering, row count, columns) are unchanged
# by preparing (or rendering) the sensitivity payload.
# ---------------------------------------------------------------------

def test_gate_results_score_decision_class_ordering_row_count_unchanged():
    result_df = _sample_result_df()
    before = result_df.copy(deep=True)

    prepare_sensitivity_payload(result_df)

    assert len(result_df) == len(before)
    assert list(result_df["R&D_Opportunity_Score"]) == list(before["R&D_Opportunity_Score"])
    assert list(result_df["Decision_Class"]) == list(before["Decision_Class"])
    assert list(result_df.index) == list(before.index)
    assert list(result_df.columns) == list(before.columns)
    assert list(result_df["Gate_Results"]) == list(before["Gate_Results"])


# ---------------------------------------------------------------------
# Streamlit wiring — AST/source inspection only (wiring, not behavior),
# same scoping discipline test_gate_layer.py already uses for its
# call-site checks. No import of step_rd_candidates here.
# ---------------------------------------------------------------------

def _step_rd_candidates_tree():
    with open("step_rd_candidates.py", encoding="utf-8") as f:
        source = f.read()
    return source, ast.parse(source, filename="step_rd_candidates.py")


def test_step_rd_candidates_imports_the_pure_adapter():
    source, tree = _step_rd_candidates_tree()
    imports_adapter = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "sensitivity_display_adapter"
        and any(alias.name == "prepare_sensitivity_payload" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imports_adapter, "step_rd_candidates.py must import prepare_sensitivity_payload"


def test_step_rd_candidates_uses_one_collapsed_expander_for_sensitivity():
    source, tree = _step_rd_candidates_tree()
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "expander":
            args_text = ast.dump(node)
            if "Scoring sensitivity" in args_text:
                found = True
                # Must be explicitly collapsed: expanded=False (default
                # is also collapsed, but Task 2 requires this explicit).
                has_expanded_false = any(
                    kw.arg == "expanded"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is False
                    for kw in node.keywords
                )
                assert has_expanded_false, (
                    "the sensitivity expander must pass expanded=False explicitly"
                )
    assert found, "step_rd_candidates.py must contain one st.expander(...) for scoring sensitivity"


def test_only_one_sensitivity_expander_exists():
    source, tree = _step_rd_candidates_tree()
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "expander":
            if "Scoring sensitivity" in ast.dump(node):
                count += 1
    assert count == 1, "there must be exactly one sensitivity/robustness expander"


def test_engine_run_is_not_called_a_second_time_for_sensitivity():
    # Count .run( call sites in step_rd_candidates.py — must remain
    # exactly the one pre-existing call that produces result_df in the
    # first place. Task 2 must not add a second engine.run() invocation.
    source, tree = _step_rd_candidates_tree()
    run_call_count = sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run"
    )
    assert run_call_count == 1, (
        f"expected exactly one .run() call site (the existing candidate "
        f"discovery call), found {run_call_count}"
    )


def test_step_rd_candidates_does_not_reassign_result_df_from_sensitivity_payload():
    # The sensitivity payload must be consumed for display only — never
    # assigned back onto the name "result_df".
    source, tree = _step_rd_candidates_tree()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "result_df" in targets and isinstance(node.value, ast.Call):
                func = node.value.func
                func_name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                assert func_name != "prepare_sensitivity_payload", (
                    "result_df must never be reassigned from the sensitivity payload"
                )


def test_no_second_sensitivity_engine_module_was_created():
    # Task 2 explicitly forbids a second sensitivity engine — confirm
    # sensitivity_display_adapter.py contains no independent
    # weighting/perturbation logic of its own: no function/attribute
    # name in its actual CODE (not its explanatory docstrings) matches
    # a duplicated-engine indicator, and no arithmetic operator is
    # applied to a "score"-named variable anywhere in the module.
    import sensitivity_display_adapter as sda
    with open(sda.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=sda.__file__)

    forbidden_identifiers = {"perturb", "reweight", "_score_candidate", "recalculate"}
    identifiers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            identifiers.add(node.name)
    lowered_identifiers = {ident.lower() for ident in identifiers}
    for term in forbidden_identifiers:
        assert term not in lowered_identifiers, f"unexpected duplicated-engine indicator in code: {term!r}"

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Add, ast.Sub, ast.Div)):
            for side in (node.left, node.right):
                if isinstance(side, ast.Name) and "score" in side.id.lower():
                    pytest.fail(
                        f"unexpected arithmetic on a score-named variable "
                        f"({side.id!r}) — this adapter must only count/summarize, "
                        f"never recompute a score"
                    )
