import copy
import pandas as pd

from decision_explainability import (
    build_candidate_explanation,
    build_human_summary,
    decision_diff,
    attach_decision_explanations,
)


def _row(**overrides):
    row = {
        "Alternative_Plant": "Plantus testus",
        "Overall_Score": 81.0,
        "R&D_Opportunity_Score": 81.0,
        "Score_Breakdown": {
            "Indication Relevance": 30.0,
            "Scientific Evidence": 24.0,
            "Compound Support": 4.0,
            "Mechanism Support": 8.0,
            "Safety & Regulatory": 12.0,
            "Novelty & Market": 3.0,
        },
        "Component_Source_Record_IDs": {
            "Indication Relevance": ["E1"],
            "Scientific Evidence": ["E1", "E2"],
            "Compound Support": ["E3"],
            "Mechanism Support": ["E3"],
            "Safety & Regulatory": ["E4"],
            "Novelty & Market": [],
        },
        "Scientific_Evidence_Contributions": [
            {"evidence_id": "E1", "marginal_score_effect": 3.2},
            {"evidence_id": "E2", "marginal_score_effect": -1.1},
        ],
        "Scientific_Triage_Status": "Shortlist",
        "Go_Investigate_Hold_NoGo": "Go",
        "Scoring_Model_Version": "authoritative-plant-v1.2",
        "Safety_Data_Status": "assessed",
        "Gate_Results": {
            "safety": {"status": "PASSED", "reason": "no hard stop", "evidence": "E4"}
        },
    }
    row.update(overrides)
    return row


def _audit():
    return [
        {"Alternative_Plant": "Plantus testus", "Source_Record_IDs": "E1", "Scientific_Triage_Status": "Shortlist", "Dosage_Form_Compatibility": "Compatible"},
        {"Alternative_Plant": "Plantus testus", "Source_Record_IDs": "E2", "Scientific_Triage_Status": "Shortlist", "Dosage_Form_Compatibility": "Compatible"},
        {"Alternative_Plant": "Plantus testus", "Source_Record_IDs": "E3", "Scientific_Triage_Status": "Shortlist", "Dosage_Form_Compatibility": "Compatible"},
        {"Alternative_Plant": "Plantus testus", "Source_Record_IDs": "E4", "Scientific_Triage_Status": "Shortlist", "Dosage_Form_Compatibility": "Compatible"},
        {"Alternative_Plant": "Plantus testus", "Source_Record_IDs": "E5", "Scientific_Triage_Status": "Excluded", "Scientific_Triage_Reasons": "preparation mismatch", "Dosage_Form_Compatibility": "Mismatch"},
        {"Alternative_Plant": "Plantus testus", "Source_Record_IDs": "E6", "Scientific_Triage_Status": "Excluded", "Scientific_Triage_Reasons": "no candidate-specific evidence was found for requested indication", "Dosage_Form_Compatibility": "Compatible"},
    ]


def test_score_breakdown_reconciles_exactly():
    ex = build_candidate_explanation(_row(), _audit())
    assert ex["score_reconciliation"] == {"component_sum": 81.0, "final_score": 81.0, "exact": True}


def test_each_used_evidence_has_id_and_scientific_effect_is_real_marginal():
    ex = build_candidate_explanation(_row(), _audit())
    used = [e for e in ex["evidence_contributions"] if e["entered_score"]]
    assert used and all(e["evidence_id"] for e in used)
    e1 = next(e for e in used if e["evidence_id"] == "E1")
    assert e1["score_points"] == 3.2
    assert e1["score_effect_method"] == "leave_one_evidence_out"


def test_wrong_preparation_and_wrong_indication_are_structured_exclusions():
    ex = build_candidate_explanation(_row(), _audit())
    reasons = {e["evidence_id"]: e["excluded_reason"] for e in ex["evidence_contributions"]}
    assert reasons["E5"] == "Wrong preparation"
    assert reasons["E6"] == "Wrong indication"


def test_gate_is_traceable_to_evidence():
    ex = build_candidate_explanation(_row(), _audit())
    safety = next(g for g in ex["applied_gates"] if g["gate"] == "safety")
    assert safety["evidence_ids"] == ["E4"]


def test_override_has_reason_and_rule_attribution_is_recorded():
    ex = build_candidate_explanation(_row(Scientific_Triage_Status="Excluded", Why_Selected_or_Rejected="hard stop"), _audit())
    assert any(r["rule_id"] == "triage.exclusion" for r in ex["rules_applied"])
    assert any(o.get("reason") for o in ex["overrides"])


def test_missing_data_states_are_not_collapsed():
    ex = build_candidate_explanation(_row(Safety_Data_Status="not_assessed", Regulatory_Barriers="Search not performed", Source_Failure="EMA unavailable"), _audit())
    states = {x["state"] for x in ex["missing_data"]}
    assert {"No Evidence", "Search Not Performed", "Source Unavailable"} <= states
    assert ex["source_failures"]


def test_repeated_build_is_reproducible_when_timestamp_is_fixed():
    meta = {"decision_timestamp": "2026-08-06T20:00:00+00:00", "evidence_snapshot_id": "snap"}
    a = build_candidate_explanation(_row(), _audit(), generated_time=meta["decision_timestamp"], decision_metadata=meta)
    b = build_candidate_explanation(_row(), _audit(), generated_time=meta["decision_timestamp"], decision_metadata=meta)
    assert a == b


def test_decision_diff_reports_score_evidence_rule_gate_and_decision_changes():
    old = build_candidate_explanation(_row(), _audit(), generated_time="T")
    new_row = _row(Overall_Score=79.0, **{"R&D_Opportunity_Score": 79.0, "Go_Investigate_Hold_NoGo": "Investigate"})
    new_row["Score_Breakdown"] = dict(new_row["Score_Breakdown"])
    new_row["Score_Breakdown"]["Novelty & Market"] = 1.0
    new_row["Component_Source_Record_IDs"] = copy.deepcopy(new_row["Component_Source_Record_IDs"])
    new_row["Component_Source_Record_IDs"]["Novelty & Market"] = ["E7"]
    new = build_candidate_explanation(new_row, _audit() + [{"Source_Record_IDs": "E7", "Alternative_Plant": "Plantus testus"}], generated_time="T")
    d = decision_diff(old, new)
    assert d["score_changed"] and d["score_delta"] == -2.0
    assert d["evidence_added"] == ["E7"]
    assert d["decision_changed"]
    assert "Novelty & Market" in d["component_changes"]


def test_human_summary_contains_only_structurally_triggered_statements():
    ex = build_candidate_explanation(_row(), _audit())
    summary = build_human_summary(ex)
    assert "Final score is 81.0" in summary
    assert "EMA" not in summary
    assert "RCT" not in summary


def test_attach_adds_one_structured_explanation_per_candidate_without_changing_score():
    df = pd.DataFrame([_row()])
    audit = pd.DataFrame(_audit())
    out = attach_decision_explanations(df, audit, decision_metadata={"decision_timestamp": "T"})
    assert out.loc[0, "Overall_Score"] == 81.0
    assert out.loc[0, "Decision_Explanation"]["candidate_id"] == "Plantus testus"
