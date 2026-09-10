"""Real Stage-6 render-path test (spec §33): the source-traceability columns
built by evidence_source_resolver / commercial_source_traceability /
claim_source_map / source_linkage_consistency must actually reach the
st.dataframe() call inside _recommendation_block(), not just exist as
standalone helper functions nobody wires in.
"""
import unittest.mock as mock

import pandas as pd

import step_rd_candidates as src


def _report_ready_row(plant, call, score, **extra):
    is_eligible = str(call).strip().startswith(("Go", "Investigate"))
    row = {
        "Alternative_Plant": plant,
        "R&D_Opportunity_Score": score,
        "Overall_Score": score,
        "Go_Investigate_Hold_NoGo": call,
        "Decision_Class_AH": (
            "B — Established scientific candidate" if is_eligible
            else "G — Hold / insufficient evidence"
        ),
        "Target_or_Mechanism": "AMPK",
        "Rationale": f"narrative for {plant}",
        "Eligibility_Status": "eligible" if is_eligible else "incomplete",
        "Eligible_For_Normal_Ranking": is_eligible,
    }
    row.update(extra)
    return row


def _evidence_df():
    return pd.DataFrame([
        {
            "Evidence_Record_ID": "E1",
            "Source_Title": "Randomized clinical trial of botanical X",
            "Source_Type": "PubMed",
            "Source_Year": 2024,
            "Source_URL": "https://example.org/article/E1",
            "Study_Type": "Randomized controlled trial",
            "Population": "human",
        },
        {
            "Evidence_Record_ID": "S1",
            "Source_Title": "Case report: interaction",
            "Source_URL": "https://example.org/article/S1",
        },
    ])


def test_source_traceability_columns_reach_the_rendered_dataframe():
    report_ready_df = pd.DataFrame([
        _report_ready_row(
            "Strong plant", "Go", 90.0,
            Direct_Human_Outcome_Evidence_IDs=["E1"],
            Safety_Evidence_IDs=["S1"],
            Safety_Concern_Level="LOW",
        ),
    ])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df, _evidence_df())

    dataframe_calls = [c.args[0] for c in mock_st.dataframe.call_args_list]
    assert dataframe_calls, "expected st.dataframe to be called"
    recommended_frame = dataframe_calls[0]

    for column in (
        "Human_Evidence_Primary_Source_URL",
        "Safety_Source_Count",
        "Safety_Primary_Source_URL",
        "Commercial_Source_Count",
        "Regulatory_Source_Count",
        "Patent_Source_Count",
        "Claim_Source_Map",
        "Derived_Claim_Provenance",
        "Evidence_Source_Linkage_Status",
    ):
        assert column in recommended_frame.columns, f"missing {column} in rendered frame"

    row = recommended_frame.iloc[0]
    assert row["Safety_Source_Count"] == 1
    assert row["Human_Evidence_Primary_Source_URL"] == "https://example.org/article/E1"


def test_link_column_config_passed_for_all_categories():
    report_ready_df = pd.DataFrame([_report_ready_row("Strong plant", "Go", 90.0)])
    with mock.patch.object(src, "st") as mock_st:
        src._recommendation_block(pd.DataFrame(), report_ready_df, _evidence_df())

    dataframe_calls = mock_st.dataframe.call_args_list
    assert dataframe_calls
    config = dataframe_calls[0].kwargs.get("column_config")
    assert config is not None
    for key in (
        "Human_Evidence_Primary_Source_URL",
        "Safety_Primary_Source_URL",
        "Commercial_Primary_Source_URL",
        "Regulatory_Primary_Source_URL",
        "Patent_Primary_Source_URL",
    ):
        assert key in config
