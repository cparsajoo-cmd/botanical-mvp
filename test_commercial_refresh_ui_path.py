"""Issue 1 (2026-09-09 second follow-up): UI-path regression test for the
"Refresh Commercial Intelligence / Investor View" button.

refresh_commercial_and_investor_view() itself was already directly tested
(test_commercial_only_refresh_no_ai_calls.py). This file instead drives
the actual button-click handler (_handle_commercial_refresh_button_click(),
the real body wired to st.button(...) in render_rd_candidates_step()) with
st.session_state mocked as a plain dict, proving the real click path
updates the three session-state keys the rest of the app reads and still
makes zero scientific/AI calls.
"""

import unittest.mock as mock

import pandas as pd

import step_rd_candidates as src
from rd_discovery_classification import DISCOVERY_LANE_EVIDENCE_BACKED


def _existing_result_df():
    return pd.DataFrame([{"Alternative_Plant": "Withania somnifera", "Overall_Score": 82.0}])


def _existing_plant_summary_df():
    return pd.DataFrame([{
        "Alternative_Plant": "Withania somnifera",
        "Scientific_Triage_Status": "Shortlist",
        "Indication_Relevance_Score": 20.0,
        "Scientific_Evidence_Score": 15.0,
        "Compound_Quality_Score": 10.0,
        "Mechanism_Support_Score": 12.0,
        "Safety_Regulatory_Score": 15.0,
        "Novelty_Market_Score": 10.0,
        "Novelty_Market_Tier": "Commercial novelty not assessed",
        "Overall_Score": 82.0,
        "R&D_Opportunity_Score": 82.0,
        "Score_Breakdown": {},
        "Score_Breakdown_Display": "",
        "Dosage_Form_Compatibility": "Compatible / unspecified",
        "Safety_Regulatory_Tier": "No major safety/regulatory flags identified",
        "Outcome_Consistency": "Results not reported",
        "Distinctive_Compound_Count": 1,
        "Supported_Target_Count": 1,
        "Mechanistic_Evidence_Count": 3,
        "Discovery_Linked_Target_Count": 1,
        "Discovery_Linked_Compound_Count": 1,
        "Discovery_Compound_Specificity": 0.8,
        "Discovery_Potential_Score": 70.0,
        "RD_Discovery_Lane": DISCOVERY_LANE_EVIDENCE_BACKED,
        "Already_In_Internal_Catalogue": True,
        "Plant_Hard_Stop": False,
        "Regulatory_Prohibition_Present": False,
        "Direct_Indication_Evidence_Count": 3,
    }])


def test_button_click_handler_updates_all_three_session_state_keys():
    session_state = {}
    with mock.patch.object(src, "st") as mock_st:
        mock_st.session_state = session_state
        src._handle_commercial_refresh_button_click(
            _existing_result_df(),
            _existing_plant_summary_df(),
            indication="sleep",
            dosage_form="capsule",
            market="FR",
        )

    assert "rd_candidates_df" in session_state
    assert "rd_candidate_plant_summary_df" in session_state
    assert "rd_report_ready_df" in session_state
    assert isinstance(session_state["rd_report_ready_df"], pd.DataFrame)
    assert not session_state["rd_report_ready_df"].empty
    assert "rd_decision_metadata" in session_state


def test_button_click_handler_calls_zero_scientific_functions():
    session_state = {}
    with mock.patch.object(src, "st") as mock_st, \
         mock.patch.object(src, "build_plant_candidate_shortlist") as mock_shortlist:
        mock_st.session_state = session_state
        src._handle_commercial_refresh_button_click(
            _existing_result_df(),
            _existing_plant_summary_df(),
            indication="sleep",
            dosage_form="capsule",
            market="FR",
        )
    mock_shortlist.assert_not_called()


def test_button_click_handler_never_calls_ai_evidence_adjudication():
    session_state = {}
    with mock.patch.object(src, "st") as mock_st, \
         mock.patch("evidence_adjudication_engine.adjudicate_candidate") as mock_adjudicate:
        mock_st.session_state = session_state
        src._handle_commercial_refresh_button_click(
            _existing_result_df(),
            _existing_plant_summary_df(),
            indication="sleep",
            dosage_form="capsule",
            market="FR",
        )
    mock_adjudicate.assert_not_called()


def test_button_click_handler_uses_current_imported_commercial_evidence():
    """The handler must pick up whatever commercial_evidence_df is
    currently imported in session state (_get_commercial_evidence_df()),
    not silently ignore it.
    """
    commercial_evidence_df = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Product_Name": "SleepWell Capsules",
        "Brand": "BrandCo",
        "Retailer": "Herbal Marketplace",
        "Market_Source_Type": "Marketplace",
    }])
    session_state = {"commercial_evidence_df": commercial_evidence_df}
    with mock.patch.object(src, "st") as mock_st:
        mock_st.session_state = session_state
        _, _, report_ready_df = src._handle_commercial_refresh_button_click(
            _existing_result_df(),
            _existing_plant_summary_df(),
            indication="sleep",
            dosage_form="capsule",
            market="FR",
        )
    assert report_ready_df.loc[0, "Overall_Product_Hits"] >= 1
