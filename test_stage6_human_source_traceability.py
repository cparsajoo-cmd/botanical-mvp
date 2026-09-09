import unittest.mock as mock

import pandas as pd

import step_rd_candidates as src
from rd_discovery_classification import (
    DISCOVERY_LANE_EVIDENCE_BACKED,
    DISCOVERY_LANE_HYPOTHESIS,
)


def _evidence_df():
    return pd.DataFrame([{
        "Evidence_Record_ID": "E1",
        "Source_Title": "Randomized clinical trial",
        "Source_URL": "https://example.org/e1",
        "PMID": "12345678",
        "Study_Type": "Randomized controlled trial",
        "Population": "human",
        "Primary_Outcome": "target outcome",
    }])


def _row(name, *, final_status, call, lane):
    return {
        "Alternative_Plant": name,
        "R&D_Opportunity_Score": 80.0,
        "Overall_Score": 80.0,
        "Go_Investigate_Hold_NoGo": call,
        "Eligible_For_Normal_Ranking": True,
        "Eligibility_Status": "eligible",
        "Final_Decision_Status": final_status,
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "RD_Discovery_Lane": lane,
        "Discovery_Potential_Score": 75.0,
        "Evidence_Maturity_Score": 60.0,
        "Already_In_Internal_Catalogue": True,
        "Discovery_Linked_Target_Count": 1,
        "Discovery_Linked_Compound_Count": 1,
        "Direct_Indication_Evidence_Count": 1,
        "Outcome_Specific_Human_Evidence_Count": 1,
        "AI_Direct_Human_Outcome_Evidence_Count": 1,
        "Direct_Human_Outcome_Evidence_IDs": "E1",
        "Human_Evidence_Strength": "MODERATE",
        "Safety_Concern_Level": "NONE",
        "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED",
        "Commercial_Status_Overall": "UNKNOWN",
        "Commercial_Status_For_Indication": "UNKNOWN",
    }


def _rendered_frames(mock_st):
    return [call.args[0] for call in mock_st.dataframe.call_args_list if call.args and isinstance(call.args[0], pd.DataFrame)]


def test_priority_table_contains_clickable_primary_human_source():
    df = pd.DataFrame([_row(
        "Priority plant", final_status="GO", call="Go", lane=DISCOVERY_LANE_EVIDENCE_BACKED
    )])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), df, evidence_df=_evidence_df())
    frames = _rendered_frames(mock_st)
    assert any(
        "Human_Evidence_Primary_Source_URL" in frame.columns
        and "https://example.org/e1" in frame["Human_Evidence_Primary_Source_URL"].astype(str).tolist()
        for frame in frames
    )
    assert mock_st.column_config.LinkColumn.called


def test_expert_review_table_contains_clickable_primary_human_source():
    df = pd.DataFrame([_row(
        "Review plant", final_status="EXPERT REVIEW REQUIRED", call="Investigate", lane=DISCOVERY_LANE_EVIDENCE_BACKED
    )])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), df, evidence_df=_evidence_df())
    frames = _rendered_frames(mock_st)
    assert any(
        "Stage_6_Section" in frame.columns
        and frame["Stage_6_Section"].astype(str).str.contains("expert review", case=False).any()
        and "Human_Evidence_Primary_Source_URL" in frame.columns
        for frame in frames
    )


def test_discovery_investor_table_contains_human_source_fields():
    row = _row(
        "Discovery plant", final_status="EXPERT REVIEW REQUIRED", call="Investigate", lane=DISCOVERY_LANE_HYPOTHESIS
    )
    row["Direct_Indication_Evidence_Count"] = 0
    row["Relevance_Gate_Result"] = "passed_indirect_exploratory_only"
    df = pd.DataFrame([row])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), df, evidence_df=_evidence_df())
    frames = _rendered_frames(mock_st)
    assert any(
        "Candidate" in frame.columns
        and "Human_Evidence_Primary_Source_URL" in frame.columns
        and "Human_Evidence_Source_Count" in frame.columns
        for frame in frames
    )


def test_missing_source_url_does_not_break_stage6_table():
    evidence_df = pd.DataFrame([{
        "Evidence_Record_ID": "E1",
        "Source_Title": "Internal record",
        "Source_URL": "",
        "PMID": "",
        "DOI": "",
        "Study_Type": "Human study",
        "Population": "human",
    }])
    df = pd.DataFrame([_row(
        "Internal-source plant", final_status="GO", call="Go", lane=DISCOVERY_LANE_EVIDENCE_BACKED
    )])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), df, evidence_df=evidence_df)
    frames = _rendered_frames(mock_st)
    assert frames
    assert any("Human_Evidence_Source_Count" in frame.columns for frame in frames)
