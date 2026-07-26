"""
Task 6 — pilot-scope evidence coverage: max_results_override precedence.

WHAT THIS COVERS
multi_source_collector._run_one_source()'s and
collect_multi_source_evidence()'s max_results_override parameter — the
mechanism that lets a small number of explicitly pilot-scoped calls
raise every source's per-plant result ceiling uniformly, without
changing any existing caller's behavior (default: None, i.e. no
change).

HOW TO RUN
    pytest -q test_multi_source_collector.py
"""

import multi_source_collector as msc


def _fake_source_config(name="FakeSource", max_results=5):
    return {"name": name, "category": "Test", "priority": 1, "enabled": True, "max_results": max_results}


# ---------------------------------------------------------------------
# _run_one_source — non-PubMed connector precedence
# ---------------------------------------------------------------------

def test_default_behavior_unchanged_non_pubmed_source_uses_its_own_registry_max_results(monkeypatch):
    captured = {}

    def fake_connector(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setitem(msc.CONNECTOR_MAP, "FakeSource", fake_connector)
    msc._run_one_source(
        _fake_source_config(max_results=5), "TestPlant", "TestIndication", "Infusion", "EU",
        max_pubmed_results=3, save=False,
        # max_results_override omitted -> default None -> no behavior change
    )
    assert captured["max_results"] == 5


def test_override_takes_precedence_over_non_pubmed_source_registry_default(monkeypatch):
    captured = {}

    def fake_connector(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setitem(msc.CONNECTOR_MAP, "FakeSource", fake_connector)
    msc._run_one_source(
        _fake_source_config(max_results=5), "TestPlant", "TestIndication", "Infusion", "EU",
        max_pubmed_results=3, save=False, max_results_override=15,
    )
    assert captured["max_results"] == 15


# ---------------------------------------------------------------------
# _run_one_source — PubMed precedence (its own special-cased branch)
# ---------------------------------------------------------------------

def test_default_behavior_unchanged_pubmed_uses_max_pubmed_results(monkeypatch):
    captured = {}

    def fake_pubmed(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(msc, "collect_pubmed_evidence", fake_pubmed)
    msc._run_one_source(
        _fake_source_config(name="PubMed", max_results=5), "TestPlant", "TestIndication",
        "Infusion", "EU", max_pubmed_results=3, save=False,
    )
    assert captured["max_results"] == 3


def test_override_takes_precedence_over_max_pubmed_results_too(monkeypatch):
    captured = {}

    def fake_pubmed(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(msc, "collect_pubmed_evidence", fake_pubmed)
    msc._run_one_source(
        _fake_source_config(name="PubMed", max_results=5), "TestPlant", "TestIndication",
        "Infusion", "EU", max_pubmed_results=3, save=False, max_results_override=15,
    )
    assert captured["max_results"] == 15


# ---------------------------------------------------------------------
# collect_multi_source_evidence — override threads through to every
# enabled source uniformly.
# ---------------------------------------------------------------------

def test_collect_multi_source_evidence_threads_override_to_all_enabled_sources(monkeypatch):
    captured_calls = {}

    def make_fake_connector(name):
        def _fake(**kwargs):
            captured_calls[name] = kwargs.get("max_results")
            return []
        return _fake

    fake_sources = [
        {"name": "Europe PMC", "category": "Test", "priority": 1, "enabled": True, "max_results": 5},
        {"name": "ChEMBL", "category": "Test", "priority": 1, "enabled": True, "max_results": 5},
    ]
    monkeypatch.setattr(msc, "get_enabled_sources", lambda: fake_sources)
    monkeypatch.setitem(msc.CONNECTOR_MAP, "Europe PMC", make_fake_connector("Europe PMC"))
    monkeypatch.setitem(msc.CONNECTOR_MAP, "ChEMBL", make_fake_connector("ChEMBL"))
    monkeypatch.setattr(msc, "collect_pubmed_evidence", None)

    msc.collect_multi_source_evidence(
        scientific_name="TestPlant", indication="TestIndication", dosage_form="Infusion",
        market="EU", save=False, max_results_override=15,
    )

    assert captured_calls == {"Europe PMC": 15, "ChEMBL": 15}


def test_collect_multi_source_evidence_default_none_preserves_per_source_defaults(monkeypatch):
    captured_calls = {}

    def make_fake_connector(name):
        def _fake(**kwargs):
            captured_calls[name] = kwargs.get("max_results")
            return []
        return _fake

    fake_sources = [
        {"name": "Europe PMC", "category": "Test", "priority": 1, "enabled": True, "max_results": 5},
        {"name": "EMA/WHO/ESCOP Regulatory", "category": "Test", "priority": 1, "enabled": True, "max_results": 1},
    ]
    monkeypatch.setattr(msc, "get_enabled_sources", lambda: fake_sources)
    monkeypatch.setitem(msc.CONNECTOR_MAP, "Europe PMC", make_fake_connector("Europe PMC"))
    # "EMA/WHO/ESCOP Regulatory" is special-cased in _run_one_source (no
    # max_results kwarg passed to it at all) — use a distinct fake that
    # doesn't require one, matching that branch's real signature.
    monkeypatch.setitem(
        msc.CONNECTOR_MAP, "EMA/WHO/ESCOP Regulatory",
        lambda **kwargs: captured_calls.__setitem__("EMA/WHO/ESCOP Regulatory", "no max_results kwarg") or [],
    )
    monkeypatch.setattr(msc, "collect_pubmed_evidence", None)

    msc.collect_multi_source_evidence(
        scientific_name="TestPlant", indication="TestIndication", dosage_form="Infusion",
        market="EU", save=False,
        # max_results_override omitted -> default None -> no behavior change
    )

    assert captured_calls["Europe PMC"] == 5


# ---------------------------------------------------------------------
# Existing callers (research_engine.py, pages/Bulk evidence.py) must
# not be forced to pass max_results_override — wiring check only.
# ---------------------------------------------------------------------

def test_research_engine_only_passes_override_when_pilot_mode_is_true():
    with open("research_engine.py", encoding="utf-8") as f:
        source = f.read()
    assert "max_results_override=PILOT_MAX_RESULTS if pilot_mode else None" in source


def test_bulk_evidence_page_does_not_reference_max_results_override():
    # Bulk Evidence Collection is intentionally the separate, ongoing
    # full-database-coverage path (see multi_source_collector.py's own
    # docstring precedent) — Task 6 does not touch its behavior at all.
    with open("pages/Bulk evidence.py", encoding="utf-8") as f:
        source = f.read()
    assert "max_results_override" not in source
