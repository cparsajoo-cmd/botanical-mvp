import json

import pandas as pd

from evidence_source_resolver import (
    attach_human_evidence_source_traceability,
    parse_sources_json,
    resolve_evidence_sources,
    resolve_external_url,
)


def _evidence_df():
    return pd.DataFrame([
        {
            "Evidence_Record_ID": "E1",
            "Source_Title": "Randomized clinical trial of botanical X",
            "Source_Type": "PubMed",
            "Source_Year": 2024,
            "Source_URL": "https://example.org/article/E1",
            "PMID": "11111111",
            "DOI": "10.1000/e1",
            "Study_Type": "Randomized controlled trial",
            "Population": "human",
            "Primary_Outcome": "sleep quality",
        },
        {
            "Evidence_Record_ID": "E2",
            "Source_Title": "Systematic review of botanical X",
            "Source_Type": "Crossref",
            "Source_Year": 2023,
            "Source_URL": "",
            "PMID": "",
            "DOI": "10.1000/e2",
            "Study_Type": "Systematic review",
            "Population": "human",
        },
        {
            "Evidence_Record_ID": "E3",
            "Source_Title": "Human observational study",
            "Source_URL": "not-a-url",
            "PMID": "33333333",
            "DOI": "",
            "Study_Type": "Human observational study",
            "Population": "human",
        },
        {
            "Evidence_Record_ID": "E4",
            "Source_Title": "Internal curated evidence record",
            "Source_URL": "",
            "PMID": "",
            "DOI": "",
            "Study_Type": "Human study",
            "Population": "human",
        },
    ])


def test_existing_source_url_has_precedence_over_doi_and_pmid():
    url, status = resolve_external_url(
        source_url="https://example.org/original", doi="10.1000/test", pmid="123456"
    )
    assert url == "https://example.org/original"
    assert status == "RESOLVED_SOURCE_URL"


def test_doi_only_builds_clickable_doi_url():
    url, status = resolve_external_url(source_url=None, doi="10.1000/test", pmid=None)
    assert url == "https://doi.org/10.1000/test"
    assert status == "RESOLVED_DOI"


def test_pmid_only_builds_clickable_pubmed_url():
    url, status = resolve_external_url(source_url=None, doi=None, pmid="12345678")
    assert url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert status == "RESOLVED_PMID"


def test_malformed_source_url_falls_back_to_doi_then_pmid():
    url, status = resolve_external_url(
        source_url="not-a-url", doi="10.1000/fallback", pmid="999999"
    )
    assert url == "https://doi.org/10.1000/fallback"
    assert status == "RESOLVED_DOI"




def test_legacy_source_url_slot_containing_doi_is_resolved_without_fabrication():
    url, status = resolve_external_url(source_url="10.1000/legacy", doi=None, pmid=None)
    assert url == "https://doi.org/10.1000/legacy"
    assert status == "RESOLVED_DOI"


def test_legacy_source_url_slot_containing_pmid_is_resolved():
    url, status = resolve_external_url(source_url="PMID:12345678", doi=None, pmid=None)
    assert url == "https://pubmed.ncbi.nlm.nih.gov/12345678/"
    assert status == "RESOLVED_PMID"

def test_internal_id_only_never_fabricates_external_url():
    sources = resolve_evidence_sources("E4", _evidence_df())
    assert len(sources) == 1
    assert sources[0]["Evidence_Record_ID"] == "E4"
    assert sources[0]["Resolved_URL"] is None
    assert sources[0]["Resolution_Status"] == "INTERNAL_ID_ONLY"


def test_unresolved_evidence_id_is_preserved_explicitly():
    sources = resolve_evidence_sources("DOES_NOT_EXIST", _evidence_df())
    assert sources == [{
        "Evidence_Record_ID": "DOES_NOT_EXIST",
        "Title": None,
        "Source_Type": None,
        "Source_Organization": None,
        "Year": None,
        "Study_Type": None,
        "Population": None,
        "Outcome": None,
        "PMID": None,
        "DOI": None,
        "Source_URL": None,
        "Resolved_URL": None,
        "Resolution_Status": "UNRESOLVED_RECORD",
    }]


def test_duplicate_and_empty_ids_are_normalized_before_resolution():
    sources = resolve_evidence_sources('E1;E1;E2;();[]', _evidence_df())
    assert [s["Evidence_Record_ID"] for s in sources] == ["E1", "E2"]


def test_literal_empty_tuple_resolves_to_no_sources():
    assert resolve_evidence_sources("()", _evidence_df()) == []


def test_attach_three_ids_two_records_one_unresolved_tracks_counts_and_urls():
    report = pd.DataFrame([{
        "Alternative_Plant": "Plant X",
        "AI_Direct_Human_Outcome_Evidence_Count": 3,
        "Direct_Human_Outcome_Evidence_IDs": "E1;E2;MISSING",
    }])
    out = attach_human_evidence_source_traceability(report, _evidence_df())
    row = out.iloc[0]
    assert row["Human_Evidence_Source_Count"] == 3
    assert row["Human_Evidence_Resolved_Source_Count"] == 2
    assert row["Human_Evidence_Unresolved_Source_Count"] == 1
    assert row["Human_Evidence_Primary_Source_Title"] == "Randomized clinical trial of botanical X"
    assert row["Human_Evidence_Primary_Source_URL"] == "https://example.org/article/E1"
    urls = json.loads(row["Human_Evidence_Source_URLs"])
    assert urls == ["https://example.org/article/E1", "https://doi.org/10.1000/e2"]
    assert row["Human_Evidence_Source_Resolution_Status"] == "PARTIAL_SOURCE_LINKAGE"


def test_ai_positive_count_without_ids_is_explicit_source_linkage_gap():
    report = pd.DataFrame([{
        "Alternative_Plant": "Plant X",
        "AI_Direct_Human_Outcome_Evidence_Count": 3,
        "Direct_Human_Outcome_Evidence_IDs": "()",
    }])
    out = attach_human_evidence_source_traceability(report, _evidence_df())
    row = out.iloc[0]
    assert row["Human_Evidence_Source_Count"] == 0
    assert row["Human_Evidence_Resolved_Source_Count"] == 0
    assert row["Human_Evidence_Unresolved_Source_Count"] == 3
    assert row["Human_Evidence_Primary_Source_URL"] is None
    assert row["Human_Evidence_Source_Resolution_Status"] == "SOURCE_LINKAGE_INCOMPLETE"


def test_no_human_ids_and_zero_count_is_not_a_linkage_error():
    report = pd.DataFrame([{
        "Alternative_Plant": "Plant X",
        "AI_Direct_Human_Outcome_Evidence_Count": 0,
        "Direct_Human_Outcome_Evidence_IDs": "()",
    }])
    out = attach_human_evidence_source_traceability(report, _evidence_df())
    row = out.iloc[0]
    assert row["Human_Evidence_Unresolved_Source_Count"] == 0
    assert row["Human_Evidence_Source_Resolution_Status"] == "NO_HUMAN_EVIDENCE_IDS"


def test_primary_source_prefers_direct_trial_over_systematic_review():
    report = pd.DataFrame([{
        "Alternative_Plant": "Plant X",
        "Direct_Human_Outcome_Evidence_IDs": "E2;E1",
    }])
    out = attach_human_evidence_source_traceability(report, _evidence_df())
    assert out.loc[0, "Human_Evidence_Primary_Source_Title"] == "Randomized clinical trial of botanical X"


def test_source_json_is_round_trippable_for_ui_detail():
    report = pd.DataFrame([{
        "Alternative_Plant": "Plant X",
        "Direct_Human_Outcome_Evidence_IDs": "E1;E3",
    }])
    out = attach_human_evidence_source_traceability(report, _evidence_df())
    sources = parse_sources_json(out.loc[0, "Human_Evidence_Sources_JSON"])
    assert [s["Evidence_Record_ID"] for s in sources] == ["E1", "E3"]
    assert sources[1]["Resolved_URL"] == "https://pubmed.ncbi.nlm.nih.gov/33333333/"
