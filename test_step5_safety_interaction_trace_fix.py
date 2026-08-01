import pandas as pd

from evidence_extractor import extract_evidence_from_text
from indication_candidate_discovery import (
    _extract_explicit_safety_and_interactions,
    discover_indication_candidates,
)


def test_strict_source_text_fallback_extracts_explicit_safety_and_interaction_only():
    text = (
        "The extract improved fasting glucose. Mild gastrointestinal adverse events were reported. "
        "Concomitant use with antidiabetic medication may increase hypoglycemia risk."
    )
    safety, interactions = _extract_explicit_safety_and_interactions(text)
    assert "gastrointestinal adverse events" in safety
    assert "antidiabetic medication" in interactions


def test_strict_source_text_fallback_does_not_invent_missing_safety():
    safety, interactions = _extract_explicit_safety_and_interactions(
        "The extract improved fasting glucose in a randomized trial."
    )
    assert safety == ""
    assert interactions == ""


def test_future_ingestion_preserves_explicit_source_safety_and_interactions():
    out = extract_evidence_from_text(
        "Trigonella foenum-graecum was studied in diabetes. Mild gastrointestinal adverse events occurred. "
        "Interaction with antidiabetic medication was cautioned."
    )
    assert out["Adverse_Events"]
    assert out["Interactions_Structured"]


class _Engine:
    def __init__(self):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([{
            "Scientific_Name": "Trigonella foenum-graecum",
            "Source_URL": "https://example.test/trial",
            "Evidence_Record_ID": 77,
            "Study_Type": "Randomized Controlled Trial",
            "Study_Model": "Human",
            "Evidence_Level": "High",
            "Target_Indication": "type 2 diabetes",
            "Primary_Outcome": "fasting glucose",
            "Result_Direction": "positive benefit",
            "Source_Raw_Text": (
                "Trigonella foenum-graecum improved fasting glucose in type 2 diabetes. "
                "Mild gastrointestinal adverse events were reported. "
                "Concomitant use with antidiabetic medication may increase hypoglycemia risk."
            ),
        }])

    def _candidate_frame(self):
        return pd.DataFrame([{
            "Scientific_Name": "Trigonella foenum-graecum",
            "Known_Active_Compounds": "4-hydroxyisoleucine",
            "Known_Targets": "glucose metabolism",
            "Indications_Text": "type 2 diabetes",
        }])

    def _pick(self, row, names):
        for name in names:
            if name in row and pd.notna(row[name]):
                return str(row[name])
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        return "High"


def test_step5_uses_saved_source_raw_text_when_structured_safety_fields_are_empty():
    out = discover_indication_candidates(
        _Engine(), "type 2 diabetes", dosage_form="oral"
    )
    assert not out.empty
    row = out.iloc[0]
    assert "gastrointestinal adverse events" in row["Safety_Flags"]
    assert "antidiabetic medication" in row["Interaction_Flags"]
    assert row["Source_Record_IDs"] == "77"
