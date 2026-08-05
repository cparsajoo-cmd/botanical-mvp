"""Direct unit tests for evidence_quality_engine.py.

This module has no importer anywhere in the repository other than the
also-unimported decision_engine.py (see PHASE3_SOURCE_AUTHORITY_AUDIT.md
§1.4/§2.1) — it is not on any live scoring path. The Phase 3 brief still
requires its outcome/quality coupling bug fixed and tested directly,
independent of whether any live caller currently reaches it.
"""
from evidence_quality_engine import assess_evidence_quality, apply_evidence_quality
import pandas as pd


def test_study_hierarchy_points_are_still_awarded():
    result = assess_evidence_quality({"Source_Title": "A randomized controlled trial of chamomile"})
    assert "Randomized study" in result["Evidence_Quality_Flags"]
    assert result["Evidence_Quality_Score"] > 0


def test_positive_outcome_wording_no_longer_raises_quality_score():
    baseline = assess_evidence_quality({"Notes": "A randomized controlled trial"})
    positive = assess_evidence_quality({
        "Notes": "A randomized controlled trial. The treatment was effective, "
                 "showed significant improvement, positive efficacy.",
    })
    assert positive["Evidence_Quality_Score"] == baseline["Evidence_Quality_Score"]


def test_negative_outcome_wording_no_longer_lowers_quality_score():
    baseline = assess_evidence_quality({"Notes": "A randomized controlled trial"})
    negative = assess_evidence_quality({
        "Notes": "A randomized controlled trial. The result was not effective "
                 "and was negative overall.",
    })
    assert negative["Evidence_Quality_Score"] == baseline["Evidence_Quality_Score"]


def test_safety_wording_no_longer_affects_quality_score():
    baseline = assess_evidence_quality({"Notes": "A randomized controlled trial"})
    safety_flagged = assess_evidence_quality({
        "Notes": "A randomized controlled trial. Adverse event reported, contraindicated, warning issued.",
    })
    assert safety_flagged["Evidence_Quality_Score"] == baseline["Evidence_Quality_Score"]


def test_negative_rct_still_classifies_as_high_hierarchy_as_positive_rct():
    """The brief's central example: 'یک RCT منفی باید از نظر quality
    همچنان RCT باکیفیت باشد'."""
    positive = assess_evidence_quality({
        "Notes": "A double-blind placebo-controlled randomized controlled trial. "
                 "Significant improvement was observed.",
    })
    negative = assess_evidence_quality({
        "Notes": "A double-blind placebo-controlled randomized controlled trial. "
                 "No significant difference was found; not effective.",
    })
    assert positive["Evidence_Quality_Score"] == negative["Evidence_Quality_Score"]
    assert positive["Evidence_Quality_Class"] == negative["Evidence_Quality_Class"]


def test_apply_evidence_quality_dataframe_wrapper_still_works():
    df = pd.DataFrame([
        {"Source_Title": "A systematic review and meta-analysis"},
        {"Source_Title": "An in vitro cell line study"},
    ])
    result = apply_evidence_quality(df)
    assert "Evidence_Quality_Score" in result.columns
    assert result.iloc[0]["Evidence_Quality_Score"] > result.iloc[1]["Evidence_Quality_Score"]
