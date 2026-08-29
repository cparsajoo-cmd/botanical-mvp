import pandas as pd
import step_rd_candidates as s


def _base(**kw):
    d = {
        "Final_Decision_Status": "GO WITH CAUTION",
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "NONE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "LOW",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Direct_Indication_Evidence_Count": 5,
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Outcome_Specific_Direct_Evidence_Count": 0,
        "Evidence_Adjudication_Evidence_Count": 25,
        "Safety_Flags": "",
    }
    d.update(kw)
    return d


def test_unverified_outcome_context_does_not_erase_multi_record_positive_direct_body():
    assert s._reconcile_final_decision_status(_base()) == "GO WITH CAUTION"


def test_single_direct_record_with_no_human_outcome_context_stays_expert_review():
    assert s._reconcile_final_decision_status(_base(Direct_Indication_Evidence_Count=1)) == "EXPERT REVIEW REQUIRED"


def test_post_insight_insufficient_weak_low_downgrades_actionable_candidate():
    df = pd.DataFrame([_base(
        Human_Evidence_Strength="WEAK",
        AI_Insight_Status="AI_REVIEW_AVAILABLE",
        AI_Evidence_Consistency="insufficient_evidence",
    )])
    out = s._reconcile_after_ai_insights(df)
    assert out.iloc[0]["Final_Decision_Status"] == "EXPERT REVIEW REQUIRED"


def test_post_insight_mixed_does_not_invent_a_downgrade():
    df = pd.DataFrame([_base(
        Human_Evidence_Strength="WEAK",
        AI_Insight_Status="AI_REVIEW_AVAILABLE",
        AI_Evidence_Consistency="mixed",
    )])
    out = s._reconcile_after_ai_insights(df)
    assert out.iloc[0]["Final_Decision_Status"] == "GO WITH CAUTION"


def test_post_insight_never_weakens_hard_no_go():
    df = pd.DataFrame([_base(
        Final_Decision_Status="NO GO SAFETY",
        AI_Insight_Status="AI_REVIEW_AVAILABLE",
        AI_Evidence_Consistency="insufficient_evidence",
    )])
    out = s._reconcile_after_ai_insights(df)
    assert out.iloc[0]["Final_Decision_Status"] == "NO GO SAFETY"
