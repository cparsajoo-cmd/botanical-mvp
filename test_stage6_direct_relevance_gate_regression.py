import pandas as pd
from candidate_shortlisting import merge_authoritative_scores


def test_report_ready_preserves_stage6_relevance_gate_fields():
    raw = pd.DataFrame([{
        "Alternative_Plant": "Example plant",
        "R&D_Opportunity_Score": 70.0,
        "Target_or_Mechanism": "generic mechanism",
    }])
    summary = pd.DataFrame([{
        "Alternative_Plant": "Example plant",
        "Overall_Score": 70.0,
        "Scientific_Triage_Status": "Exploratory",
        "Why_Selected_or_Rejected": "mechanistic only",
        "Indication_Relevance": "Low relevance",
        "Indication_Relevance_Score": 8.0,
        "Indication_Evidence_Mode": "Mechanistic empirical",
        "Indication_Supporting_Source_Count": 2,
        "Relevance_Gate_Result": "passed_indirect_exploratory_only",
        "Evidence_Route": "mechanistic_only",
        "Direct_Indication_Evidence_Count": 0,
        "Mechanistic_Evidence_Count": 4,
        "Preparation_Specific_Evidence_Count": 0,
        "Preparation_Applicability_Class": "not_reported",
        "Triage_Gate_Reasons": "direct evidence required",
        "Supported_Targets_or_Mechanisms": "GABA; stress response",
    }])
    merged = merge_authoritative_scores(raw, summary)
    row = merged.iloc[0]
    assert row["Relevance_Gate_Result"] == "passed_indirect_exploratory_only"
    assert row["Direct_Indication_Evidence_Count"] == 0
    assert row["Evidence_Route"] == "mechanistic_only"
    assert row["Supported_Targets_or_Mechanisms"] == "GABA; stress response"
