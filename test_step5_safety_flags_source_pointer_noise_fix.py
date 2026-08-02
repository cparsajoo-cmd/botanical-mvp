"""Regression test: connector-generated "a safety source exists" pointer
statements (LiverTox, OpenFDA FAERS) must not be misclassified as actual
adverse-event findings in Safety_Flags, and unrelated evidence-record columns
must not be glued into one run-on sentence that garbles the output.

Observed symptom (production export, Ginkgo biloba):

    Safety_Flags = "Unknown Unknown Cognitive decline / Alzheimer's support
    LiverTox hepatotoxicity/safety source found for Ginkgo biloba.; ...
    OpenFDA FAERS returned 5 adverse event records for Ginkgo biloba. (+8 more)"

Two causes, both pre-existing (not introduced by the structured-JSONB-
transport fix in test_step5_structured_only_safety_record_fix.py):

1. `livertox_connector.py` / `openfda_connector.py` write a Notes sentence
   that says a safety-relevant *source* was found, not what that source
   says (e.g. "OpenFDA FAERS returned 5 adverse event records for Ginkgo
   biloba. This is a safety signal source and requires manual clinical
   interpretation."). Because it contains medical trigger words
   ("hepatotoxicity", "adverse event"), the conservative extractor accepted
   it as if it described an actual finding.

2. `_record_text()` joined every column's value with a bare space, so
   placeholder values ("Unknown" Study_Type/Evidence_Level) and unrelated
   Target_Indication text were glued onto the Notes sentence with no
   sentence boundary, producing one run-on fragment instead of separable
   sentences for the classifier to evaluate independently.
"""
import pandas as pd

from indication_candidate_discovery import _record_text, discover_indication_candidates
from safety_interaction_attribution import (
    extract_attributed_safety_interactions,
    extract_structured_safety_interactions,
)


def test_record_text_separates_columns_with_sentence_boundary():
    row = pd.Series({
        "Scientific_Name": "Ginkgo biloba",
        "Study_Type": "Unknown",
        "Evidence_Level": "Unknown",
        "Target_Indication": "Cognitive decline / Alzheimer's support",
        "Notes": "LiverTox hepatotoxicity/safety source found for Ginkgo biloba.",
    })
    text = _record_text(row)
    # Each column's content must be its own sentence, not glued to its
    # neighbor with a bare space.
    assert "Unknown. Unknown." in text
    assert "support. LiverTox" in text


def test_livertox_source_pointer_statement_is_rejected_as_noise():
    text = "LiverTox hepatotoxicity/safety source found for Ginkgo biloba."
    result = extract_attributed_safety_interactions(
        text, plant_name="Ginkgo biloba", structurally_linked=True,
    )
    assert result["adverse_events"] == []
    assert result["safety_data_status"] == "not_assessed"


def test_openfda_source_pointer_statement_is_rejected_as_noise():
    text = (
        "OpenFDA FAERS returned 5 adverse event records for Ginkgo biloba. "
        "This is a safety signal source and requires manual clinical interpretation."
    )
    result = extract_attributed_safety_interactions(
        text, plant_name="Ginkgo biloba", structurally_linked=True,
    )
    assert result["adverse_events"] == []
    assert result["safety_data_status"] == "not_assessed"


def test_source_pointer_statement_rejected_in_structured_field_too():
    result = extract_structured_safety_interactions(
        "LiverTox hepatotoxicity/safety source found for Ginkgo biloba.",
        "",
        plant_name="Ginkgo biloba",
    )
    assert result["adverse_events"] == []


def test_genuine_adverse_event_sentence_still_accepted():
    """Non-regression: the noise filter must not become over-broad."""
    text = "Ginkgo biloba was studied for cognitive decline. Mild gastrointestinal adverse events were reported."
    result = extract_attributed_safety_interactions(
        text, plant_name="Ginkgo biloba", structurally_linked=True,
    )
    assert result["adverse_events"] == ["Mild gastrointestinal adverse events were reported."]


class _Engine:
    def __init__(self):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([
            {
                # A genuine, plant-attributed structured safety/interaction
                # record (as in test_step5_structured_only_safety_record_fix.py).
                "Scientific_Name": "Ginkgo biloba",
                "Evidence_Record_ID": 314,
                "Adverse_Events": [{"event": "fatal breakthrough seizure"}],
                "Interactions_Structured": [{
                    "interacting_class": "anticonvulsants",
                    "drugs": ["phenytoin", "valproate"],
                    "mechanism": "CYP2C19 induction",
                }],
            },
            {
                # A connector-style pointer record: no real finding, just
                # metadata saying a source exists, plus "Unknown" placeholders.
                "Scientific_Name": "Ginkgo biloba",
                "Evidence_Record_ID": 315,
                "Study_Type": "Unknown",
                "Evidence_Level": "Unknown",
                "Target_Indication": "Cognitive decline / Alzheimer's support",
                "Notes": "LiverTox hepatotoxicity/safety source found for Ginkgo biloba.",
            },
        ])

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


def test_step5_output_keeps_real_finding_and_drops_source_pointer_noise():
    out = discover_indication_candidates(_Engine(), "cognitive decline", dosage_form="oral")
    assert not out.empty
    row = out.iloc[0]
    assert "fatal breakthrough seizure" in row["Safety_Flags"]
    assert "LiverTox" not in row["Safety_Flags"]
    assert "source found for" not in row["Safety_Flags"]
    assert "Unknown" not in row["Safety_Flags"]
