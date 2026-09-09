import os

import pytest

from commercial_evidence_provider import (
    dispatch_retail_provider_search,
    SEARCH_NOT_PERFORMED,
    PROVIDER_UNAVAILABLE,
    CONNECTOR_NOT_IMPLEMENTED,
    SEARCH_COMPLETED_RESULTS_FOUND,
    SEARCH_COMPLETED_NO_RESULTS,
    SEARCH_FAILED,
    _PROVIDER_IMPLEMENTATIONS,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("SEARCH_API_KEY", raising=False)
    monkeypatch.delenv("SEARCH_API_PROVIDER", raising=False)
    yield


def test_live_search_disabled_returns_search_not_performed():
    result = dispatch_retail_provider_search("Withania somnifera", use_live_search=False)
    assert result["status"] == SEARCH_NOT_PERFORMED
    assert result["canonical_status"] == SEARCH_NOT_PERFORMED
    assert result["results"] == []


def test_no_api_key_returns_provider_unavailable():
    result = dispatch_retail_provider_search("Withania somnifera", use_live_search=True)
    assert result["status"] == PROVIDER_UNAVAILABLE


def test_api_key_without_provider_name_returns_provider_unavailable(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "fake-key")
    result = dispatch_retail_provider_search("Withania somnifera", use_live_search=True)
    assert result["status"] == PROVIDER_UNAVAILABLE


def test_unrecognized_provider_name_returns_connector_not_implemented(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("SEARCH_API_PROVIDER", "some_unregistered_provider")
    result = dispatch_retail_provider_search("Withania somnifera", use_live_search=True)
    assert result["status"] == CONNECTOR_NOT_IMPLEMENTED


def test_registered_provider_success_returns_results_found(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("SEARCH_API_PROVIDER", "fake_provider")
    _PROVIDER_IMPLEMENTATIONS["fake_provider"] = lambda query, api_key: {
        "results": [{"product": "Fake Product"}]
    }
    try:
        result = dispatch_retail_provider_search("Withania somnifera", use_live_search=True)
        assert result["status"] == SEARCH_COMPLETED_RESULTS_FOUND
        assert result["results"] == [{"product": "Fake Product"}]
    finally:
        del _PROVIDER_IMPLEMENTATIONS["fake_provider"]


def test_registered_provider_no_results_returns_completed_no_results(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("SEARCH_API_PROVIDER", "fake_provider_empty")
    _PROVIDER_IMPLEMENTATIONS["fake_provider_empty"] = lambda query, api_key: {"results": []}
    try:
        result = dispatch_retail_provider_search("Withania somnifera", use_live_search=True)
        assert result["status"] == SEARCH_COMPLETED_NO_RESULTS
    finally:
        del _PROVIDER_IMPLEMENTATIONS["fake_provider_empty"]


def test_registered_provider_that_raises_returns_search_failed(monkeypatch):
    monkeypatch.setenv("SEARCH_API_KEY", "fake-key")
    monkeypatch.setenv("SEARCH_API_PROVIDER", "fake_provider_broken")

    def _boom(query, api_key):
        raise RuntimeError("provider timeout")

    _PROVIDER_IMPLEMENTATIONS["fake_provider_broken"] = _boom
    try:
        result = dispatch_retail_provider_search("Withania somnifera", use_live_search=True)
        assert result["status"] == SEARCH_FAILED
    finally:
        del _PROVIDER_IMPLEMENTATIONS["fake_provider_broken"]


def test_no_real_provider_is_registered_by_default():
    """Section 12: this pass must not silently ship a fabricated/paid
    provider integration -- the registry must be empty out of the box.
    """
    assert _PROVIDER_IMPLEMENTATIONS == {}
