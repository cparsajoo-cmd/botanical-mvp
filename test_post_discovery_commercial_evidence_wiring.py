"""Root-cause regression tests: the scientific `evidence_df` collected in
Stage 2 essentially never contains structured market/product rows, so
MarketIntelligenceEngine's ``_market_rows`` was always empty in production
runs -- regardless of which candidates the selector chose
(test_post_discovery_commercial_enrichment_selector.py already covers
that earlier, separate fix). Every Stage-5 discovery candidate therefore
always fell into the honest-but-unhelpful "Search not performed" branch.

THE FIX
_attach_commercial_market_intelligence() now accepts an optional, separate
``commercial_evidence_df`` (Section 10) which is combined with
``evidence_df`` before MarketIntelligenceEngine is constructed
(_combine_scientific_and_commercial_evidence()). Real commercial rows --
however they got there (a structured import today; a future live
provider) -- are now actually used.
"""

import pandas as pd

import step_rd_candidates as src


def _market_row(plant="Withania somnifera", product="SleepWell Capsules", brand="BrandCo"):
    return {
        "Scientific_Name": plant,
        "Product_Name": product,
        "Brand": brand,
        "Retailer": "Herbal Marketplace",
        "Market_Source_Type": "Marketplace",
        "Country_Market": "FR",
        "Indication": "sleep",
        "Retrieval_Timestamp": "2026-09-01T00:00:00+00:00",
    }


def _scientific_evidence_row(plant="Withania somnifera"):
    """A row shaped like real Stage-2 scientific evidence -- no product/
    brand/retailer identity, so it must never be picked up as a market row.
    """
    return {
        "Alternative_Plant": plant,
        "Source_Type": "PubMed",
        "Evidence_Type": "Clinical study",
        "Primary_Outcome": "Reduced sleep latency",
        "Result_Direction": "Positive",
    }


def test_scientific_evidence_df_alone_still_falls_through_to_search_not_performed():
    """Non-regression / documents the bug scenario: with ONLY scientific
    evidence and no commercial_evidence_df, the honest neutral defaults
    are still what's returned (this is not itself wrong -- it's what
    "we truly have no commercial data" should look like).
    """
    out = pd.DataFrame([{"Alternative_Plant": "Withania somnifera"}])
    scientific_evidence_df = pd.DataFrame([_scientific_evidence_row()])
    result = src._attach_commercial_market_intelligence(
        out,
        evidence_df=scientific_evidence_df,
        indication="sleep",
        dosage_form="capsule",
        market="FR",
    )
    assert result.loc[0, "Commercial_Search_Status"] == "SEARCH_NOT_PERFORMED"
    assert result.loc[0, "Commercial_Novelty_Status"] == "Commercial novelty not assessed"


def test_dedicated_commercial_evidence_df_populates_real_product_data():
    """The actual fix: a separate commercial_evidence_df with real product
    rows must be used, even though scientific evidence_df has none.
    """
    out = pd.DataFrame([{"Alternative_Plant": "Withania somnifera"}])
    scientific_evidence_df = pd.DataFrame([_scientific_evidence_row()])
    commercial_evidence_df = pd.DataFrame([_market_row()])

    result = src._attach_commercial_market_intelligence(
        out,
        evidence_df=scientific_evidence_df,
        commercial_evidence_df=commercial_evidence_df,
        indication="sleep",
        dosage_form="capsule",
        market="FR",
    )
    assert result.loc[0, "Commercial_Search_Status"] != "SEARCH_NOT_PERFORMED"
    assert result.loc[0, "Overall_Product_Hits"] >= 1


def test_commercial_evidence_df_alone_without_scientific_evidence_also_works():
    out = pd.DataFrame([{"Alternative_Plant": "Withania somnifera"}])
    commercial_evidence_df = pd.DataFrame([_market_row()])

    result = src._attach_commercial_market_intelligence(
        out,
        evidence_df=pd.DataFrame(),
        commercial_evidence_df=commercial_evidence_df,
        indication="sleep",
        dosage_form="capsule",
        market="FR",
    )
    assert result.loc[0, "Overall_Product_Hits"] >= 1


def test_scientific_rows_never_get_misclassified_as_market_rows_when_combined():
    """Guard against over-correction: concatenating the two frames must
    not cause scientific rows to be swept into the market-row count --
    only actual product/brand-shaped rows count.
    """
    out = pd.DataFrame([{"Alternative_Plant": "Withania somnifera"}])
    # Ten scientific rows, one real market row -- product count must
    # reflect only the one legitimate product row, not eleven.
    scientific_evidence_df = pd.DataFrame([_scientific_evidence_row() for _ in range(10)])
    commercial_evidence_df = pd.DataFrame([_market_row()])

    result = src._attach_commercial_market_intelligence(
        out,
        evidence_df=scientific_evidence_df,
        commercial_evidence_df=commercial_evidence_df,
        indication="sleep",
        dosage_form="capsule",
        market="FR",
    )
    assert result.loc[0, "Overall_Product_Hits"] == 1


def test_missing_commercial_evidence_df_is_fully_backward_compatible():
    """Existing callers that never pass commercial_evidence_df (the
    default None) must behave byte-for-byte as before this change.
    """
    out = pd.DataFrame([{"Alternative_Plant": "Plant A"}])
    result_without_kwarg = src._attach_commercial_market_intelligence(
        out, evidence_df=pd.DataFrame(), indication="sleep", dosage_form="capsule", market="FR",
    )
    result_with_none = src._attach_commercial_market_intelligence(
        out, evidence_df=pd.DataFrame(), commercial_evidence_df=None,
        indication="sleep", dosage_form="capsule", market="FR",
    )
    pd.testing.assert_frame_equal(result_without_kwarg, result_with_none)


def test_combine_helper_handles_all_none_and_empty_combinations():
    combine = src._combine_scientific_and_commercial_evidence
    assert combine(None, None) is None
    empty = pd.DataFrame()
    assert combine(empty, None) is empty
    only_commercial = pd.DataFrame([_market_row()])
    result = combine(None, only_commercial)
    assert len(result) == 1
    only_scientific = pd.DataFrame([_scientific_evidence_row()])
    result = combine(only_scientific, pd.DataFrame())
    assert len(result) == 1
    combined = combine(only_scientific, only_commercial)
    assert len(combined) == 2
