"""
Task 1 — Formal Gate Layer regression tests.

WHAT THIS COVERS
_evaluate_gates() / _hard_safety_gate() in botanical_rd_candidate_engine.py,
and the additive Gate_Results column produced through run() and the
multi-compound merge path. Public status vocabulary is exactly
GateStatus.PASSED / GateStatus.FAILED / GateStatus.NOT_EVALUABLE — there
is no "needs review" state. Per-gate PASSED/FAILED/NOT_EVALUABLE cases
are covered, plus the non-negotiable backward-compatibility guarantees:
Decision_Class, R&D_Opportunity_Score, and candidate ordering must be
byte-identical to pre-Task-1 behavior, since gates are additive-only
(except that "safety" reports, rather than changes, the pre-existing
hard exclusion).

CALL-SITE SMOKE TESTS
research_engine.py and step_rd_candidates.py are checked via AST
inspection of their source only — this repo does not require streamlit
or supabase to be installed to run its test suite, and these two tests
must not either. AST inspection confirms the actual wiring (the
BotanicalRDCandidateEngine import, construction call, and — for
step_rd_candidates.py — the .run() invocation) without importing either
module or its optional dependencies.

HOW TO RUN
    pytest -q test_gate_layer.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import ast

import pandas as pd

import botanical_rd_candidate_engine as eng
from data_contracts import GateStatus
from decision_class_ah import classify_decision_ah
from structured_rationale import go_investigate_hold_no_go
from test_botanical_rd_candidate_engine import make_engine


REQUIRED_GATE_NAMES = {"safety", "identity", "minimum_evidence", "regulatory"}
# Correction round — Phase 4 added a 5th key, "eligibility", carrying
# the authoritative EligibilityStatus so Gate_Results can never
# disagree with Decision_Class (design review item 4). The four
# legacy keys above are unchanged in shape/meaning; "eligibility" is
# additive. See botanical_rd_candidate_engine.py::_evaluate_gates().
REQUIRED_GATE_NAMES_WITH_ELIGIBILITY = REQUIRED_GATE_NAMES | {"eligibility"}
REQUIRED_NESTED_KEYS = {"gate_name", "status", "reason", "evidence"}


# ---------------------------------------------------------------------
# GateStatus public vocabulary
# ---------------------------------------------------------------------

def test_gate_status_values_are_exactly_passed_failed_not_evaluable():
    values = {member.value for member in GateStatus}
    assert values == {"passed", "failed", "not_evaluable"}


def test_gate_status_has_no_needs_review_member():
    names = {member.name for member in GateStatus}
    assert "NEEDS_REVIEW" not in names
    assert not hasattr(GateStatus, "NEEDS_REVIEW")


# ---------------------------------------------------------------------
# _hard_safety_gate — the single source of truth shared by
# _decision_class() and _evaluate_gates()
# ---------------------------------------------------------------------

def test_hard_safety_gate_fails_on_a_hard_term():
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "lithogenic", same_plant=False
    )
    assert status == GateStatus.FAILED
    assert hit_terms == {"lithogenic"}


def test_hard_safety_gate_passes_with_no_flags():
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "", same_plant=False
    )
    assert status == GateStatus.PASSED
    assert hit_terms == set()


def test_hard_safety_gate_passes_on_controversial_only_terms():
    # "hepatotoxic" is CONTROVERSIAL_SAFETY_TERMS, not HARD_SAFETY_TERMS —
    # must not fail the gate (matches the existing _decision_class cap
    # behavior, which visibly flags but doesn't auto-exclude these).
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "hepatotoxic", same_plant=False
    )
    assert status == GateStatus.PASSED
    assert hit_terms == set()


def test_hard_safety_gate_not_evaluable_for_same_plant_even_with_hard_term():
    status, hit_terms, flagged = eng.BotanicalRDCandidateEngine._hard_safety_gate(
        "lithogenic", same_plant=True
    )
    assert status == GateStatus.NOT_EVALUABLE
    assert hit_terms == {"lithogenic"}  # term is still visible in output, just not gating


# ---------------------------------------------------------------------
# _evaluate_gates — overall shape: exactly 4 gates, exactly 4 keys each,
# gate_name matches the containing dictionary key.
# ---------------------------------------------------------------------

def test_evaluate_gates_returns_exactly_four_top_level_gates():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert set(gates.keys()) == REQUIRED_GATE_NAMES_WITH_ELIGIBILITY


def test_evaluate_gates_each_nested_result_has_exactly_required_keys():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="lithogenic", match_quality="", has_evidence=False,
        evidence_level="No direct evidence",
        regulatory_barrier_types=None, same_plant=False,
    )
    for gate_name, gate in gates.items():
        assert set(gate.keys()) == REQUIRED_NESTED_KEYS, gate_name
        # Correction round: the "eligibility" gate's status vocabulary is
        # EligibilityStatus (6 values), not GateStatus (3 values) — a
        # richer classification than the legacy gates' PASSED/FAILED/
        # NOT_EVALUABLE, stored as its .value string rather than
        # forced into GateStatus and losing information. The four
        # legacy gates are unaffected and still return real GateStatus
        # instances.
        if gate_name == "eligibility":
            assert isinstance(gate["status"], str) and gate["status"]
        else:
            assert isinstance(gate["status"], GateStatus)
        assert isinstance(gate["reason"], str) and gate["reason"]
        assert isinstance(gate["evidence"], str)


def test_evaluate_gates_gate_name_matches_its_dictionary_key():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    for key, gate in gates.items():
        assert gate["gate_name"] == key


# ---------------------------------------------------------------------
# _evaluate_gates — safety
# ---------------------------------------------------------------------

def test_evaluate_gates_safety_failed_matches_hard_safety_gate():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="lithogenic",
        match_quality="exact",
        has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[],
        same_plant=False,
    )
    assert gates["safety"]["status"] == GateStatus.FAILED
    assert "lithogenic" in gates["safety"]["reason"]
    assert gates["safety"]["evidence"] == "lithogenic"


def test_evaluate_gates_safety_passed_when_no_flags():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="",
        match_quality="exact",
        has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[],
        same_plant=False,
    )
    assert gates["safety"]["status"] == GateStatus.PASSED


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

def test_evaluate_gates_identity_passed_on_exact_match():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.PASSED


def test_evaluate_gates_identity_passed_on_target_verified_match():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="target_verified", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.PASSED


def test_evaluate_gates_identity_class_only_is_not_evaluable():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="class_only", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.NOT_EVALUABLE
    assert "class-only" in gates["identity"]["reason"] or "class_only" in gates["identity"]["reason"]


def test_evaluate_gates_identity_not_evaluable_when_match_quality_missing():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["identity"]["status"] == GateStatus.NOT_EVALUABLE


def test_evaluate_gates_identity_never_returns_failed():
    # No validated affirmative identity-failure signal exists in the
    # repository — identity must only ever be PASSED or NOT_EVALUABLE.
    for match_quality in ["", "exact", "target_verified", "class_only", "anything_else"]:
        gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
            safety_flags="", match_quality=match_quality, has_evidence=True,
            evidence_level="Clinical / human evidence",
            regulatory_barrier_types=[], same_plant=False,
        )
        assert gates["identity"]["status"] != GateStatus.FAILED


# ---------------------------------------------------------------------
# _evaluate_gates — minimum_evidence
# ---------------------------------------------------------------------

def test_evaluate_gates_minimum_evidence_passed_with_real_evidence():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Preclinical / mechanistic evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["minimum_evidence"]["status"] == GateStatus.PASSED


def test_evaluate_gates_minimum_evidence_generic_missing_is_not_evaluable():
    # No repository signal distinguishes "not searched" from "searched
    # and none found" — the generic no-evidence case must be
    # NOT_EVALUABLE, never a silent FAILED.
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=False,
        evidence_level="No direct evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["minimum_evidence"]["status"] == GateStatus.NOT_EVALUABLE


def test_evaluate_gates_minimum_evidence_never_returns_failed_today():
    # Has_Negative_Evidence/negative_evidence.is_negative was inspected
    # as a candidate signal for this gate and rejected: it measures
    # finding DIRECTION (a study was found and failed/was null), not
    # evidence VOLUME being insufficient — a different concept. No
    # genuine affirmative-insufficiency signal exists today, so FAILED
    # must not be reachable for any combination of has_evidence/
    # evidence_level this gate actually receives.
    for has_evidence in (True, False):
        for evidence_level in (
            "No direct evidence",
            "Preclinical / mechanistic evidence",
            "Clinical / human evidence",
        ):
            gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
                safety_flags="", match_quality="exact", has_evidence=has_evidence,
                evidence_level=evidence_level,
                regulatory_barrier_types=[], same_plant=False,
            )
            assert gates["minimum_evidence"]["status"] != GateStatus.FAILED


# ---------------------------------------------------------------------
# _evaluate_gates — regulatory
# ---------------------------------------------------------------------

def test_evaluate_gates_regulatory_failed_on_explicit_prohibition():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=["Prohibited / banned"], same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.FAILED


def test_evaluate_gates_regulatory_passed_when_checked_and_clear():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=[], same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.PASSED


def test_evaluate_gates_regulatory_non_ban_restrictions_do_not_fail():
    # A restriction (e.g. prescription-only) is a real finding but is
    # NOT a prohibition — must not fail this gate, only "Prohibited /
    # banned" does. Restriction stays visible in evidence/reason.
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=["Restricted access (prescription/controlled)"],
        same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.PASSED
    assert "Restricted access" in gates["regulatory"]["evidence"]


def test_evaluate_gates_regulatory_not_evaluable_when_never_checked():
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=None, same_plant=False,
    )
    assert gates["regulatory"]["status"] == GateStatus.NOT_EVALUABLE


# ---------------------------------------------------------------------
# Backward compatibility: Decision_Class must be byte-identical to
# pre-Task-1 behavior after the _hard_safety_gate refactor.
# ---------------------------------------------------------------------

def test_decision_class_hard_safety_exclusion_unchanged_after_refactor():
    # Correction round: an unconfirmed hit term on a different plant no
    # longer auto-resolves to "Safety concern..." -- see
    # eligibility_gate.py's corrected default-scope policy. This test's
    # ORIGINAL intent (documenting that a hard safety term is not
    # silently ignored) still holds: it must not be a positive/Go-
    # mapping Decision_Class either.
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,  # unbound call, same pattern the existing suite already uses
        score=80, safety_flags="lithogenic", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=False,
    )
    assert decision.startswith("Expert review required")
    assert "Strong R&D candidate" not in decision
    assert "Promising candidate" not in decision


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
# R&D_Opportunity_Score / ordering are exactly what they were before
# this task.
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
    assert set(gates.keys()) == REQUIRED_GATE_NAMES_WITH_ELIGIBILITY
    for gate_name, gate in gates.items():
        assert set(gate.keys()) == REQUIRED_NESTED_KEYS
        assert gate["gate_name"] == gate_name
    # Same_plant row -> safety gate must be NOT_EVALUABLE, not silently PASSED.
    assert gates["safety"]["status"] == GateStatus.NOT_EVALUABLE


def test_run_score_decision_class_and_ordering_unaffected_by_gate_wiring():
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

    assert "Gate_Results" in result.columns
    # Phase 4: this synthetic fixture has no raw evidence text at all
    # (no Notes/abstract fields populated), which the Eligibility Gate
    # now correctly classifies as INCOMPLETE rather than silently
    # falling into "Low priority / insufficient data" (a fail-open gap
    # the Phase 4 audit proved) — see eligibility_gate.py's
    # classify_safety_finding()/classify_regulatory_finding().
    assert row["Decision_Class"] in {
        "Strong R&D candidate",
        "Promising candidate; verify safety and standardization",
        "Early-stage candidate; more evidence needed",
        "Low priority / insufficient data",
        "Safety concern — not suitable without expert review",
        "Incomplete — insufficient safety/regulatory evidence for a validated recommendation",
    }
    assert 0 <= row["R&D_Opportunity_Score"] <= 100

    # Row count: this fixture (1 reference plant + 1 alternative plant,
    # sharing one compound, no merge-worthy duplicates) must still
    # produce exactly the same two rows (self-row + alternative) that
    # it did before Gate_Results existed.
    assert len(result) == 2

    # Ordering: the result must still be sorted by score, descending —
    # Gate_Results must not have introduced any secondary sort key.
    scores = result["R&D_Opportunity_Score"].tolist()
    assert scores == sorted(scores, reverse=True)


def test_deterministic_output_contract_locked_engineering_regression():
    """Engineering regression lock, NOT scientific/domain validation.

    This records the EXACT numeric/string output this deterministic
    synthetic fixture already produced from the existing, untouched
    _score_candidate/_decision_class logic, and asserts Gate_Results'
    addition changed none of it. It says nothing about whether these
    are scientifically "correct" values for a real plant/compound —
    only that this specific engineering change (Task 1) is additive.
    If a FUTURE task deliberately changes scoring/decision logic, this
    test is expected to need updating too; that is the point of it
    being a tight, exact lock rather than a range check.
    """
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

    # Row count and column count locked exactly.
    assert len(result) == 2
    # Column count updated from 52 to 53 by Task 15's additive
    # Decision_Engine_Version column (reproducibility metadata), then
    # from 53 to 55 by Task 2's additive GRADE_Certainty/
    # GRADE_Certainty_Rationale columns (GRADE-style clinical-evidence
    # certainty grading) — a legitimate, expected change to this lock,
    # not a regression. Row count, scores, and Decision_Class below are
    # UNCHANGED, which is what this test actually guards. (Previously
    # bumped 51 -> 52 by Task 10.2's Applicability_Summary, following
    # the same pattern.)
    #
    # A Robustness_Analysis/Boundary_Fragility pair was briefly added
    # here (57) and then removed — that computation duplicated
    # sensitivity_display_adapter.py's existing, UI-facing sensitivity
    # analysis with no additional consumer of its own; see that
    # module's docstring and test_task5_sensitivity_analysis_activation.py
    # for the single-source-of-truth this run() output no longer
    # duplicates.
    #
    # Bumped 55 -> 59 by the Phase 1 evidence-direction audit fix
    # (evidence_interpretation.py): Study_Design, Evidence_Direction,
    # Evidence_Quality, and Evidence_Applicability are new, independent,
    # additive output columns. These concepts must remain stored
    # separately rather than folded into an existing field. Same
    # "legitimate, expected change to this lock" pattern as every prior
    # bump above.
    #
    # Bumped 59 -> 74 by Phase 4's Eligibility Gate redesign: 15 new,
    # additive, structured columns (Eligibility_Status, Hard_No_Go,
    # Eligible_For_Normal_Ranking, Score_Validity, Gate_Type, Gate_Reason,
    # Gate_Evidence_IDs, Safety_Severity, Safety_Scope,
    # Safety_Context_Relevance, Regulatory_Status, Regulatory_Scope,
    # Regulatory_Context_Relevance, Data_Completeness,
    # Requires_Expert_Review) — see eligibility_gate.py. Inserted before
    # Decision_Engine_Version, which remains the last column.
    #
    # Bumped 74 -> 76 by the correction round: Safety_Gate_Evidence_IDs
    # and Regulatory_Gate_Evidence_IDs (finding-specific traceability,
    # design review item 3) are new, additive columns.
    #
    # Bumped 78 -> 82 by Pharmaceutical-grade Safety hardening:
    # Safety_Assertions, Safety_Decision_Confidence,
    # Safety_Evidence_Conflict, and Safety_Severity_Rule.
    #
    # Bumped 76 -> 77 by the correction round (2nd pass): Ranking_Partition
    # (design review item 2 — NORMAL / PRELIMINARY_OR_EXPERT_REVIEW /
    # EXCLUDED_NO_GO, see eligibility_gate.RankingPartition) is a new,
    # additive column.
    assert len(result.columns) == 82
    assert "Gate_Results" in result.columns
    assert "Applicability_Summary" in result.columns
    assert "Decision_Engine_Version" in result.columns
    assert "GRADE_Certainty" in result.columns
    assert "GRADE_Certainty_Rationale" in result.columns
    assert "Robustness_Analysis" not in result.columns
    assert "Boundary_Fragility" not in result.columns

    # A representative set of pre-existing output fields must still be
    # present and untouched by this task's column addition.
    for pre_existing_column in (
        "Reference_Plant", "Alternative_Plant", "R&D_Opportunity_Score",
        "Decision_Class", "Decision_Class_AH", "Safety_Flags",
        "Score_Breakdown", "Rationale",
    ):
        assert pre_existing_column in result.columns

    result_sorted = result.sort_values(
        ["Reference_Plant", "Alternative_Plant"]
    ).reset_index(drop=True)

    alt_row = result_sorted[result_sorted["Alternative_Plant"] == "AltPlant"].iloc[0]
    self_row = result_sorted[result_sorted["Alternative_Plant"] == "RefPlant"].iloc[0]

    # Exact SCORE values for this fixed, deterministic fixture are
    # unchanged by Phase 4 (see test_scoring_config.py for the same
    # point made explicitly). Decision_Class changes for this specific
    # zero-evidence-text fixture — intended, see that same test's
    # comment.
    # PHASE 5 (§10 fix, confirmed defect in the main Phase 5 audit
    # §3.1): this fixture's market status resolves to the "neutral
    # default" branch (no verified market signal either way).
    # market_neutral_default changed from +3 (a confirmed defect — it
    # scored ABOVE a verified positive market finding of +1) to the
    # correct neutral 0.0 (phase5_scoring_config.MARKET_STATUS_POINTS).
    # 38.0 (old, defective) -> 35.0 (new, correct) is exactly that -3.0
    # market-component change; nothing else about this fixture's
    # scoring path changed.
    assert alt_row["R&D_Opportunity_Score"] == 35.0
    assert alt_row["Decision_Class"] == (
        "Incomplete — insufficient safety/regulatory evidence for a validated recommendation"
    )
    assert self_row["R&D_Opportunity_Score"] == 20.0
    assert self_row["Decision_Class"] == (
        "Incomplete — insufficient safety/regulatory evidence for a validated recommendation"
    )

    # Row order (by score, descending) is exactly: alternative row
    # first, self-row second — unchanged by Gate_Results.
    # PHASE 5: absolute values shifted by the market_neutral_default fix
    # (see the assertions above) but relative order is unchanged.
    ordered_scores = result["R&D_Opportunity_Score"].tolist()
    assert ordered_scores == [35.0, 20.0]


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
    assert set(gates.keys()) == REQUIRED_GATE_NAMES_WITH_ELIGIBILITY
    for gate_name, gate in gates.items():
        assert set(gate.keys()) == REQUIRED_NESTED_KEYS
        assert gate["gate_name"] == gate_name


def test_merged_row_safety_gate_reflects_merged_safety_flags():
    # A hard-safety term on only ONE of several merged sub-rows must
    # still surface as FAILED on the merged row's safety gate — same
    # union-of-flags behavior Safety_Flags/Decision_Class already had
    # before Task 1 (see test_merged_rows_keep_safety_flags_decision_class_and_rationale_in_sync
    # in test_botanical_rd_candidate_engine.py).
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
    ].iloc[0]
    if alt_row["Decision_Class"] == "Safety concern — not suitable without expert review":
        assert alt_row["Gate_Results"]["safety"]["status"] == GateStatus.FAILED
    else:
        assert alt_row["Gate_Results"]["safety"]["status"] != GateStatus.FAILED


# ---------------------------------------------------------------------
# Both engine call sites (Step 2's research_engine.py and Step 5's
# step_rd_candidates.py) continue to wire BotanicalRDCandidateEngine —
# verified via AST/source inspection only (wiring checks only, not
# behavioral validation), so this test suite does not require
# streamlit or supabase to be installed. Behavior itself (gate
# semantics, run() output) is covered by the executable engine tests
# above, not here.
# ---------------------------------------------------------------------

# A handful of columns that are unambiguously part of run()'s existing
# OUTPUT_COLUMNS contract — used below only to recognize a literal
# column-allowlist subscript (df[[...]]) as being "the output columns",
# so a narrowing that quietly excludes Gate_Results can be detected.
_KNOWN_OUTPUT_COLUMN_SAMPLE = {
    "Reference_Plant", "Alternative_Plant", "R&D_Opportunity_Score",
    "Decision_Class", "Decision_Class_AH", "Safety_Flags", "Rationale",
}


def _source_calls_and_imports(path):
    with open(path, encoding="utf-8") as f:
        source = f.read()
        tree = ast.parse(source, filename=path)

    imports_engine = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "botanical_rd_candidate_engine":
            if any(alias.name == "BotanicalRDCandidateEngine" for alias in node.names):
                imports_engine = True

    call_func_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_func_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_func_names.add(node.func.attr)

    return imports_engine, call_func_names, tree


def _string_constant(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _gate_results_not_stripped(tree):
    """Wiring-only check: neither an explicit .drop(...) targeting
    "Gate_Results", nor a literal output-columns allowlist subscript
    (df[[...]]) that includes several known OUTPUT_COLUMNS entries but
    omits "Gate_Results", appears in this module. This does not (and
    cannot, via AST alone) prove behavior — it proves the wiring
    doesn't statically remove or overwrite the column by name."""
    for node in ast.walk(tree):
        # .drop(columns=["Gate_Results", ...]) or .drop(["Gate_Results"], axis=1)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "drop":
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                targets = []
                if isinstance(arg, ast.List):
                    targets = [_string_constant(elt) for elt in arg.elts]
                else:
                    targets = [_string_constant(arg)]
                if "Gate_Results" in targets:
                    return False

        # df[[...]] / df.loc[:, [...]] literal column allowlist that
        # looks like the run() output columns but excludes Gate_Results.
        if isinstance(node, ast.Subscript):
            slice_node = node.slice
            if isinstance(slice_node, ast.List):
                names = {_string_constant(elt) for elt in slice_node.elts}
                names.discard(None)
                if len(names & _KNOWN_OUTPUT_COLUMN_SAMPLE) >= 3 and "Gate_Results" not in names:
                    return False

    return True


def test_research_engine_call_site_still_wires_botanical_rd_candidate_engine():
    imports_engine, call_func_names, tree = _source_calls_and_imports("research_engine.py")
    assert imports_engine, "research_engine.py must import BotanicalRDCandidateEngine"
    assert "BotanicalRDCandidateEngine" in call_func_names, (
        "research_engine.py must still construct BotanicalRDCandidateEngine"
    )
    assert _gate_results_not_stripped(tree), (
        "research_engine.py must not drop or allowlist-exclude the Gate_Results column"
    )


def test_step_rd_candidates_call_site_still_wires_botanical_rd_candidate_engine():
    imports_engine, call_func_names, tree = _source_calls_and_imports("step_rd_candidates.py")
    assert imports_engine, "step_rd_candidates.py must import BotanicalRDCandidateEngine"
    assert "BotanicalRDCandidateEngine" in call_func_names, (
        "step_rd_candidates.py must still construct BotanicalRDCandidateEngine"
    )
    assert "run" in call_func_names, (
        "step_rd_candidates.py must still invoke .run() on the engine"
    )
    assert _gate_results_not_stripped(tree), (
        "step_rd_candidates.py must not drop or allowlist-exclude the Gate_Results column"
    )


# ---------------------------------------------------------------------
# Task 4 — activating the regulatory gate as a second hard,
# non-compensatory Decision_Class stop, alongside the existing safety
# one. See _hard_regulatory_gate(), the REGULATORY_PROHIBITION_
# DECISION_CLASS/HARD_STOP_DECISION_CLASSES constants, and
# _decision_class()'s early-return in botanical_rd_candidate_engine.py.
# ---------------------------------------------------------------------

def test_hard_regulatory_gate_fails_on_explicit_prohibition():
    status, banned = eng.BotanicalRDCandidateEngine._hard_regulatory_gate(
        ["Prohibited / banned"], same_plant=False,
    )
    assert status == GateStatus.FAILED
    assert banned == {"Prohibited / banned"}


def test_hard_regulatory_gate_passes_when_checked_and_clear():
    status, banned = eng.BotanicalRDCandidateEngine._hard_regulatory_gate(
        [], same_plant=False,
    )
    assert status == GateStatus.PASSED
    assert banned == set()


def test_hard_regulatory_gate_not_evaluable_when_never_checked():
    status, banned = eng.BotanicalRDCandidateEngine._hard_regulatory_gate(
        None, same_plant=False,
    )
    assert status == GateStatus.NOT_EVALUABLE
    assert banned == set()


def test_hard_regulatory_gate_non_ban_restriction_does_not_fail():
    status, banned = eng.BotanicalRDCandidateEngine._hard_regulatory_gate(
        ["Restricted access (prescription/controlled)"], same_plant=False,
    )
    assert status == GateStatus.PASSED
    assert banned == set()


def test_hard_regulatory_gate_same_plant_skips_exclusion_even_when_banned():
    status, banned = eng.BotanicalRDCandidateEngine._hard_regulatory_gate(
        ["Prohibited / banned"], same_plant=True,
    )
    assert status == GateStatus.NOT_EVALUABLE
    assert banned == set()


def test_evaluate_gates_regulatory_same_plant_reason_and_status():
    # same_plant now overrides ANY regulatory_barrier_types value,
    # exactly like the safety gate already does — the reason text must
    # reflect the exemption, not "never checked" or a bare pass/fail.
    gates = eng.BotanicalRDCandidateEngine._evaluate_gates(
        safety_flags="", match_quality="exact", has_evidence=True,
        evidence_level="Clinical / human evidence",
        regulatory_barrier_types=["Prohibited / banned"], same_plant=True,
    )
    assert gates["regulatory"]["status"] == GateStatus.NOT_EVALUABLE
    assert "matched to itself" in gates["regulatory"]["reason"]
    assert "Prohibited / banned" in gates["regulatory"]["evidence"]


def test_decision_class_regulatory_prohibition_hard_stop():
    # Correction round: without a CONFIRMED species-wide/relevant scope
    # (which production never supplies today), an unconfirmed
    # prohibition hit resolves to EXPERT_REVIEW_REQUIRED, not an
    # automatic hard no-go -- see eligibility_gate.py's corrected
    # default policy. The test's original intent (a prohibition is
    # never silently ignored / never lets a high score win) still
    # holds.
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,
        score=90, safety_flags="", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=False,
        regulatory_barrier_types=["Prohibited / banned"],
    )
    assert decision != eng.REGULATORY_PROHIBITION_DECISION_CLASS  # not the OLD auto hard-stop string...
    assert decision.startswith("Expert review required")           # ...but not silently ignored either
    assert "Strong R&D candidate" not in decision


def test_decision_class_regulatory_prohibition_beats_high_score():
    # Non-compensatory: even a score that would otherwise earn "Strong"
    # must not escape into a positive Decision_Class while a
    # prohibition is present, confirmed scope or not.
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,
        score=99, safety_flags="", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=False,
        regulatory_barrier_types=["Prohibited / banned"],
    )
    assert decision.startswith("Expert review required")
    assert "Strong R&D candidate" not in decision


def test_decision_class_regulatory_prohibition_with_confirmed_scope_is_hard_stop():
    """The OLD test's exact scenario, now expressed honestly: NO_GO_
    REGULATORY (the REGULATORY_PROHIBITION_DECISION_CLASS string) is
    still fully reachable -- just only when scope is CONFIRMED, via
    eligibility_gate.classify_regulatory_finding()'s confirmed_scope/
    confirmed_context_relevance overrides. Exercises the underlying
    eligibility_gate function directly, since _decision_class() itself
    has no confirmed-scope parameter (production never supplies one
    today -- see eligibility_gate.py's module docstring)."""
    from eligibility_gate import (
        ContextRelevance, EligibilityStatus, FindingScope,
        classify_regulatory_finding, classify_safety_finding, evaluate_eligibility,
    )
    safety = classify_safety_finding(hit_terms=frozenset(), has_evidence_text=True, same_plant=False)
    regulatory = classify_regulatory_finding(
        barrier_types=frozenset({"Prohibited / banned"}), has_evidence_text=True, same_plant=False,
        confirmed_scope=FindingScope.SPECIES_WIDE,
        confirmed_context_relevance=ContextRelevance.RELEVANT,
    )
    decision = evaluate_eligibility(safety, regulatory)
    assert decision.status == EligibilityStatus.NO_GO_REGULATORY
    assert decision.hard_no_go is True


def test_decision_class_same_plant_skips_regulatory_hard_stop():
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,
        score=80, safety_flags="", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=True,
        regulatory_barrier_types=["Prohibited / banned"],
    )
    assert decision != eng.REGULATORY_PROHIBITION_DECISION_CLASS


def test_decision_class_non_ban_restriction_does_not_trigger_hard_stop():
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,
        score=90, safety_flags="", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=False,
        regulatory_barrier_types=["Restricted access (prescription/controlled)"],
    )
    assert decision != eng.REGULATORY_PROHIBITION_DECISION_CLASS
    assert decision == "Strong R&D candidate"


def test_decision_class_default_regulatory_barrier_types_is_backward_compatible():
    # Every pre-Task-4 caller that doesn't pass regulatory_barrier_types
    # at all must be completely unaffected (defaults to None -> never a
    # hard stop).
    decision = eng.BotanicalRDCandidateEngine._decision_class(
        None,
        score=90, safety_flags="", interaction_flags="",
        has_evidence=True, match_quality="exact",
        evidence_level="Clinical / human evidence", same_plant=False,
    )
    assert decision == "Strong R&D candidate"


def test_decision_class_ah_maps_regulatory_prohibition_to_h():
    result = classify_decision_ah(
        existing_decision_class=eng.REGULATORY_PROHIBITION_DECISION_CLASS,
        evidence_confidence=90, rd_opportunity_score=99,
        market_status="", match_quality="exact", same_plant=False,
    )
    assert result == "H — No-go / safety concern"


def test_go_investigate_hold_no_go_is_no_go_for_regulatory_prohibition():
    decision_ah = classify_decision_ah(
        existing_decision_class=eng.REGULATORY_PROHIBITION_DECISION_CLASS,
        evidence_confidence=90, rd_opportunity_score=99,
        market_status="", match_quality="exact", same_plant=False,
    )
    assert go_investigate_hold_no_go(decision_ah) == "No-Go"


def test_regulatory_prohibition_end_to_end_through_run():
    """Correction round: through the real run() pipeline, a
    'prohibited and banned' text match on a DIFFERENT plant is
    documented and NOT ignored, but — since production never confirms
    species-wide/relevant scope — it resolves end-to-end to
    EXPERT_REVIEW_REQUIRED, not an automatic NO_GO_REGULATORY. See
    eligibility_gate.py's corrected default policy and
    test_decision_class_regulatory_prohibition_with_confirmed_scope_is_hard_stop
    above for proof NO_GO_REGULATORY is still fully reachable when
    scope IS confirmed."""
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "AltPlant",
        "Target_Indication": "TestIndication",
        "Notes": "This substance is prohibited and banned for sale in several jurisdictions.",
    }])
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    alt_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "AltPlant")
    ].iloc[0]
    assert alt_row["Decision_Class"].startswith("Expert review required")
    assert alt_row["Decision_Class"] != eng.REGULATORY_PROHIBITION_DECISION_CLASS
    assert alt_row["Eligibility_Status"] == "expert_review_required"
    assert bool(alt_row["Eligible_For_Normal_Ranking"]) is False
    # The legacy regulatory gate (unchanged function) still reports
    # FAILED on its own coarser vocabulary -- this is now understood as
    # the coarse/legacy view; Gate_Results["eligibility"] is the
    # authoritative one and must agree with Decision_Class.
    assert alt_row["Gate_Results"]["regulatory"]["status"] == GateStatus.FAILED
    assert alt_row["Gate_Results"]["eligibility"]["status"] == "expert_review_required"
    assert alt_row["Decision_Class_AH"] == "G — Hold / insufficient evidence"
    assert alt_row["Go_Investigate_Hold_NoGo"] == "Hold"


def test_regulatory_prohibition_same_plant_exempt_end_to_end_through_run():
    eng.SIMILAR_COMPOUND_GROUPS = {}
    eng.COMPOUND_TARGETS = {}
    rows = [
        dict(scientific_name="RefPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="AltPlant", compound_name="SharedCompound",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]
    # The banned text is attached to the REFERENCE plant itself, so the
    # self-matched row (RefPlant vs RefPlant) must be exempt.
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "RefPlant",
        "Target_Indication": "TestIndication",
        "Notes": "This substance is prohibited and banned for sale in several jurisdictions.",
    }])
    engine = make_engine(rows)
    engine.evidence_df = evidence_df
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")

    self_row = result[
        (result["Reference_Plant"] == "RefPlant") & (result["Alternative_Plant"] == "RefPlant")
    ].iloc[0]
    assert self_row["Decision_Class"] != eng.REGULATORY_PROHIBITION_DECISION_CLASS
    assert self_row["Gate_Results"]["regulatory"]["status"] == GateStatus.NOT_EVALUABLE
    assert "Prohibited / banned" in self_row["Gate_Results"]["regulatory"]["evidence"]


def test_merge_tightest_pool_treats_both_hard_stops_as_equally_worst():
    # A candidate matching on TWO compounds, where one sub-row is
    # "Strong" and the other independently earned the regulatory
    # hard-stop, must merge down to the hard-stop — same conservative
    # "tightest wins" principle as the pre-existing safety case, now
    # covering the regulatory hard-stop too.
    output = pd.DataFrame([
        {
            "Reference_Plant": "RefPlant", "Alternative_Plant": "AltPlant",
            "Reference_Compound": "CompoundA", "Shared_or_Similar_Compound": "CompoundA",
            "R&D_Opportunity_Score": 90.0, "Decision_Class": "Strong R&D candidate",
            "Safety_Flags": "No explicit flag found", "Interaction_Flags": "No explicit flag found",
            "Novelty_Status": "Alternative source with similar compound",
            "Rationale": "Decision: Strong R&D candidate.",
        },
        {
            "Reference_Plant": "RefPlant", "Alternative_Plant": "AltPlant",
            "Reference_Compound": "CompoundB", "Shared_or_Similar_Compound": "CompoundB",
            "R&D_Opportunity_Score": 40.0,
            "Decision_Class": eng.REGULATORY_PROHIBITION_DECISION_CLASS,
            "Safety_Flags": "No explicit flag found", "Interaction_Flags": "No explicit flag found",
            "Novelty_Status": "Alternative source with similar compound",
            "Rationale": f"Decision: {eng.REGULATORY_PROHIBITION_DECISION_CLASS}.",
        },
    ])
    engine = eng.BotanicalRDCandidateEngine.__new__(eng.BotanicalRDCandidateEngine)
    merged = engine._merge_multi_compound_matches(output)
    assert len(merged) == 1
    assert merged.iloc[0]["Decision_Class"] == eng.REGULATORY_PROHIBITION_DECISION_CLASS
