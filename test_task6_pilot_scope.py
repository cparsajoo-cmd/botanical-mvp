"""
Task 6 — pilot-scope deliverable: pilot_mode wiring and the
already-structural single-select pilot-scope constraint.

WHAT THIS COVERS
- research_engine.run_research_engine()'s pilot_mode parameter
- source_registry.PILOT_MAX_RESULTS
- step_evidence.py's pilot-mode checkbox wiring (AST/source only)
- step_inputs.py: confirms indication/dosage_form/market/product_type
  are already single-select (st.selectbox, never st.multiselect) — the
  "one question, one product group, one country" pilot-scope
  constraint the roadmap called for is satisfied STRUCTURALLY by this
  existing design, not by new validation code. This test is the
  regression lock for that fact, not new production logic.

HOW TO RUN
    pytest -q test_task6_pilot_scope.py
"""

import ast

import source_registry as sr
from research_engine import run_research_engine


# ---------------------------------------------------------------------
# source_registry.PILOT_MAX_RESULTS
# ---------------------------------------------------------------------

def test_pilot_max_results_is_a_documented_multiplier_of_the_default():
    default_max_results = {s["max_results"] for s in sr.SOURCE_REGISTRY if s["name"] != "EMA/WHO/ESCOP Regulatory"}
    assert default_max_results == {5}
    assert sr.PILOT_MAX_RESULTS == 15  # 3x the shared default of 5


def test_pilot_max_results_is_bounded_not_unlimited():
    assert sr.PILOT_MAX_RESULTS < 100


# ---------------------------------------------------------------------
# research_engine.run_research_engine — pilot_mode wiring
# ---------------------------------------------------------------------

def test_run_research_engine_default_pilot_mode_is_false(monkeypatch):
    captured = {}

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return {"saved_records": [], "errors": [], "sources_checked": []}

    monkeypatch.setattr("research_engine.collect_multi_source_evidence", fake_collect)
    monkeypatch.setattr("research_engine.rank_global_candidates", lambda **kwargs: None)
    monkeypatch.setattr("research_engine._richer_candidate_plants", lambda **kwargs: ["TestPlant"])

    run_research_engine(
        product_type="Food supplement", dosage_form="Infusion",
        indication="TestIndication", target_market="EU",
    )
    assert captured["max_results_override"] is None


def test_run_research_engine_pilot_mode_true_passes_pilot_max_results(monkeypatch):
    captured = {}

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return {"saved_records": [], "errors": [], "sources_checked": []}

    monkeypatch.setattr("research_engine.collect_multi_source_evidence", fake_collect)
    monkeypatch.setattr("research_engine.rank_global_candidates", lambda **kwargs: None)
    monkeypatch.setattr("research_engine._richer_candidate_plants", lambda **kwargs: ["TestPlant"])

    run_research_engine(
        product_type="Food supplement", dosage_form="Infusion",
        indication="TestIndication", target_market="EU", pilot_mode=True,
    )
    assert captured["max_results_override"] == sr.PILOT_MAX_RESULTS


# ---------------------------------------------------------------------
# step_evidence.py — AST/source wiring only (not behavior)
# ---------------------------------------------------------------------

def test_step_evidence_pilot_checkbox_defaults_to_false():
    with open("step_evidence.py", encoding="utf-8") as f:
        source = f.read()
        tree = ast.parse(source, filename="step_evidence.py")

    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "checkbox":
            if "Pilot-scope coverage" in ast.dump(node):
                found = True
                has_value_false = any(
                    kw.arg == "value" and isinstance(kw.value, ast.Constant) and kw.value.value is False
                    for kw in node.keywords
                )
                assert has_value_false, "the pilot-scope checkbox must default to value=False"
    assert found, "step_evidence.py must contain a pilot-scope coverage checkbox"


def test_step_evidence_threads_pilot_mode_into_run_research_engine():
    with open("step_evidence.py", encoding="utf-8") as f:
        source = f.read()
    assert "pilot_mode=pilot_mode" in source


# ---------------------------------------------------------------------
# step_inputs.py — the pilot-scope "one question, one product group,
# one country" constraint already holds structurally: every relevant
# field is a single-select selectbox, never a multiselect. This is a
# regression lock on that fact, not new validation logic.
# ---------------------------------------------------------------------

def test_step_inputs_scope_fields_are_single_select_not_multiselect():
    with open("step_inputs.py", encoding="utf-8") as f:
        source = f.read()
        tree = ast.parse(source, filename="step_inputs.py")

    selectbox_keys = set()
    multiselect_keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            key_kw = next((kw for kw in node.keywords if kw.arg == "key"), None)
            key_value = key_kw.value.value if key_kw and isinstance(key_kw.value, ast.Constant) else None
            if node.func.attr == "selectbox" and key_value:
                selectbox_keys.add(key_value)
            elif node.func.attr == "multiselect" and key_value:
                multiselect_keys.add(key_value)

    for expected_key in ("rd_product_type", "rd_indication", "rd_dosage_form", "rd_market"):
        assert expected_key in selectbox_keys, (
            f"{expected_key} must be a single-select st.selectbox — this is what "
            f"structurally satisfies the 'one question, one product group, one "
            f"country' pilot-scope constraint"
        )
    assert not multiselect_keys & {"rd_product_type", "rd_indication", "rd_dosage_form", "rd_market"}
