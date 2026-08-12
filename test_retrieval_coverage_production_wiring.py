import pandas as pd

import research_engine as re


CORE = [
    "PubMed", "Europe PMC", "LiverTox", "DailyMed", "OpenFDA FAERS",
    "EMA/WHO/ESCOP Regulatory",
]


def _wire_single_candidate(monkeypatch, collection_result):
    monkeypatch.setattr(re, "_richer_candidate_plants", lambda **kwargs: ["Heldout plant"])
    monkeypatch.setattr(
        re, "_online_discovered_candidate_plants",
        lambda **kwargs: ([], {"ranked_matches": {}, "connector_errors": []}),
    )
    monkeypatch.setattr(
        re, "rank_global_candidates",
        lambda **kwargs: pd.DataFrame(columns=["Scientific_Name"]),
    )
    monkeypatch.setattr(re.therapeutic_area_registry, "get_candidate_hypotheses", lambda indication: [])
    monkeypatch.setattr(re, "collect_multi_source_evidence", lambda **kwargs: dict(collection_result))


def test_research_engine_exports_per_plant_retrieval_coverage(monkeypatch):
    _wire_single_candidate(monkeypatch, {
        "saved_records": [], "errors": [], "sources_checked": CORE,
    })
    out = re.run_research_engine(
        product_type="botanical", dosage_form="Infusion", indication="test",
        target_market="European Union", global_candidate_count=1, save=False,
    )
    cov = out["retrieval_coverage_by_plant"]["Heldout plant"]
    assert cov["status"] == "COMPLETE_WITH_LIMITATIONS"
    assert out["retrieval_coverage_market"] == "European Union"
    assert out["retrieval_coverage_indication"] == "test"


def test_research_engine_marks_required_source_failure_incomplete(monkeypatch):
    _wire_single_candidate(monkeypatch, {
        "saved_records": [],
        "errors": [{"source": "EMA/WHO/ESCOP Regulatory", "error": "Timed out"}],
        "sources_checked": CORE,
    })
    out = re.run_research_engine(
        product_type="botanical", dosage_form="Infusion", indication="test",
        target_market="European Union", global_candidate_count=1, save=False,
    )
    assert out["retrieval_coverage_by_plant"]["Heldout plant"]["status"] == "INCOMPLETE"
    assert out["retrieval_coverage_status"] == "INCOMPLETE"
