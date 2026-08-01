import sys
from unittest.mock import MagicMock

import pandas as pd

_streamlit = MagicMock()
_streamlit.cache_data.side_effect = lambda *args, **kwargs: (lambda fn: fn)
_streamlit.cache_resource.side_effect = lambda *args, **kwargs: (lambda fn: fn)
sys.modules.setdefault("streamlit", _streamlit)
_supabase = MagicMock()
_supabase.create_client = MagicMock()
sys.modules.setdefault("supabase", _supabase)

import step_rd_candidates as src


def test_main_triage_display_uses_authoritative_score_not_legacy_score():
    df = pd.DataFrame([
        {
            "Alternative_Plant": "Plant A",
            "Scientific_Triage_Score": 92.5,
            "Overall_Score": 81.2,
            "R&D_Opportunity_Score": 81.2,
            "Evidence_Confidence": 74.0,
            "Scientific_Triage_Status": "Shortlist",
            "Go_Investigate_Hold_NoGo": "Go",
            "Indication_Relevance": "High relevance",
            "Evidence_Quality_Score": 26.0,
            "Why_Selected_or_Rejected": "Selected because evidence is strong.",
        },
        {
            "Alternative_Plant": "Plant B",
            "Scientific_Triage_Score": 99.0,
            "Overall_Score": 88.7,
            "R&D_Opportunity_Score": 88.7,
            "Evidence_Confidence": 82.0,
            "Scientific_Triage_Status": "Shortlist",
            "Go_Investigate_Hold_NoGo": "Investigate",
            "Indication_Relevance": "High relevance",
            "Evidence_Quality_Score": 29.0,
            "Why_Selected_or_Rejected": "Selected because evidence is stronger.",
        },
    ])

    shown = src._prepare_plant_triage_display(df)

    assert "Scientific_Triage_Score" not in shown.columns
    assert "Overall_Score" not in shown.columns
    assert "R&D_Opportunity_Score" not in shown.columns
    assert "R&D Opportunity Score" in shown.columns
    assert list(shown["Plant"]) == ["Plant B", "Plant A"]
    assert list(shown["R&D Opportunity Score"]) == [88.7, 81.2]


def test_display_falls_back_to_overall_score_when_alias_is_absent():
    df = pd.DataFrame([{
        "Alternative_Plant": "Plant A",
        "Scientific_Triage_Score": 92.5,
        "Overall_Score": 83.4,
        "Scientific_Triage_Status": "Exploratory",
    }])

    shown = src._prepare_plant_triage_display(df)

    assert shown.loc[0, "R&D Opportunity Score"] == 83.4
    assert "Scientific_Triage_Score" not in shown.columns
