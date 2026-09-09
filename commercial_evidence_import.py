"""Structured commercial evidence import (Section 11 of the 2026-09-09
investor-view cahier des charges).

WHAT THIS IS
A live retail-search provider is not wired in yet (see
commercial_evidence_provider.py's docstring for why). Until one is, real
commercial data can still enter the system as a structured import -- a
spreadsheet of already-known products/brands/retailers per plant, produced
by the user or a research assistant, WITHOUT any generative AI. This
module validates and normalizes such an import into the exact column
vocabulary market_intelligence_engine.py already recognizes (its
_is_market_row()/_record_from_row() functions), so imported rows are
picked up by MarketIntelligenceEngine with zero changes to that module --
no new "if imported" branch anywhere downstream.

WHY THE COLUMN NAMES BELOW EXACTLY MATCH THE SPEC'S SECTION 11 LIST
market_intelligence_engine.py already accepts almost this exact vocabulary
(Scientific_Name, Product_Name, Brand, Retailer/Seller, Market_Source_Type,
Country_Market, Indication/Claim/Intended_Use, Dosage_Form, Preparation,
Retrieval_Timestamp) -- confirmed by reading _record_from_row() and
_EXPLICIT_CLAIM_COLUMNS directly rather than assumed. This module is
therefore mostly validation + two column renames
(Retailer_or_Seller -> Retailer, Source_URL_or_ID -> Source_URL), not a
new schema.

VALIDATION RULE (matches _is_market_row()'s own admission rule exactly --
see that function's docstring: "Structured product rows are admissible
only if they carry a concrete product/brand/retailer identity, never from
prose keyword matches")
A row is accepted only if it has:
    - a non-blank plant name (Scientific_Name or Plant), AND
    - EITHER a recognized Market_Source_Type, OR both a non-blank
      Product_Name and a non-blank Brand/Retailer_or_Seller.
Every rejected row is returned with an explicit, specific reason -- never
silently dropped.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

try:
    from market_intelligence_engine import _MARKET_SOURCE_TYPES as _RECOGNIZED_SOURCE_TYPES
except ImportError:  # pragma: no cover - defensive only
    _RECOGNIZED_SOURCE_TYPES = {
        "major retailer", "official manufacturer", "marketplace",
        "market research source", "search engine proxy",
    }

# The import template's column names (Section 11), in the order the spec
# lists them. Only Scientific_Name/Plant is hard-required by this module;
# everything else is optional (Section 11: "Do NOT require every optional
# field.").
COMMERCIAL_EVIDENCE_IMPORT_COLUMNS = [
    "Scientific_Name",   # or "Plant"
    "Product_Name",
    "Brand",
    "Retailer_or_Seller",
    "Market_Source_Type",
    "Country_Market",
    "Indication",        # or "Claim" / "Intended_Use"
    "Dosage_Form",
    "Preparation",
    "Source_URL_or_ID",
    "Retrieval_Timestamp",
]

# raw import column -> market_intelligence_engine.py-recognized column.
# Columns not listed here (Scientific_Name, Product_Name, Brand,
# Market_Source_Type, Country_Market, Indication, Dosage_Form,
# Preparation, Retrieval_Timestamp) are already spelled the way that
# module expects and pass through unchanged.
_RENAME_TO_ENGINE_COLUMNS = {
    "Plant": "Scientific_Name",
    "Retailer_or_Seller": "Retailer",
    "Source_URL_or_ID": "Source_URL",
}


def _clean(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    return "" if s.lower() in {"nan", "none", "null"} else s


def normalize_commercial_evidence_import(raw_df: Optional[pd.DataFrame]):
    """Validates and normalizes a structured commercial-evidence import.

    Returns (normalized_df, rejected_rows):
      - normalized_df: a DataFrame in market_intelligence_engine.py's
        native column vocabulary, containing ONLY rows that pass the
        admission rule above. Empty (not None) if nothing was accepted.
      - rejected_rows: a list of {"row_index": int, "reason": str} for
        every row that did NOT pass, so the caller can show the user
        exactly what was dropped and why (Section 11: "Add validation and
        explicit rejected-row reasons.").

    Never raises on malformed input -- an empty/None/non-DataFrame input
    returns (empty DataFrame, []).
    """
    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame(), []

    df = raw_df.rename(columns=_RENAME_TO_ENGINE_COLUMNS)

    accepted_rows = []
    rejected_rows = []
    for idx, row in df.iterrows():
        plant = _clean(row.get("Scientific_Name"))
        if not plant:
            rejected_rows.append({
                "row_index": int(idx),
                "reason": "Missing plant name (Scientific_Name or Plant).",
            })
            continue

        source_type = _clean(row.get("Market_Source_Type")).lower()
        product_name = _clean(row.get("Product_Name"))
        brand_or_retailer = _clean(row.get("Brand")) or _clean(row.get("Retailer"))

        has_recognized_source_type = source_type in _RECOGNIZED_SOURCE_TYPES
        has_structured_product_identity = bool(product_name) and bool(brand_or_retailer)

        if not (has_recognized_source_type or has_structured_product_identity):
            rejected_rows.append({
                "row_index": int(idx),
                "reason": (
                    "No concrete product identity: needs either a recognized "
                    f"Market_Source_Type ({sorted(_RECOGNIZED_SOURCE_TYPES)}) "
                    "or both Product_Name and Brand/Retailer_or_Seller."
                ),
            })
            continue

        accepted_rows.append(row)

    if not accepted_rows:
        return pd.DataFrame(), rejected_rows

    normalized_df = pd.DataFrame(accepted_rows).reset_index(drop=True)
    return normalized_df, rejected_rows
