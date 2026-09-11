"""PROBLEM 2 regression tests -- hard evidence-sufficiency gate.

A candidate must never receive an actionable positive efficacy
recommendation (GO / GO WITH CAUTION) when it has zero VERIFIED
outcome-specific HUMAN evidence for the requested indication, regardless
of AI-estimated human counts, mechanistic evidence, generic/direct-
indication labels, related-indication evidence, Human_Evidence_Strength
prose, or a positive adjudication. This is an evidence-SUFFICIENCY gate,
not a safety gate: genuine safety/regulatory NO-GO decisions must remain
untouched and must never be downgraded to EXPERT REVIEW REQUIRED by it.

All botanicals/indications used below are fictional.
"""
import pandas as pd
import pytest

from step_rd_candidates import (
    _reconcile_final_decision_status,
    _pre_gate_final_decision_status,
    _verified_outcome_specific_human_evidence_count,
    _evidence_sufficiency_gate_triggered,
    _merge_and_sync_final_decision_status,
)
from evidence_adjudication_engine import build_final_rationale
from candidate_shortlisting import build_plant_candidate_shortlist


NON_ACTIONABLE_STATUSES = {
    "EXPERT REVIEW REQUIRED",
    "NO GO SAFETY",
    "NO GO REGULATORY",
    "INSUFFICIENT EVIDENCE",
}


def _go_row(**overrides):
    """A pre-gate row that reaches an unqualified GO via the bottom
    decision_class/gate fallback path (no AI adjudication involved)."""
    row = {
        "Decision_Class_AH": "A — Strong candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Outcome_Specific_Human_Evidence_Count": 0,
    }
    row.update(overrides)
    return row


def _go_with_caution_row(**overrides):
    """A pre-gate row that reaches GO WITH CAUTION via the bottom
    decision_class/gate fallback path (no AI adjudication involved)."""
    row = {
        "Decision_Class_AH": "C — Candidate requiring further evidence",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Outcome_Specific_Human_Evidence_Count": 0,
    }
    row.update(overrides)
    return row


def _ai_ok_direct_human_row(**overrides):
    """A pre-gate row that reaches GO via the 'Direct human/clinical' +
    AI_ADJUDICATION_OK path, using the outcome_context_unverified_but_
    supported escape hatch so zero verified human evidence does not, by
    itself, already trip an EXPERT REVIEW REQUIRED inside the pre-gate
    function. This isolates the NEW hard gate from the existing checks."""
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 3,
        "Outcome_Specific_Direct_Evidence_Count": 3,
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Evidence_Adjudication_Evidence_Count": 3,
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Human_Evidence_Strength": "MODERATE",
        "Direct_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
        "Direct_Human_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------
# Sanity: prove the fixtures above actually exercise the intended
# pre-gate code paths (GO / GO WITH CAUTION) BEFORE the new hard gate is
# considered. If these ever fail, the adversarial tests below would be
# vacuous.
# ---------------------------------------------------------------------

def test_fixture_sanity_go_row_reaches_go_pre_gate():
    assert _pre_gate_final_decision_status(_go_row()) == "GO"


def test_fixture_sanity_go_with_caution_row_reaches_go_with_caution_pre_gate():
    assert _pre_gate_final_decision_status(_go_with_caution_row()) == "GO WITH CAUTION"


def test_fixture_sanity_ai_ok_direct_human_row_reaches_go_pre_gate():
    assert _pre_gate_final_decision_status(_ai_ok_direct_human_row()) == "GO"


# ---------------------------------------------------------------------
# Required regression tests 1-5
# ---------------------------------------------------------------------

def test_1_zero_verified_count_with_high_ai_human_count_is_non_actionable():
    row = _go_row(
        Direct_Human_Outcome_Evidence_IDs=[f"ai_{i}" for i in range(12)],
        Human_Evidence_Strength="STRONG",
    )
    status = _reconcile_final_decision_status(row)
    assert status not in {"GO", "GO WITH CAUTION"}
    assert status in NON_ACTIONABLE_STATUSES
    assert status == "EXPERT REVIEW REQUIRED"


def test_2_zero_verified_count_with_strong_mechanistic_evidence_is_non_actionable():
    row = _go_with_caution_row(Mechanistic_Evidence_Count=25)
    status = _reconcile_final_decision_status(row)
    assert status not in {"GO", "GO WITH CAUTION"}
    assert status == "EXPERT REVIEW REQUIRED"


def test_3_zero_verified_count_with_direct_human_clinical_label_is_non_actionable():
    row = _ai_ok_direct_human_row()
    status = _reconcile_final_decision_status(row)
    assert status not in {"GO", "GO WITH CAUTION"}
    assert status == "EXPERT REVIEW REQUIRED"


def test_4_zero_verified_count_with_strong_human_evidence_strength_label_is_non_actionable():
    row = _go_with_caution_row(Human_Evidence_Strength="STRONG")
    status = _reconcile_final_decision_status(row)
    assert status not in {"GO", "GO WITH CAUTION"}
    assert status == "EXPERT REVIEW REQUIRED"


def test_5_zero_verified_count_with_positive_adjudication_is_non_actionable():
    row = _go_row(
        Evidence_Adjudication_Status="AI_ADJUDICATION_OK",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
        Human_Evidence_Strength="MODERATE",
        Evidence_Conflict_Level="NONE",
        Scientific_Evidence_Confidence="HIGH",
        Direct_Indication_Evidence_Count=3,
        Evidence_Adjudication_Evidence_Count=3,
        Direct_Outcome_Evidence_IDs=["e1", "e2", "e3"],
    )
    status = _reconcile_final_decision_status(row)
    assert status not in {"GO", "GO WITH CAUTION"}
    assert status == "EXPERT REVIEW REQUIRED"


# ---------------------------------------------------------------------
# Required regression test 6 -- positive control: one genuinely verified
# candidate-specific, outcome-specific human study means the hard gate no
# longer blocks; the normal existing decision logic applies unchanged.
# ---------------------------------------------------------------------

def test_6_one_verified_outcome_specific_human_record_gate_does_not_block():
    go_row = _go_row(Outcome_Specific_Human_Evidence_Count=1)
    assert _reconcile_final_decision_status(go_row) == "GO"

    caution_row = _go_with_caution_row(Outcome_Specific_Human_Evidence_Count=1)
    assert _reconcile_final_decision_status(caution_row) == "GO WITH CAUTION"

    # Necessary condition, not sufficient: the gate merely stops blocking.
    # It must NOT force GO/GO WITH CAUTION for a row whose normal logic
    # would legitimately land somewhere else.
    insufficient_row = {
        "Decision_Class_AH": "G — Hold / insufficient evidence",
        "Relevance_Gate_Result": "passed_direct",
        "Outcome_Specific_Human_Evidence_Count": 1,
    }
    assert _reconcile_final_decision_status(insufficient_row) == "INSUFFICIENT EVIDENCE"


# ---------------------------------------------------------------------
# Required regression tests 7-10 -- the canonical count itself must stay
# zero for evidence that does not qualify. These exercise the canonical
# count reader/candidate-shortlisting pipeline directly with fictional
# botanicals, rather than re-deriving the rule a second time.
# ---------------------------------------------------------------------

def _shortlist_row(**overrides):
    row = {
        "Reference_Plant": "Reference plant",
        "Alternative_Plant": "Fictional botanical Alpha",
        "Shared_or_Similar_Compound": "fictionoside",
        "Novelty_Status": "Rare / differentiating",
        "Target_or_Mechanism": "FICR1",
        "Target_Provenance": "Supported by source record",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human clinical evidence",
        "Candidate_Evidence_Strength_Tier": "Direct evidence",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": "PMID:900001",
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "Regulatory_Barriers": "None identified",
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "Investigate",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "R&D_Opportunity_Score": 70,
        "Candidate_Attribution_Verified": True,
        "Indication_Match_Type": "exact_indication",
        "Indication_Match_Terms": "Fictional sleep-support indication",
        "Scientific_Rationale": "human clinical trial reported improved sleep latency",
        "Clinical_Rationale": "human clinical trial reported improved sleep latency",
    }
    row.update(overrides)
    return row


INDICATION = "Fictional sleep-support indication"


def test_7_unrelated_human_study_count_remains_zero():
    df = pd.DataFrame([_shortlist_row(
        Indication_Match_Terms="Fictional joint-mobility indication",
        Scientific_Rationale="human clinical trial reported improved joint mobility",
        Clinical_Rationale="human clinical trial reported improved joint mobility",
    )])
    summary, _ = build_plant_candidate_shortlist(df, indication=INDICATION, dosage_form="Infusion")
    row = summary.set_index("Alternative_Plant").loc["Fictional botanical Alpha"]
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 0


def test_8_human_study_for_wrong_indication_count_remains_zero():
    df = pd.DataFrame([_shortlist_row(
        Indication_Match_Terms="Fictional appetite indication",
        Scientific_Rationale="human clinical trial reported reduced appetite",
        Clinical_Rationale="human clinical trial reported reduced appetite",
    )])
    summary, _ = build_plant_candidate_shortlist(df, indication=INDICATION, dosage_form="Infusion")
    row = summary.set_index("Alternative_Plant").loc["Fictional botanical Alpha"]
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 0


def test_9_candidate_attribution_missing_or_false_count_remains_zero():
    df_missing = pd.DataFrame([_shortlist_row(Candidate_Attribution_Verified=None)])
    summary, _ = build_plant_candidate_shortlist(df_missing, indication=INDICATION, dosage_form="Infusion")
    row = summary.set_index("Alternative_Plant").loc["Fictional botanical Alpha"]
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 0

    df_false = pd.DataFrame([_shortlist_row(Candidate_Attribution_Verified=False)])
    summary2, _ = build_plant_candidate_shortlist(df_false, indication=INDICATION, dosage_form="Infusion")
    row2 = summary2.set_index("Alternative_Plant").loc["Fictional botanical Alpha"]
    assert int(row2["Outcome_Specific_Human_Evidence_Count"]) == 0


def test_10_mechanistic_animal_in_vitro_only_count_remains_zero():
    df = pd.DataFrame([_shortlist_row(
        Evidence_Level="Preclinical / in vitro evidence",
        Evidence_Hierarchy_Detail="In vitro assay",
        Candidate_Evidence_Strength_Tier="Mechanistic evidence",
        Scientific_Rationale="in vitro assay showed receptor binding",
        Clinical_Rationale="animal model showed reduced inflammation markers",
    )])
    summary, _ = build_plant_candidate_shortlist(df, indication=INDICATION, dosage_form="Infusion")
    row = summary.set_index("Alternative_Plant").loc["Fictional botanical Alpha"]
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 0


# ---------------------------------------------------------------------
# Required regression test 11 -- a genuine safety NO-GO with zero
# efficacy human evidence must remain a safety NO-GO, never downgraded to
# EXPERT REVIEW REQUIRED by the evidence-sufficiency gate.
# ---------------------------------------------------------------------

def test_11_real_safety_no_go_with_zero_human_evidence_remains_safety_no_go():
    row = {
        "Decision_Class_AH": "H — Hard safety stop",
        "Relevance_Gate_Result": "passed_direct",
        "Outcome_Specific_Human_Evidence_Count": 0,
    }
    assert _pre_gate_final_decision_status(row) == "NO GO SAFETY"
    assert _reconcile_final_decision_status(row) == "NO GO SAFETY"

    # Also verify the pass-through-from-upstream NO GO SAFETY/REGULATORY
    # path (current already set) is untouched by the gate.
    upstream_row = {
        "Final_Decision_Status": "NO GO SAFETY",
        "Outcome_Specific_Human_Evidence_Count": 0,
    }
    assert _reconcile_final_decision_status(upstream_row) == "NO GO SAFETY"

    upstream_reg_row = {
        "Final_Decision_Status": "NO GO REGULATORY",
        "Outcome_Specific_Human_Evidence_Count": 0,
    }
    assert _reconcile_final_decision_status(upstream_reg_row) == "NO GO REGULATORY"


# ---------------------------------------------------------------------
# Required regression test 12 -- missing/legacy attribution fields fail
# closed and never produce an actionable recommendation.
# ---------------------------------------------------------------------

def test_12_missing_or_legacy_count_field_fails_closed_non_actionable():
    row_missing_field = _go_row()
    del row_missing_field["Outcome_Specific_Human_Evidence_Count"]
    assert _verified_outcome_specific_human_evidence_count(row_missing_field) == 0
    assert _reconcile_final_decision_status(row_missing_field) == "EXPERT REVIEW REQUIRED"

    row_legacy_blank = _go_with_caution_row(Outcome_Specific_Human_Evidence_Count="")
    assert _verified_outcome_specific_human_evidence_count(row_legacy_blank) == 0
    assert _reconcile_final_decision_status(row_legacy_blank) == "EXPERT REVIEW REQUIRED"

    row_legacy_nan = _go_row(Outcome_Specific_Human_Evidence_Count=float("nan"))
    assert _verified_outcome_specific_human_evidence_count(row_legacy_nan) == 0
    assert _reconcile_final_decision_status(row_legacy_nan) == "EXPERT REVIEW REQUIRED"

    row_legacy_garbage = _go_row(Outcome_Specific_Human_Evidence_Count="not-a-number")
    assert _verified_outcome_specific_human_evidence_count(row_legacy_garbage) == 0
    assert _reconcile_final_decision_status(row_legacy_garbage) == "EXPERT REVIEW REQUIRED"


# ---------------------------------------------------------------------
# End-to-end test: canonical evidence records -> verified outcome-
# specific human count -> decision reconciliation -> final status ->
# final rationale.
# ---------------------------------------------------------------------

def test_end_to_end_zero_count_candidate_is_non_actionable_with_honest_rationale():
    result_df = pd.DataFrame([{
        "Alternative_Plant": "Fictional botanical Beta",
        "Overall_Score": 55,
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Evidence_Adjudication_Rationale": (
            "Moderate human evidence consistently supports the requested indication."
        ),
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 3,
        "Outcome_Specific_Direct_Evidence_Count": 3,
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Evidence_Adjudication_Evidence_Count": 3,
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Human_Evidence_Strength": "MODERATE",
        "Direct_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
        "Direct_Human_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
    }])
    plant_summary_df = result_df.copy()

    report_ready_df = _merge_and_sync_final_decision_status(result_df, plant_summary_df)
    row = report_ready_df.set_index("Alternative_Plant").loc["Fictional botanical Beta"]

    assert row["Final_Decision_Status"] not in {"GO", "GO WITH CAUTION"}
    assert row["Final_Decision_Status"] == "EXPERT REVIEW REQUIRED"
    assert bool(row["Evidence_Sufficiency_Gate_Triggered"]) is True

    rationale = build_final_rationale(row)
    assert "no verified outcome-specific human evidence" in rationale.lower()
    assert "moderate human evidence" not in rationale.lower()
    assert "consistently supports" not in rationale.lower()


def test_end_to_end_positive_control_one_verified_record_survives_gate():
    result_df = pd.DataFrame([{
        "Alternative_Plant": "Fictional botanical Gamma",
        "Overall_Score": 55,
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Evidence_Adjudication_Rationale": (
            "Moderate human evidence consistently supports the requested indication."
        ),
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 3,
        "Outcome_Specific_Direct_Evidence_Count": 3,
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Evidence_Adjudication_Evidence_Count": 3,
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Human_Evidence_Strength": "MODERATE",
        "Direct_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
        "Direct_Human_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
    }])
    plant_summary_df = result_df.copy()

    report_ready_df = _merge_and_sync_final_decision_status(result_df, plant_summary_df)
    row = report_ready_df.set_index("Alternative_Plant").loc["Fictional botanical Gamma"]

    # Necessary-not-sufficient: normal logic applies, and here that logic
    # produces GO (see test_fixture_sanity_ai_ok_direct_human_row... for the
    # analogous unit-level path). The hard gate must not have intervened.
    assert bool(row["Evidence_Sufficiency_Gate_Triggered"]) is False
    assert row["Final_Decision_Status"] == "GO"


# ---------------------------------------------------------------------
# Adversarial testing: >=15 fictional combinations designed to try to
# bypass the gate. None may produce an actionable positive recommendation
# when the canonical verified outcome-specific human count is zero.
# ---------------------------------------------------------------------

ADVERSARIAL_ROWS = [
    # 1: high AI human count via bottom GO path
    _go_row(Direct_Human_Outcome_Evidence_IDs=[f"a{i}" for i in range(20)]),
    # 2: high AI human count via bottom GO WITH CAUTION path
    _go_with_caution_row(Direct_Human_Outcome_Evidence_IDs=[f"a{i}" for i in range(20)]),
    # 3: legacy direct count field, bottom GO path
    _go_row(Direct_Indication_Evidence_Count=9),
    # 4: legacy direct count field, GO WITH CAUTION path
    _go_with_caution_row(Direct_Indication_Evidence_Count=9),
    # 5: strong mechanism count, GO path
    _go_row(Mechanistic_Evidence_Count=40),
    # 6: strong mechanism count, GO WITH CAUTION path
    _go_with_caution_row(Mechanistic_Evidence_Count=40),
    # 7: strong Human_Evidence_Strength label, GO path
    _go_row(Human_Evidence_Strength="STRONG"),
    # 8: strong Human_Evidence_Strength label, GO WITH CAUTION path
    _go_with_caution_row(Human_Evidence_Strength="STRONG"),
    # 9: Direct human/clinical mode via the escape-hatch combination
    _ai_ok_direct_human_row(),
    # 10: Direct human/clinical mode + positive adjudication + high AI count
    _ai_ok_direct_human_row(Direct_Human_Outcome_Evidence_IDs=[f"h{i}" for i in range(15)]),
    # 11: positive adjudication via AI_ADJUDICATION_FALLBACK bottom branch
    _go_with_caution_row(
        Evidence_Adjudication_Status="AI_ADJUDICATION_FALLBACK",
        Decision_Class_AH="C — Candidate requiring further evidence",
    ),
    # 12: related-indication style strong evidence-strength + AI count together
    _go_row(Human_Evidence_Strength="STRONG", Direct_Human_Outcome_Evidence_IDs=["r1", "r2"]),
    # 13: review/meta-analysis style adjudication count with zero verified human count
    _go_with_caution_row(Evidence_Adjudication_Evidence_Count=8),
    # 14: unverified candidate attribution flag alongside strong signals
    _go_row(Candidate_Attribution_Verified=False, Human_Evidence_Strength="STRONG"),
    # 15: everything stacked at once
    _ai_ok_direct_human_row(
        Human_Evidence_Strength="STRONG",
        Mechanistic_Evidence_Count=50,
        Direct_Human_Outcome_Evidence_IDs=[f"x{i}" for i in range(30)],
        Direct_Indication_Evidence_Count=10,
    ),
    # 16: bonus -- AI_ADJUDICATION_OK, non-"Direct human/clinical" mode,
    # weak human strength reaching GO WITH CAUTION via the human=="WEAK"
    # branch, which never inspects outcome_human_count at all.
    {
        "Decision_Class_AH": "C — Candidate requiring further evidence",
        "Relevance_Gate_Result": "passed_direct",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Mode": "AI-estimated indirect signal",
        "Direct_Outcome_Evidence_IDs": ["m1"],
        "Human_Evidence_Strength": "WEAK",
        "Indication_Evidence_Direction": "MOSTLY_POSITIVE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Outcome_Specific_Human_Evidence_Count": 0,
    },
]


@pytest.mark.parametrize("row", ADVERSARIAL_ROWS)
def test_adversarial_zero_count_never_produces_actionable_positive(row):
    status = _reconcile_final_decision_status(row)
    assert status not in {"GO", "GO WITH CAUTION"}, (
        f"Adversarial row bypassed the evidence-sufficiency gate: {row!r} -> {status!r}"
    )


def test_at_least_fifteen_adversarial_cases_defined():
    assert len(ADVERSARIAL_ROWS) >= 15


# ---------------------------------------------------------------------
# Direct unit coverage of the gate helper functions themselves.
# ---------------------------------------------------------------------

def test_verified_count_reader_is_fail_closed_and_non_negative():
    assert _verified_outcome_specific_human_evidence_count({}) == 0
    assert _verified_outcome_specific_human_evidence_count({"Outcome_Specific_Human_Evidence_Count": None}) == 0
    assert _verified_outcome_specific_human_evidence_count({"Outcome_Specific_Human_Evidence_Count": -3}) == 0
    assert _verified_outcome_specific_human_evidence_count({"Outcome_Specific_Human_Evidence_Count": "2"}) == 2
    assert _verified_outcome_specific_human_evidence_count({"Outcome_Specific_Human_Evidence_Count": 2.0}) == 2
    # Corrupted/ambiguous numeric transports must fail closed, never be
    # truncated into a positive verified-evidence count or crash reconciliation.
    assert _verified_outcome_specific_human_evidence_count({"Outcome_Specific_Human_Evidence_Count": 1.5}) == 0
    assert _verified_outcome_specific_human_evidence_count({"Outcome_Specific_Human_Evidence_Count": float("inf")}) == 0


def test_gate_triggered_only_for_actionable_positive_pre_gate_statuses():
    assert _evidence_sufficiency_gate_triggered("GO", {"Outcome_Specific_Human_Evidence_Count": 0}) is True
    assert _evidence_sufficiency_gate_triggered("GO WITH CAUTION", {"Outcome_Specific_Human_Evidence_Count": 0}) is True
    for status in ("NO GO SAFETY", "NO GO REGULATORY", "EXPERT REVIEW REQUIRED", "INSUFFICIENT EVIDENCE"):
        assert _evidence_sufficiency_gate_triggered(status, {"Outcome_Specific_Human_Evidence_Count": 0}) is False
    assert _evidence_sufficiency_gate_triggered("GO", {"Outcome_Specific_Human_Evidence_Count": 1}) is False
