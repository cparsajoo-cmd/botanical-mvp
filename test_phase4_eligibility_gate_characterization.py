"""
Phase 4 audit — characterization tests (Section 10 of the audit brief).

These tests record CURRENT, PRE-FIX behavior of the live pipeline —
several of them assert behavior that is the BUG itself (documented as
such below). They exist to (a) prove the audit's claims with real
test-runner output rather than prose, and (b) act as a regression
baseline: once Phase 4 implementation changes this behavior on
purpose, the corresponding assertion here must be updated in the same
change, never silently left green by accident.

Marked per-test:
  [CURRENT-BUGGY]  — asserts the unsafe behavior that exists today;
                      MUST be rewritten (not deleted) once fixed.
  [CURRENT-SAFE]   — asserts behavior that is already correct and
                      must NOT regress during Phase 4 implementation.
"""
from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from data_contracts import GateStatus


# ---------------------------------------------------------------------
# 1. same_plant bypass of the hard SAFETY gate  [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def test_same_plant_bypasses_hard_safety_gate_to_not_evaluable():
    status_same, hit_same, _ = BotanicalRDCandidateEngine._hard_safety_gate(
        "teratogenic", same_plant=True
    )
    status_diff, hit_diff, _ = BotanicalRDCandidateEngine._hard_safety_gate(
        "teratogenic", same_plant=False
    )
    assert status_same == GateStatus.NOT_EVALUABLE
    assert status_diff == GateStatus.FAILED
    assert hit_same == {"teratogenic"}  # the term IS detected, just not enforced


@pytest.mark.phase4_legacy_behavior
@pytest.mark.xfail(
    strict=True,
    reason="Phase 4 intentionally removes this unsafe legacy behavior — "
           "_decision_class() now derives its outcome from eligibility_gate."
           "evaluate_eligibility() instead of a raw same_plant bypass. See "
           "test_phase4_eligibility_gate_desired_behavior.py for the "
           "replacement, correct assertion.",
)
def test_same_plant_downgrades_decision_class_for_identical_hard_safety_flag():
    """[CURRENT-BUGGY] Identical inputs (score=90, safety_flags='teratogenic'),
    differing ONLY in same_plant, produce a hard no-go label in one case
    and a top-tier positive label in the other. This is the exact
    Decision_Class-level proof of the gate bypass, not just the gate
    function in isolation."""
    decision_same_plant = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="teratogenic", interaction_flags="",
        has_evidence=True, match_quality="exact", same_plant=True,
    )
    decision_alt_plant = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="teratogenic", interaction_flags="",
        has_evidence=True, match_quality="exact", same_plant=False,
    )
    assert decision_alt_plant == "Safety concern — not suitable without expert review"
    assert decision_same_plant == "Promising candidate; verify safety and standardization"
    assert "Safety concern" not in decision_same_plant


# ---------------------------------------------------------------------
# 2. same_plant bypass of the hard REGULATORY gate  [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def test_same_plant_bypasses_hard_regulatory_gate_to_not_evaluable():
    status_same, banned_same = BotanicalRDCandidateEngine._hard_regulatory_gate(
        {"Prohibited / banned"}, same_plant=True
    )
    status_diff, banned_diff = BotanicalRDCandidateEngine._hard_regulatory_gate(
        {"Prohibited / banned"}, same_plant=False
    )
    assert status_same == GateStatus.NOT_EVALUABLE
    assert status_diff == GateStatus.FAILED


@pytest.mark.phase4_legacy_behavior
@pytest.mark.xfail(
    strict=True,
    reason="Phase 4 intentionally removes this unsafe legacy behavior — "
           "_decision_class() now derives its outcome from eligibility_gate."
           "evaluate_eligibility() instead of a raw same_plant bypass. See "
           "test_phase4_eligibility_gate_desired_behavior.py for the "
           "replacement, correct assertion.",
)
def test_same_plant_downgrades_decision_class_for_identical_prohibition():
    """[CURRENT-BUGGY] mirror of the safety test above, for the
    regulatory hard-stop."""
    decision_same_plant = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="", interaction_flags="", has_evidence=True,
        match_quality="exact", same_plant=True,
        regulatory_barrier_types={"Prohibited / banned"},
    )
    decision_alt_plant = BotanicalRDCandidateEngine._decision_class(
        None, score=90, safety_flags="", interaction_flags="", has_evidence=True,
        match_quality="exact", same_plant=False,
        regulatory_barrier_types={"Prohibited / banned"},
    )
    assert decision_alt_plant == "Regulatory prohibition — not suitable without regulatory review"
    assert decision_same_plant == "Promising candidate; verify safety and standardization"


# ---------------------------------------------------------------------
# 3. Score is computed independently of gate outcome  [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def test_score_unaffected_by_hard_gate_failure_vs_bypass():
    """[CURRENT-BUGGY] botanical_rd_candidate_engine.run()'s per-row loop
    calls _score_candidate() BEFORE _decision_class()/_evaluate_gates()
    (source order: lines ~1304, ~1325, ~1350) and the score value is
    never fed back into by gate outcome. This test proves it directly:
    a hard safety flag applies the SAME flat -14 penalty regardless of
    whether the gate is later bypassed (same_plant) or enforced."""
    kwargs = dict(
        matched_compound="X", reference_compound="X", match_quality="exact",
        concentration="10mg", extraction="aqueous", dosage_form="tea",
        co_compounds="", interaction_flags="", market_status="Unknown",
        novelty_status="Alternative", target="T", evidence="some evidence text",
        evidence_level="Preclinical / mechanistic evidence",
    )
    from botanical_rd_candidate_engine import DEFAULT_SCORING_CONFIG
    engine = BotanicalRDCandidateEngine.__new__(BotanicalRDCandidateEngine)
    engine.scoring_config = DEFAULT_SCORING_CONFIG
    engine.compound_commonality_threshold = None
    score_bypassed, _ = BotanicalRDCandidateEngine._score_candidate(
        engine, same_plant=True, safety_flags="teratogenic", **kwargs
    )
    # same_plant carries its OWN -15 penalty unrelated to the gate, so
    # compare same_plant=False in both safety-flag cases instead, to
    # isolate the safety-flag penalty from the same_plant penalty.
    score_flag, _ = BotanicalRDCandidateEngine._score_candidate(
        engine, same_plant=False, safety_flags="teratogenic", **kwargs
    )
    score_no_flag, _ = BotanicalRDCandidateEngine._score_candidate(
        engine, same_plant=False, safety_flags="", **kwargs
    )
    # Whether the gate would FAIL (same_plant=False) or be bypassed
    # (same_plant=True is a separate penalty, not tested here), the
    # flat safety penalty is identical -14 either way -- score carries
    # no concept of "hard" vs "soft" safety severity at all.
    assert round(score_no_flag - score_flag, 1) == 14.0


# ---------------------------------------------------------------------
# 4. Final ranking/sort has no eligibility filter  [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def test_run_output_sort_has_no_decision_class_filter():
    """[CURRENT-BUGGY] Confirms, by reading run()'s own sort call, that
    the ONLY sort key for the final per-row DataFrame is
    R&D_Opportunity_Score -- Decision_Class/Gate_Results are carried as
    columns but never used as a sort/filter key. Static-inspection
    proof (grepping the source) rather than a full run() execution,
    since run() requires a fully populated evidence/compound database
    to produce real rows."""
    import inspect
    import re
    source = inspect.getsource(BotanicalRDCandidateEngine.run)
    # sort_values(...) calls can span multiple lines (by=[...] on its
    # own line), so match each call as a whole block rather than a
    # single source line.
    sort_blocks = re.findall(r"\.sort_values\(.*?\)", source, flags=re.DOTALL)
    assert len(sort_blocks) >= 1
    score_sort_blocks = [b for b in sort_blocks if "R&D_Opportunity_Score" in b]
    assert len(score_sort_blocks) >= 1
    # No sort_values(...) call anywhere in run() references
    # Decision_Class or Gate_Results as a sort key.
    decision_sort_blocks = [b for b in sort_blocks if "Decision_Class" in b or "Gate_Results" in b]
    assert decision_sort_blocks == []


# ---------------------------------------------------------------------
# 5. UI legacy-fallback surfaces hard no-go candidates as "Recommended"
#    [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def _stub_streamlit_and_supabase():
    """Returns a context manager that stubs streamlit/supabase_client
    for the duration of the `with` block, then restores sys.modules to
    its prior state — including popping any of step_rd_candidates /
    pharma_report_generator / candidate_output_adapter that got
    (re-)imported while the stub was active, so a LATER test that
    imports the real streamlit (e.g. test_production_dependency_integrity.py)
    never sees a module still bound to this test's fake `st` object.
    Without this, sys.modules["streamlit"] = st_stub leaked past this
    test's own scope and broke unrelated, later-running tests in the
    same pytest session — a real regression, not a hypothetical one.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        def _noop_decorator(*_a, **_k):
            def wrap(fn):
                return fn
            return wrap

        captured = {"dataframe_calls": []}
        st_stub = types.ModuleType("streamlit")
        st_stub.markdown = lambda *a, **k: None
        st_stub.caption = lambda *a, **k: None
        st_stub.dataframe = lambda df, *a, **k: captured["dataframe_calls"].append(df.copy())
        st_stub.warning = lambda *a, **k: None
        st_stub.cache_data = _noop_decorator
        st_stub.cache_resource = _noop_decorator
        st_stub.session_state = {}

        sc_stub = types.ModuleType("supabase_client")
        sc_stub.get_supabase_client = lambda *a, **k: None

        poisonable_modules = (
            "streamlit", "supabase_client",
            "step_rd_candidates", "pharma_report_generator", "candidate_output_adapter",
        )
        saved = {name: sys.modules.get(name) for name in poisonable_modules}
        sys.modules["streamlit"] = st_stub
        sys.modules["supabase_client"] = sc_stub
        for name in ("step_rd_candidates", "pharma_report_generator", "candidate_output_adapter"):
            sys.modules.pop(name, None)
        try:
            yield captured
        finally:
            for name, mod in saved.items():
                if mod is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = mod

    return _ctx()


@pytest.mark.phase4_legacy_behavior
@pytest.mark.xfail(
    strict=True,
    reason="Phase 4 intentionally removes this unsafe legacy behavior — "
           "_recommendation_block()'s legacy fallback now filters by "
           "Eligible_For_Normal_Ranking instead of an unguarded head(5). See "
           "test_phase4_eligibility_gate_desired_behavior.py for the "
           "replacement, correct assertion.",
)
def test_ui_legacy_fallback_surfaces_no_go_candidates_as_recommended():
    result_df = pd.DataFrame([
        {
            "Alternative_Plant": "Piper methysticum",
            "Shared_or_Similar_Compound": "Kavain",
            "Target_or_Mechanism": "GABA-A",
            "R&D_Opportunity_Score": 92.0,
            "Decision_Class": "Regulatory prohibition — not suitable without regulatory review",
            "Safety_Flags": "hepatotoxic",
            "Market_Status": "Unknown",
            "Novelty_Status": "Alternative",
            "Rationale": "characterization test row",
        },
        {
            "Alternative_Plant": "Aristolochia clematitis",
            "Shared_or_Similar_Compound": "Aristolochic acid",
            "Target_or_Mechanism": "DNA adduct",
            "R&D_Opportunity_Score": 88.0,
            "Decision_Class": "Safety concern — not suitable without expert review",
            "Safety_Flags": "carcinogenic",
            "Market_Status": "Unknown",
            "Novelty_Status": "Alternative",
            "Rationale": "characterization test row",
        },
    ])

    with _stub_streamlit_and_supabase() as captured:
        from step_rd_candidates import _recommendation_block  # import after stubbing

        # report_ready_df=None forces the legacy (pre-Phase-3) fallback branch.
        _recommendation_block(result_df, report_ready_df=None)

    assert len(captured["dataframe_calls"]) >= 1
    recommended_shown = captured["dataframe_calls"][0]
    shown_plants = set(recommended_shown["Alternative_Plant"])
    # [CURRENT-BUGGY]: both hard no-go plants appear in the "Recommended"
    # table, with the regulatory-prohibited one ranked FIRST by raw score.
    assert "Piper methysticum" in shown_plants
    assert "Aristolochia clematitis" in shown_plants


# ---------------------------------------------------------------------
# 6. global_candidate_ranking_engine has no hard-gate concept
#    [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def test_global_ranking_engine_ranks_prohibited_plant_first_on_score():
    import global_candidate_ranking_engine as gcre

    fake_candidates = [
        {
            "Scientific_Name": "piper methysticum",  # the ONLY hardcoded
            "Common_Name": "Kava",                    # caution_plant --
            "Region": "Pacific",                       # Safety_Score=35
            "Known_Active_Compounds": ["Kavain", "Dihydrokavain", "Yangonin", "Methysticin"],
            "Known_Targets": ["GABA-A", "MAO-B", "Sodium channel"],
            "Plant_Part": "Root",
            "Extraction_Method": "ethanolic",
            "EMA_Status": "No",
            "Research_Priority": "High",
            "Indications": ["anxiety"],
        },
        {
            "Scientific_Name": "matricaria chamomilla",  # ordinary, safe
            "Common_Name": "Chamomile",                  # plant with weak
            "Region": "Europe",                          # chemistry data
            "Known_Active_Compounds": ["Apigenin"],
            "Known_Targets": [],
            "Plant_Part": "Flower",
            "Extraction_Method": "",
            "EMA_Status": "Yes",
            "Research_Priority": "Low",
            "Indications": ["anxiety"],
        },
    ]
    gcre.GLOBAL_PLANT_CANDIDATES = fake_candidates

    df = gcre.rank_global_candidates(
        indication="anxiety", dosage_form="tea", market="European Union", target_count=10
    )
    assert not df.empty
    top_row = df.iloc[0]
    # [CURRENT-BUGGY]: Piper methysticum -- a real-world EU-regulated/
    # restricted botanical -- outranks the ordinary plant purely because
    # of chemistry/active-compound/target richness. Safety_Score (35 vs
    # 70) only carries 4% weight and Regulatory_Score only 8%, nowhere
    # near enough to overcome a strong Chemistry/Active_Compound/Target
    # lead, and there is no hard no-go concept in this engine at all.
    assert top_row["Scientific_Name"] == "piper methysticum"
    assert top_row["Safety_Score"] == 35


# ---------------------------------------------------------------------
# 7. Regulatory barrier classifier: absence of a keyword hit is
#    indistinguishable from "checked and cleared"  [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def test_regulatory_barrier_classifier_empty_text_vs_unrelated_text_both_clear():
    from regulatory_barrier_classifier import classify_regulatory_barriers

    # No evidence text at all.
    result_no_text = classify_regulatory_barriers(None)
    # Evidence text exists but never mentions any regulatory status
    # (e.g. a chemistry-only source) -- structurally indistinguishable
    # downstream from "regulatory status was checked and found clear".
    result_unrelated_text = classify_regulatory_barriers(
        "This compound was isolated via HPLC and its structure confirmed by NMR."
    )
    assert result_no_text.has_barrier is False
    assert result_unrelated_text.has_barrier is False
    # Both produce an EMPTY barrier_types list -- not None, not a
    # distinct INSUFFICIENT_DATA/SOURCE_UNAVAILABLE marker -- so
    # _hard_regulatory_gate() (called with this list) returns PASSED
    # for both, identically to a genuinely verified "not prohibited"
    # finding.
    status_no_text, _ = BotanicalRDCandidateEngine._hard_regulatory_gate(
        result_no_text.barrier_types, same_plant=False
    )
    status_unrelated, _ = BotanicalRDCandidateEngine._hard_regulatory_gate(
        result_unrelated_text.barrier_types, same_plant=False
    )
    assert status_no_text == GateStatus.PASSED
    assert status_unrelated == GateStatus.PASSED


# ---------------------------------------------------------------------
# 8. Plant-part / preparation context is not read by either hard gate
#    [CURRENT-BUGGY]
# ---------------------------------------------------------------------
def test_hard_gates_ignore_plant_part_and_preparation_entirely():
    """[CURRENT-BUGGY] Neither _hard_safety_gate nor _hard_regulatory_gate
    accept a plant-part, preparation, dose, route, or population
    argument at all -- proven directly from their signatures -- so a
    risk documented for one part/preparation is applied identically
    regardless of which part/preparation the candidate row represents."""
    import inspect
    safety_params = list(inspect.signature(
        BotanicalRDCandidateEngine._hard_safety_gate
    ).parameters)
    regulatory_params = list(inspect.signature(
        BotanicalRDCandidateEngine._hard_regulatory_gate
    ).parameters)
    assert safety_params == ["safety_flags", "same_plant"]
    assert regulatory_params == ["regulatory_barrier_types", "same_plant"]
    for forbidden in ("plant_part", "preparation", "dose", "route", "population"):
        assert forbidden not in safety_params
        assert forbidden not in regulatory_params
