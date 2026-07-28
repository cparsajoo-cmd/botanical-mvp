"""
Validation Architecture v3 — Phase 2: GoldCase Persistence.

Mirrors validation_protocol_persistence.py's exact pattern and
reasoning: a GoldCase, like a ValidationCaseProtocol, is typically
curated across multiple sessions (decision context today, references
and applicability next week, expected output finalized later) — so
persist_gold_case() is always allowed regardless of curation
completeness, unlike expert_sign_off.persist_sign_off()'s hard
completeness gate. See validation_protocol_persistence.py's own
module docstring for the full reasoning, which applies identically
here.

LOCK SEMANTICS: append-only, same as every other persistence module in
this repository. case_id is the caller-supplied, stable identity (a
GoldCase's own case_id — no separate generated ID needed, unlike
ValidationCaseProtocol's protocol_id, since GoldCase already requires
a case_id at construction).

REQUIRED TABLE (created outside this repository, like every other
Supabase table here): `gold_cases`, with columns: case_id, dataset_split,
risk_strata (JSON array), saved_at, gold_case_json (gold_case_serialization
.gold_case_to_dict() output, JSON-serialized).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from gold_case import GoldCase
from gold_case_serialization import gold_case_to_dict, gold_case_from_dict

GOLD_CASE_TABLE_NAME = "gold_cases"


def persist_gold_case(gold_case: GoldCase, supabase_client=None) -> dict:
    """Always allowed regardless of curation completeness — see module
    docstring. Never raises; database/connectivity failures degrade to
    a status dict.

    Returns:
      {"status": "persisted" | "unavailable", "case_id": str,
       "dataset_split": str, "detail": str}
    """
    payload = gold_case_to_dict(gold_case)
    row = {
        "case_id": gold_case.case_id,
        "dataset_split": gold_case.dataset_split.value,
        "risk_strata": [s.value for s in gold_case.risk_strata],
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "gold_case_json": json.dumps(payload, default=str),
    }

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        supabase_client.table(GOLD_CASE_TABLE_NAME).insert(row).execute()

        return {
            "status": "persisted",
            "case_id": gold_case.case_id,
            "dataset_split": gold_case.dataset_split.value,
            "detail": f"GoldCase {gold_case.case_id!r} persisted.",
        }
    except Exception:
        return {
            "status": "unavailable",
            "case_id": gold_case.case_id,
            "dataset_split": gold_case.dataset_split.value,
            "detail": "GoldCase persistence unavailable this session "
                      "(table may not exist yet, or the database is unreachable).",
        }


def load_gold_case(case_id: str, supabase_client=None):
    """Loads the MOST RECENT saved version of a GoldCase by case_id.
    Returns None on any failure — never raises."""
    if not case_id:
        return None

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        response = (
            supabase_client.table(GOLD_CASE_TABLE_NAME)
            .select("*").eq("case_id", case_id).execute()
        )
        rows = response.data or []
        if not rows:
            return None
        latest = sorted(rows, key=lambda r: r.get("saved_at") or "", reverse=True)[0]
        return gold_case_from_dict(json.loads(latest["gold_case_json"]))
    except Exception:
        return None


def load_gold_cases_by_split(dataset_split_value: str, supabase_client=None) -> list:
    """Loads the MOST RECENT saved version of every GoldCase currently
    at the given dataset_split — the function evaluation_run.py will
    use to gather a locked-holdout run's input set. Returns [] on any
    failure. De-duplicates by case_id, keeping only the latest saved_at
    per case_id (an earlier save under a DIFFERENT split is not
    returned even if it matches by coincidence — only the CURRENT,
    latest version's split value counts)."""
    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        response = supabase_client.table(GOLD_CASE_TABLE_NAME).select("*").execute()
        rows = response.data or []
    except Exception:
        return []

    latest_by_case_id = {}
    for row in rows:
        case_id = row.get("case_id")
        if case_id is None:
            continue
        existing = latest_by_case_id.get(case_id)
        if existing is None or (row.get("saved_at") or "") > (existing.get("saved_at") or ""):
            latest_by_case_id[case_id] = row

    result = []
    for row in latest_by_case_id.values():
        if row.get("dataset_split") == dataset_split_value:
            try:
                result.append(gold_case_from_dict(json.loads(row["gold_case_json"])))
            except Exception:
                continue
    return result
