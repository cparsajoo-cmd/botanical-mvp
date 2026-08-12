"""Test for IMPLEMENTATION_PLAN.md Phase 2's evidence_collector.py change:
the PMID search_and_fetch_pubmed() already returns (and this module
already carried separately as item["pmid"] in its own return value) is
now also set on the record itself, so it reaches save_evidence_record()
instead of being dropped before standardization."""

import unittest.mock as mock

import evidence_collector


def test_pubmed_pmid_is_set_on_the_record_passed_to_standardization():
    fake_article = {
        "PMID": "99999", "Title": "Valerian for sleep",
        "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/99999/",
        "Raw_Text": "A randomized controlled trial of valerian for insomnia.",
    }
    captured = {}

    def fake_standardize(extracted, source_metadata):
        captured["extracted"] = dict(extracted)
        return dict(extracted)

    with mock.patch("evidence_collector.search_and_fetch_pubmed", return_value=[fake_article]), \
         mock.patch("evidence_collector.standardize_extracted_record", side_effect=fake_standardize), \
         mock.patch("evidence_collector.save_evidence_record", return_value=1):
        evidence_collector.collect_pubmed_evidence(
            scientific_name="Valeriana officinalis", indication="sleep",
            dosage_form="Infusion", save=True,
        )

    assert captured["extracted"]["PMID"] == "99999"


def test_pubmed_pmid_absent_is_not_fabricated():
    fake_article = {
        "PMID": "", "Title": "X", "Source_URL": "", "Raw_Text": "Some text.",
    }
    captured = {}

    def fake_standardize(extracted, source_metadata):
        captured["extracted"] = dict(extracted)
        return dict(extracted)

    with mock.patch("evidence_collector.search_and_fetch_pubmed", return_value=[fake_article]), \
         mock.patch("evidence_collector.standardize_extracted_record", side_effect=fake_standardize), \
         mock.patch("evidence_collector.save_evidence_record", return_value=1):
        evidence_collector.collect_pubmed_evidence(
            scientific_name="Valeriana officinalis", indication="sleep",
            dosage_form="Infusion", save=True,
        )

    assert not captured["extracted"]["PMID"]


def test_requested_form_and_indication_do_not_overwrite_study_facts():
    """Requested product context must stay separate from source study context."""
    fake_article = {
        "PMID": "77777", "Title": "Extract trial",
        "Source_URL": "https://pubmed.ncbi.nlm.nih.gov/77777/",
        "Raw_Text": (
            "A randomized controlled trial studied a standardized dry extract "
            "administered orally at a dose of 240 mg/day for hypertension."
        ),
    }
    captured = {}

    def fake_standardize(extracted, source_metadata):
        captured["extracted"] = dict(extracted)
        return dict(extracted)

    with mock.patch("evidence_collector.search_and_fetch_pubmed", return_value=[fake_article]), \
         mock.patch("evidence_collector.standardize_extracted_record", side_effect=fake_standardize), \
         mock.patch("evidence_collector.save_evidence_record", return_value=1):
        evidence_collector.collect_pubmed_evidence(
            scientific_name="Example species", indication="sleep",
            dosage_form="Infusion", save=True,
        )

    row = captured["extracted"]
    assert row["Dosage_Form"] == "Extract"
    assert row["Preparation"] == "standardized dry extract"
    assert row["Dose"] == "240 mg/day"
    assert row["Requested_Dosage_Form"] == "Infusion"
    assert row["Requested_Target_Indication"] == "sleep"
    # The collector no longer fabricates the requested target as a source fact.
    assert row.get("Target_Indication", "") != "sleep"
