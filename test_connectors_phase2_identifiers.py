"""Tests for IMPLEMENTATION_PLAN.md Phase 2 connector changes: PMID/DOI/
NCT_ID were already fetched by these connectors (used to build
Source_URL) but discarded before reaching the returned record. Each
connector now keeps the identifier it already has — none of this
infers or fetches anything new."""

import unittest.mock as mock

import europepmc_connector
import crossref_connector
import clinicaltrials_connector


class _FakeHTTPResponse:
    def __init__(self, json_data):
        self._json_data = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_data


def test_europepmc_persists_pmid_and_doi_it_already_fetched():
    payload = {
        "resultList": {"result": [{
            "title": "Valerian for sleep", "abstractText": "A trial.",
            "pubYear": "2020", "pmid": "12345678", "doi": "10.1000/example",
        }]}
    }
    with mock.patch("europepmc_connector.requests.get", return_value=_FakeHTTPResponse(payload)):
        records = europepmc_connector.search_europepmc("Valeriana officinalis", "sleep")
    assert records[0]["PMID"] == "12345678"
    assert records[0]["DOI"] == "10.1000/example"


def test_europepmc_leaves_pmid_and_doi_empty_when_the_api_did_not_provide_them():
    payload = {"resultList": {"result": [{"title": "X", "abstractText": "Y", "pubYear": "2020"}]}}
    with mock.patch("europepmc_connector.requests.get", return_value=_FakeHTTPResponse(payload)):
        records = europepmc_connector.search_europepmc("Valeriana officinalis", "sleep")
    assert records[0]["PMID"] == ""
    assert records[0]["DOI"] == ""


def test_crossref_persists_doi_it_already_fetched():
    payload = {"message": {"items": [{
        "title": ["Valerian review"], "abstract": "An abstract.",
        "DOI": "10.2000/example",
    }]}}
    with mock.patch("crossref_connector.requests.get", return_value=_FakeHTTPResponse(payload)):
        records = crossref_connector.search_crossref("Valeriana officinalis", "sleep")
    assert records[0]["DOI"] == "10.2000/example"


def test_clinicaltrials_persists_nct_id_it_already_fetched():
    payload = {"studies": [{
        "protocolSection": {
            "identificationModule": {"nctId": "NCT01234567", "briefTitle": "A trial"},
            "statusModule": {}, "designModule": {"phases": [], "studyType": "Interventional",
                                                  "enrollmentInfo": {"count": 60}},
            "conditionsModule": {"conditions": ["Insomnia"]},
            "armsInterventionsModule": {"interventions": []},
            "outcomesModule": {"primaryOutcomes": []},
        }
    }]}
    with mock.patch("clinicaltrials_connector.requests.get", return_value=_FakeHTTPResponse(payload)):
        records = clinicaltrials_connector.search_clinicaltrials("Valeriana officinalis", "sleep")
    assert records[0]["NCT_ID"] == "NCT01234567"
    # Confirms Phase 2 didn't touch the pre-existing Sample_Size mapping
    # (already sourced from the same connector's enrollment count).
    assert records[0]["Sample_Size"] == "60"
