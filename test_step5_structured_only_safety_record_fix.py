"""Regression test: structured-only Safety/Interaction JSONB must survive to
Step 5 output (Safety_Flags / Interaction_Flags), even when the evidence
record carries no free-text Title/Abstract/Outcome/Notes/Target_Indication
and even when the plant is being scored for an indication other than the one
the safety record happens to be filed under.

Two independent root causes previously emptied Safety_Flags / Interaction_Flags
for exactly this shape of record:

1. `_record_text()` in indication_candidate_discovery.py did not read
   Adverse_Events / Interactions_Structured, so a record with only those two
   columns populated produced an empty `text`. `_build_plant_evidence_index()`
   then dropped the record entirely via `if not text: continue` -- before any
   safety logic ever saw it.

2. Even once indexed, `extract_structured_safety_interactions()` in
   safety_interaction_attribution.py used a fixed adverse-event/drug-term
   vocabulary that did not include "seizure", "hyphema", or the
   anticonvulsant drug family (phenytoin, valproate, CYP2C19), so a genuine
   structured adverse event / interaction was classified as not present.

This test reproduces the real-world Ginkgo biloba case (fatal breakthrough
seizure; spontaneous hyphema; interaction with anticonvulsants phenytoin and
valproate via CYP2C19 induction) and pins both fixes.
"""
import pandas as pd

from indication_candidate_discovery import _record_text, discover_indication_candidates
from safety_interaction_attribution import extract_structured_safety_interactions


def test_record_text_is_not_empty_for_structured_only_safety_record():
    """A record with only Adverse_Events/Interactions_Structured populated
    must not be treated as textless, or _build_plant_evidence_index drops it
    before any safety logic runs."""
    row = pd.Series({
        "Scientific_Name": "Ginkgo biloba",
        "Adverse_Events": [
            {"event": "fatal breakthrough seizure"},
            {"event": "spontaneous hyphema"},
        ],
        "Interactions_Structured": [
            {
                "interacting_class": "anticonvulsants",
                "drugs": ["phenytoin", "valproate"],
                "mechanism": "CYP2C19 induction",
            }
        ],
    })
    text = _record_text(row)
    assert text.strip() != ""
    assert "fatal breakthrough seizure" in text
    assert "phenytoin" in text


def test_record_text_still_empty_when_truly_no_content():
    """The fix must not turn genuinely empty records into non-empty ones."""
    row = pd.Series({"Scientific_Name": "Ginkgo biloba"})
    assert _record_text(row) == ""


def test_structured_extractor_recognizes_seizure_and_hyphema_as_adverse_events():
    result = extract_structured_safety_interactions(
        "event: fatal breakthrough seizure; event: spontaneous hyphema",
        "",
        plant_name="Ginkgo biloba",
    )
    joined = "; ".join(result["adverse_events"])
    assert "seizure" in joined.lower()
    assert "hyphema" in joined.lower()
    assert result["safety_data_status"] == "adverse_signal_present"


def test_structured_extractor_recognizes_anticonvulsant_interaction():
    result = extract_structured_safety_interactions(
        "",
        "drugs: phenytoin; valproate; interacting_class: anticonvulsants; mechanism: CYP2C19 induction",
        plant_name="Ginkgo biloba",
    )
    joined = "; ".join(result["interactions"]).lower()
    assert "phenytoin" in joined or "anticonvulsant" in joined or "cyp2c19" in joined


class _Engine:
    """Mirrors BotanicalRDCandidateEngine._pick (the real production
    implementation) -- notably it does NOT use pd.notna, so it does not choke
    on list/dict JSONB values, unlike a naive pd.notna-based mock."""

    def __init__(self):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        # A pure safety/interaction record: no Title/Abstract/Outcome/Notes/
        # Target_Indication at all, exactly like a Supabase evidence_records
        # row that exists solely to carry a case-report safety + interaction
        # finding, unrelated in its own text to the indication being scored.
        self.evidence_records_df = pd.DataFrame([{
            "Scientific_Name": "Ginkgo biloba",
            "Source_URL": "https://example.test/case-report",
            "Evidence_Record_ID": 314,
            "Adverse_Events": [
                {"event": "fatal breakthrough seizure"},
                {"event": "spontaneous hyphema"},
            ],
            "Interactions_Structured": [
                {
                    "interacting_class": "anticonvulsants",
                    "drugs": ["phenytoin", "valproate"],
                    "mechanism": "CYP2C19 induction",
                }
            ],
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


def test_step5_output_carries_structured_only_ginkgo_safety_and_interaction():
    """End-to-end: the Ginkgo case must reach Safety_Flags / Interaction_Flags
    in the Step 5 output row, even though its own record text has nothing to
    do with the queried indication (cross-indication safety preservation)."""
    out = discover_indication_candidates(_Engine(), "cognitive decline", dosage_form="oral")
    assert not out.empty
    row = out.iloc[0]
    assert "fatal breakthrough seizure" in row["Safety_Flags"]
    assert "spontaneous hyphema" in row["Safety_Flags"]
    interaction_text = row["Interaction_Flags"].lower()
    assert "phenytoin" in interaction_text or "anticonvulsant" in interaction_text
