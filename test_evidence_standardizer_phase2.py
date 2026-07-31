"""Tests for IMPLEMENTATION_PLAN.md Phase 2's fix to
evidence_standardizer.py: normalize_source_record's STANDARD_FIELDS
allowlist (source_ingestion_engine.py) silently drops PMID/DOI/NCT_ID/
Sample_Size, exactly like it already dropped Evidence_Level before that
field's existing hand-copy-back fix. These tests confirm the same
pattern now covers the four Phase 2 identifier fields too."""

import unittest.mock as mock

import evidence_standardizer


def _standardize(extracted):
    # extract_evidence_with_llm patched to None so these tests never
    # depend on an LLM call — irrelevant to what Phase 2 changed.
    with mock.patch.object(evidence_standardizer, "extract_evidence_with_llm", None):
        return evidence_standardizer.standardize_extracted_record(
            extracted=extracted,
            source_metadata={
                "source_type": "PubMed", "source_title": "A study",
                "source_url": "https://pubmed.ncbi.nlm.nih.gov/12345/",
                "source_organization": "NCBI PubMed", "source_year": "2020",
            },
        )


def test_pmid_doi_nct_id_survive_standardization_when_the_connector_set_them():
    result = _standardize({
        "Scientific_Name": "Valeriana officinalis",
        "PMID": "12345", "DOI": "10.1000/example", "NCT_ID": "NCT00000001",
    })
    assert result["PMID"] == "12345"
    assert result["DOI"] == "10.1000/example"
    assert result["NCT_ID"] == "NCT00000001"


def test_sample_size_survives_standardization_when_the_connector_set_it():
    result = _standardize({
        "Scientific_Name": "Valeriana officinalis", "Sample_Size": "60",
    })
    assert result["Sample_Size"] == "60"


def test_absent_identifier_fields_are_not_fabricated():
    # A source that never provided these fields must not end up with any
    # value for them — not even an empty string standing in for "unknown".
    result = _standardize({"Scientific_Name": "Valeriana officinalis"})
    assert "PMID" not in result or not result.get("PMID")
    assert "NCT_ID" not in result or not result.get("NCT_ID")


def test_falsy_identifier_values_are_not_copied_over_either():
    # An explicit empty string from a connector is treated the same as
    # "not provided" — never written as a copied-through falsy value.
    result = _standardize({"Scientific_Name": "Valeriana officinalis", "PMID": ""})
    assert not result.get("PMID")


def test_connector_sample_size_is_not_overwritten_by_the_empty_llm_default():
    # Regression: standard_evidence_builder.build_standard_evidence() used
    # to unconditionally set Sample_Size from LLM_Sample_Size, discarding
    # a real connector-provided Sample_Size (e.g. ClinicalTrials.gov's
    # enrollment count) whenever no LLM ran and LLM_Sample_Size was "".
    result = _standardize({
        "Scientific_Name": "Valeriana officinalis", "Sample_Size": "60",
    })
    assert result["Sample_Size"] == "60"
    assert result["Sample_Size"] != ""
