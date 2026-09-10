"""Claim_Source_Map / Derived_Claim_Provenance + regulatory/patent honesty layer.

Presentation/provenance only. Adds the audit-rich structured fields the
source-traceability pass requires:

  * Regulatory_Source_Count / Patent_Source_Count and friends -- exposed
    honestly as zero/NOT_INTEGRATED today, because
    Regulatory_Assessment_Status and Patent_Assessment_Status are already
    "NOT_INTEGRATED" upstream (post_discovery_investor_view.py). This module
    does not run a regulatory or patent search; it only reads the existing
    assessment-status fields and, if a future pass ever populates real
    Regulatory_Source_URL / Patent_IDs columns, surfaces those instead.
  * Claim_Source_Map -- one JSON object per candidate, the union of actual
    source-backed evidence-record IDs behind each claim category.
  * Derived_Claim_Provenance -- one JSON object per candidate documenting
    which upstream fields a platform-derived classification (not a single
    citable source) was computed from.
"""
from __future__ import annotations

import json

import pandas as pd

from evidence_source_resolver import _clean


def _json_list(value) -> list:
    if isinstance(value, list):
        return value
    text = _clean(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def attach_regulatory_patent_source_traceability(report_df: pd.DataFrame) -> pd.DataFrame:
    """Append Regulatory_* / Patent_* source fields, honestly, to a Stage-6 frame.

    Regulatory_Assessment_Status / Patent_Assessment_Status already encode
    whether a genuine assessment exists (see post_discovery_investor_view.py
    -- both are "NOT_INTEGRATED" in the current architecture). Only when a
    row's status is the real "ASSESSED" value AND it already carries a
    resolvable URL/authority/ID column does this expose a source; otherwise
    it reports zero rather than fabricating a regulator or patent-office link.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    payloads = []
    for _, row in out.iterrows():
        reg_status = _clean(row.get("Regulatory_Assessment_Status")) or "NOT_INTEGRATED"
        reg_url = None
        reg_title = None
        reg_authority = _clean(row.get("Regulatory_Authority"))
        if reg_status == "ASSESSED":
            from evidence_source_resolver import _valid_http_url
            reg_url = _valid_http_url(row.get("Regulatory_Source_URL"))
            reg_title = _clean(row.get("Regulatory_Primary_Source_Title"))
        reg_count = 1 if reg_url else 0

        pat_status = _clean(row.get("Patent_Assessment_Status")) or "NOT_INTEGRATED"
        pat_ids = _json_list(row.get("Patent_IDs"))
        pat_url = None
        pat_title = None
        if pat_status == "ASSESSED":
            from evidence_source_resolver import _valid_http_url
            pat_url = _valid_http_url(row.get("Patent_Primary_Source_URL"))
            pat_title = _clean(row.get("Patent_Primary_Source_Title"))
        pat_count = len(pat_ids) if pat_ids else (1 if pat_url else 0)

        payloads.append({
            "Regulatory_Source_Count": reg_count,
            "Regulatory_Primary_Source_Title": reg_title,
            "Regulatory_Primary_Source_URL": reg_url,
            "Regulatory_Source_URLs": json.dumps([reg_url] if reg_url else [], ensure_ascii=False),
            "Regulatory_Authority": reg_authority,
            "Regulatory_Source_Status": reg_status,

            "Patent_Source_Count": pat_count,
            "Patent_IDs": json.dumps(pat_ids, ensure_ascii=False),
            "Patent_Primary_Source_Title": pat_title,
            "Patent_Primary_Source_URL": pat_url,
            "Patent_Source_URLs": json.dumps([pat_url] if pat_url else [], ensure_ascii=False),
            "Patent_Source_Status": pat_status,
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


# Static architecture knowledge: which upstream fields each platform-derived
# (not single-source-citable) classification is computed from. This mirrors
# post_discovery_investor_view.py's real deterministic rule functions -- see
# _why_interesting(), _next_rd_step(), _opportunity_type() etc. Kept as one
# named constant so the mapping cannot silently drift out of sync in two
# places; update it here if those rule functions' actual inputs change.
DERIVED_CLAIM_PROVENANCE = {
    "Opportunity_Type": {
        "derived_from_fields": [
            "RD_Discovery_Lane",
            "Commercial_Opportunity_Class",
            "Discovery_Admission_Path",
        ],
    },
    "Why_Interesting": {
        "derived_from_fields": [
            "RD_Discovery_Lane",
            "Discovery_Potential_Score",
            "Evidence_Maturity_Score",
            "Human_Evidence_Status",
        ],
    },
    "What_Is_New": {
        "derived_from_fields": [
            "Commercial_Novelty_Status",
            "Commercial_Status_For_Indication",
        ],
    },
    "Key_Evidence_Gap": {
        "derived_from_fields": [
            "Human_Evidence_Status",
            "Evidence_Maturity_Score",
            "Safety_Assertion_Status",
        ],
    },
    "Next_R&D_Step": {
        "derived_from_fields": [
            "Safety_Concern_Level",
            "Human_Evidence_Status",
            "Preparation_Applicability_Class",
        ],
    },
    "Development_Readiness_Score": {
        "derived_from_fields": [
            "Human_Evidence_Status",
            "Safety_Assertion_Status",
            "Preparation_Applicability_Class",
        ],
    },
    "Commercial_Opportunity_Score": {
        "derived_from_fields": [
            "Commercial_Status_Overall",
            "Commercial_Status_For_Indication",
            "Commercial_Data_Completeness",
        ],
    },
}

_CLAIM_SOURCE_CATEGORY_ID_FIELDS = {
    "human_evidence": "Human_Evidence_Record_IDs",
    "safety": "Safety_Evidence_Record_IDs",
}


def build_claim_source_map(row) -> dict:
    """Build the Claim_Source_Map object for one candidate row.

    Deterministic union of the *actual* source-backed evidence-record IDs
    already attached to this row by each category's attach_* function --
    never a source reused across categories (no source-laundering: each
    category reads only its own ID field).
    """
    result: dict = {}
    for category, field in _CLAIM_SOURCE_CATEGORY_ID_FIELDS.items():
        ids = _json_list(row.get(field))
        if ids:
            result[category] = ids

    commercial_titles = _json_list(row.get("Commercial_Source_Titles"))
    if commercial_titles:
        result["commercial"] = commercial_titles

    regulatory_url = _clean(row.get("Regulatory_Primary_Source_URL"))
    if regulatory_url:
        result["regulatory"] = [regulatory_url]

    patent_ids = _json_list(row.get("Patent_IDs"))
    if patent_ids:
        result["patent"] = patent_ids

    return result


def attach_claim_source_map(report_df: pd.DataFrame) -> pd.DataFrame:
    """Append Claim_Source_Map (JSON) and Derived_Claim_Provenance (JSON).

    Must run AFTER the human/safety/commercial/regulatory/patent attach
    functions, since it only reads fields those functions already produced.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df

    out = report_df.copy()
    claim_maps = []
    derived = []
    for _, row in out.iterrows():
        claim_maps.append(json.dumps(build_claim_source_map(row), ensure_ascii=False))
        derived.append(json.dumps(DERIVED_CLAIM_PROVENANCE, ensure_ascii=False))
    out["Claim_Source_Map"] = claim_maps
    out["Derived_Claim_Provenance"] = derived
    return out


def parse_claim_source_map(value) -> dict:
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}
