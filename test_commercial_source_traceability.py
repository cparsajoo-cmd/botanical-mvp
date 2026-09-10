import json

import pandas as pd

from commercial_source_traceability import (
    attach_commercial_source_traceability,
    build_commercial_source_bundle,
    parse_commercial_sources_json,
)


def _market_evidence_record(**overrides):
    record = {
        "source": "RetailerCo",
        "source_type": "Retailer product page",
        "product_name": "Botanical X Extract 500mg",
        "brand": "BrandY",
        "seller_retailer": "RetailerCo",
        "country_market": "US",
        "retrieval_timestamp": "2026-09-01T00:00:00Z",
        "source_url_or_id": "https://example.com/product/123",
    }
    record.update(overrides)
    return record


def test_zero_market_evidence_yields_zero_bundle():
    bundle = build_commercial_source_bundle([])
    assert bundle["source_count"] == 0
    assert bundle["primary_source_url"] is None


def test_one_resolved_market_source():
    bundle = build_commercial_source_bundle([_market_evidence_record()])
    assert bundle["source_count"] == 1
    assert bundle["resolved_source_count"] == 1
    assert bundle["primary_source_url"] == "https://example.com/product/123"
    assert bundle["primary_source_title"] == "Botanical X Extract 500mg"


def test_invalid_url_is_not_fabricated_into_a_link():
    bundle = build_commercial_source_bundle([
        _market_evidence_record(source_url_or_id="internal-id-789")
    ])
    assert bundle["source_count"] == 1
    assert bundle["resolved_source_count"] == 0
    assert bundle["primary_source_url"] is None
    assert bundle["sources"][0]["Resolution_Status"] == "INTERNAL_ID_ONLY"


def test_multiple_sources_prefers_one_with_url_and_title():
    bundle = build_commercial_source_bundle([
        _market_evidence_record(product_name=None, source_url_or_id="not-a-url"),
        _market_evidence_record(),
    ])
    assert bundle["primary_source_url"] == "https://example.com/product/123"


def test_attach_commercial_source_traceability_no_evidence_column():
    report_df = pd.DataFrame([{"Alternative_Plant": "Plantus exampleus"}])
    out = attach_commercial_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Commercial_Source_Count"] == 0
    assert row["Commercial_Primary_Source_URL"] is None


def test_attach_commercial_source_traceability_search_not_performed_is_not_flagged():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Commercial_Market_Evidence": [],
        "Commercial_Search_Status": "SEARCH_NOT_PERFORMED",
        "Commercial_Status_Overall": "UNKNOWN",
    }])
    out = attach_commercial_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Commercial_Source_Count"] == 0
    assert row["Commercial_Source_Resolution_Status"] == "SEARCH_NOT_PERFORMED"


def test_attach_commercial_source_traceability_marketed_claim_without_sources_flags_incomplete():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Commercial_Market_Evidence": [],
        "Commercial_Status_Overall": "VERIFIED_MARKETED",
    }])
    out = attach_commercial_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Commercial_Source_Resolution_Status"] == "SOURCE_LINKAGE_INCOMPLETE"


def test_attach_commercial_source_traceability_with_real_records():
    report_df = pd.DataFrame([{
        "Alternative_Plant": "Plantus exampleus",
        "Commercial_Market_Evidence": [_market_evidence_record()],
        "Commercial_Status_Overall": "VERIFIED_MARKETED",
    }])
    out = attach_commercial_source_traceability(report_df)
    row = out.iloc[0]
    assert row["Commercial_Source_Count"] == 1
    assert row["Commercial_Primary_Source_URL"] == "https://example.com/product/123"
    assert row["Commercial_Source_Resolution_Status"] == "ALL_RECORDS_RESOLVED"


def test_parse_commercial_sources_json_roundtrip():
    bundle = build_commercial_source_bundle([_market_evidence_record()])
    text = json.dumps(bundle["sources"])
    parsed = parse_commercial_sources_json(text)
    assert parsed[0]["Product_Name"] == "Botanical X Extract 500mg"


def test_empty_report_df_returns_unchanged():
    empty = pd.DataFrame()
    assert attach_commercial_source_traceability(empty).empty
