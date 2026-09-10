import json

import pandas as pd

from claim_source_map import (
    attach_claim_source_map,
    attach_regulatory_patent_source_traceability,
    build_claim_source_map,
    parse_claim_source_map,
)


def test_regulatory_patent_not_integrated_reports_zero_not_fabricated():
    report_df = pd.DataFrame([{
        "Regulatory_Assessment_Status": "NOT_INTEGRATED",
        "Patent_Assessment_Status": "NOT_INTEGRATED",
    }])
    out = attach_regulatory_patent_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Regulatory_Source_Count"] == 0
    assert row["Regulatory_Primary_Source_URL"] is None
    assert row["Patent_Source_Count"] == 0
    assert row["Patent_Primary_Source_URL"] is None


def test_regulatory_assessed_with_real_url_is_exposed():
    report_df = pd.DataFrame([{
        "Regulatory_Assessment_Status": "ASSESSED",
        "Regulatory_Source_URL": "https://www.ema.europa.eu/en/medicines/herbal/example",
        "Regulatory_Primary_Source_Title": "EMA HMPC monograph",
        "Regulatory_Authority": "EMA / HMPC",
    }])
    out = attach_regulatory_patent_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Regulatory_Source_Count"] == 1
    assert row["Regulatory_Primary_Source_URL"].startswith("https://www.ema.europa.eu")


def test_regulatory_assessed_with_invalid_url_is_not_fabricated():
    report_df = pd.DataFrame([{
        "Regulatory_Assessment_Status": "ASSESSED",
        "Regulatory_Source_URL": "internal-record-only",
    }])
    out = attach_regulatory_patent_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Regulatory_Source_Count"] == 0
    assert row["Regulatory_Primary_Source_URL"] is None


def test_patent_ids_present_are_preserved():
    report_df = pd.DataFrame([{
        "Patent_Assessment_Status": "ASSESSED",
        "Patent_IDs": ["EP1234567"],
    }])
    out = attach_regulatory_patent_source_traceability(report_df)
    row = out.iloc[0]
    assert json.loads(row["Patent_IDs"]) == ["EP1234567"]
    assert row["Patent_Source_Count"] == 1


def test_build_claim_source_map_unions_only_actual_ids():
    row = pd.Series({
        "Human_Evidence_Record_IDs": json.dumps(["E1", "E2"]),
        "Safety_Evidence_Record_IDs": json.dumps(["S1"]),
        "Commercial_Source_Titles": json.dumps([]),
        "Regulatory_Primary_Source_URL": None,
        "Patent_IDs": json.dumps([]),
    })
    claim_map = build_claim_source_map(row)
    assert claim_map == {"human_evidence": ["E1", "E2"], "safety": ["S1"]}

def test_build_claim_source_map_empty_when_nothing_resolved():
    row = pd.Series({
        "Human_Evidence_Record_IDs": json.dumps([]),
        "Safety_Evidence_Record_IDs": json.dumps([]),
    })
    assert build_claim_source_map(row) == {}


def test_attach_claim_source_map_adds_valid_json_columns():
    report_df = pd.DataFrame([{
        "Human_Evidence_Record_IDs": json.dumps(["E1"]),
        "Safety_Evidence_Record_IDs": json.dumps([]),
    }])
    out = attach_claim_source_map(report_df)
    row = out.iloc[0]
    parsed_claims = parse_claim_source_map(row["Claim_Source_Map"])
    assert parsed_claims["human_evidence"] == ["E1"]
    derived = json.loads(row["Derived_Claim_Provenance"])
    assert "Opportunity_Type" in derived
    assert "derived_from_fields" in derived["Opportunity_Type"]


def test_derived_claim_provenance_never_claims_a_single_publication():
    report_df = pd.DataFrame([{"Human_Evidence_Record_IDs": "[]", "Safety_Evidence_Record_IDs": "[]"}])
    out = attach_claim_source_map(report_df)
    derived = json.loads(out.iloc[0]["Derived_Claim_Provenance"])
    for entry in derived.values():
        assert "derived_from_fields" in entry
        assert isinstance(entry["derived_from_fields"], list)
        assert len(entry["derived_from_fields"]) >= 1


def test_empty_report_df_returns_unchanged():
    empty = pd.DataFrame()
    assert attach_claim_source_map(empty).empty
    assert attach_regulatory_patent_source_traceability(empty).empty


# ---------------------------------------------------------------------------
# Corrective pass (2026-09-10, gap 6): Claim_Source_Map must include
# targets/mechanisms/compounds/structured-commercial when available.
# ---------------------------------------------------------------------------

def test_claim_source_map_includes_targets_and_mechanisms_when_available():
    row = pd.Series({
        "Target_Source_Map": json.dumps({"GABA-A receptor": ["M-1"]}),
        "Mechanism_Source_Map": json.dumps({"GABAergic modulation": ["M-1"]}),
    })
    claim_map = build_claim_source_map(row)
    assert claim_map["targets"] == {"GABA-A receptor": ["M-1"]}
    assert claim_map["mechanisms"] == {"GABAergic modulation": ["M-1"]}


def test_claim_source_map_includes_compounds_with_provenance_type():
    row = pd.Series({
        "Compound_Source_Map": json.dumps({
            "Apigenin": {"provenance_type": "INTERNAL_CURATED_PROVENANCE", "source": "internal db", "url": None},
        }),
    })
    claim_map = build_claim_source_map(row)
    assert claim_map["compounds"]["Apigenin"]["provenance_type"] == "INTERNAL_CURATED_PROVENANCE"


def test_claim_source_map_commercial_uses_structured_identity_not_bare_title():
    row = pd.Series({
        "Commercial_Sources_JSON": json.dumps([
            {"Title": "Botanical X Extract", "Resolved_URL": "https://example.com/p1", "Source_Organization": "RetailerCo"},
        ]),
    })
    claim_map = build_claim_source_map(row)
    assert claim_map["commercial"] == [{
        "title": "Botanical X Extract", "url": "https://example.com/p1", "source": "RetailerCo",
    }]


def test_claim_source_map_empty_when_nothing_available_for_new_categories():
    row = pd.Series({"Human_Evidence_Record_IDs": "[]", "Safety_Evidence_Record_IDs": "[]"})
    claim_map = build_claim_source_map(row)
    assert "targets" not in claim_map
    assert "mechanisms" not in claim_map
    assert "compounds" not in claim_map
    assert "commercial" not in claim_map


def test_attach_claim_source_map_end_to_end_all_categories():
    report_df = pd.DataFrame([{
        "Human_Evidence_Record_IDs": json.dumps(["E1"]),
        "Safety_Evidence_Record_IDs": json.dumps(["S1"]),
        "Target_Source_Map": json.dumps({"GABA-A receptor": ["M-1"]}),
        "Mechanism_Source_Map": json.dumps({"GABAergic modulation": ["M-1"]}),
        "Compound_Source_Map": json.dumps({"Apigenin": {"provenance_type": "INTERNAL_CURATED_PROVENANCE"}}),
        "Commercial_Sources_JSON": json.dumps([{"Title": "P", "Resolved_URL": "https://x.com/p"}]),
        "Regulatory_Primary_Source_URL": "https://www.ema.europa.eu/x",
    }])
    out = attach_claim_source_map(report_df)
    claim_map = parse_claim_source_map(out.iloc[0]["Claim_Source_Map"])
    assert set(claim_map.keys()) == {
        "human_evidence", "safety", "targets", "mechanisms", "compounds", "commercial", "regulatory",
    }
