"""Conservative backfill for evidence_records safety and interaction fields.

Dry-run by default. Use ``--apply`` only after reviewing the printed changes.
The script never overwrites non-empty structured values and only derives values
from the evidence row's own notes using the repository's attribution parser.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from supabase_client import get_supabase_client
from safety_interaction_attribution import extract_attributed_safety_interactions


NOISE_PREFIXES = (
    "patent/protection landscape proxy search",
    "chebi chemical ontology record",
    "dailymed label/safety search result",
)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) == 0
    return str(value).strip().lower() in {"", "null", "none", "not assessed", "unknown"}


def _load_plant_map(client) -> dict[int, str]:
    rows = client.table("plants").select("id,scientific_name").execute().data or []
    return {int(row["id"]): str(row.get("scientific_name") or "").strip() for row in rows}


def _iter_rows(client, batch_size: int, limit: int | None):
    offset = 0
    yielded = 0
    select_cols = (
        "id,plant_id,source_id,notes,adverse_events,interactions_structured,"
        "safety_findings"
    )
    while True:
        end = offset + batch_size - 1
        rows = (
            client.table("evidence_records")
            .select(select_cols)
            .order("id")
            .range(offset, end)
            .execute()
            .data
            or []
        )
        if not rows:
            break
        for row in rows:
            yield row
            yielded += 1
            if limit is not None and yielded >= limit:
                return
        if len(rows) < batch_size:
            break
        offset += batch_size


def _build_update(row: dict[str, Any], plant_name: str) -> dict[str, Any]:
    notes = str(row.get("notes") or "").strip()
    if not notes or notes.lower().startswith(NOISE_PREFIXES):
        return {}

    result = extract_attributed_safety_interactions(
        notes,
        plant_name=plant_name,
        structurally_linked=True,
    )

    update: dict[str, Any] = {}
    adverse = result.get("adverse_events") or []
    interactions = result.get("interactions") or []
    reassurance = result.get("safety_reassurance") or []

    if _is_empty(row.get("adverse_events")) and adverse:
        update["adverse_events"] = adverse
    if _is_empty(row.get("interactions_structured")) and interactions:
        update["interactions_structured"] = interactions
    if _is_empty(row.get("safety_findings")):
        findings: list[str] = []
        if adverse:
            findings.append("Adverse signals: " + " | ".join(adverse))
        if reassurance:
            findings.append("Safety reassurance: " + " | ".join(reassurance))
        if interactions:
            findings.append("Interaction signals: " + " | ".join(interactions))
        if findings:
            update["safety_findings"] = " ; ".join(findings)
    return update


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Persist updates. Default is dry-run.")
    parser.add_argument("--plant", default="", help="Optional exact scientific name filter.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    client = get_supabase_client()
    plant_map = _load_plant_map(client)
    inspected = changed = skipped = 0

    for row in _iter_rows(client, args.batch_size, args.limit):
        plant_name = plant_map.get(int(row.get("plant_id") or 0), "")
        if args.plant and plant_name.lower() != args.plant.strip().lower():
            continue
        inspected += 1
        update = _build_update(row, plant_name)
        if not update:
            skipped += 1
            continue

        changed += 1
        print(json.dumps({"id": row["id"], "plant": plant_name, "update": update}, ensure_ascii=False))
        if args.apply:
            client.table("evidence_records").update(update).eq("id", row["id"]).execute()

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] inspected={inspected} changed={changed} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
