"""Phase 8 market intelligence engine.

Only real market-source records may contribute to Market_Score. Scientific and
regulatory records are explicitly excluded even if their text contains words
such as product, market, EMA, FDA or DailyMed.

Commercial presence is reported on two deliberately separate axes:

* overall plant commercial presence; and
* commercial presence for the *selected indication*.

This prevents a plant sold for one use (for example stress) from being treated
as an established product for a different R&D indication (for example sleep).
Missing indication/claim metadata is kept as UNKNOWN and never converted into
commercial white space.
"""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict
from functools import lru_cache
import re
import pandas as pd

from indication_semantics import resolve_indication_semantics, normalize_indication_text
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

# Fields that explicitly describe a product's intended use/claim.  If at least
# one of these is populated, a non-match is informative.  Product names and
# descriptions can establish a positive indication match, but their *silence*
# does not prove the product is for another indication.
_EXPLICIT_CLAIM_COLUMNS = (
    "Indication", "Indications", "Claim", "Claims", "Product_Claim",
    "Product_Claims", "Health_Claim", "Health_Claims", "Intended_Use",
    "Intended_Uses", "Use", "Uses", "Purpose", "Purposes",
)
_DESCRIPTIVE_MARKET_COLUMNS = (
    "Product_Name", "product_name", "Source_Title", "Description",
    "Product_Description", "Marketing_Description", "Title", "Snippet",
)
_MARKET_SCOPE_COLUMNS = (
    "Country_Market", "Target_Market", "Market", "market",
)

_UNAVAILABLE_SEARCH_STATES = {
    MarketSearchStatus.SEARCH_NOT_PERFORMED.value,
    MarketSearchStatus.SOURCE_UNAVAILABLE.value,
    MarketSearchStatus.CONNECTOR_NOT_IMPLEMENTED.value,
    MarketSearchStatus.MARKET_NOT_COVERED.value,
}


def _clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "none", "null"} else s


def _norm(v):
    return _clean(v).lower()


def _plant_key_variants(v):
    """Return stable lookup keys for a structured plant-name field.

    Market evidence should carry a structured scientific/common plant name.
    We index the full normalized value and, for scientific names that include
    an author suffix (for example ``Valeriana officinalis L.``), the leading
    binomial.  This gives tolerant structured matching without ever scanning
    the whole market table per candidate.
    """
    text = _norm(v)
    if not text:
        return ()
    keys = {text}
    tokens = re.findall(r"[a-z0-9×x-]+", text)
    if len(tokens) >= 2:
        keys.add(" ".join(tokens[:2]))
    return tuple(keys)


def _pick(row, *names):
    for name in names:
        if name in row and _clean(row.get(name)):
            return row.get(name)
    return ""


def _joined(row, names):
    values = []
    for name in names:
        if name in row:
            value = _clean(row.get(name))
            if value:
                values.append(value)
    return " | ".join(values)


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


def _first_nonblank_series(df: pd.DataFrame, names) -> pd.Series:
    """Vectorized equivalent of ``_pick`` for dataframe-wide preprocessing.

    It is intentionally used only for market-row/index construction.  Row-level
    evidence semantics continue to use ``_pick`` so the public behavior stays
    unchanged while avoiding ``DataFrame.apply(..., axis=1)`` on large evidence
    tables.
    """
    out = pd.Series("", index=df.index, dtype="object")
    for name in names:
        if name not in df.columns:
            continue
        values = df[name].fillna("").astype(str).str.strip()
        valid = ~values.str.lower().isin({"", "nan", "none", "null"})
        take = out.eq("") & valid
        if take.any():
            out.loc[take] = values.loc[take]
    return out


def _market_row_mask(df: pd.DataFrame) -> pd.Series:
    """Vectorized market-row classifier matching ``_is_market_row`` semantics."""
    if df is None or df.empty:
        return pd.Series(False, index=getattr(df, "index", None), dtype=bool)

    source_type = _first_nonblank_series(df, ("Market_Source_Type", "Source_Type")).str.lower()
    evidence_type = _first_nonblank_series(df, ("Evidence_Type", "Publication_Type", "Study_Type")).str.lower()
    source_org = _first_nonblank_series(df, ("Source_Organization", "Source", "Seller", "Retailer")).str.lower()
    combined = source_type.str.cat(evidence_type, sep=" ").str.cat(source_org, sep=" ")

    excluded = pd.Series(False, index=df.index)
    for term in _EXCLUDED_SOURCE_TERMS:
        excluded |= combined.str.contains(re.escape(term), regex=True, na=False)

    explicit_market_source = source_type.isin(_MARKET_SOURCE_TYPES)
    product = _first_nonblank_series(df, ("Product_Name", "product_name"))
    seller = _first_nonblank_series(df, ("Brand", "brand", "Retailer", "Seller", "seller"))
    structured_product = product.ne("") & seller.ne("")
    return (~excluded) & (explicit_market_source | structured_product)


def _market_scope_mask(df: pd.DataFrame, market: str) -> pd.Series:
    """Rows that are compatible with the requested market.

    Blank market scope is retained because some structured product sources are
    multi-market.  A row explicitly scoped to another market is not used to
    prove presence or absence in the requested one.
    """
    if not market:
        return pd.Series(True, index=df.index)
    target = _norm(market)
    available = [c for c in _MARKET_SCOPE_COLUMNS if c in df.columns]
    if not available:
        return pd.Series(True, index=df.index)
    scope = df[available].fillna("").astype(str).agg(" ".join, axis=1).str.lower().str.strip()
    return scope.eq("") | scope.str.contains(re.escape(target), regex=True, na=False)


@lru_cache(maxsize=256)
def _indication_phrases(indication: str) -> tuple[str, ...]:
    """Direct commercial-claim phrases for a canonical or free-text indication.

    Mechanism-only terms are intentionally excluded: a product saying "GABA"
    is not automatically a marketed insomnia product.  For known indication
    families we use the canonical name + aliases + direct outcome terms.  For
    free text we fall back to meaningful tokens/phrases.

    Pure function of ``indication`` alone (INDICATION_SEMANTICS is a fixed
    module-level table), so this is cached: ``_classify_indication_row()``
    previously re-resolved the full indication-semantics table once per
    market row being classified, which meant re-doing that resolution for
    every product row of every candidate plant in a Step 5 run instead of
    once per distinct indication.
    """
    indication = _clean(indication)
    if not indication:
        return ()

    family = resolve_indication_semantics(indication)
    raw_terms = [indication]
    if family:
        raw_terms.extend(family.get("aliases", ()))
        raw_terms.extend(family.get("direct", ()))

    normalized = []
    seen = set()
    for term in raw_terms:
        norm = normalize_indication_text(term)
        if not norm:
            continue
        # Generic framing words cannot create a match by themselves.
        if norm in {"support", "health", "comfort", "product", "products"}:
            continue
        if norm not in seen:
            seen.add(norm)
            normalized.append(norm)

    if not family:
        tokens = [
            token for token in normalize_indication_text(indication).split()
            if len(token) >= 4 and token not in {"support", "health", "comfort", "with", "and"}
        ]
        for token in tokens:
            if token not in seen:
                seen.add(token)
                normalized.append(token)

    # Longer phrases first improves traceability of the reported matched terms.
    return tuple(sorted(normalized, key=lambda x: (-len(x.split()), -len(x), x)))


def _contains_phrase(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    # Text/phrase are already normalized to alphanumeric/space.  Word-boundary
    # matching avoids short aliases such as IBS matching inside another word.
    return re.search(r"(?:^|\s)" + re.escape(phrase) + r"(?:$|\s)", text) is not None


def _classify_indication_row(row, indication: str) -> tuple[str, tuple[str, ...]]:
    """Return MATCH, NON_MATCH, UNKNOWN, or NOT_REQUESTED for one product row."""
    phrases = _indication_phrases(indication)
    if not phrases:
        return "NOT_REQUESTED", ()

    explicit_claim_text = normalize_indication_text(_joined(row, _EXPLICIT_CLAIM_COLUMNS))
    descriptive_text = normalize_indication_text(
        " | ".join(
            x for x in (
                _joined(row, _EXPLICIT_CLAIM_COLUMNS),
                _joined(row, _DESCRIPTIVE_MARKET_COLUMNS),
            ) if x
        )
    )
    matched = tuple(phrase for phrase in phrases if _contains_phrase(descriptive_text, phrase))
    if matched:
        return "MATCH", matched
    if explicit_claim_text:
        # We know what the product claims, and the selected indication is absent.
        return "NON_MATCH", ()
    # A generic product name such as "Ashwagandha 500 mg" does not prove either
    # presence or absence for the selected indication.
    return "UNKNOWN", ()


def _record_from_row(row, query: str, market: str, *, indication_match="", matched_terms=()) -> MarketEvidence:
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
        metadata={
            "indication_match": indication_match,
            "matched_indication_terms": list(matched_terms),
            "explicit_claim_text_present": bool(_joined(row, _EXPLICIT_CLAIM_COLUMNS)),
        },
    )


def _commercial_overall_status(search_status: MarketSearchStatus, product_count: int) -> str:
    if search_status.value in _UNAVAILABLE_SEARCH_STATES:
        return "UNKNOWN"
    if product_count > 0:
        return "VERIFIED_MARKETED"
    if search_status == MarketSearchStatus.NO_PRODUCTS_FOUND:
        return "NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES"
    return "UNKNOWN"


def _commercial_indication_status(indication: str, indication_search_status: str, indication_count: int, overall_count: int) -> str:
    if not _clean(indication):
        return "NOT_REQUESTED"
    if indication_count > 0:
        return "VERIFIED_MARKETED_FOR_INDICATION"
    if indication_search_status == MarketSearchStatus.NO_PRODUCTS_FOUND.value:
        return "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES"
    if indication_search_status == MarketSearchStatus.COMPLETED.value and overall_count > 0:
        return "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES"
    if indication_search_status == MarketSearchStatus.INSUFFICIENT_SAMPLE.value and overall_count > 0:
        return "COMMERCIAL_PRESENCE_INDICATION_UNCLEAR"
    if indication_search_status in _UNAVAILABLE_SEARCH_STATES:
        return "UNKNOWN"
    return "UNKNOWN"


def _commercial_novelty_status(overall_status: str, indication_status: str, indication_saturation: str) -> str:
    """Commercial novelty only.  Never uses chemical novelty."""
    if indication_status == "VERIFIED_MARKETED_FOR_INDICATION":
        if indication_saturation == "HIGH":
            return "Established commercial use for selected indication"
        if indication_saturation == "MEDIUM":
            return "Active commercial use for selected indication"
        return "Commercial use verified for selected indication; saturation not established"
    if indication_status == "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES":
        if overall_status == "VERIFIED_MARKETED":
            return "Indication-repurposing white space in covered sources"
        return "Commercial white space in covered sources"
    if indication_status == "COMMERCIAL_PRESENCE_INDICATION_UNCLEAR":
        return "Commercial presence verified; selected-indication positioning unverified"
    if overall_status == "VERIFIED_MARKETED":
        return "Commercial presence verified; indication not assessed"
    if overall_status == "NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES":
        return "No verified commercial product in covered sources"
    return "Commercial novelty not assessed"


def _commercial_positioning(overall_status: str, indication_status: str) -> str:
    if indication_status == "VERIFIED_MARKETED_FOR_INDICATION":
        return "Established / commercially active for selected indication"
    if indication_status == "NO_VERIFIED_PRODUCT_FOR_INDICATION_IN_COVERED_SOURCES":
        if overall_status == "VERIFIED_MARKETED":
            return "Potential indication-repurposing opportunity"
        return "Potential commercial white-space opportunity"
    if indication_status == "COMMERCIAL_PRESENCE_INDICATION_UNCLEAR":
        return "Commercially active overall; indication positioning requires verification"
    if overall_status == "VERIFIED_MARKETED":
        return "Commercially active overall; selected indication not assessed"
    if overall_status == "NO_VERIFIED_PRODUCT_FOUND_IN_COVERED_SOURCES":
        return "No verified commercial product in covered sources"
    return "Market data incomplete — do not classify as new commercial R&D"


class MarketIntelligenceEngine:
    def __init__(self, evidence_df=None):
        if evidence_df is not None:
            self.evidence_df = evidence_df.copy()
        else:
            # Lazy import: market unit tests and non-Supabase deployments should
            # not fail merely by importing this module.
            try:
                from evidence_database import load_evidence_database
                self.evidence_df = load_evidence_database()
            except Exception:
                self.evidence_df = pd.DataFrame()

        self._market_rows = pd.DataFrame()
        if self.evidence_df is not None and not self.evidence_df.empty:
            try:
                # IMPORTANT: do this once, vectorized.  The previous
                # ``DataFrame.apply(_is_market_row, axis=1)`` incurred Python
                # function-call overhead for every evidence row and became a
                # noticeable part of Step 5 on large evidence tables.
                self._market_rows = self.evidence_df[_market_row_mask(self.evidence_df)].copy()
            except Exception:
                # Preserve the historical fail-closed behavior.
                self._market_rows = pd.DataFrame()

        # Per-market cache.  Candidate matching is STRICTLY index based in
        # Step 5: no per-candidate ``str.contains`` fallback is allowed.  The
        # previous fallback reintroduced candidates x market_rows behavior for
        # the common case where a candidate simply had no commercial record.
        self._scope_cache = {}
        self._candidate_match_cache = {}

    def _scoped_market_index(self, market: str):
        key = _norm(market)
        if key in self._scope_cache:
            return self._scope_cache[key]

        market_rows = self._market_rows
        if market:
            scoped = market_rows[_market_scope_mask(market_rows, market)].copy()
            if scoped.empty:
                result = {
                    "rows": scoped,
                    "exact_index": {},
                    "status": MarketSearchStatus.MARKET_NOT_COVERED,
                }
                self._scope_cache[key] = result
                return result
            market_rows = scoped

        searchable_cols = [c for c in market_rows.columns if c.lower() in {
            "scientific_name", "common_name", "plant", "ingredient", "plant_ingredient"
        }]
        if not searchable_cols:
            result = {
                "rows": market_rows,
                "exact_index": {},
                "status": MarketSearchStatus.INSUFFICIENT_SAMPLE,
            }
            self._scope_cache[key] = result
            return result

        searchable = market_rows[searchable_cols].fillna("").astype(str)

        # Build a structured lookup once per market.  Each source value gets
        # its full normalized key plus a scientific-binomial key when present,
        # so author-suffixed names still match without a table-wide substring
        # scan.  A missing key is a constant-time "no row in covered sources"
        # result, not a reason to rescan every market row.
        exact_index = {}
        for col in searchable_cols:
            for idx, value in searchable[col].items():
                for key_variant in _plant_key_variants(value):
                    exact_index.setdefault(key_variant, set()).add(idx)

        result = {
            "rows": market_rows,
            "exact_index": exact_index,
            "status": MarketSearchStatus.COMPLETED,
        }
        self._scope_cache[key] = result
        return result

    def _matched_market_rows(self, scope, terms, market: str):
        """Return candidate-specific rows using only the prebuilt index.

        No dataframe-wide substring fallback is permitted here.  Structured
        market rows are indexed by normalized full name and scientific
        binomial, which is sufficient for the production Step 5 path and keeps
        a true O(candidates + market_rows) matching profile.
        """
        normalized_terms = tuple(sorted({
            key
            for term in terms
            for key in _plant_key_variants(term)
            if key
        }))
        cache_key = (_norm(market), normalized_terms)
        if cache_key in self._candidate_match_cache:
            idxs = self._candidate_match_cache[cache_key]
            return scope["rows"].loc[list(idxs)] if idxs else scope["rows"].iloc[0:0]

        idxs = set()
        exact_index = scope["exact_index"]
        for term in normalized_terms:
            idxs.update(exact_index.get(term, ()))

        frozen = tuple(idxs)
        self._candidate_match_cache[cache_key] = frozen
        return scope["rows"].loc[list(frozen)] if frozen else scope["rows"].iloc[0:0]

    def evaluate(self, row, indication="", dosage_form="", market=""):
        plant = _clean(row.get("Scientific_Name", "") or row.get("Alternative_Plant", ""))
        common = _clean(row.get("Common_Name", ""))
        query = " ".join(x for x in (plant or common, indication, dosage_form) if x).strip()

        if self.evidence_df is None or self.evidence_df.empty or self._market_rows.empty:
            return self._result(
                [], MarketSearchStatus.SEARCH_NOT_PERFORMED, market, "Search not performed",
                indication=indication,
                indication_records=[],
                indication_search_status=MarketSearchStatus.SEARCH_NOT_PERFORMED.value,
            )

        scope = self._scoped_market_index(market)
        market_rows = scope["rows"]
        scope_status = scope["status"]
        if scope_status == MarketSearchStatus.MARKET_NOT_COVERED:
            return self._result(
                [], MarketSearchStatus.MARKET_NOT_COVERED, market,
                "Requested market not covered by available structured market sources",
                indication=indication,
                indication_records=[],
                indication_search_status=MarketSearchStatus.MARKET_NOT_COVERED.value,
            )
        if scope_status == MarketSearchStatus.INSUFFICIENT_SAMPLE:
            return self._result(
                [], MarketSearchStatus.INSUFFICIENT_SAMPLE, market,
                "Insufficient structured market data",
                indication=indication,
                indication_records=[],
                indication_search_status=MarketSearchStatus.INSUFFICIENT_SAMPLE.value,
            )

        # Commercial status is plant-specific.  A shared compound is not enough
        # to prove that the alternative plant itself is marketed.
        terms = [t.lower() for t in (plant, common) if t]
        if not terms:
            return self._result(
                [], MarketSearchStatus.INSUFFICIENT_SAMPLE, market, "No searchable plant term",
                indication=indication,
                indication_records=[],
                indication_search_status=MarketSearchStatus.INSUFFICIENT_SAMPLE.value,
            )

        matched = self._matched_market_rows(scope, terms, market)
        if matched.empty:
            # The covered structured source was actually queried.  This is not
            # equivalent to SEARCH_NOT_PERFORMED, but the absence claim is only
            # scoped to the covered sources/market.
            return self._result(
                [], MarketSearchStatus.NO_PRODUCTS_FOUND, market,
                "No products found in covered market source",
                indication=indication,
                indication_records=[],
                indication_search_status=(
                    MarketSearchStatus.NO_PRODUCTS_FOUND.value
                    if _clean(indication) else "NOT_REQUESTED"
                ),
            )

        records = []
        indication_records = []
        indication_classes = []
        matched_terms = set()
        for _, r in matched.iterrows():
            indication_class, row_terms = _classify_indication_row(r, indication)
            record = _record_from_row(
                r, query, market,
                indication_match=indication_class,
                matched_terms=row_terms,
            )
            records.append(record)
            indication_classes.append(indication_class)
            if indication_class == "MATCH":
                indication_records.append(record)
                matched_terms.update(row_terms)

        if not _clean(indication):
            indication_search_status = "NOT_REQUESTED"
        elif indication_records:
            indication_search_status = MarketSearchStatus.COMPLETED.value
        else:
            known_nonmatches = sum(c == "NON_MATCH" for c in indication_classes)
            unknowns = sum(c == "UNKNOWN" for c in indication_classes)
            if known_nonmatches > 0 and unknowns == 0:
                indication_search_status = MarketSearchStatus.COMPLETED.value
            else:
                # Some/all products lack explicit claims; absence of an
                # indication phrase is not enough to call a repurposing gap.
                indication_search_status = MarketSearchStatus.INSUFFICIENT_SAMPLE.value

        return self._result(
            records, MarketSearchStatus.COMPLETED, market, "Market evidence available",
            indication=indication,
            indication_records=indication_records,
            indication_search_status=indication_search_status,
            matched_indication_terms=sorted(matched_terms),
            indication_unknown_count=sum(c == "UNKNOWN" for c in indication_classes),
            indication_nonmatch_count=sum(c == "NON_MATCH" for c in indication_classes),
        )

    def evaluate_records(self, records, *, search_status=MarketSearchStatus.COMPLETED, market="", indication=""):
        records = list(records)
        indication_records = []
        matched_terms = set()
        if indication:
            phrases = _indication_phrases(indication)
            for record in records:
                metadata = record.metadata or {}
                status = metadata.get("indication_match")
                if status == "MATCH":
                    indication_records.append(record)
                    matched_terms.update(metadata.get("matched_indication_terms") or [])
                    continue
                text = normalize_indication_text(record.product_name or "")
                hits = [p for p in phrases if _contains_phrase(text, p)]
                if hits:
                    indication_records.append(record)
                    matched_terms.update(hits)
            indication_search_status = (
                MarketSearchStatus.COMPLETED.value
                if indication_records
                else MarketSearchStatus.INSUFFICIENT_SAMPLE.value
            )
        else:
            indication_search_status = "NOT_REQUESTED"

        return self._result(
            records, search_status, market, "Market evidence available",
            indication=indication,
            indication_records=indication_records,
            indication_search_status=indication_search_status,
            matched_indication_terms=sorted(matched_terms),
        )

    def _result(
        self,
        records,
        search_status,
        market,
        status_text,
        *,
        indication="",
        indication_records=None,
        indication_search_status="NOT_REQUESTED",
        matched_indication_terms=None,
        indication_unknown_count=0,
        indication_nonmatch_count=0,
    ):
        records = list(records)
        indication_records = list(indication_records or [])
        matched_indication_terms = list(matched_indication_terms or [])

        metrics = compute_market_metrics(records, search_status=search_status, country_market=market)
        scored = score_market(records, metrics)
        stale = sum(r.freshness == FreshnessStatus.STALE for r in records)
        unknown_freshness = sum(r.freshness == FreshnessStatus.UNKNOWN for r in records)
        source_ids = [
            r.source_record_id or r.source_url_or_id
            for r in records if r.source_record_id or r.source_url_or_id
        ]

        if indication_search_status == MarketSearchStatus.COMPLETED.value:
            indication_metric_status = (
                MarketSearchStatus.COMPLETED
                if indication_records
                else MarketSearchStatus.NO_PRODUCTS_FOUND
            )
        elif indication_search_status == MarketSearchStatus.NO_PRODUCTS_FOUND.value:
            indication_metric_status = MarketSearchStatus.NO_PRODUCTS_FOUND
        elif indication_search_status == MarketSearchStatus.INSUFFICIENT_SAMPLE.value:
            indication_metric_status = MarketSearchStatus.INSUFFICIENT_SAMPLE
        elif indication_search_status == MarketSearchStatus.MARKET_NOT_COVERED.value:
            indication_metric_status = MarketSearchStatus.MARKET_NOT_COVERED
        elif indication_search_status == MarketSearchStatus.SOURCE_UNAVAILABLE.value:
            indication_metric_status = MarketSearchStatus.SOURCE_UNAVAILABLE
        else:
            indication_metric_status = MarketSearchStatus.SEARCH_NOT_PERFORMED

        indication_metrics = compute_market_metrics(
            indication_records,
            search_status=indication_metric_status,
            country_market=market,
        )
        indication_scored = score_market(indication_records, indication_metrics)

        overall_status = _commercial_overall_status(search_status, metrics["Product_Count"])
        indication_status = _commercial_indication_status(
            indication,
            indication_search_status,
            indication_metrics["Product_Count"],
            metrics["Product_Count"],
        )
        commercial_novelty = _commercial_novelty_status(
            overall_status,
            indication_status,
            indication_metrics["Market_Saturation"],
        )
        positioning = _commercial_positioning(overall_status, indication_status)

        return {
            **scored,
            **metrics,
            "Market_Status": status_text,
            "Product_Hits": metrics["Product_Count"],  # backward-compatible overall count
            "Overall_Product_Hits": metrics["Product_Count"],
            "Patent_Hits": metrics["Patent_Activity_Count"],
            "Regulatory_Hits": 0,  # regulatory is never market evidence
            "White_Space": "Unknown" if metrics["Market_Saturation"] == "UNKNOWN" else (
                "Low" if metrics["Market_Saturation"] == "HIGH" else "Potential"
            ),
            "Commercial_Status_Overall": overall_status,
            "Commercial_Status_For_Indication": indication_status,
            "Commercial_Novelty_Status": commercial_novelty,
            "Commercial_Positioning": positioning,
            "Indication_Product_Hits": indication_metrics["Product_Count"],
            "Indication_Brand_Count": indication_metrics["Brand_Count"],
            "Indication_Market_Saturation": indication_metrics["Market_Saturation"],
            "Indication_Market_Search_Status": indication_search_status,
            "Indication_Market_Data_Usable": indication_scored["Market_Data_Usable"],
            "Indication_Market_Score": indication_scored["Market_Score"],
            "Indication_Matched_Terms": matched_indication_terms,
            "Indication_Unclear_Product_Count": int(indication_unknown_count),
            "Indication_Explicit_Nonmatch_Product_Count": int(indication_nonmatch_count),
            "Market_Evidence_Count": len(records),
            "Market_Evidence_Source_IDs": source_ids,
            "Market_Stale_Record_Count": stale,
            "Market_Unknown_Freshness_Count": unknown_freshness,
            "Market_Source_Reliability": [round(r.reliability, 2) for r in records],
            "Market_Evidence": [
                {**asdict(r), "freshness": getattr(r.freshness, "value", r.freshness)}
                for r in records
            ],
            "Market_Retrieval_Timestamp": datetime.now(timezone.utc).isoformat(),
        }
