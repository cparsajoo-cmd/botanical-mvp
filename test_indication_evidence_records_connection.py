"""Regression tests for persisted evidence_records -> indication discovery wiring."""

import pandas as pd

from indication_candidate_discovery import discover_indication_candidates


class _Engine:
    def __init__(self):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([
            {
                "id": 901,
                "plant": "Trigonella foenum-graecum",
                "target_indication": "Type 2 diabetes",
                "study_type": "Randomized human clinical trial",
                "primary_outcome": "Reduced HbA1c and fasting glucose",
                "result_direction": "beneficial",
                "evidence_level": "Human RCT",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/123456/",
                "pmid": "123456",
            }
        ])

    def _candidate_frame(self):
        return pd.DataFrame([
            {
                "Scientific_Name": "Trigonella foenum-graecum",
                "Known_Active_Compounds": "trigonelline",
                "Known_Targets": "AMPK",
            }
        ])

    def _pick(self, row, names):
        for name in names:
            if name in row and pd.notna(row[name]) and str(row[name]).strip():
                return str(row[name])
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        return "Clinical / human evidence" if "randomized" in text.lower() else "Unknown"


def test_persisted_evidence_records_are_used_for_indication_discovery():
    out = discover_indication_candidates(_Engine(), "Type 2 diabetes")
    assert len(out) == 1
    row = out.iloc[0]
    assert row["Alternative_Plant"] == "Trigonella foenum-graecum"
    assert row["Candidate_Evidence_Strength_Tier"] == "Direct human evidence"
    assert row["Evidence_Source"] == "https://pubmed.ncbi.nlm.nih.gov/123456/"
    assert row["Source_Record_IDs"] == "901"
    assert row["R&D_Opportunity_Score"] > 17


def test_source_urls_and_evidence_record_ids_are_not_mixed():
    row = discover_indication_candidates(_Engine(), "Type 2 diabetes").iloc[0]
    assert "pubmed.ncbi.nlm.nih.gov" in row["Evidence_Source"]
    assert "pubmed.ncbi.nlm.nih.gov" not in row["Source_Record_IDs"]
    assert row["Source_Record_IDs"] == "901"
