"""Quota-bounded read-back + deterministic gate integration check.

This script intentionally reads ONLY the 20 evidence_records rows written by
our first semantic-gate apply batch. It performs one bounded Supabase SELECT,
zero writes, and zero OpenAI calls.

It validates:
1) all expected rows are present and have llm_gate_assertions;
2) persisted JSON parses against the exact source text used for backfill;
3) semantic assertions can be consumed by the production deterministic
   safety/regulatory gate functions;
4) the resulting eligibility decision can be produced without exceptions;
5) no row from this known non-hard-stop batch unexpectedly becomes a hard
   NO-GO through the semantic layer.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List

from supabase_client import get_supabase_client
from semantic_gate_assertions import parse_semantic_gate_payload
from eligibility_gate import (
    classify_safety_finding,
    classify_regulatory_finding,
    evaluate_eligibility,
)

# Exact IDs visible in the successful first apply batch (2026-08-11).
# Hard-coding them prevents an accidental scan / moving-window read.
EXPECTED_IDS = (
    1, 3, 4, 5, 6,
    55, 56, 57, 58, 59, 60, 62, 63, 64,
    76, 77, 78, 82, 83, 128,
)

SELECT_EXPR = "id,notes,llm_gate_assertions"


def _payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("llm_gate_assertions is missing or is not a JSON object")


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _fetch_exact_rows() -> List[Dict[str, Any]]:
    client = get_supabase_client()
    response = (
        client.table("evidence_records")
        .select(SELECT_EXPR)
        .in_("id", list(EXPECTED_IDS))
        .order("id")
        .execute()
    )
    return response.data or []


def main() -> int:
    rows = _fetch_exact_rows()
    by_id = {int(row["id"]): row for row in rows if row.get("id") is not None}

    missing_ids = [record_id for record_id in EXPECTED_IDS if record_id not in by_id]
    if missing_ids:
        print("ERROR missing_ids=" + json.dumps(missing_ids))
        print(
            "SUMMARY read_rows=%d expected_rows=%d parsed=0 gate_evaluated=0 "
            "missing=%d invalid_payload=0 parse_warnings=0 hard_no_go=0 failed=1 "
            "supabase_reads=1 supabase_writes=0 openai_calls=0"
            % (len(rows), len(EXPECTED_IDS), len(missing_ids))
        )
        return 1

    parsed_count = 0
    gate_evaluated = 0
    invalid_payload = 0
    warning_count = 0
    hard_no_go = 0
    failures = 0
    decision_counts: Counter[str] = Counter()

    for record_id in EXPECTED_IDS:
        row = by_id[record_id]
        source_text = str(row.get("notes") or "")

        try:
            payload = _payload(row.get("llm_gate_assertions"))
        except Exception as exc:  # noqa: BLE001
            invalid_payload += 1
            failures += 1
            print(
                "READBACK "
                + json.dumps(
                    {"id": record_id, "status": "INVALID_PAYLOAD", "error": str(exc)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            continue

        try:
            safety_assertions, regulatory_assertions, warnings = parse_semantic_gate_payload(
                payload,
                source_text=source_text,
                evidence_record_id=str(record_id),
            )
            parsed_count += 1
            warning_count += len(warnings)

            # Feed the persisted semantic assertions through the SAME pure,
            # deterministic gate functions used by the candidate engine.
            safety = classify_safety_finding(
                hit_terms=frozenset(),
                flagged_terms=frozenset(),
                has_evidence_text=bool(source_text.strip()),
                same_plant=True,
                evidence_ids=(str(record_id),),
                assertions=tuple(safety_assertions),
            )
            regulatory = classify_regulatory_finding(
                barrier_types=frozenset(),
                has_evidence_text=bool(source_text.strip()),
                same_plant=True,
                finding_text=source_text,
                evidence_ids=(str(record_id),),
                semantic_assertions=tuple(regulatory_assertions),
            )
            decision = evaluate_eligibility(safety, regulatory)
            gate_evaluated += 1

            status = _enum_value(decision.status)
            decision_counts[status] += 1
            is_hard_no_go = bool(getattr(decision, "hard_no_go", False))
            if is_hard_no_go:
                hard_no_go += 1
                # The original 20-row audit had serious_safety=0 and
                # regulatory_blocks=0. A hard NO-GO here is therefore a
                # persistence/integration surprise and must fail the probe.
                failures += 1

            print(
                "READBACK "
                + json.dumps(
                    {
                        "id": record_id,
                        "status": "PASS" if not is_hard_no_go else "UNEXPECTED_HARD_NO_GO",
                        "schema_version": payload.get("schema_version"),
                        "safety_assertions": len(safety_assertions),
                        "regulatory_assertions": len(regulatory_assertions),
                        "warnings": list(warnings),
                        "safety_severity": _enum_value(getattr(safety, "severity", "")),
                        "regulatory_status": _enum_value(getattr(regulatory, "status", "")),
                        "eligibility_status": status,
                        "hard_no_go": is_hard_no_go,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(
                "READBACK "
                + json.dumps(
                    {"id": record_id, "status": "INTEGRATION_ERROR", "error": str(exc)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )

    decision_summary = ",".join(
        f"{key}:{value}" for key, value in sorted(decision_counts.items())
    ) or "none"

    print(
        "SUMMARY "
        f"read_rows={len(rows)} "
        f"expected_rows={len(EXPECTED_IDS)} "
        f"parsed={parsed_count} "
        f"gate_evaluated={gate_evaluated} "
        f"missing=0 "
        f"invalid_payload={invalid_payload} "
        f"parse_warnings={warning_count} "
        f"hard_no_go={hard_no_go} "
        f"failed={failures} "
        f"decisions={decision_summary} "
        "supabase_reads=1 supabase_writes=0 openai_calls=0"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
