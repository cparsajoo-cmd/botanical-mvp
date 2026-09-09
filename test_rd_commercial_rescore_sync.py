import pandas as pd

from candidate_shortlisting import rescore_commercial_component


def test_commercial_rescore_refreshes_rd_discovery_lane_and_score():
    summary = pd.DataFrame([{
        "Alternative_Plant": "Catalogue plant",
        "Scientific_Triage_Status": "Exploratory",
        "Indication_Relevance_Score": 12.0,
        "Scientific_Evidence_Score": 0.0,
        "Compound_Quality_Score": 1.0,
        "Mechanism_Support_Score": 8.0,
        "Safety_Regulatory_Score": 10.0,
        "Novelty_Market_Score": 2.5,
        "Novelty_Market_Tier": "Commercial novelty not assessed",
        "Overall_Score": 31.0,
        "R&D_Opportunity_Score": 31.0,
        "Score_Breakdown": {},
        "Score_Breakdown_Display": "",
        "Dosage_Form_Compatibility": "Compatible / unspecified",
        "Safety_Regulatory_Tier": "No major safety/regulatory flags identified",
        "Outcome_Consistency": "Results not reported",
        "Distinctive_Compound_Count": 0,
        "Supported_Target_Count": 1,
        "Mechanistic_Evidence_Count": 2,
        "Discovery_Linked_Target_Count": 1,
        "Discovery_Linked_Compound_Count": 1,
        "Discovery_Compound_Specificity": 0.8,
        "Discovery_Potential_Score": 55.0,
        "RD_Discovery_Lane": "Catalogue R&D Hypothesis — Market Novelty Unassessed",
        "Already_In_Internal_Catalogue": True,
        "Plant_Hard_Stop": False,
        "Regulatory_Prohibition_Present": False,
        "Direct_Indication_Evidence_Count": 0,
    }])
    enriched_raw = pd.DataFrame([{
        "Alternative_Plant": "Catalogue plant",
        "Commercial_Novelty_Status": "Established commercial use",
    }])

    out = rescore_commercial_component(summary, enriched_raw, ["Catalogue plant"])
    row = out.iloc[0]
    assert row["Novelty_Market_Tier"] == "Established / commercially active"
    assert row["RD_Discovery_Lane"] == "Established Plant — Evidence Gap for This Indication"
    assert row["Discovery_Potential_Score"] != 55.0
