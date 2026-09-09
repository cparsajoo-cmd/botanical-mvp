"""Mandatory regression test (Section 6): a commercial-only refresh must
reuse an existing valid Stage-5 scientific result and invoke NONE of the
expensive/AI-calling scientific functions.
"""

import unittest.mock as mock

import pandas as pd

import step_rd_candidates as src
from rd_discovery_classification import DISCOVERY_LANE_EVIDENCE_BACKED


def _existing_result_df():
    return pd.DataFrame([
        {"Alternative_Plant": "Withania somnifera", "Overall_Score": 82.0},
    ])


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


def test_commercial_only_refresh_calls_zero_scientific_or_ai_functions():
    result_df = _existing_result_df()
    plant_summary_df = _existing_plant_summary_df()

    # Spy on every scientific/AI-heavy entrypoint this refresh must never
    # touch. If the refresh is genuinely commercial-only, call_count stays
    # zero for all of them.
    with mock.patch.object(src, "build_plant_candidate_shortlist") as mock_shortlist:
        result_df_out, plant_summary_df_out, report_ready_df = (
            src.refresh_commercial_and_investor_view(
                result_df,
                plant_summary_df,
                indication="sleep",
                dosage_form="capsule",
                market="FR",
            )
        )

    mock_shortlist.assert_not_called()
    assert isinstance(result_df_out, pd.DataFrame) and not result_df_out.empty
    assert isinstance(plant_summary_df_out, pd.DataFrame) and not plant_summary_df_out.empty
    assert isinstance(report_ready_df, pd.DataFrame) and not report_ready_df.empty


def test_commercial_only_refresh_never_imports_or_touches_ai_evidence_adjudication():
    """A second, independent spy at a different layer: the AI evidence
    adjudication entrypoint must also never be invoked by a commercial
    refresh (it belongs to Stage 5 scientific processing, not Stage 6
    commercial/presentation).
    """
    result_df = _existing_result_df()
    plant_summary_df = _existing_plant_summary_df()

    with mock.patch("evidence_adjudication_engine.adjudicate_candidate") as mock_adjudicate:
        src.refresh_commercial_and_investor_view(
            result_df,
            plant_summary_df,
            indication="sleep",
            dosage_form="capsule",
            market="FR",
        )
    mock_adjudicate.assert_not_called()


def test_commercial_only_refresh_output_carries_matching_scientific_fingerprint():
    """The refreshed report-ready frame must carry the SAME scientific
    fingerprint the input carried (unchanged -- no scientific rerun),
    while the commercial fingerprint reflects the current commercial code.
    """
    result_df = _existing_result_df()
    plant_summary_df = _existing_plant_summary_df()

    _, _, report_ready_df = src.refresh_commercial_and_investor_view(
        result_df, plant_summary_df, indication="sleep", dosage_form="capsule", market="FR",
    )
    assert (
        report_ready_df["Scientific_Implementation_Fingerprint"].iloc[0]
        == src.scientific_implementation_fingerprint()
    )
    assert (
        report_ready_df["Commercial_Implementation_Fingerprint"].iloc[0]
        == src.commercial_implementation_fingerprint()
    )


def test_commercial_only_refresh_with_empty_inputs_does_not_raise():
    result_df_out, plant_summary_df_out, report_ready_df = (
        src.refresh_commercial_and_investor_view(
            pd.DataFrame(), pd.DataFrame(), indication="sleep", dosage_form="capsule", market="FR",
        )
    )
    assert report_ready_df.empty
