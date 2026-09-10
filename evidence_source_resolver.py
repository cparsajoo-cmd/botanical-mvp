"""Deterministic evidence-record -> source metadata resolution for Stage 6.

This module is presentation/traceability infrastructure only.  It never
retrieves new scientific evidence, never calls AI/network services, and never
changes scoring or candidate decisions.  It resolves evidence IDs already
present on a candidate against the evidence_df already loaded in session.

Human evidence is the first consumer, but the normalized source contract is
intentionally category-agnostic so safety/mechanism/commercial/regulatory
traceability can reuse it later.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from evidence_id_parsing import normalize_evidence_ids
from standard_evidence_builder import get_scientific_evidence_by_ids

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
_PMID_RE = re.compile(r"^\d{1,12}$")
_MISSING = {"", "none", "nan", "null", "na", "n/a"}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text or text.lower() in _MISSING:
        return None
    return text


def _valid_http_url(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except Exception:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return text


def _normalize_doi(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    lowered = text.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    text = text.rstrip(".,; ")
    return text if _DOI_RE.match(text) else None


def _normalize_pmid(value: Any) -> str | None:
    text = _clean(value)
    if not text:
        return None
    lowered = text.lower()
    for prefix in (
        "pmid:",
        "https://pubmed.ncbi.nlm.nih.gov/",
        "http://pubmed.ncbi.nlm.nih.gov/",
    ):
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip().strip("/")
            break
    text = text.strip().strip("/")
    return text if _PMID_RE.match(text) else None


def resolve_external_url(*, source_url=None, doi=None, pmid=None) -> tuple[str | None, str]:
    """Resolve one clickable external URL without fabricating a source.

    Precedence: valid original Source_URL -> DOI -> PMID -> no external URL.
    Returns (url, resolution_status).
    """
    valid_source_url = _valid_http_url(source_url)
    if valid_source_url:
        return valid_source_url, "RESOLVED_SOURCE_URL"

    # Some legacy rows stored a DOI/PMID token in the broad Source_URL /
    # ScientificEvidence.doi_pmid_url slot rather than a dedicated column.
    # Treat it as a DOI/PMID only when it validates as such; never turn an
    # arbitrary malformed URL/string into a fabricated link.
    normalized_doi = _normalize_doi(doi) or _normalize_doi(source_url)
    if normalized_doi:
        return f"https://doi.org/{normalized_doi}", "RESOLVED_DOI"

    normalized_pmid = _normalize_pmid(pmid) or _normalize_pmid(source_url)
    if normalized_pmid:
        return f"https://pubmed.ncbi.nlm.nih.gov/{normalized_pmid}/", "RESOLVED_PMID"

    return None, "INTERNAL_ID_ONLY"


def _record_id_from_row(row) -> str | None:
    for field in ("Evidence_Record_ID", "evidence_record_id"):
        value = _clean(row.get(field))
        if value:
            return value
    return None


def _raw_evidence_index(evidence_df: pd.DataFrame) -> dict[str, dict]:
    if not isinstance(evidence_df, pd.DataFrame) or evidence_df.empty:
        return {}
    out: dict[str, dict] = {}
    for _, row in evidence_df.iterrows():
        record_id = _record_id_from_row(row)
        if record_id:
            out[record_id] = row.to_dict()  # last-row-wins: existing project convention
    return out


def _normalized_source(record_id: str, raw: dict | None, scientific) -> dict:
    if raw is None and scientific is None:
        return {
            "Evidence_Record_ID": record_id,
            "Title": None,
            "Source_Type": None,
            "Source_Organization": None,
            "Year": None,
            "Study_Type": None,
            "Population": None,
            "Outcome": None,
            "PMID": None,
            "DOI": None,
            "Source_URL": None,
            "Resolved_URL": None,
            "Resolution_Status": "UNRESOLVED_RECORD",
        }

    raw = raw or {}
    title = _clean(raw.get("Source_Title") or raw.get("source_title") or raw.get("Title") or raw.get("title"))
    source_type = _clean(raw.get("Source_Type") or raw.get("source_type"))
    organization = _clean(raw.get("Source_Organization") or raw.get("source_organization"))
    year = _clean(raw.get("Source_Year") or raw.get("source_year") or raw.get("Year") or raw.get("year"))
    study_type = _clean(raw.get("Study_Type") or raw.get("Evidence_Type"))
    population = _clean(raw.get("Population"))
    outcome = _clean(raw.get("Primary_Outcome"))
    pmid = _normalize_pmid(raw.get("PMID") or raw.get("pmid"))
    doi = _normalize_doi(raw.get("DOI") or raw.get("doi"))
    source_url = _clean(raw.get("Source_URL") or raw.get("source_url"))

    if scientific is not None:
        source_type = source_type or _clean(getattr(scientific, "source_type", None))
        study_type = study_type or _clean(getattr(scientific, "study_type", None))
        population = population or _clean(getattr(scientific, "population", None))
        outcome = outcome or _clean(getattr(scientific, "outcome", None))
        source_url = source_url or _clean(getattr(scientific, "doi_pmid_url", None))

    resolved_url, resolution_status = resolve_external_url(
        source_url=source_url,
        doi=doi,
        pmid=pmid,
    )
    if raw and not resolved_url:
        resolution_status = "INTERNAL_ID_ONLY"

    return {
        "Evidence_Record_ID": record_id,
        "Title": title,
        "Source_Type": source_type,
        "Source_Organization": organization,
        "Year": year,
        "Study_Type": study_type,
        "Population": population,
        "Outcome": outcome,
        "PMID": pmid,
        "DOI": doi,
        "Source_URL": source_url,
        "Resolved_URL": resolved_url,
        "Resolution_Status": resolution_status,
    }


def resolve_evidence_sources(evidence_ids, evidence_df) -> list[dict]:
    """Resolve normalized evidence IDs to normalized source records, in ID order.

    Unresolved IDs are retained as explicit ``UNRESOLVED_RECORD`` entries.
    Empty collection representations (including the literal string ``"()"``)
    resolve to an empty list through normalize_evidence_ids().
    """
    ids = normalize_evidence_ids(evidence_ids)
    if not ids:
        return []

    raw_index = _raw_evidence_index(evidence_df)
    scientific_index = get_scientific_evidence_by_ids(ids, evidence_df)
    return [
        _normalized_source(record_id, raw_index.get(record_id), scientific_index.get(record_id))
        for record_id in ids
    ]


def _numeric_present(row, field: str) -> tuple[bool, int | None]:
    if field not in row:
        return False, None
    raw = row.get(field)
    if raw is None:
        return False, None
    try:
        if pd.isna(raw):
            return False, None
    except (TypeError, ValueError):
        pass
    try:
        return True, int(float(raw))
    except (TypeError, ValueError):
        return False, None


def _expected_human_count(row, ids: list[str]) -> int | None:
    present, count = _numeric_present(row, "AI_Direct_Human_Outcome_Evidence_Count")
    if present:
        return max(count or 0, 0)
    if "Direct_Human_Outcome_Evidence_IDs" in row:
        return len(ids)
    present, count = _numeric_present(row, "Outcome_Specific_Human_Evidence_Count")
    if present:
        return max(count or 0, 0)
    return None


def _source_rank(source: dict) -> tuple[int, str]:
    text = " ".join(
        str(source.get(k) or "")
        for k in ("Study_Type", "Source_Type", "Title")
    ).lower()
    if any(term in text for term in ("randomized", "randomised", "clinical trial", "controlled trial", "rct")):
        rank = 0
    elif any(term in text for term in ("systematic review", "meta-analysis", "meta analysis")):
        rank = 1
    elif "human" in text:
        rank = 2
    else:
        rank = 3
    return rank, str(source.get("Evidence_Record_ID") or "")


def attach_human_evidence_source_traceability(report_df, evidence_df):
    """Append human-evidence source fields to a candidate/report DataFrame.

    Read-only over both inputs.  No scientific judgment is recomputed.
    The AI/outcome count is used only to quantify *missing source linkage*;
    evidence IDs themselves remain the sole source identities.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    payloads = []
    for _, row in out.iterrows():
        ids = normalize_evidence_ids(row.get("Direct_Human_Outcome_Evidence_IDs"))
        sources = resolve_evidence_sources(ids, evidence_df)
        found_sources = [s for s in sources if s["Resolution_Status"] != "UNRESOLVED_RECORD"]
        unresolved_record_count = len(sources) - len(found_sources)
        expected_count = _expected_human_count(row, ids)
        missing_linkage_count = max(0, (expected_count or 0) - len(ids)) if expected_count is not None else 0
        unresolved_count = unresolved_record_count + missing_linkage_count
        urls = [s["Resolved_URL"] for s in sources if s.get("Resolved_URL")]
        titles = [s["Title"] for s in sources if s.get("Title")]

        primary = None
        if found_sources:
            primary = sorted(found_sources, key=_source_rank)[0]

        if not ids and not expected_count:
            resolution_status = "NO_HUMAN_EVIDENCE_IDS"
        elif unresolved_count > 0 and found_sources:
            resolution_status = "PARTIAL_SOURCE_LINKAGE"
        elif unresolved_count > 0:
            resolution_status = "SOURCE_LINKAGE_INCOMPLETE"
        elif ids and len(found_sources) == len(ids):
            resolution_status = "ALL_RECORDS_RESOLVED"
        else:
            resolution_status = "SOURCE_LINKAGE_INCOMPLETE"

        payloads.append({
            "Human_Evidence_Record_IDs": json.dumps(ids, ensure_ascii=False),
            "Human_Evidence_Source_Count": len(ids),
            "Human_Evidence_Resolved_Source_Count": len(found_sources),
            "Human_Evidence_Unresolved_Source_Count": unresolved_count,
            "Human_Evidence_Primary_Source_Title": primary.get("Title") if primary else None,
            "Human_Evidence_Primary_Source_URL": primary.get("Resolved_URL") if primary else None,
            "Human_Evidence_Source_URLs": json.dumps(urls, ensure_ascii=False),
            "Human_Evidence_Source_Titles": json.dumps(titles, ensure_ascii=False),
            "Human_Evidence_Sources_JSON": json.dumps(sources, ensure_ascii=False),
            "Human_Evidence_Source_Resolution_Status": resolution_status,
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def build_source_bundle(ids, evidence_df, *, rank_fn=None) -> dict:
    """Generic, category-agnostic source-bundle builder.

    This is the single reusable abstraction every category-specific
    ``attach_*_source_traceability`` function is built on (human, safety,
    commercial, ...). It performs no scientific judgment: it normalizes
    whatever evidence IDs the caller already has for one candidate/claim
    into the shared bundle shape:

        {
            "record_ids": [...],
            "source_count": ...,
            "resolved_source_count": ...,
            "unresolved_source_count": ...,
            "primary_source_title": ...,
            "primary_source_url": ...,
            "source_titles": [...],
            "source_urls": [...],
            "sources": [...],
        }

    ``rank_fn`` lets a category pick a different deterministic primary-
    source rule than the default (which prefers RCT > systematic review /
    meta-analysis > other human evidence > everything else). Categories
    with their own precedence rule (e.g. "the record actually carrying the
    safety assertion") should pass their own ``rank_fn`` rather than
    reordering ``sources`` themselves, so the bundle's ``primary_source_*``
    fields and its ``sources`` list never disagree about which record is
    primary.
    """
    normalized_ids = normalize_evidence_ids(ids)
    sources = resolve_evidence_sources(normalized_ids, evidence_df)
    found = [s for s in sources if s["Resolution_Status"] != "UNRESOLVED_RECORD"]
    unresolved = len(sources) - len(found)
    urls = [s["Resolved_URL"] for s in sources if s.get("Resolved_URL")]
    titles = [s["Title"] for s in sources if s.get("Title")]

    primary = None
    if found:
        primary = sorted(found, key=rank_fn or _source_rank)[0]

    return {
        "record_ids": normalized_ids,
        "source_count": len(normalized_ids),
        "resolved_source_count": len(found),
        "unresolved_source_count": unresolved,
        "primary_source_title": primary.get("Title") if primary else None,
        "primary_source_url": primary.get("Resolved_URL") if primary else None,
        "source_titles": titles,
        "source_urls": urls,
        "sources": sources,
    }


def _safety_source_rank(source: dict) -> tuple[int, str]:
    """Primary-source rule for safety: the record actually carrying the
    safety assertion has no independent quality hierarchy of its own (per
    spec §19 -- "prefer the actual evidence record supporting the active
    safety assertion"), so all resolved safety records rank equally and the
    deterministic tiebreaker is the evidence record ID itself.
    """
    return (0, str(source.get("Evidence_Record_ID") or ""))


def attach_safety_evidence_source_traceability(report_df, evidence_df):
    """Append safety-evidence source fields to a candidate/report DataFrame.

    Resolves ``Safety_Evidence_IDs`` (already computed by
    safety_assertion_engine and pooled by candidate_shortlisting -- this
    function recomputes no safety judgment) through the same evidence
    source resolver used for human evidence, so a safety source can never
    be laundered from an unrelated efficacy paper: only IDs the safety
    layer itself attached to the candidate are resolved here.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    payloads = []
    for _, row in out.iterrows():
        ids = normalize_evidence_ids(row.get("Safety_Evidence_IDs"))
        bundle = build_source_bundle(ids, evidence_df, rank_fn=_safety_source_rank)
        concern_level = _clean(row.get("Safety_Concern_Level"))
        is_serious = bool(concern_level) and concern_level.strip().upper() == "SERIOUS"

        if not ids:
            resolution_status = (
                "SOURCE_LINKAGE_INCOMPLETE" if is_serious else "NO_SAFETY_EVIDENCE_IDS"
            )
        elif bundle["unresolved_source_count"] > 0 and bundle["resolved_source_count"] > 0:
            resolution_status = "PARTIAL_SOURCE_LINKAGE"
        elif bundle["unresolved_source_count"] > 0:
            resolution_status = "SOURCE_LINKAGE_INCOMPLETE"
        else:
            resolution_status = "ALL_RECORDS_RESOLVED"

        payloads.append({
            "Safety_Evidence_Record_IDs": json.dumps(bundle["record_ids"], ensure_ascii=False),
            "Safety_Source_Count": bundle["source_count"],
            "Safety_Resolved_Source_Count": bundle["resolved_source_count"],
            "Safety_Unresolved_Source_Count": bundle["unresolved_source_count"],
            "Safety_Primary_Source_Title": bundle["primary_source_title"],
            "Safety_Primary_Source_URL": bundle["primary_source_url"],
            "Safety_Source_Titles": json.dumps(bundle["source_titles"], ensure_ascii=False),
            "Safety_Source_URLs": json.dumps(bundle["source_urls"], ensure_ascii=False),
            "Safety_Sources_JSON": json.dumps(bundle["sources"], ensure_ascii=False),
            "Safety_Source_Resolution_Status": resolution_status,
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def attach_mechanistic_evidence_source_traceability(report_df, evidence_df):
    """Append mechanistic/target-evidence source fields to a candidate/report DataFrame.

    Resolves ``Mechanistic_Evidence_Record_IDs`` (candidate_shortlisting.py's
    ``mechanistic_source_ids`` -- previously computed and then discarded
    down to a bare count; now persisted) through the same evidence source
    resolver used for human/safety evidence. Reads only IDs the mechanistic
    layer itself attached to the candidate, so a target/mechanism claim can
    never be traced to an unrelated plant paper.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    payloads = []
    for _, row in out.iterrows():
        ids = normalize_evidence_ids(row.get("Mechanistic_Evidence_Record_IDs"))
        bundle = build_source_bundle(ids, evidence_df)

        if not ids:
            resolution_status = "NO_MECHANISTIC_EVIDENCE_IDS"
        elif bundle["unresolved_source_count"] > 0 and bundle["resolved_source_count"] > 0:
            resolution_status = "PARTIAL_SOURCE_LINKAGE"
        elif bundle["unresolved_source_count"] > 0:
            resolution_status = "SOURCE_LINKAGE_INCOMPLETE"
        else:
            resolution_status = "ALL_RECORDS_RESOLVED"

        # Target_Source_Map / Mechanism_Source_Map already carry exact
        # per-target/per-mechanism evidence-record IDs from
        # candidate_shortlisting.py (row-level pairing, no laundering).
        # JSON-encode here for safe CSV export / Claim_Source_Map reuse --
        # the ID vocabulary itself is not re-resolved (spec example shape
        # is {"target name": ["E1", "E2"]}, i.e. IDs, not URLs).
        target_map = row.get("Target_Source_Map")
        mechanism_map = row.get("Mechanism_Source_Map")
        target_map = target_map if isinstance(target_map, dict) else {}
        mechanism_map = mechanism_map if isinstance(mechanism_map, dict) else {}

        payloads.append({
            "Mechanistic_Evidence_Record_IDs": json.dumps(bundle["record_ids"], ensure_ascii=False),
            "Mechanistic_Source_Count": bundle["source_count"],
            "Mechanistic_Resolved_Source_Count": bundle["resolved_source_count"],
            "Mechanistic_Unresolved_Source_Count": bundle["unresolved_source_count"],
            "Mechanistic_Primary_Source_Title": bundle["primary_source_title"],
            "Mechanistic_Primary_Source_URL": bundle["primary_source_url"],
            "Mechanistic_Source_URLs": json.dumps(bundle["source_urls"], ensure_ascii=False),
            "Mechanistic_Sources_JSON": json.dumps(bundle["sources"], ensure_ascii=False),
            "Mechanistic_Source_Resolution_Status": resolution_status,
            "Target_Source_Map": json.dumps(target_map, ensure_ascii=False),
            "Mechanism_Source_Map": json.dumps(mechanism_map, ensure_ascii=False),
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def attach_scientific_source_summary(report_df):
    """Append a compact Scientific_Source_Count / Primary_Scientific_Source_*
    summary that unions human + mechanistic evidence-record IDs WITHOUT
    double-counting a record that supports both (spec, compact investor
    table §5). Must run after attach_human_evidence_source_traceability()
    and attach_mechanistic_evidence_source_traceability(). No new scoring
    model: this is a deterministic count/union + existing precedence
    (direct human evidence first, then mechanistic), never a re-ranking of
    individual sources.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    payloads = []
    for _, row in out.iterrows():
        human_ids = set(normalize_evidence_ids(row.get("Human_Evidence_Record_IDs")))
        mech_ids = set(normalize_evidence_ids(row.get("Mechanistic_Evidence_Record_IDs")))
        union_ids = human_ids | mech_ids

        human_url = _clean(row.get("Human_Evidence_Primary_Source_URL"))
        human_title = _clean(row.get("Human_Evidence_Primary_Source_Title"))
        mech_url = _clean(row.get("Mechanistic_Primary_Source_URL"))
        mech_title = _clean(row.get("Mechanistic_Primary_Source_Title"))

        # Precedence: direct human evidence first, then mechanistic --
        # matches the existing evidence-type/quality hierarchy used
        # elsewhere (human > mechanistic-only), not a new scoring model.
        primary_url = human_url or mech_url
        primary_title = human_title if human_url else (mech_title or human_title)

        payloads.append({
            "Scientific_Source_Count": len(union_ids),
            "Primary_Scientific_Source_URL": primary_url,
            "Primary_Scientific_Source_Title": primary_title,
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def parse_sources_json(value) -> list[dict]:
    """Safe inverse for UI/detail rendering of Human_Evidence_Sources_JSON."""
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
