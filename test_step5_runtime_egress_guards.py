"""Regression tests for Step 5 runtime/Egress safeguards.

These tests intentionally do not change any scoring expectation. They cover only
transport/runtime behavior added after the Streamlit Cloud cache-stampede audit.
"""

import pandas as pd

import step_rd_candidates as src
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def test_candidate_discovery_run_key_reuses_exact_inputs_and_invalidates_changes():
    evidence = pd.DataFrame([
        {"Evidence_Record_ID": 1, "Scientific_Name": "Plant A", "Target_Indication": "Cough"}
    ])
    kwargs = dict(
        indication="Cough",
        dosage_form="Infusion",
        market="European Union",
        reference_plant="",
        reference_compound="",
        discovery_mode="indication",
        use_live_search=False,
        evidence_df=evidence,
    )
    key1 = src._candidate_discovery_run_key(**kwargs)
    key2 = src._candidate_discovery_run_key(**kwargs)
    assert key1 == key2

    changed = dict(kwargs)
    changed["indication"] = "Migraine"
    assert src._candidate_discovery_run_key(**changed) != key1


def test_candidate_discovery_process_lock_is_singleton_and_nonblocking():
    lock1 = src._candidate_discovery_process_lock()
    lock2 = src._candidate_discovery_process_lock()
    assert lock1 is lock2

    assert lock1.acquire(blocking=False) is True
    try:
        # A second concurrent Streamlit script thread must not be able to start
        # another Step 5 job while the first one owns the process lock.
        assert lock2.acquire(blocking=False) is False
    finally:
        lock1.release()


def test_cached_engine_injects_cached_evidence_records_instead_of_self_fetch(monkeypatch):
    plant_compounds = pd.DataFrame([{"scientific_name": "Plant A", "compound_name": "X"}])
    compound_profiles = pd.DataFrame([{"compound": "X"}])
    scientific_evidence = pd.DataFrame([{"plant": "Plant A"}])
    evidence_records = pd.DataFrame([{"Evidence_Record_ID": 1, "Scientific_Name": "Plant A"}])
    canonical_evidence = pd.DataFrame([{"Evidence_Record_ID": 1, "Scientific_Name": "Plant A"}])

    monkeypatch.setattr(src, "_cached_plant_compounds_df", lambda: (plant_compounds, True))
    monkeypatch.setattr(src, "_cached_compound_profiles_df", lambda: (compound_profiles, True))
    monkeypatch.setattr(src, "_cached_scientific_evidence_df", lambda: (scientific_evidence, True))
    monkeypatch.setattr(src, "_cached_evidence_records_df", lambda: (evidence_records, True))

    captured = {}

    class _FakeEngine:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(src, "BotanicalRDCandidateEngine", _FakeEngine)
    if hasattr(src._cached_engine, "clear"):
        src._cached_engine.clear()

    src._cached_engine(
        False,
        (1, 123),
        "runtime-egress-test",
        _evidence_df=canonical_evidence,
    )

    assert captured["evidence_df"] is canonical_evidence
    assert captured["evidence_records_df"] is evidence_records
    assert captured["data_source_reliable"] is True


def test_indication_run_forwards_optional_progress_callback(monkeypatch):
    seen = {}

    def _fake_discover(engine, indication, dosage_form="", market="", product_type="", progress_callback=None):
        seen["callback"] = progress_callback
        seen["indication"] = indication
        return pd.DataFrame([{"ok": True}])

    import indication_candidate_discovery as module
    monkeypatch.setattr(module, "discover_indication_candidates", _fake_discover)

    engine = BotanicalRDCandidateEngine.__new__(BotanicalRDCandidateEngine)
    callback = lambda *args: None
    out = engine.run(
        indication="Cough",
        discovery_mode="indication",
        progress_callback=callback,
    )

    assert seen["callback"] is callback
    assert seen["indication"] == "Cough"
    assert len(out) == 1
