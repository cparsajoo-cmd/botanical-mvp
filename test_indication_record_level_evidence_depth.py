"""Regression tests for record-level evidence depth in indication discovery.

These tests lock the fix for the plant-wide evidence collapse that made many
botanicals receive identical Evidence_Quality_Score values.
"""

import pandas as pd

from indication_candidate_discovery import discover_indication_candidates
from candidate_shortlisting import build_plant_candidate_shortlist


class _Engine:
    def __init__(self, records):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame(records)

    def _candidate_frame(self):
        plants = sorted(set(self.evidence_records_df["plant"]))
        return pd.DataFrame([
            {
                "Scientific_Name": plant,
                "Known_Active_Compounds": "specific alkaloid",
                "Known_Targets": "blood glucose; AMPK",
            }
            for plant in plants
        ])

    def _pick(self, row, names):
        for name in names:
            if name in row and pd.notna(row[name]) and str(row[name]).strip():
                return str(row[name])
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        low = text.lower()
        if "systematic review" in low or "meta-analysis" in low:
            return "Systematic review / meta-analysis"
        if "randomized" in low:
            return "Randomized clinical trial"
        if "animal" in low:
            return "Animal / in vivo evidence"
        if "in vitro" in low:
            return "In vitro evidence"
        return "Unknown"


def _record(record_id, plant, study_type, source, *, result="beneficial", nct_id=""):
    return {
        "id": record_id,
        "plant": plant,
        "target_indication": "Type 2 diabetes",
        "study_type": study_type,
        "primary_outcome": "HbA1c and fasting blood glucose",
        "result_direction": result,
        "evidence_level": study_type,
        "source_url": source,
        "nct_id": nct_id,
    }


def test_discovery_emits_one_row_per_independent_evidence_record():
    records = [
        _record(1, "Trigonella foenum-graecum", "Systematic review and meta-analysis", "https://doi.org/a"),
        _record(2, "Trigonella foenum-graecum", "Randomized human clinical trial", "https://pubmed.ncbi.nlm.nih.gov/2"),
        _record(3, "Trigonella foenum-graecum", "Animal in vivo study", "https://pubmed.ncbi.nlm.nih.gov/3"),
    ]
    out = discover_indication_candidates(_Engine(records), "Type 2 diabetes")

    assert len(out) == 3
    assert set(out["Source_Record_IDs"].astype(str)) == {"1", "2", "3"}
    assert out["Evidence_Source"].nunique() == 3
    assert set(out["Evidence_Level"]) >= {
        "Systematic review and meta-analysis",
        "Randomized human clinical trial",
        "Animal in vivo study",
    }


def test_registry_without_results_is_not_promoted_to_human_efficacy_evidence():
    records = [{
        "id": 10,
        "plant": "Gymnema sylvestre",
        "target_indication": "Type 2 diabetes",
        "study_type": "Interventional clinical trial protocol",
        "primary_outcome": "HbA1c",
        "result_direction": "",
        "evidence_level": "Clinical trial registry",
        "source_url": "https://clinicaltrials.gov/study/NCT00000010",
        "nct_id": "NCT00000010",
    }]
    out = discover_indication_candidates(_Engine(records), "Type 2 diabetes")
    row = out.iloc[0]
    assert row["Candidate_Evidence_Strength_Tier"] == "Registry record without reported results"
    assert row["Go_Investigate_Hold_NoGo"] == "Hold — await reported results"
    assert "human evidence detected" not in row["Clinical_Rationale"].lower()


def test_more_and_better_independent_records_produce_a_higher_evidence_quality_score():
    strong = [
        _record(100, "Plant strong", "Systematic review and meta-analysis", "https://doi.org/strong-review"),
        _record(101, "Plant strong", "Randomized human clinical trial", "https://doi.org/strong-rct1"),
        _record(102, "Plant strong", "Randomized human clinical trial", "https://doi.org/strong-rct2"),
        _record(103, "Plant strong", "Human clinical trial", "https://doi.org/strong-human"),
        _record(104, "Plant strong", "Animal in vivo study", "https://doi.org/strong-animal"),
        _record(105, "Plant strong", "In vitro mechanistic study", "https://doi.org/strong-vitro"),
    ]
    limited = [
        _record(200, "Plant limited", "Human clinical trial", "https://doi.org/limited-human"),
        _record(201, "Plant limited", "In vitro mechanistic study", "https://doi.org/limited-vitro"),
    ]
    raw = discover_indication_candidates(_Engine(strong + limited), "Type 2 diabetes")
    summary, _ = build_plant_candidate_shortlist(
        raw,
        indication="Type 2 diabetes",
        dosage_form="",
    )
    scores = dict(zip(summary["Alternative_Plant"], summary["Evidence_Quality_Score"]))
    counts = dict(zip(summary["Alternative_Plant"], summary["Candidate_Specific_Empirical_Row_Count"]))

    assert counts["Plant strong"] == 6
    assert counts["Plant limited"] == 2
    assert scores["Plant strong"] > scores["Plant limited"]
    assert scores["Plant strong"] != scores["Plant limited"]
