import pandas as pd
import evidence_adjudication_engine as eae


def test_adjudication_prefers_stage5_canonical_human_context():
    df = pd.DataFrame([{
        "Alternative_Plant": "Example plant",
        "Source_Record_IDs": "E1",
        "Indication_Match_Type": "exact_indication",
        "Primary_Outcome": "sleep quality",
        "Evidence_Level": "ambiguous evidence label",
        "Evidence_Hierarchy_Detail": "",
        "Canonical_Study_Context": "HUMAN",
        "Outcome_Specific_Direct_Evidence": True,
    }])
    items = eae.build_adjudication_evidence_items(df, "Example plant", "sleep")
    assert len(items) == 1
    assert items[0]["human_animal_in_vitro"] == "HUMAN"
    assert items[0]["outcome_specific"] is True


def test_adjudication_prefers_stage5_canonical_nonhuman_context():
    df = pd.DataFrame([{
        "Alternative_Plant": "Example plant",
        "Source_Record_IDs": "E2",
        "Indication_Match_Type": "exact_indication",
        "Primary_Outcome": "sleep latency",
        "Evidence_Level": "clinical-looking words",
        "Evidence_Hierarchy_Detail": "clinical trial",
        "Canonical_Study_Context": "ANIMAL_OR_IN_VITRO",
        "Outcome_Specific_Direct_Evidence": True,
    }])
    items = eae.build_adjudication_evidence_items(df, "Example plant", "sleep")
    assert len(items) == 1
    assert items[0]["human_animal_in_vitro"] == "ANIMAL_OR_IN_VITRO"
