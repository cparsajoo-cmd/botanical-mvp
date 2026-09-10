"""Deterministic commercial-evidence source traceability for Stage 6.

Presentation/provenance layer only -- like evidence_source_resolver.py, this
module never performs a new commercial search and never fabricates a URL. It
normalizes the ``Commercial_Market_Evidence`` list (already produced this
session by MarketIntelligenceEngine.evaluate() -- see
data_contracts.MarketEvidence and step_rd_candidates._attach_commercial_
market_intelligence()) into the same normalized source-bundle shape used for
human and safety evidence (evidence_source_resolver.build_source_bundle()).

Each MarketEvidence record already carries its own source metadata directly
(product/brand/retailer/source_url_or_id) rather than an Evidence_Record_ID
that needs resolving against evidence_df, so this module adapts that shape
into the shared bundle contract instead of calling resolve_evidence_sources().
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd

from evidence_source_resolver import _clean, _valid_http_url  # shared, no fabrication


def _market_evidence_list(value) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    text = _clean(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _normalized_commercial_source(record: dict) -> dict:
    title = _clean(record.get("product_name")) or _clean(record.get("brand"))
    organization = _clean(record.get("source")) or _clean(record.get("seller_retailer"))
    source_type = _clean(record.get("source_type"))
    url = _valid_http_url(record.get("source_url_or_id"))
    return {
        "Product_Name": _clean(record.get("product_name")),
        "Brand": _clean(record.get("brand")),
        "Title": title,
        "Source_Organization": organization,
        "Source_Type": source_type,
        "Retailer": _clean(record.get("seller_retailer")),
        "Country_Market": _clean(record.get("country_market")),
        "Retrieval_Timestamp": _clean(record.get("retrieval_timestamp")),
        "Source_URL": _clean(record.get("source_url_or_id")),
        "Resolved_URL": url,
        "Resolution_Status": "RESOLVED_SOURCE_URL" if url else "INTERNAL_ID_ONLY",
    }


def build_commercial_source_bundle(market_evidence: list[dict]) -> dict:
    """Build the shared source-bundle shape from already-computed market evidence.

    Mirrors evidence_source_resolver.build_source_bundle()'s output shape
    (record_ids/source_count/.../sources) so downstream rendering can treat
    every category uniformly, even though commercial records are keyed by
    retailer/product rather than an Evidence_Record_ID.
    """
    records = market_evidence or []
    sources = [_normalized_commercial_source(r) for r in records]
    resolved = [s for s in sources if s["Resolved_URL"]]
    unresolved = len(sources) - len(resolved)
    urls = [s["Resolved_URL"] for s in sources if s.get("Resolved_URL")]
    titles = [s["Title"] for s in sources if s.get("Title")]

    primary = None
    if sources:
        # Deterministic: the strongest verified DIRECT market source first
        # (per spec §19) -- a source with both a clickable URL and a named
        # product outranks a source with only a count/claim.
        primary = sorted(
            sources,
            key=lambda s: (0 if s["Resolved_URL"] else 1, 0 if s["Title"] else 1, s["Title"] or ""),
        )[0]

    return {
        "record_ids": [],  # commercial records have no Evidence_Record_ID identity
        "source_count": len(sources),
        "resolved_source_count": len(resolved),
        "unresolved_source_count": unresolved,
        "primary_source_title": primary.get("Title") if primary else None,
        "primary_source_url": primary.get("Resolved_URL") if primary else None,
        "source_titles": titles,
        "source_urls": urls,
        "sources": sources,
    }


def attach_commercial_source_traceability(report_df: pd.DataFrame) -> pd.DataFrame:
    """Append Commercial_* source-traceability fields to a Stage-6 frame.

    Reads ``Commercial_Market_Evidence`` if present (already attached by
    ``_attach_commercial_market_intelligence`` this session); if the column
    is absent or a row's search was never performed, this honestly reports
    zero sources rather than inventing one -- matching the existing
    SEARCH_NOT_PERFORMED / PROVIDER_UNAVAILABLE / CONNECTOR_NOT_IMPLEMENTED /
    SEARCH_FAILED vocabulary already produced upstream.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    has_evidence_col = "Commercial_Market_Evidence" in out.columns
    payloads = []
    for _, row in out.iterrows():
        market_evidence = _market_evidence_list(row.get("Commercial_Market_Evidence")) if has_evidence_col else []
        bundle = build_commercial_source_bundle(market_evidence)

        search_status = _clean(row.get("Commercial_Search_Status"))
        overall_status = _clean(row.get("Commercial_Status_Overall"))
        marketed_claim = bool(overall_status) and overall_status.strip().upper() not in {
            "UNKNOWN", "SEARCH_NOT_PERFORMED",
        }

        if bundle["source_count"] > 0:
            resolution_status = (
                "ALL_RECORDS_RESOLVED" if bundle["unresolved_source_count"] == 0
                else "PARTIAL_SOURCE_LINKAGE"
            )
        elif marketed_claim:
            resolution_status = "SOURCE_LINKAGE_INCOMPLETE"
        else:
            resolution_status = search_status or "NOT_ASSESSED"

        payloads.append({
            "Commercial_Source_Count": bundle["source_count"],
            "Commercial_Resolved_Source_Count": bundle["resolved_source_count"],
            "Commercial_Unresolved_Source_Count": bundle["unresolved_source_count"],
            "Commercial_Primary_Source_Title": bundle["primary_source_title"],
            "Commercial_Primary_Source_URL": bundle["primary_source_url"],
            "Commercial_Source_Titles": json.dumps(bundle["source_titles"], ensure_ascii=False),
            "Commercial_Source_URLs": json.dumps(bundle["source_urls"], ensure_ascii=False),
            "Commercial_Sources_JSON": json.dumps(bundle["sources"], ensure_ascii=False),
            "Commercial_Source_Resolution_Status": resolution_status,
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def parse_commercial_sources_json(value) -> list[dict]:
    """Safe inverse of Commercial_Sources_JSON for UI/detail rendering."""
    return _market_evidence_list(value)
