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
