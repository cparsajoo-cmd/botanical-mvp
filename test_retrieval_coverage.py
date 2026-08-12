import pandas as pd

from retrieval_coverage import (
    EMA_SOURCE,
    RetrievalCoverageStatus,
    assess_retrieval_coverage,
    aggregate_coverage_status,
)
from botanical_rd_candidate_engine import apply_retrieval_coverage_guard
from final_decision_policy import FinalDecisionStatus
from bulk_collection_progress import progress_status, is_complete_progress_row


def _result(*, checked=None, records=None, errors=None):
    return {
        "sources_checked": checked or [],
        "saved_records": records or [],
        "errors": errors or [],
    }


def _core_checked():
    return [
        "PubMed", "Europe PMC", "LiverTox", "DailyMed", "OpenFDA FAERS",
        EMA_SOURCE,
    ]


def test_eu_clean_retrieval_is_complete_with_declared_regulatory_limitation():
    cov = assess_retrieval_coverage(
        _result(checked=_core_checked()), market="European Union"
    )
    assert cov["status"] == RetrievalCoverageStatus.COMPLETE_WITH_LIMITATIONS.value
    assert cov["missing_required_sources"] == []
    assert any("EMA/HMPC" in x for x in cov["limitations"])


def test_zero_records_is_not_retrieval_failure_when_sources_completed():
    cov = assess_retrieval_coverage(
        _result(checked=_core_checked(), records=[]), market="European Union"
    )
    assert cov["status"] == RetrievalCoverageStatus.COMPLETE_WITH_LIMITATIONS.value


def test_one_primary_literature_lane_failure_is_limitation_not_false_absence():
    cov = assess_retrieval_coverage(
        _result(
            checked=_core_checked(),
            errors=[{"source": "PubMed", "error": "Timed out"}],
        ),
        market="European Union",
    )
    assert cov["status"] == RetrievalCoverageStatus.COMPLETE_WITH_LIMITATIONS.value
    assert not cov["missing_required_sources"]


def test_both_primary_literature_lanes_failed_is_incomplete():
    cov = assess_retrieval_coverage(
        _result(
            checked=_core_checked(),
            errors=[
                {"source": "PubMed", "error": "Timed out"},
                {"source": "Europe PMC", "error": "Timed out"},
            ],
        ),
        market="European Union",
    )
    assert cov["status"] == RetrievalCoverageStatus.INCOMPLETE.value
    assert any("PubMed/Europe PMC" in x for x in cov["missing_required_sources"])


def test_unfinished_plant_is_incomplete_even_if_partial_records_exist():
    cov = assess_retrieval_coverage(
        _result(checked=_core_checked(), records=[{"source": "PubMed"}]),
        market="European Union",
        collection_finished=False,
    )
    assert cov["status"] == RetrievalCoverageStatus.INCOMPLETE.value


def test_canada_without_health_canada_connector_is_incomplete():
    cov = assess_retrieval_coverage(
        _result(checked=_core_checked()), market="Canada"
    )
    assert cov["status"] == RetrievalCoverageStatus.INCOMPLETE.value
    assert any("Health Canada" in x for x in cov["missing_required_sources"])


def test_global_market_is_not_assessable_by_one_regulatory_connector_set():
    cov = assess_retrieval_coverage(
        _result(checked=_core_checked()), market="Global / Multi-market"
    )
    assert cov["status"] == RetrievalCoverageStatus.NOT_ASSESSABLE.value


def test_aggregate_uses_most_conservative_status():
    status = aggregate_coverage_status({
        "A": {"status": "COMPLETE"},
        "B": {"status": "INCOMPLETE"},
    })
    assert status == RetrievalCoverageStatus.INCOMPLETE.value


def _candidate_row(status):
    return {
        "Alternative_Plant": "Plant A",
        "Final_Decision_Status": status,
        "Decision_Class": "old",
        "Eligible_For_Normal_Ranking": True,
        "Ranking_Partition": "normal",
        "Score_Validity": "valid",
        "Requires_Expert_Review": False,
        "Go_Investigate_Hold_NoGo": "Go",
        "Confidence_Note": "",
        "R&D_Opportunity_Score": 90.0,
    }


def test_incomplete_retrieval_caps_go_to_expert_review():
    df = pd.DataFrame([_candidate_row(FinalDecisionStatus.GO.value)])
    out = apply_retrieval_coverage_guard(df, {
        "Plant A": {
            "status": "INCOMPLETE",
            "reason": "missing authority",
            "missing_required_sources": ["Health Canada"],
            "limitations": [],
        }
    })
    row = out.iloc[0]
    assert row["Final_Decision_Status"] == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED.value
    assert row["Eligible_For_Normal_Ranking"] == False
    assert row["Go_Investigate_Hold_NoGo"].startswith("Investigate")


def test_incomplete_retrieval_never_weakens_existing_hard_no_go():
    df = pd.DataFrame([_candidate_row(FinalDecisionStatus.NO_GO_SAFETY.value)])
    out = apply_retrieval_coverage_guard(df, {
        "Plant A": {"status": "INCOMPLETE", "reason": "x", "missing_required_sources": [], "limitations": []}
    })
    assert out.iloc[0]["Final_Decision_Status"] == FinalDecisionStatus.NO_GO_SAFETY.value


def test_complete_with_limitations_does_not_cap_go():
    df = pd.DataFrame([_candidate_row(FinalDecisionStatus.GO.value)])
    out = apply_retrieval_coverage_guard(df, {
        "Plant A": {"status": "COMPLETE_WITH_LIMITATIONS", "reason": "x", "missing_required_sources": [], "limitations": ["limited"]}
    })
    assert out.iloc[0]["Final_Decision_Status"] == FinalDecisionStatus.GO.value


def test_explicit_empty_coverage_map_is_not_assessable_and_caps_go():
    df = pd.DataFrame([_candidate_row(FinalDecisionStatus.GO_WITH_CAUTION.value)])
    out = apply_retrieval_coverage_guard(df, {})
    assert out.iloc[0]["Retrieval_Coverage_Status"] == "NOT_ASSESSABLE"
    assert out.iloc[0]["Final_Decision_Status"] == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED.value


def test_bulk_progress_only_marks_clean_collection_done():
    assert progress_status(error_count=0) == "done"
    assert progress_status(error_count=1) == "retry_required"
    assert progress_status(error_count=1, failed_entirely=True) == "failed"
    assert is_complete_progress_row({"status": "done", "error_count": 0})
    assert not is_complete_progress_row({"status": "done", "error_count": 2})
    assert not is_complete_progress_row({"status": "retry_required", "error_count": 1})
