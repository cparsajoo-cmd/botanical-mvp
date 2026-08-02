"""Regression test: reassurance statements phrased as "no important safety
concerns" (a common meta-analysis wording) must populate Safety_Reassurance,
not be dropped as unrecognized.

Observed symptom: for Ginkgo biloba, a meta-analysis reports "no important
safety concerns with EGb761 at 240 mg/day", but Safety_Reassurance stayed
empty because _REASSURANCE_PATTERNS only recognized a fixed set of phrases
("well tolerated", "no serious adverse events", ...) and not this wording.
"""
import pandas as pd

from indication_candidate_discovery import discover_indication_candidates
from safety_interaction_attribution import (
    extract_attributed_safety_interactions,
    extract_structured_safety_interactions,
)


def test_no_important_safety_concerns_recognized_in_structured_field():
    result = extract_structured_safety_interactions(
        "No important safety concerns with EGb761 at 240 mg/day",
        "",
        plant_name="Ginkgo biloba",
    )
    assert result["safety_reassurance"] == ["No important safety concerns with EGb761 at 240 mg/day"]
    assert result["safety_data_status"] == "reassurance_reported"


def test_no_important_safety_concerns_recognized_in_free_text():
    text = (
        "Ginkgo biloba extract EGb761 caused no important safety concerns "
        "in the treated group."
    )
    result = extract_attributed_safety_interactions(
        text, plant_name="Ginkgo biloba", structurally_linked=True,
    )
    assert result["safety_reassurance"]
    assert result["safety_data_status"] == "reassurance_reported"


def test_generic_no_safety_concerns_also_recognized():
    result = extract_structured_safety_interactions(
        "no safety concerns", "", plant_name="Ginkgo biloba",
    )
    assert result["safety_reassurance"] == ["no safety concerns"]


class _Engine:
    def __init__(self):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([{
            "Scientific_Name": "Ginkgo biloba",
            "Evidence_Record_ID": 700,
            "Safety_Findings": "No important safety concerns with EGb761 at 240 mg/day",
        }])

    def _candidate_frame(self):
        return pd.DataFrame([{
            "Scientific_Name": "Ginkgo biloba",
            "Known_Active_Compounds": "ginkgolide B",
            "Known_Targets": "platelet activating factor",
            "Indications_Text": "cognitive decline",
        }])

    def _pick(self, row, names):
        for name in names:
            try:
                value = row.get(name, "")
            except AttributeError:
                value = ""
            if (
                value is not None
                and str(value).strip()
                and str(value).lower() not in {"nan", "none", "null"}
            ):
                return str(value).strip()
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        return "High"


def test_step5_output_populates_safety_reassurance_for_ginkgo():
    out = discover_indication_candidates(_Engine(), "cognitive decline", dosage_form="oral")
    assert not out.empty
    row = out.iloc[0]
    assert "no important safety concerns" in row["Safety_Reassurance"].lower()
    assert row["Safety_Data_Status"] != ""
