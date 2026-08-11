"""Quota-conscious backfill for record-level semantic safety/regulatory assertions.

Design goals
------------
* No full-table reads or counts.
* Server-side filter: only rows whose ``llm_gate_assertions`` is SQL NULL.
* Fetch only the columns required by semantic extraction.
* Dry-run never writes to Supabase.
* Apply writes one JSONB field per successfully processed row; an empty but
  versioned payload is persisted too, so already-reviewed rows are not fetched
  again on later batches.
* LLM/extraction failures remain NULL and are therefore retryable.

The script deliberately does not run the final GO/NO-GO policy. It only
backfills the additive semantic assertion payload consumed by the existing
engine.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List

from llm_extractor import extract_gate_assertions_with_llm
from semantic_gate_assertions import (
    SEMANTIC_GATE_ASSERTION_VERSION,
    parse_semantic_gate_payload,
)
from supabase_client import get_supabase_client


SELECT_EXPR = ",".join(
    [
        "id",
        "notes",
        "target_indication",
        "dosage_form",
        "target_market",
        "llm_gate_assertions",
    ]
)

# Keep manual/shadow runs intentionally small. This protects Supabase egress
# and prevents an accidental large OpenAI job from one workflow click.
MAX_ROWS_PER_RUN = 100
MAX_RETRIES = 2


@dataclass
class Stats:
    scanned: int = 0
    extracted: int = 0
    would_update: int = 0
    updated: int = 0
    empty_assertion_payloads: int = 0
    serious_safety: int = 0
    regulatory_blocks: int = 0
    review_warnings: int = 0
    failed: int = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _candidate_context(row: Dict[str, Any]) -> str:
    return " | ".join(
        str(row.get(key) or "").strip()
        for key in ("target_indication", "dosage_form", "target_market")
        if str(row.get(key) or "").strip()
    )


def _fetch_rows(client, limit: int) -> List[Dict[str, Any]]:
    """One bounded Supabase read; never count or scan the full table."""
    response = (
        client.table("evidence_records")
        .select(SELECT_EXPR)
        .is_("llm_gate_assertions", "null")
        .order("id")
        .limit(int(limit))
        .execute()
    )
    return response.data or []


def _extract_with_retry(record: Dict[str, Any], candidate_context: str):
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return extract_gate_assertions_with_llm(
                record,
                candidate_context=candidate_context,
            )
        except Exception as exc:  # noqa: BLE001 - reported per-row below
            last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(0.75 * (attempt + 1))
    raise last_error


def _persisted_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap output with minimal audit metadata while preserving schema body."""
    return {
        "schema_version": SEMANTIC_GATE_ASSERTION_VERSION,
        "processed_at": _utc_now(),
        "safety_assertions": list(raw.get("safety_assertions") or []),
        "regulatory_assertions": list(raw.get("regulatory_assertions") or []),
    }


def _preview(text: str, max_chars: int = 180) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1] + "…"


def run(*, apply: bool, limit: int) -> tuple[Stats, list[dict]]:
    if limit < 1 or limit > MAX_ROWS_PER_RUN:
        raise ValueError(f"limit must be between 1 and {MAX_ROWS_PER_RUN}")

    client = get_supabase_client()
    rows = _fetch_rows(client, limit)
    stats = Stats()
    audit_rows: list[dict] = []

    for row in rows:
        stats.scanned += 1
        record_id = row.get("id")
        notes = str(row.get("notes") or "")

        # A no-text row can be marked as processed safely: no semantic claim can
        # have a verbatim supporting span when there is no evidence text.
        if not notes.strip():
            raw = {"safety_assertions": [], "regulatory_assertions": []}
        else:
            record = {
                "Notes": notes,
                "Target_Indication": row.get("target_indication") or "",
                "Dosage_Form": row.get("dosage_form") or "",
                "Target_Market": row.get("target_market") or "",
            }
            try:
                raw = _extract_with_retry(record, _candidate_context(row))
                stats.extracted += 1
            except Exception as exc:  # noqa: BLE001
                stats.failed += 1
                audit_rows.append(
                    {
                        "id": record_id,
                        "status": "failed",
                        "error": _preview(str(exc), 240),
                    }
                )
                continue

        # Validate verbatim spans now, before anything can reach production
        # policy. This mirrors the engine-side parser and makes the shadow run
        # explicitly auditable.
        safety, regulatory, warnings = parse_semantic_gate_payload(
            raw,
            source_text=notes,
            evidence_record_id=str(record_id or ""),
        )

        serious = [
            a for a in safety
            if str(getattr(getattr(a, "severity", None), "value", getattr(a, "severity", ""))).lower()
            == "serious"
        ]
        blocking = [a for a in regulatory if getattr(a, "blocking", False)]

        stats.serious_safety += len(serious)
        stats.regulatory_blocks += len(blocking)
        stats.review_warnings += len(warnings)

        payload = _persisted_payload(raw)
        if not payload["safety_assertions"] and not payload["regulatory_assertions"]:
            stats.empty_assertion_payloads += 1

        stats.would_update += 1
        if apply:
            client.table("evidence_records").update(
                {"llm_gate_assertions": payload}
            ).eq("id", record_id).execute()
            stats.updated += 1

        # Logs expose only compact supporting spans/assertion labels, never the
        # full source record, keeping GitHub logs readable and lower-risk.
        audit_rows.append(
            {
                "id": record_id,
                "status": "updated" if apply else "dry-run",
                "text_chars": len(notes),
                "safety": [
                    {
                        "type": getattr(getattr(a, "assertion_type", None), "value", str(getattr(a, "assertion_type", ""))),
                        "severity": getattr(getattr(a, "severity", None), "value", str(getattr(a, "severity", ""))),
                        "span": _preview(getattr(a, "source_sentence", "")),
                    }
                    for a in safety
                ],
                "regulatory": [
                    {
                        "action": getattr(getattr(a, "action", None), "value", str(getattr(a, "action", ""))),
                        "market_access_effect": getattr(
                            getattr(a, "market_access_effect", None),
                            "value",
                            str(getattr(a, "market_access_effect", "")),
                        ),
                        "span": _preview(getattr(a, "supporting_text", "")),
                    }
                    for a in regulatory
                ],
                "warnings": warnings,
            }
        )

    return stats, audit_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write JSONB payloads")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    stats, audits = run(apply=args.apply, limit=args.limit)

    for item in audits:
        print("AUDIT " + json.dumps(item, ensure_ascii=False, separators=(",", ":")))

    print(
        "SUMMARY "
        f"mode={'apply' if args.apply else 'dry-run'} "
        f"scanned={stats.scanned} "
        f"extracted={stats.extracted} "
        f"would_update={stats.would_update} "
        f"updated={stats.updated} "
        f"empty={stats.empty_assertion_payloads} "
        f"serious_safety={stats.serious_safety} "
        f"regulatory_blocks={stats.regulatory_blocks} "
        f"warnings={stats.review_warnings} "
        f"failed={stats.failed}"
    )
    return 1 if stats.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
