import pandas as pd

from indication_candidate_discovery import (
    SCORING_CONFIG_VERSION,
    discover_indication_candidates,
)


class FakeEngine:
    evidence_df = pd.DataFrame([
        {
            "Scientific_Name": "Plant A",
            "Title": "Plant A improved HbA1c in a randomized human trial",
            "Source_URL": "https://example/a",
        },
        {
            "Scientific_Name": "Plant B",
            "Title": "General antioxidant chemistry",
            "Source_URL": "https://example/b",
        },
        {
            "Scientific_Name": "Unrelated",
            "Title": "Type 2 diabetes and blood glucose review",
            "Source_URL": "https://example/general",
        },
    ])
    evidence_records_df = pd.DataFrame()
    scientific_evidence_df = pd.DataFrame()

    def _candidate_frame(self):
        return pd.DataFrame([
            {"Scientific_Name": "Plant A", "Known_Active_Compounds": "x"},
            {"Scientific_Name": "Plant B", "Known_Active_Compounds": "x"},
        ])

    def _pick(self, row, names):
        for name in names:
            if name in row and pd.notna(row[name]):
                return str(row[name])
        return ""

    def _split_compound_terms(self, value):
        return [item.strip() for item in str(value).split(";") if item.strip()]

    def _evidence_level(self, text):
        return "Clinical trial" if "randomized" in text.lower() else "Unknown"


def test_general_indication_record_does_not_leak_to_other_plants():
    out = discover_indication_candidates(FakeEngine(), "type 2 diabetes")

    assert set(out["Alternative_Plant"]) == {"Plant A"}
    row = out.iloc[0]

    assert "example/a" in row["Evidence_Source"]
    assert "example/general" not in row["Evidence_Source"]
    assert "example/a" not in row["Source_Record_IDs"]
    assert row["Scoring_Config_Version"] == SCORING_CONFIG_VERSION
