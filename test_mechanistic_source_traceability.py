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
    assert row["Target_Source_Map"] == {
        "GABA-A receptor": {"evidence_ids": ["M-1"], "references": []}
    }


def test_mechanism_source_map_uses_exact_source_ids():
    plant_summary = _run_shortlist([_mechanistic_row()])
    row = plant_summary.iloc[0]
    assert row["Mechanism_Source_Map"] == {
        "GABAergic modulation": {"evidence_ids": ["M-1"], "references": []}
    }


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
    assert row["Target_Source_Map"]["GABA-A receptor"]["evidence_ids"] == ["M-1"]
    assert row["Target_Source_Map"]["5-HT1A receptor"]["evidence_ids"] == ["M-2"]
    assert "M-2" not in row["Target_Source_Map"]["GABA-A receptor"]["evidence_ids"]
    assert "M-1" not in row["Target_Source_Map"]["5-HT1A receptor"]["evidence_ids"]


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


def test_mechanistic_target_and_mechanism_maps_are_enriched_and_json_encoded():
    report_df = pd.DataFrame([{
        "Mechanistic_Evidence_Record_IDs": ["M-1"],
        "Target_Source_Map": {"GABA-A receptor": {"evidence_ids": ["M-1"], "references": []}},
        "Mechanism_Source_Map": {"GABAergic modulation": {"evidence_ids": ["M-1"], "references": []}},
    }])
    out = attach_mechanistic_evidence_source_traceability(report_df, _evidence_df())
    row = out.iloc[0]
    targets = json.loads(row["Target_Source_Map"])
    assert targets["GABA-A receptor"]["evidence_ids"] == ["M-1"]
    assert targets["GABA-A receptor"]["primary_source_url"] == "https://example.org/m1"
    mechanisms = json.loads(row["Mechanism_Source_Map"])
    assert mechanisms["GABAergic modulation"]["primary_source_url"] == "https://example.org/m1"


def test_target_with_only_a_raw_reference_url_still_resolves_clickable():
    """Compound-target links from the plant-compound DB generally have no
    Evidence_Record_ID -- only a reference_title/reference_url pair. These
    must still surface as a clickable source."""
    report_df = pd.DataFrame([{
        "Mechanistic_Evidence_Record_IDs": [],
        "Target_Source_Map": {
            "5-HT1A receptor": {
                "evidence_ids": [],
                "references": [{"compound": "Apigenin", "title": "Dr. Duke phytochemical DB", "url": "https://example.org/apigenin-5ht1a"}],
            }
        },
        "Mechanism_Source_Map": {},
    }])
    out = attach_mechanistic_evidence_source_traceability(report_df, pd.DataFrame())
    row = out.iloc[0]
    targets = json.loads(row["Target_Source_Map"])
    assert targets["5-HT1A receptor"]["primary_source_url"] == "https://example.org/apigenin-5ht1a"
    assert row["Mechanistic_Primary_Source_URL"] == "https://example.org/apigenin-5ht1a"


def test_target_with_evidence_id_resolves_doi_pmid_or_source_url():
    """Mandatory (corrective pass, §I.1): a target's evidence_ids must
    resolve to the record's real DOI/PMID/Source_URL via the shared
    resolver -- not just an internal ID."""
    evidence_df = pd.DataFrame([{
        "Evidence_Record_ID": "E1",
        "Source_Title": "GABA-A receptor binding study",
        "DOI": "10.1000/example-gaba",
        "PMID": "87654321",
    }])
    report_df = pd.DataFrame([{
        "Mechanistic_Evidence_Record_IDs": ["E1"],
        "Target_Source_Map": {"GABA-A receptor": {"evidence_ids": ["E1"], "references": []}},
        "Mechanism_Source_Map": {},
    }])
    out = attach_mechanistic_evidence_source_traceability(report_df, evidence_df)
    targets = json.loads(out.iloc[0]["Target_Source_Map"])
    # No Source_URL on the record -- DOI takes precedence per
    # evidence_source_resolver.resolve_external_url()'s existing rule.
    assert targets["GABA-A receptor"]["primary_source_url"] == "https://doi.org/10.1000/example-gaba"


def test_target_never_receives_an_unrelated_human_efficacy_source():
    """No laundering: a target's evidence_ids list only ever contains what
    candidate_shortlisting.py's row-level pairing put there -- resolving it
    must never pull in an unrelated record from evidence_df."""
    evidence_df = pd.DataFrame([
        {"Evidence_Record_ID": "EFF1", "Source_Title": "Unrelated human efficacy RCT", "Source_URL": "https://example.org/eff1"},
        {"Evidence_Record_ID": "M-1", "Source_Title": "Mechanistic study", "Source_URL": "https://example.org/m1"},
    ])
    report_df = pd.DataFrame([{
        "Mechanistic_Evidence_Record_IDs": ["M-1"],
        "Target_Source_Map": {"GABA-A receptor": {"evidence_ids": ["M-1"], "references": []}},
        "Mechanism_Source_Map": {},
    }])
    out = attach_mechanistic_evidence_source_traceability(report_df, evidence_df)
    targets = json.loads(out.iloc[0]["Target_Source_Map"])
    urls = [s["url"] for s in targets["GABA-A receptor"]["sources"]]
    assert "https://example.org/eff1" not in urls
    assert urls == ["https://example.org/m1"]


def test_empty_report_df_returns_unchanged():
    empty = pd.DataFrame()
    assert attach_mechanistic_evidence_source_traceability(empty, _evidence_df()).empty
