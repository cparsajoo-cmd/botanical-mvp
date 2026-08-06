"""Phase 8 market intelligence engine.

Only real market-source records may contribute to Market_Score. Scientific and
regulatory records are explicitly excluded even if their text contains words
such as product, market, EMA, FDA or DailyMed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict
import pandas as pd

from market_evidence import (
    MarketEvidence,
    MarketSearchStatus,
    FreshnessStatus,
    compute_market_metrics,
    freshness_status,
    score_market,
    source_reliability,
)

_MARKET_SOURCE_TYPES = {
    "major retailer", "official manufacturer", "marketplace",
    "market research source", "search engine proxy",
}
_EXCLUDED_SOURCE_TERMS = (
    "pubmed", "clinical", "journal", "scientific", "ema", "who", "escop",
    "regulatory", "dailymed", "openfda", "fda label", "monograph",
)


def _clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "none", "null"} else s


def _norm(v):
    return _clean(v).lower()


def _pick(row, *names):
    for name in names:
        if name in row and _clean(row.get(name)):
            return row.get(name)
    return ""


def _is_market_row(row) -> bool:
    source_type = _norm(_pick(row, "Market_Source_Type", "Source_Type"))
    evidence_type = _norm(_pick(row, "Evidence_Type", "Publication_Type", "Study_Type"))
    source_org = _norm(_pick(row, "Source_Organization", "Source", "Seller", "Retailer"))
    combined = " ".join((source_type, evidence_type, source_org))
    if any(term in combined for term in _EXCLUDED_SOURCE_TERMS):
        return False
    if source_type in _MARKET_SOURCE_TYPES:
        return True
    # Structured product rows are admissible only if they carry a concrete
    # product/brand/retailer identity, never from prose keyword matches.
    return bool(_clean(_pick(row, "Product_Name", "product_name"))) and bool(
        _clean(_pick(row, "Brand", "brand", "Retailer", "Seller", "seller"))
    )


def _record_from_row(row, query: str, market: str) -> MarketEvidence:
    source_type = _clean(_pick(row, "Market_Source_Type", "Source_Type")) or "Unknown source"
    ts = _pick(row, "Retrieval_Timestamp", "retrieval_timestamp", "Retrieved_At", "last_verified")
    reliability = source_reliability(source_type)
    confidence_raw = _pick(row, "Market_Confidence", "Confidence", "confidence")
    try:
        confidence = float(confidence_raw)
        if confidence > 1:
            confidence /= 100.0
    except (TypeError, ValueError):
        confidence = reliability
    try:
        price = float(_pick(row, "Price", "price"))
    except (TypeError, ValueError):
        price = None
    try:
        reviews = int(float(_pick(row, "Review_Count", "review_count")))
    except (TypeError, ValueError):
        reviews = None
    try:
        rating = float(_pick(row, "Rating", "rating"))
    except (TypeError, ValueError):
        rating = None
    return MarketEvidence(
        source=_clean(_pick(row, "Source_Organization", "Source", "Retailer", "Seller")),
        source_type=source_type,
        query=query,
        country_market=_clean(_pick(row, "Country_Market", "Target_Market", "Market", "market")) or market,
        product_name=_clean(_pick(row, "Product_Name", "product_name", "Source_Title")),
        brand=_clean(_pick(row, "Brand", "brand", "Manufacturer")),
        plant_ingredient=_clean(_pick(row, "Scientific_Name", "Plant", "Ingredient")),
        preparation=_clean(_pick(row, "Preparation", "preparation", "Extraction_Method")),
        dosage_form=_clean(_pick(row, "Dosage_Form", "dosage_form")),
        price=price,
        currency=_clean(_pick(row, "Currency", "currency")),
        availability=_clean(_pick(row, "Availability", "availability", "Availability_Status")),
        review_count=reviews,
        rating=rating,
        seller_retailer=_clean(_pick(row, "Retailer", "Seller", "seller", "Source_Organization")),
        retrieval_timestamp=_clean(ts) or None,
        source_url_or_id=_clean(_pick(row, "Source_URL", "URL", "Source_ID", "source_identifier")),
        freshness=freshness_status(ts),
        confidence=max(0.0, min(1.0, confidence)),
        reliability=reliability,
        source_record_id=_clean(_pick(row, "Evidence_ID", "Record_ID", "id")),
        evidence_kind="retail",
    )


class MarketIntelligenceEngine:
    def __init__(self, evidence_df=None):
        if evidence_df is not None:
            self.evidence_df = evidence_df.copy()
            return
        # Lazy import: market unit tests and non-Supabase deployments should
        # not fail merely by importing this module.
        try:
            from evidence_database import load_evidence_database
            self.evidence_df = load_evidence_database()
        except Exception:
            self.evidence_df = pd.DataFrame()

    def evaluate(self, row, indication="", dosage_form="", market=""):
        plant = _clean(row.get("Scientific_Name", ""))
        common = _clean(row.get("Common_Name", ""))
        compound = _clean(row.get("compound_name", ""))
        query = " ".join(x for x in (plant or common, indication, dosage_form) if x).strip()

        if self.evidence_df is None or self.evidence_df.empty:
            return self._result([], MarketSearchStatus.SEARCH_NOT_PERFORMED, market, "Search not performed")

        market_rows = self.evidence_df[self.evidence_df.apply(_is_market_row, axis=1)].copy()
        if market_rows.empty:
            return self._result([], MarketSearchStatus.SEARCH_NOT_PERFORMED, market, "Search not performed")

        searchable_cols = [c for c in market_rows.columns if c.lower() in {
            "scientific_name", "common_name", "plant", "ingredient", "compound", "compound_name", "product_name"
        }]
        if not searchable_cols:
            return self._result([], MarketSearchStatus.INSUFFICIENT_SAMPLE, market, "Insufficient structured market data")

        haystack = market_rows[searchable_cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
        terms = [t.lower() for t in (plant, common, compound) if t]
        if not terms:
            return self._result([], MarketSearchStatus.INSUFFICIENT_SAMPLE, market, "No searchable market term")
        mask = pd.Series(False, index=market_rows.index)
        for term in terms:
            mask |= haystack.str.contains(term, regex=False, na=False)
        matched = market_rows[mask]
        if matched.empty:
            # The source was covered and queried, so this differs from not performed.
            return self._result([], MarketSearchStatus.NO_PRODUCTS_FOUND, market, "No products found in covered market source")

        records = [_record_from_row(r, query, market) for _, r in matched.iterrows()]
        return self._result(records, MarketSearchStatus.COMPLETED, market, "Market evidence available")

    def evaluate_records(self, records, *, search_status=MarketSearchStatus.COMPLETED, market=""):
        return self._result(list(records), search_status, market, "Market evidence available")

    def _result(self, records, search_status, market, status_text):
        metrics = compute_market_metrics(records, search_status=search_status, country_market=market)
        scored = score_market(records, metrics)
        stale = sum(r.freshness == FreshnessStatus.STALE for r in records)
        unknown_freshness = sum(r.freshness == FreshnessStatus.UNKNOWN for r in records)
        source_ids = [r.source_record_id or r.source_url_or_id for r in records if r.source_record_id or r.source_url_or_id]
        return {
            **scored,
            **metrics,
            "Market_Status": status_text,
            "Product_Hits": metrics["Product_Count"],
            "Patent_Hits": metrics["Patent_Activity_Count"],
            "Regulatory_Hits": 0,  # retained compatibility column; regulatory is never market evidence
            "White_Space": "Unknown" if metrics["Market_Saturation"] == "UNKNOWN" else ("Low" if metrics["Market_Saturation"] == "HIGH" else "Potential"),
            "Market_Evidence_Count": len(records),
            "Market_Evidence_Source_IDs": source_ids,
            "Market_Stale_Record_Count": stale,
            "Market_Unknown_Freshness_Count": unknown_freshness,
            "Market_Source_Reliability": [round(r.reliability, 2) for r in records],
            "Market_Evidence": [{**asdict(r), "freshness": getattr(r.freshness, "value", r.freshness)} for r in records],
            "Market_Retrieval_Timestamp": datetime.now(timezone.utc).isoformat(),
        }
