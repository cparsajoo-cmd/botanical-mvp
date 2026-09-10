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
    assert source_map["Apigenin"]["url"] is None


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
    assert entry["url"] == "https://pubchem.ncbi.nlm.nih.gov/compound/6549"
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
