import json

import pandas as pd

import candidate_shortlisting as cs
from evidence_source_resolver import attach_mechanistic_evidence_source_traceability


def _mechanistic_row(**overrides):
    row = {
        "Alternative_Plant": "Fictus mechanisticus",
        "Reference_Plant": "Indication-centric discovery",
        "Source_Record_IDs": "M-1",
        "Evidence_Source": "PubMed",
        "Indication_Match_Type": "outcome_or_mechanism_support",
        "Indication_Match_Terms": "sleep",
        "Indication_Match_Reason": "Mechanistic support only",
        "Evidence_Level": "Preclinical / in vitro",
        "Evidence_Hierarchy_Detail": "In vitro receptor binding assay",
        "Study_Type": "In vitro",
        "Study_Model": "In vitro",
        "Population": "",
        "Primary_Outcome": "",
        "Source_Outcome_Text": "",
        "Source_Evidence_Text": "GABA-A receptor binding assay",
        "Result_Direction": "unknown",
        "Scientific_Rationale": "in vitro receptor binding",
        "Clinical_Rationale": "",
        "Target_or_Mechanism": "GABA-A receptor",
        "Mechanistic_Linked_Targets": "GABA-A receptor",
        "Mechanistic_Linked_Mechanisms": "GABAergic modulation",
        "R&D_Opportunity_Score": 40,
        "Decision_Class_AH": "D",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Direct_Evidence_Present": False,
        "Supported_Target_or_Mechanism": True,
    }
    row.update(overrides)
    return row


def _run_shortlist(rows):
    raw = pd.DataFrame(rows)
    plant_summary, _ = cs.build_plant_candidate_shortlist(
        raw, indication="sleep", dosage_form="capsule",
    )
    return plant_summary


def test_mechanistic_evidence_record_ids_survive_to_plant_summary():
    """Root-cause fix: mechanistic_source_ids used to be collapsed into a
    bare count (Mechanistic_Evidence_Count) with the IDs themselves
    discarded. They must now be a real, non-empty column."""
    plant_summary = _run_shortlist([_mechanistic_row()])
    assert not plant_summary.empty
    row = plant_summary.iloc[0]
    assert "Mechanistic_Evidence_Record_IDs" in plant_summary.columns
    assert row["Mechanistic_Evidence_Record_IDs"] == ["M-1"]
    assert row["Mechanistic_Evidence_Count"] == 1


def test_target_source_map_uses_exact_source_ids():
    plant_summary = _run_shortlist([_mechanistic_row()])
    row = plant_summary.iloc[0]
    assert row["Target_Source_Map"] == {"GABA-A receptor": ["M-1"]}


def test_mechanism_source_map_uses_exact_source_ids():
    plant_summary = _run_shortlist([_mechanistic_row()])
    row = plant_summary.iloc[0]
    assert row["Mechanism_Source_Map"] == {"GABAergic modulation": ["M-1"]}


def test_target_source_map_never_attaches_an_unrelated_rows_source():
    """No source-laundering: a second row for the SAME plant with a
    DIFFERENT target/source pair must not have its ID attributed to the
    first row's target, and vice versa."""
    rows = [
        _mechanistic_row(
            Source_Record_IDs="M-1",
            Mechanistic_Linked_Targets="GABA-A receptor",
            Mechanistic_Linked_Mechanisms="GABAergic modulation",
        ),
        _mechanistic_row(
            Source_Record_IDs="M-2",
            Mechanistic_Linked_Targets="5-HT1A receptor",
            Mechanistic_Linked_Mechanisms="Serotonergic modulation",
        ),
    ]
    plant_summary = _run_shortlist(rows)
    row = plant_summary.iloc[0]
    assert row["Target_Source_Map"]["GABA-A receptor"] == ["M-1"]
    assert row["Target_Source_Map"]["5-HT1A receptor"] == ["M-2"]
    assert "M-2" not in row["Target_Source_Map"]["GABA-A receptor"]
    assert "M-1" not in row["Target_Source_Map"]["5-HT1A receptor"]


def test_mechanistic_ids_absent_when_no_authoritative_relevance():
    """Legacy path (no Indication_Match_Type at all) must stay honestly
    empty rather than guessing at provenance."""
    raw = pd.DataFrame([{
        "Alternative_Plant": "Legacyus plantus",
        "Reference_Plant": "Legacy discovery",
        "Direct_Evidence_Present": False,
        "Supported_Target_or_Mechanism": True,
        "R&D_Opportunity_Score": 30,
        "Decision_Class_AH": "D",
        "Go_Investigate_Hold_NoGo": "Hold",
    }])
    plant_summary, _ = cs.build_plant_candidate_shortlist(raw, indication="sleep")
    row = plant_summary.iloc[0]
    assert row["Mechanistic_Evidence_Record_IDs"] == []
    assert row["Target_Source_Map"] == {}
    assert row["Mechanism_Source_Map"] == {}


# ---------------------------------------------------------------------------
# Resolution through evidence_source_resolver (Claim_Source_Map's ID vocabulary)
# ---------------------------------------------------------------------------

def _evidence_df():
    return pd.DataFrame([{
        "Evidence_Record_ID": "M-1",
        "Source_Title": "In vitro GABA-A receptor binding assay",
        "Source_URL": "https://example.org/m1",
    }])


def test_mechanistic_ids_resolve_through_the_shared_resolver():
    report_df = pd.DataFrame([{
        "Mechanistic_Evidence_Record_IDs": ["M-1"],
    }])
    out = attach_mechanistic_evidence_source_traceability(report_df, _evidence_df())
    row = out.iloc[0]
    assert row["Mechanistic_Source_Count"] == 1
    assert row["Mechanistic_Primary_Source_URL"] == "https://example.org/m1"
    assert row["Mechanistic_Source_Resolution_Status"] == "ALL_RECORDS_RESOLVED"


def test_mechanistic_target_and_mechanism_maps_are_json_encoded_for_export():
    report_df = pd.DataFrame([{
        "Mechanistic_Evidence_Record_IDs": ["M-1"],
        "Target_Source_Map": {"GABA-A receptor": ["M-1"]},
        "Mechanism_Source_Map": {"GABAergic modulation": ["M-1"]},
    }])
    out = attach_mechanistic_evidence_source_traceability(report_df, _evidence_df())
    row = out.iloc[0]
    assert json.loads(row["Target_Source_Map"]) == {"GABA-A receptor": ["M-1"]}
    assert json.loads(row["Mechanism_Source_Map"]) == {"GABAergic modulation": ["M-1"]}


def test_empty_report_df_returns_unchanged():
    empty = pd.DataFrame()
    assert attach_mechanistic_evidence_source_traceability(empty, _evidence_df()).empty
