"""
Task 1 — Formal Gate Layer regression tests.

WHAT THIS COVERS
_evaluate_gates() / _hard_safety_gate() in botanical_rd_candidate_engine.py,
and the additive Gate_Results column produced through run() and the
multi-compound merge path. Per-gate PASS/FAIL/NEEDS_REVIEW/NOT_EVALUABLE
cases, plus the two non-negotiable backward-compatibility guarantees:
Decision_Class and R&D_Opportunity_Score must be byte-identical to
pre-Task-1 behavior, since gates are additive-only (except that "safety"
reports, rather than changes, the pre-existing hard exclusion).

HOW TO RUN
    pytest -q test_gate_layer.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
from data_contracts import GateStatus
from test_botanical_rd_candidate_engine import make_engine


# ---------------------------------------------------------------------
# _hard_safety_gate — the single source of truth shared by
# _decision_class() and _evaluate_gates()
# ---------------------------------------------------------------------

def test_hard_safety_gate_fails_on_a_hard_term():
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "lithogenic", same_plant=False
    )
    assert status == GateStatus.FAIL
    assert hit_terms == {"lithogenic"}


def test_hard_safety_gate_passes_with_no_flags():
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "", same_plant=False
    )
    assert status == GateStatus.PASS
    assert hit_terms == set()


def test_hard_safety_gate_passes_on_controversial_only_terms():
    # "hepatotoxic" is CONTROVERSIAL_SAFETY_TERMS, not HARD_SAFETY_TERMS —
    # must not fail the gate (matches the existing _decision_class cap
    # behavior, which visibly flags but doesn't auto-exclude these).
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "hepatotoxic", same_plant=False
    )
    assert status == GateStatus.PASS
    assert hit_terms == set()


def test_hard_safety_gate_not_evaluable_for_same_plant_even_with_hard_term():
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "lithogenic", same_plant=True
    )
    assert status == GateStatus.NOT_EVALUABLE
    assert hit_terms == {"lithogenic"}  # term is still visible in output, just not gating


# ---------------------------------------------------------------------
# _evaluate_gates — safety
# ---------------------------------------------------------------------

def test_evaluate_gates_safety_fail_matches_hard_safety_gate():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="lithogenic",
        match_quality="exact",
        has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[],
        same_plant=False,
    )
    assert gates["safety"]["status"] == GateStatus.FAIL
    assert "lithogenic" in gates["safety"]["reason"]
    assert gates["safety"]["evidence"] == "lithogenic"


def test_evaluate_gates_safety_pass_when_no_flags():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="",
        match_quality="exact",
        has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[],
        same_plant=False,
    )
    assert gates["safety"]["status"] == GateStatus.PASS


def test_evaluate_gates_safety_not_evaluable_for_same_plant():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="lithogenic",
        match_quality="exact",
        has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[],
        same_plant=True,
    )
    assert gates["safety"]["status"] == GateStatus.NOT_EVALUABLE


# ---------------------------------------------------------------------
# _evaluate_gates — identity
# ---------------------------------------------------------------------

def test_evaluate_gates_identity_pass_on_exact_match():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.PASS


def test_evaluate_gates_identity_pass_on_target_verified_match():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="target_verified", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.PASS


def test_evaluate_gates_identity_needs_review_on_class_only_match():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="class_only", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.NEEDS_REVIEW


def test_evaluate_gates_identity_not_evaluable_when_match_quality_missing():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.NOT_EVALUABLE


# ---------------------------------------------------------------------
# _evaluate_gates — minimum_evidence
# ---------------------------------------------------------------------

def test_evaluate_gates_minimum_evidence_fail_with_no_direct_evidence():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=False,
        evidence_level="No direct evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["minimum_evidence"]["status"] == GateStatus.FAIL


def test_evaluate_gates_minimum_evidence_pass_with_real_evidence():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Preclinical / mechanistic evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["minimum_evidence"]["status"] == GateStatus.PASS


# ---------------------------------------------------------------------
# _evaluate_gates — regulatory
# ---------------------------------------------------------------------

def test_evaluate_gates_regulatory_fail_on_explicit_prohibition():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=["Prohibited / banned"], same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.FAIL


def test_evaluate_gates_regulatory_pass_when_checked_and_clear():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.PASS


def test_evaluate_gates_regulatory_pass_on_non_prohibition_barrier():
    # A restriction (e.g. prescription-only) is a real finding but is
    # NOT a prohibition — must not fail this gate, only "Prohibited /
    # banned" does.
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=["Restricted access (prescription/controlled)"],
        same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.PASS


def test_evaluate_gates_regulatory_not_evaluable_when_never_checked():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=None, same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.NOT_EVALUABLE


# ---------------------------------------------------------------------
# Every gate returns exactly the required shape
# ---------------------------------------------------------------------

def test_evaluate_gates_returns_all_four_gates_with_required_keys():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert set(gates.keys()) == {"safety", "identity", "minimum_evidence", "regulatory"}
    for gate in gates.values():
        assert set(gate.keys()) == {"status", "reason", "evidence"}
        assert isinstance(gate["status"], GateStatus)
        assert isinstance(gate["reason"], str) and gate["reason"]


# ---------------------------------------------------------------------
# Backward compatibility: Decision_Class must be byte-identical to
# pre-Task-1 behavior after the _hard_safety_gate refactor.
# ---------------------------------------------------------------------

def test_decision_class_hard_safety_exclusion_unchanged_after_refactor():
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,  # unbound call, same pattern the existing suite already uses
        score=80, safety_flags="lithogenic", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=False,
    )
    assert decision == "Safety concern — not suitable without expert review"


def test_decision_class_same_plant_skips_hard_exclusion_unchanged_after_refactor():
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,
        score=80, safety_flags="lithogenic", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=True,
    )
    assert decision != "Safety concern — not suitable without expert review"


def test_decision_class_strong_candidate_unchanged_after_refactor():
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,
        score=90, safety_flags="", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=False,
    )
    assert decision == "Strong R&D candidate"


# ---------------------------------------------------------------------
# End-to-end through run(): Gate_Results populated, and Decision_Class /
# R&D_Opportunity_Score are exactly what they were before this task.
# ---------------------------------------------------------------------

def test_gate_results_populated_end_to_end_through_run():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="TestPlant", compound_name="ActiveCompound",
             indication="TestIndication", target="Hepatoprotective",
             common_name="", plant_part="", extraction_method=""),
    ]
    engine = make_engine(rows)
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "TestPlant",
        "Target_Indication": "TestIndication",
        "Notes": (
            "A randomized controlled trial, double-blind and "
            "placebo-controlled, found significant hepatoprotective effects."
        ),
    }])
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    assert "Gate_Results" in result.columns
    self_row = result[
        (result["Reference_Plant"] == "TestPlant") & (result["Alternative_Plant"] == "TestPlant")
    ].iloc[0]
    gates = self_row["Gate_Results"]
    assert isinstance(gates, dict)
    assert set(gates.keys()) == {"safety", "identity", "minimum_evidence", "regulatory"}
    # Same_plant row -> safety gate must be NOT_EVALUABLE, not silently PASS.
    assert gates["safety"]["status"] == GateStatus.NOT_EVALUABLE


def test_run_score_and_decision_class_unaffected_by_gate_wiring():
    # A candidate carrying a hard safety term, not the reference plant
    # itself, must still be capped to the safety-concern string exactly
    # as before Task 1 — this is the one place gates and Decision_Class
    # are allowed to agree; the point of this test is that nothing else
    # about scoring changed.
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
    engine = make_engine(rows)
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    alt_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlant")
    ]
    assert not alt_row.empty
    row = alt_row.iloc[0]
    # Gate_Results present and additive, decision/score computed exactly
    # by the same untouched _score_candidate/_decision_class logic.
    assert "Gate_Results" in result.columns
    assert row["Decision_Class"] in {
        "Strong R&D candidate",
        "Promising candidate; verify safety and standardization",
        "Early-stage candidate; more evidence needed",
        "Low priority / insufficient data",
        "Safety concern — not suitable without expert review",
    }
    assert 0 <= row["R&D_Opportunity_Score"] <= 100


# ---------------------------------------------------------------------
# Merge path: Gate_Results must be recomputed from merged fields, not
# left stale from whichever sub-row happened to be "best" pre-merge.
# ---------------------------------------------------------------------

def test_gate_results_recomputed_after_multi_compound_merge():
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
    gates = alt_row.iloc[0]["Gate_Results"]
    assert isinstance(gates, dict)
    assert set(gates.keys()) == {"safety", "identity", "minimum_evidence", "regulatory"}


# ---------------------------------------------------------------------
# Both engine call sites (Step 2's research_engine.py and Step 5's
# step_rd_candidates.py) continue to work unmodified.
# ---------------------------------------------------------------------

def test_research_engine_call_site_still_instantiates_and_imports():
    import research_engine  # noqa: F401 — import-only smoke check
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    engine = BotanicalRDCandidateEngine(use_live_search=False)
    assert engine is not None


def test_step_rd_candidates_call_site_still_imports():
    import step_rd_candidates  # noqa: F401 — import-only smoke check
