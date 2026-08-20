"""Regression test for outbound-request identification headers.

CONTEXT
During the Step 2 wall-clock investigation (see
test_step2_collection_budget.py), a real run's error export showed CrossRef
(api.crossref.org) returning genuine HTTP 429 rate-limit responses, and
LiverTox (eutils.ncbi.nlm.nih.gov -- the same host PubMed was simultaneously
being 429'd on) timing out on every plant. Two real, verified gaps:

1. crossref_connector.py and patent_connector.py (patent_connector.py is
   itself a CrossRef bibliographic-search proxy -- see its own
   Source_Type field) both called api.crossref.org fully anonymously.
   CrossRef's documented "polite pool" gives identified requests (a
   mailto param) much better throughput/priority than anonymous ones.
   openalex_connector.py already follows this exact pattern for OpenAlex;
   both CrossRef-hitting connectors now do too.

2. livertox_connector.py calls eutils.ncbi.nlm.nih.gov (the same NCBI
   E-utilities host as pubmed_connector.py) but never sent an email or
   api_key param, so it always used NCBI's strictest anonymous rate limit
   (3 req/s) even when an NCBI_API_KEY is configured for PubMed (which
   would raise the shared eutils limit to 10 req/s). It now reuses the
   same NCBI_EMAIL / NCBI_API_KEY environment variables as
   pubmed_connector.py.

These do not guarantee a rate-limited provider recovers instantly, but they
close two verified, self-inflicted gaps (unidentified requests are always
treated worse by these APIs than identified ones) and this test locks the
fix in place.

HOW TO RUN
    pytest -q test_connector_identification_headers.py
"""
import os

import crossref_connector
import patent_connector
import livertox_connector
import pubmed_connector


def test_crossref_connector_sends_mailto_when_contact_email_configured(monkeypatch):
    monkeypatch.setenv("CROSSREF_CONTACT_EMAIL", "hamid@example.com")
    # Reload the module-level constant the way the connector reads it.
    import importlib
    importlib.reload(crossref_connector)

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        class _Resp:
            def raise_for_status(self_inner):
                pass
            def json(self_inner):
                return {"message": {"items": []}}
        return _Resp()

    monkeypatch.setattr(crossref_connector.requests, "get", fake_get)
    crossref_connector.search_crossref("Test Plant", "Cough")

    assert captured["params"].get("mailto") == "hamid@example.com"
    importlib.reload(crossref_connector)  # restore for other tests


def test_patent_connector_sends_mailto_when_contact_email_configured(monkeypatch):
    monkeypatch.setenv("CROSSREF_CONTACT_EMAIL", "hamid@example.com")
    import importlib
    importlib.reload(patent_connector)

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        class _Resp:
            def raise_for_status(self_inner):
                pass
            def json(self_inner):
                return {"message": {"items": []}}
        return _Resp()

    monkeypatch.setattr(patent_connector.requests, "get", fake_get)
    patent_connector.search_patents("Test Plant", "Cough")

    assert captured["params"].get("mailto") == "hamid@example.com"
    importlib.reload(patent_connector)  # restore for other tests


def test_livertox_connector_reuses_ncbi_email_and_api_key(monkeypatch):
    monkeypatch.setenv("NCBI_EMAIL", "hamid@example.com")
    monkeypatch.setenv("NCBI_API_KEY", "test-key-123")
    import importlib
    importlib.reload(livertox_connector)
    importlib.reload(pubmed_connector)

    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        class _Resp:
            def raise_for_status(self_inner):
                pass
            def json(self_inner):
                return {"esearchresult": {"idlist": []}}
        return _Resp()

    monkeypatch.setattr(livertox_connector.requests, "get", fake_get)
    livertox_connector.search_livertox("Test Plant", "Cough")

    assert captured["params"].get("email") == "hamid@example.com"
    assert captured["params"].get("api_key") == "test-key-123"
    # LiverTox must use the SAME env vars as PubMed, not a second,
    # independently-configured pair.
    assert livertox_connector.NCBI_EMAIL == pubmed_connector.DEFAULT_EMAIL
    assert livertox_connector.NCBI_API_KEY == pubmed_connector.API_KEY
    importlib.reload(livertox_connector)  # restore for other tests
    importlib.reload(pubmed_connector)
