"""Phase 8 — canonical, conservative Market Evidence model and metrics.

Market evidence is deliberately independent from scientific efficacy evidence and
regulatory status. Missing/unavailable searches are states, never opportunity.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from statistics import median
from typing import Any, Iterable, Optional

from data_contracts import MarketEvidence
import math
import re


class MarketSearchStatus(str, Enum):
    COMPLETED = "COMPLETED"
    NO_PRODUCTS_FOUND = "NO_PRODUCTS_FOUND"
    SEARCH_NOT_PERFORMED = "SEARCH_NOT_PERFORMED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    CONNECTOR_NOT_IMPLEMENTED = "CONNECTOR_NOT_IMPLEMENTED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    MARKET_NOT_COVERED = "MARKET_NOT_COVERED"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


SOURCE_RELIABILITY = {
    "major retailer": 0.90,
    "official manufacturer": 0.85,
    "marketplace": 0.65,
    "market research source": 0.80,
    "patent database": 0.90,
    "search engine proxy": 0.45,
    "unknown source": 0.25,
}

DEFAULT_FRESHNESS_DAYS = 90


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "null"} else text


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", _clean(value).lower()).strip()


def _float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_timestamp(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        dt = value
    else:
        text = _clean(value)
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def freshness_status(retrieved_at: Any, *, now: Optional[datetime] = None, threshold_days: int = DEFAULT_FRESHNESS_DAYS) -> FreshnessStatus:
    dt = parse_timestamp(retrieved_at)
    if dt is None:
        return FreshnessStatus.UNKNOWN
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return FreshnessStatus.FRESH if now.astimezone(timezone.utc) - dt <= timedelta(days=threshold_days) else FreshnessStatus.STALE


def source_reliability(source_type: Any) -> float:
    return SOURCE_RELIABILITY.get(_norm(source_type), SOURCE_RELIABILITY["unknown source"])


def product_identity(record: MarketEvidence) -> tuple:
    """Stable product identity for de-duplicating mirrored/repeated listings."""
    product = _norm(record.product_name)
    brand = _norm(record.brand)
    prep = _norm(record.preparation)
    form = _norm(record.dosage_form)
    ingredient = _norm(record.plant_ingredient)
    if product or brand:
        return (brand, product, prep, form, ingredient)
    return (_norm(record.source_url_or_id), _norm(record.seller_retailer), ingredient, prep, form)


def deduplicate_products(records: Iterable[MarketEvidence]) -> list[MarketEvidence]:
    best: dict[tuple, MarketEvidence] = {}
    for record in records:
        if record.evidence_kind != "retail":
            continue
        key = product_identity(record)
        if not any(key):
            continue
        current = best.get(key)
        rank = (record.reliability, record.confidence, 1 if str(record.freshness) in {FreshnessStatus.FRESH.value, str(FreshnessStatus.FRESH)} else 0)
        if current is None:
            best[key] = record
        else:
            current_rank = (current.reliability, current.confidence, 1 if current.freshness == FreshnessStatus.FRESH else 0)
            if rank > current_rank:
                best[key] = record
    return list(best.values())


def _comparable_prices(records: Iterable[MarketEvidence]) -> list[float]:
    # Only positive prices with a known, single common currency are comparable.
    valid = [(r.price, _norm(r.currency)) for r in records if r.price is not None and r.price > 0 and _norm(r.currency)]
    currencies = {currency for _, currency in valid}
    if len(currencies) != 1:
        return []
    return [float(price) for price, _ in valid]


def compute_market_metrics(records: Iterable[MarketEvidence], *, search_status: MarketSearchStatus, country_market: str = "") -> dict:
    records = list(records)
    retail = deduplicate_products(r for r in records if r.evidence_kind == "retail")
    target_market = _norm(country_market)
    if target_market:
        retail = [r for r in retail if not _norm(r.country_market) or _norm(r.country_market) == target_market]

    brands = {_norm(r.brand) for r in retail if _norm(r.brand)}
    retailers = {_norm(r.seller_retailer or r.source) for r in retail if _norm(r.seller_retailer or r.source)}
    dosage_forms = {_norm(r.dosage_form) for r in retail if _norm(r.dosage_form)}
    preparations = {_norm(r.preparation) for r in retail if _norm(r.preparation)}
    prices = _comparable_prices(retail)

    # Saturation requires coverage, not merely a tiny product count from one shop.
    saturation = "UNKNOWN"
    concentration = None
    if len(retail) >= 5 and len(brands) >= 2 and len(retailers) >= 2:
        brand_counts = {}
        for r in retail:
            b = _norm(r.brand) or "<unknown>"
            brand_counts[b] = brand_counts.get(b, 0) + 1
        shares = [count / len(retail) for count in brand_counts.values()]
        concentration = round(sum(s * s for s in shares), 4)  # HHI on 0..1 scale
        diversity = len(dosage_forms) + len(preparations)
        if len(retail) >= 20 or len(brands) >= 10 or concentration <= 0.18:
            saturation = "HIGH"
        elif len(retail) >= 10 or len(brands) >= 5 or diversity >= 5:
            saturation = "MEDIUM"
        else:
            saturation = "LOW"

    patent_records = [r for r in records if r.evidence_kind == "patent" and _norm(r.source_type) == "patent database"]
    trend_records = [r for r in records if r.evidence_kind == "trend"]

    return {
        "Product_Count": len(retail),
        "Brand_Count": len(brands),
        "Retailer_Count": len(retailers),
        "Price_Min": min(prices) if prices else None,
        "Price_Max": max(prices) if prices else None,
        "Median_Price": median(prices) if prices else None,
        "Price_Currency": retail[0].currency if prices and retail else "",
        "Dosage_Form_Diversity": len(dosage_forms),
        "Preparation_Diversity": len(preparations),
        "Market_Saturation": saturation,
        "Market_Concentration_HHI": concentration,
        "Retail_Availability": "AVAILABLE" if retail else ("NONE_FOUND" if search_status == MarketSearchStatus.NO_PRODUCTS_FOUND else "UNKNOWN"),
        "Trend_Signal_Count": len(trend_records),
        "Patent_Activity_Count": len(patent_records),
        "Search_Status": search_status.value,
    }


def score_market(records: Iterable[MarketEvidence], metrics: dict) -> dict:
    records = list(records)
    status = metrics.get("Search_Status", MarketSearchStatus.SEARCH_NOT_PERFORMED.value)
    unavailable = status in {
        MarketSearchStatus.SEARCH_NOT_PERFORMED.value,
        MarketSearchStatus.SOURCE_UNAVAILABLE.value,
        MarketSearchStatus.CONNECTOR_NOT_IMPLEMENTED.value,
        MarketSearchStatus.MARKET_NOT_COVERED.value,
    }
    if unavailable or not records:
        breakdown = {
            "Demand_Signal": 0.0,
            "Competition_Saturation": 0.0,
            "Price_Opportunity": 0.0,
            "Product_Diversity_Gap": 0.0,
            "Trend_Signal": 0.0,
            "Patent_Activity": 0.0,
            "Data_Confidence": 0.0,
        }
        return {"Market_Score": 0.0, "Market_Score_Breakdown": breakdown, "Market_Data_Usable": False}

    retail = [r for r in records if r.evidence_kind == "retail"]
    trend = [r for r in records if r.evidence_kind == "trend"]
    patent = [r for r in records if r.evidence_kind == "patent" and _norm(r.source_type) == "patent database"]

    reviews = sum(max(0, int(r.review_count or 0)) for r in retail)
    demand = min(25.0, metrics.get("Product_Count", 0) * 2.0 + math.log10(reviews + 1) * 5.0)

    sat = metrics.get("Market_Saturation")
    competition = {"LOW": 15.0, "MEDIUM": 8.0, "HIGH": 2.0}.get(sat, 0.0)

    prices_available = metrics.get("Median_Price") is not None
    price_opportunity = 5.0 if prices_available else 0.0  # presence/quality of comparable price data, not a fabricated margin estimate

    diversity = metrics.get("Dosage_Form_Diversity", 0) + metrics.get("Preparation_Diversity", 0)
    product_gap = 5.0 if sat in {"LOW", "MEDIUM"} and diversity <= 2 else 0.0

    trend_signal = min(10.0, len(trend) * 2.5)
    patent_activity = min(5.0, len(patent) * 1.0)

    if records:
        confidence_values = [max(0.0, min(1.0, r.confidence)) * max(0.0, min(1.0, r.reliability)) for r in records]
        fresh_share = sum(str(r.freshness) in {FreshnessStatus.FRESH.value, str(FreshnessStatus.FRESH)} for r in records) / len(records)
        data_confidence = min(35.0, 25.0 * (sum(confidence_values) / len(confidence_values)) + 10.0 * fresh_share)
    else:
        data_confidence = 0.0

    breakdown = {
        "Demand_Signal": round(demand, 2),
        "Competition_Saturation": round(competition, 2),
        "Price_Opportunity": round(price_opportunity, 2),
        "Product_Diversity_Gap": round(product_gap, 2),
        "Trend_Signal": round(trend_signal, 2),
        "Patent_Activity": round(patent_activity, 2),
        "Data_Confidence": round(data_confidence, 2),
    }
    score = round(min(100.0, sum(breakdown.values())), 2)
    return {"Market_Score": score, "Market_Score_Breakdown": breakdown, "Market_Data_Usable": True}
