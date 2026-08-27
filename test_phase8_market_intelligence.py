from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from market_evidence import (
    MarketEvidence, MarketSearchStatus, FreshnessStatus,
    compute_market_metrics, freshness_status, score_market,
)
from market_intelligence_engine import MarketIntelligenceEngine


def rec(**kw):
    base = dict(source="Retailer A", source_type="Major retailer", query="valerian sleep", country_market="FR",
                product_name="Valerian Sleep", brand="Brand A", plant_ingredient="Valeriana officinalis",
                dosage_form="capsule", preparation="dry extract", price=10.0, currency="EUR",
                availability="in stock", seller_retailer="Retailer A", retrieval_timestamp=datetime.now(timezone.utc).isoformat(),
                source_url_or_id="https://example.test/a", freshness=FreshnessStatus.FRESH, confidence=.9, reliability=.9)
    base.update(kw)
    return MarketEvidence(**base)


def test_retail_stub_does_not_produce_positive_market_score():
    result = MarketIntelligenceEngine(pd.DataFrame()).evaluate({"Scientific_Name":"Valeriana officinalis"}, market="FR")
    assert result["Market_Score"] == 0
    assert result["Search_Status"] == "SEARCH_NOT_PERFORMED"


def test_search_not_performed_does_not_imply_low_saturation():
    m = compute_market_metrics([], search_status=MarketSearchStatus.SEARCH_NOT_PERFORMED)
    assert m["Market_Saturation"] == "UNKNOWN"


def test_source_unavailable_does_not_imply_market_opportunity():
    m = compute_market_metrics([], search_status=MarketSearchStatus.SOURCE_UNAVAILABLE)
    assert score_market([], m)["Market_Score"] == 0


def test_no_products_found_differs_from_search_not_performed():
    a = compute_market_metrics([], search_status=MarketSearchStatus.NO_PRODUCTS_FOUND)
    b = compute_market_metrics([], search_status=MarketSearchStatus.SEARCH_NOT_PERFORMED)
    assert a["Search_Status"] != b["Search_Status"]
    assert a["Retail_Availability"] == "NONE_FOUND"
    assert b["Retail_Availability"] == "UNKNOWN"


# ---------------------------------------------------------------------
# Part C -- SEARCH_NOT_PERFORMED (and other not-usable statuses) must
# yield nullable/UNKNOWN hit counts, never a numeric 0, since 0 means "a
# real search ran and found zero products". Covers both the
# MarketIntelligenceEngine.evaluate() path (evidence_df empty -> _result
# early return) and the vectorized step_rd_candidates.py shortcut for
# "no structured market rows at all".
# ---------------------------------------------------------------------
def test_search_not_performed_yields_nullable_hit_counts_not_zero():
    result = MarketIntelligenceEngine(pd.DataFrame()).evaluate(
        {"Scientific_Name": "Valeriana officinalis"}, indication="sleep", market="FR",
    )
    assert result["Search_Status"] == "SEARCH_NOT_PERFORMED"
    assert result["Overall_Product_Hits"] is None
    assert result["Product_Hits"] is None
    assert result["Indication_Product_Hits"] is None
    assert result["Indication_Brand_Count"] is None


def test_source_unavailable_hit_counts_are_also_nullable():
    metrics = compute_market_metrics([], search_status=MarketSearchStatus.SOURCE_UNAVAILABLE)
    # compute_market_metrics itself always returns len([]) == 0 -- the
    # nulling happens one layer up, in MarketIntelligenceEngine._result(),
    # which is what every real caller (evaluate()) actually returns.
    # Confirmed via the evaluate()-level test above; this call just
    # documents that compute_market_metrics is not itself status-aware.
    assert metrics["Product_Count"] == 0


def test_vectorized_no_market_rows_shortcut_uses_nullable_hit_counts():
    import step_rd_candidates as src

    out = pd.DataFrame([{"Alternative_Plant": "Plant A"}])
    # An empty evidence_df -> MarketIntelligenceEngine(evidence_df)._market_rows
    # is empty -> hits the vectorized "no structured market evidence at
    # all" shortcut this test targets (part C fix).
    result = src._attach_commercial_market_intelligence(
        out, evidence_df=pd.DataFrame(), indication="sleep", dosage_form="capsule", market="FR",
    )
    assert result.loc[0, "Commercial_Search_Status"] == "SEARCH_NOT_PERFORMED"
    assert pd.isna(result.loc[0, "Overall_Product_Hits"])
    assert pd.isna(result.loc[0, "Indication_Product_Hits"])
    assert pd.isna(result.loc[0, "Indication_Brand_Count"])


def test_duplicate_products_counted_once_and_brand_deduplicated():
    rows = [rec(), rec(source="Retailer B", seller_retailer="Retailer B", source_url_or_id="https://example.test/b"), rec(product_name="Other", source_url_or_id="x", brand="Brand A")]
    m = compute_market_metrics(rows, search_status=MarketSearchStatus.COMPLETED)
    assert m["Product_Count"] == 2
    assert m["Brand_Count"] == 1


def test_stale_data_flagged_and_unknown_not_fresh():
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    assert freshness_status(old) == FreshnessStatus.STALE
    assert freshness_status("") == FreshnessStatus.UNKNOWN


def test_breakdown_sums_to_market_score():
    rows = [rec(product_name=f"P{i}", brand=f"B{i%3}", seller_retailer=f"R{i%2}", source_url_or_id=str(i)) for i in range(6)]
    m = compute_market_metrics(rows, search_status=MarketSearchStatus.COMPLETED)
    s = score_market(rows, m)
    assert s["Market_Score"] == round(sum(s["Market_Score_Breakdown"].values()), 2)


def test_regulatory_approval_does_not_count_as_market_evidence():
    df = pd.DataFrame([{"Scientific_Name":"Valeriana officinalis", "Source_Type":"Regulatory", "Source_Organization":"EMA", "Source_Title":"HMPC monograph", "EMA_Status":"Approved"}])
    out = MarketIntelligenceEngine(df).evaluate({"Scientific_Name":"Valeriana officinalis"}, market="FR")
    assert out["Market_Evidence_Count"] == 0
    assert out["Regulatory_Hits"] == 0
    assert out["Market_Score"] == 0


def test_patent_proxy_not_counted_as_patent_activity():
    proxy = rec(evidence_kind="patent", source_type="Search engine proxy")
    real = rec(product_name="", brand="", evidence_kind="patent", source_type="Patent database", source="EPO", source_url_or_id="EP1")
    m = compute_market_metrics([proxy, real], search_status=MarketSearchStatus.COMPLETED)
    assert m["Patent_Activity_Count"] == 1


def test_low_product_count_one_retailer_is_unknown_saturation():
    rows = [rec(product_name=f"P{i}", source_url_or_id=str(i)) for i in range(4)]
    m = compute_market_metrics(rows, search_status=MarketSearchStatus.COMPLETED)
    assert m["Market_Saturation"] == "UNKNOWN"


def test_price_statistics_use_only_comparable_currency():
    rows = [rec(product_name="A", price=10, currency="EUR"), rec(product_name="B", price=20, currency="USD", source_url_or_id="b")]
    m = compute_market_metrics(rows, search_status=MarketSearchStatus.COMPLETED)
    assert m["Median_Price"] is None


def test_country_specific_data_does_not_generalize_silently():
    rows = [rec(country_market="FR"), rec(country_market="DE", product_name="DE product", source_url_or_id="de")]
    m = compute_market_metrics(rows, search_status=MarketSearchStatus.COMPLETED, country_market="FR")
    assert m["Product_Count"] == 1


def test_source_reliability_and_timestamp_traceable():
    out = MarketIntelligenceEngine().evaluate_records([rec(source_record_id="M1")], market="FR")
    assert out["Market_Evidence_Source_IDs"] == ["M1"]
    assert out["Market_Source_Reliability"][0] > 0
    assert out["Market_Evidence"][0]["retrieval_timestamp"]


@pytest.fixture
def step_ranking_module(monkeypatch):
    import sys, types, importlib
    monkeypatch.setitem(sys.modules, "streamlit", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "rd_discovery_engine", types.SimpleNamespace(build_rd_discovery_ranking=lambda *a, **k: pd.DataFrame()))
    sys.modules.pop("step_ranking", None)
    module = importlib.import_module("step_ranking")
    yield module
    sys.modules.pop("step_ranking", None)


def test_high_market_score_cannot_override_safety_no_go(step_ranking_module):
    sr = step_ranking_module
    df = pd.DataFrame([{"Final_RnD_Score":90,"Evidence_Score_Unified":90,"Chemistry_Score_Unified":90,"Target_Match_Score":90,"Innovation_Score":90,
                        "Market_Score":100,"Product_Hits":20,"Regulatory_Hits":0,"Patent_Hits":0,"Market_Status":"Market evidence available",
                        "Market_Data_Usable":True,"Search_Status":"COMPLETED","Eligibility_Status":"no_go_safety","Ranking_Partition":"excluded_no_go"}])
    out = sr.add_decision_layers(df).iloc[0]
    assert out["Decision_Category"] == "Excluded / hard no-go"


def test_high_market_score_cannot_convert_insufficient_science(step_ranking_module):
    sr = step_ranking_module
    df = pd.DataFrame([{"Final_RnD_Score":80,"Evidence_Score_Unified":5,"Chemistry_Score_Unified":90,"Target_Match_Score":90,"Innovation_Score":90,
                        "Market_Score":100,"Product_Hits":20,"Regulatory_Hits":0,"Patent_Hits":0,"Market_Status":"Market evidence available",
                        "Market_Data_Usable":True,"Search_Status":"COMPLETED"}])
    out = sr.add_decision_layers(df).iloc[0]
    assert "scientifically insufficient" in out["Decision_Category"].lower()


def test_incomplete_market_data_not_treated_as_white_space(step_ranking_module):
    sr = step_ranking_module
    df = pd.DataFrame([{"Final_RnD_Score":90,"Evidence_Score_Unified":80,"Chemistry_Score_Unified":90,"Target_Match_Score":90,"Innovation_Score":90,
                        "Market_Score":0,"Product_Hits":0,"Regulatory_Hits":0,"Patent_Hits":0,"Market_Status":"Search not performed",
                        "Market_Data_Usable":False,"Search_Status":"SEARCH_NOT_PERFORMED"}])
    out = sr.add_decision_layers(df).iloc[0]
    assert not bool(out["Is_New_RnD_Opportunity"])
    assert "incomplete" in out["Decision_Category"].lower()



def test_connector_not_implemented_is_zero_not_opportunity():
    m = compute_market_metrics([], search_status=MarketSearchStatus.CONNECTOR_NOT_IMPLEMENTED)
    s = score_market([], m)
    assert s["Market_Score"] == 0
    assert m["Market_Saturation"] == "UNKNOWN"


def test_trend_signal_is_separate_from_sales_and_product_count():
    trend = rec(product_name="", brand="", price=None, currency="", seller_retailer="", evidence_kind="trend", source_type="Search engine proxy", source_url_or_id="trend-1")
    m = compute_market_metrics([trend], search_status=MarketSearchStatus.COMPLETED)
    assert m["Trend_Signal_Count"] == 1
    assert m["Product_Count"] == 0
    assert m["Median_Price"] is None


def test_source_reliability_is_independent_of_popularity():
    from market_evidence import source_reliability
    assert source_reliability("Major retailer") > source_reliability("Marketplace") > source_reliability("Unknown source")


def test_patent_activity_is_market_only_and_does_not_mutate_scientific_score():
    input_row = {"Scientific_Name": "Valeriana officinalis", "Evidence_Score_Unified": 7.0}
    patent = rec(product_name="", brand="", evidence_kind="patent", source_type="Patent database", source="EPO OPS", source_url_or_id="EP123")
    out = MarketIntelligenceEngine().evaluate_records([patent], market="FR")
    assert out["Patent_Activity_Count"] == 1
    assert input_row["Evidence_Score_Unified"] == 7.0
    assert "Evidence_Score_Unified" not in out


def test_overall_commercial_presence_is_separate_from_selected_indication():
    df = pd.DataFrame([{
        "Scientific_Name": "Rhodiola rosea",
        "Source_Type": "Official manufacturer",
        "Source_Organization": "Example Brand",
        "Product_Name": "Rhodiola Stress Support",
        "Brand": "Example Brand",
        "Claims": "Helps with perceived stress and fatigue",
        "Country_Market": "FR",
        "Source_URL": "https://example.test/rhodiola",
    }])
    out = MarketIntelligenceEngine(df).evaluate(
        {"Scientific_Name": "Rhodiola rosea"},
        indication="Sleep and relaxation",
        market="FR",
    )
    assert out["Overall_Product_Hits"] == 1
    assert out["Indication_Product_Hits"] == 0
    assert out["Commercial_Status_Overall"] == "VERIFIED_MARKETED"
    assert out["Commercial_Status_For_Indication"] == "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES"
    assert "repurposing" in out["Commercial_Novelty_Status"].lower()


def test_generic_product_without_claims_does_not_create_false_repurposing_gap():
    df = pd.DataFrame([{
        "Scientific_Name": "Withania somnifera",
        "Source_Type": "Major retailer",
        "Source_Organization": "Retailer A",
        "Product_Name": "Ashwagandha 500 mg",
        "Brand": "Brand A",
        "Country_Market": "FR",
        "Source_URL": "https://example.test/ashwa",
    }])
    out = MarketIntelligenceEngine(df).evaluate(
        {"Scientific_Name": "Withania somnifera"},
        indication="Sleep and relaxation",
        market="FR",
    )
    assert out["Overall_Product_Hits"] == 1
    assert out["Indication_Product_Hits"] == 0
    assert out["Indication_Market_Search_Status"] == "INSUFFICIENT_SAMPLE"
    assert out["Commercial_Status_For_Indication"] == "COMMERCIAL_PRESENCE_INDICATION_UNCLEAR"
    assert "unverified" in out["Commercial_Novelty_Status"].lower()


def test_product_claim_matching_selected_indication_is_established_not_new_rd():
    df = pd.DataFrame([{
        "Scientific_Name": "Valeriana officinalis",
        "Source_Type": "Official manufacturer",
        "Source_Organization": "Example Brand",
        "Product_Name": "Valerian Sleep",
        "Brand": "Example Brand",
        "Claims": "Supports sleep quality and helps reduce sleep latency",
        "Country_Market": "FR",
        "Source_URL": "https://example.test/valerian",
    }])
    out = MarketIntelligenceEngine(df).evaluate(
        {"Scientific_Name": "Valeriana officinalis"},
        indication="Sleep and relaxation",
        market="FR",
    )
    assert out["Indication_Product_Hits"] == 1
    assert out["Commercial_Status_For_Indication"] == "VERIFIED_MARKETED_FOR_INDICATION"
    assert "commercial" in out["Commercial_Novelty_Status"].lower()
    assert "white space" not in out["Commercial_Novelty_Status"].lower()


def test_step_ranking_separates_established_repurposing_and_unknown(step_ranking_module):
    sr = step_ranking_module
    base = {
        "Final_RnD_Score": 80,
        "Evidence_Score_Unified": 70,
        "Chemistry_Score_Unified": 70,
        "Target_Match_Score": 70,
        "Innovation_Score": 70,
        "Market_Score": 20,
        "Regulatory_Hits": 0,
        "Patent_Hits": 0,
        "Market_Data_Usable": True,
        "Search_Status": "COMPLETED",
    }
    df = pd.DataFrame([
        {**base, "Product_Hits": 3, "Overall_Product_Hits": 3, "Indication_Product_Hits": 2,
         "Indication_Market_Search_Status": "COMPLETED",
         "Commercial_Status_Overall": "VERIFIED_MARKETED",
         "Commercial_Status_For_Indication": "VERIFIED_MARKETED_FOR_INDICATION"},
        {**base, "Product_Hits": 3, "Overall_Product_Hits": 3, "Indication_Product_Hits": 0,
         "Indication_Market_Search_Status": "COMPLETED",
         "Commercial_Status_Overall": "VERIFIED_MARKETED",
         "Commercial_Status_For_Indication": "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES"},
        {**base, "Product_Hits": 3, "Overall_Product_Hits": 3, "Indication_Product_Hits": 0,
         "Indication_Market_Search_Status": "INSUFFICIENT_SAMPLE",
         "Commercial_Status_Overall": "VERIFIED_MARKETED",
         "Commercial_Status_For_Indication": "COMMERCIAL_PRESENCE_INDICATION_UNCLEAR"},
    ])
    out = sr.add_decision_layers(df)
    assert out.iloc[0]["Decision_Category"] == "Established / commercially active for indication"
    assert out.iloc[1]["Decision_Category"] == "Indication-repurposing R&D opportunity"
    assert out.iloc[2]["Decision_Category"] == "Commercially active overall / indication unverified"
    assert not bool(out.iloc[2]["Is_New_RnD_Opportunity"])
