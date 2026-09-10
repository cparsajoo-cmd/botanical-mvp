import json

import pandas as pd

from compound_source_traceability import (
    attach_compound_source_traceability,
    build_compound_source_map,
    parse_compound_source_map,
)


def test_no_linked_compounds_yields_empty_map():
    assert build_compound_source_map([]) == {}


def test_compound_without_metadata_is_internal_curated_provenance():
    source_map = build_compound_source_map(["Apigenin"])
    assert source_map["Apigenin"]["provenance_type"] == "INTERNAL_CURATED_PROVENANCE"
    assert source_map["Apigenin"]["plant_compound_source"]["url"] is None


def test_compound_with_real_external_metadata_is_externally_linked():
    source_map = build_compound_source_map(
        ["Linalool"],
        compound_metadata={
            "Linalool": {
                "reference_url": "https://pubchem.ncbi.nlm.nih.gov/compound/6549",
                "reference_title": "PubChem CID 6549",
                "pubchem_cid": "6549",
            }
        },
    )
    entry = source_map["Linalool"]
    assert entry["provenance_type"] == "EXTERNALLY_LINKED"
    assert entry["plant_compound_source"]["url"] == "https://pubchem.ncbi.nlm.nih.gov/compound/6549"
    assert entry["pubchem_cid"] == "6549"


def test_invalid_external_url_is_not_fabricated_into_a_link():
    source_map = build_compound_source_map(
        ["Ghostol"],
        compound_metadata={"Ghostol": {"reference_url": "internal-id-only"}},
    )
    # No valid URL and no pubchem/chembl id -> falls back to internal curated.
    assert source_map["Ghostol"]["provenance_type"] == "INTERNAL_CURATED_PROVENANCE"


def test_attach_compound_source_traceability_no_linked_compounds_column():
    report_df = pd.DataFrame([{"Alternative_Plant": "Plantus exampleus"}])
    out = attach_compound_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Compound_Source_Count"] == 0
    assert row["Compound_Primary_Source_URL"] is None


def test_attach_compound_source_traceability_with_internal_only_compounds():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Discovery_Linked_Compounds": "Apigenin; Linalool",
    }])
    out = attach_compound_source_traceability(report_df)
    row = out.iloc[0]
    source_map = parse_compound_source_map(row["Compound_Source_Map"])
    assert source_map["Apigenin"]["provenance_type"] == "INTERNAL_CURATED_PROVENANCE"
    assert source_map["Linalool"]["provenance_type"] == "INTERNAL_CURATED_PROVENANCE"
    assert row["Compound_Source_Count"] == 2
    assert row["Compound_Resolved_Source_Count"] == 0
    assert row["Compound_Primary_Source_URL"] is None


def test_attach_compound_source_traceability_with_real_external_metadata():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Discovery_Linked_Compounds": "Linalool",
    }])
    metadata = {"Linalool": {
        "reference_url": "https://pubchem.ncbi.nlm.nih.gov/compound/6549",
        "reference_title": "PubChem CID 6549",
    }}
    out = attach_compound_source_traceability(report_df, compound_metadata=metadata)
    row = out.iloc[0]
    assert row["Compound_Resolved_Source_Count"] == 1
    assert row["Compound_Primary_Source_URL"] == "https://pubchem.ncbi.nlm.nih.gov/compound/6549"


def test_never_fabricates_an_external_publication_for_internal_relation():
    """Even with a compound_metadata dict passed in, a compound absent from
    it must never acquire an external URL/title out of nowhere."""
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Discovery_Linked_Compounds": "Unlisted Compound",
    }])
    out = attach_compound_source_traceability(report_df, compound_metadata={})
    row = out.iloc[0]
    source_map = parse_compound_source_map(row["Compound_Source_Map"])
    assert source_map["Unlisted Compound"]["provenance_type"] == "INTERNAL_CURATED_PROVENANCE"
    assert source_map["Unlisted Compound"].get("url") is None


def test_parse_compound_source_map_roundtrip():
    source_map = build_compound_source_map(["Apigenin"])
    text = json.dumps(source_map)
    parsed = parse_compound_source_map(text)
    assert parsed == source_map


def test_empty_report_df_returns_unchanged():
    empty = pd.DataFrame()
    assert attach_compound_source_traceability(empty).empty


# ---------------------------------------------------------------------------
# Corrective pass (2026-09-10): plant->compound vs compound->target/mechanism
# provenance must stay distinct, and a compound-target link's real citation
# must reach Stage 6 as a clickable URL even with no Evidence_Record_ID.
# ---------------------------------------------------------------------------

def test_plant_compound_source_and_compound_target_source_are_distinct():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Withania somnifera",
        "Discovery_Linked_Compounds": "Withanolide A",
        "Compound_Reference_Map": {
            "Withanolide A": {"title": "Dr. Duke phytochemical DB", "url": "https://example.org/plant-compound"},
        },
        "Compound_Target_Source_Map": {
            "Withanolide A": {
                "GABA-A receptor": [{"title": "Receptor binding study", "url": "https://example.org/compound-target"}],
            },
        },
    }])
    out = attach_compound_source_traceability(report_df)
    source_map = parse_compound_source_map(out.iloc[0]["Compound_Source_Map"])
    entry = source_map["Withanolide A"]
    assert entry["plant_compound_source"]["url"] == "https://example.org/plant-compound"
    assert entry["target_sources"]["GABA-A receptor"][0]["url"] == "https://example.org/compound-target"
    # The two claims are genuinely different URLs here -- neither field
    # leaked into the other.
    assert entry["plant_compound_source"]["url"] != entry["target_sources"]["GABA-A receptor"][0]["url"]


def test_compound_target_source_reaches_stage6_with_no_evidence_record_id():
    """Compound-target links from the plant-compound DB typically have no
    Evidence_Record_ID -- only their own reference_url. Must still surface
    as a clickable Stage-6 source."""
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Withania somnifera",
        "Discovery_Linked_Compounds": "Withanolide A",
        "Compound_Target_Source_Map": {
            "Withanolide A": {
                "GABA-A receptor": [{"title": "Receptor binding study", "url": "https://example.org/compound-target"}],
            },
        },
    }])
    out = attach_compound_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Compound_Resolved_Source_Count"] == 1
    assert row["Compound_Primary_Source_URL"] == "https://example.org/compound-target"


def test_compound_target_source_for_one_compound_never_attaches_to_another():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Withania somnifera",
        "Discovery_Linked_Compounds": "Withanolide A; Withaferin A",
        "Compound_Target_Source_Map": {
            "Withanolide A": {"GABA-A receptor": [{"title": "Study A", "url": "https://example.org/a"}]},
            "Withaferin A": {"NF-kB": [{"title": "Study B", "url": "https://example.org/b"}]},
        },
    }])
    out = attach_compound_source_traceability(report_df)
    source_map = parse_compound_source_map(out.iloc[0]["Compound_Source_Map"])
    assert "NF-kB" not in source_map["Withanolide A"].get("target_sources", {})
    assert "GABA-A receptor" not in source_map["Withaferin A"].get("target_sources", {})
