"""Targeted semantic hard-gate stress test using already-exposed local validation cases.

No Supabase access. No database reads/writes. Uses existing repository snapshots and
curator-verified source records to test catastrophic safety/regulatory misses before
any semantic-gate backfill is applied.
"""
from __future__ import annotations

import json
from pathlib import Path

from llm_extractor import extract_gate_assertions_with_llm
from semantic_gate_assertions import parse_semantic_gate_payload

ROOT = Path(__file__).resolve().parent


def _snapshot(case_id: str) -> dict:
    p = ROOT / "gold_corpus" / "scientific_validity" / "final_holdout_v1" / "snapshots" / f"{case_id}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    rec = data["records"][0]
    q = data.get("question")
    if isinstance(q, dict):
        context = " | ".join(str(q.get(k) or "") for k in ("indication", "dosage_form", "market") if q.get(k))
    else:
        context = str(q or "")
    return {
        "id": case_id,
        "text": rec["notes"],
        "title": rec.get("source_title", ""),
        "context": context or rec.get("target_indication", ""),
    }


def _source_json(relpath: str, *, text_key: tuple[str, ...], context: str, case_id: str) -> dict:
    data = json.loads((ROOT / relpath).read_text(encoding="utf-8"))
    cur = data
    for key in text_key:
        cur = cur[key]
    return {"id": case_id, "text": str(cur), "title": str(data.get("title") or data.get("document_title") or ""), "context": context}


CASES = [
    # Catastrophic safety-positive cases already exposed in earlier validation.
    {**_snapshot("rgv1_017_chaparral_oral"), "expect": "serious_safety"},
    {**_snapshot("rgv2_017_aconitum_oral"), "expect": "serious_safety"},
    {**_snapshot("rgv2_018_datura_oral"), "expect": "serious_safety"},
    {**_snapshot("rgv2_019_colchicum_oral"), "expect": "serious_safety"},
    {**_snapshot("rgv2_020_belladonna_oral"), "expect": "serious_safety"},

    # Regulatory hard-block cases already exposed in earlier validation.
    {**_snapshot("rgv3_017_cistanche_eu_food"), "expect": "regulatory_block"},
    {**_snapshot("rgv3_018_terminaliacatappa_eu_food"), "expect": "regulatory_block"},
    {**_snapshot("rgv2_022_cbd_eu_food"), "expect": "regulatory_block"},

    # Controls: moderate interaction must not become SERIOUS.
    {
        **_source_json(
            "gold_cases/case_014_source_record.json",
            text_key=("verified_excerpt",),
            context="Ginkgo biloba oral extract | EU | concomitant dabigatran",
            case_id="control_ginkgo_dabigatran_moderate",
        ),
        "expect": "no_serious_safety",
    },
    # Control: a dose/supply-channel restriction is not an absolute prohibition.
    {
        **_source_json(
            "gold_cases/case_018_source_record.json",
            text_key=("verified_excerpt",),
            context="Ephedra sinica | oral medicinal use | UK",
            case_id="control_ephedra_conditional_access",
        ),
        "expect": "no_regulatory_block",
    },
]


def _enum_value(value):
    return getattr(value, "value", str(value))


def main() -> int:
    failed = 0
    catastrophic_fn = 0
    false_hard_stop = 0

    for case in CASES:
        record = {"Notes": case["text"], "Source_Title": case["title"]}
        raw = extract_gate_assertions_with_llm(record, candidate_context=case["context"])
        safety, regulatory, warnings = parse_semantic_gate_payload(
            raw,
            source_text=case["text"],
            evidence_record_id=case["id"],
        )

        serious = [a for a in safety if str(_enum_value(getattr(a, "severity", ""))).lower() == "serious"]
        blocking = [a for a in regulatory if bool(getattr(a, "blocking", False))]

        expect = case["expect"]
        ok = True
        if expect == "serious_safety":
            ok = bool(serious)
            if not ok:
                catastrophic_fn += 1
        elif expect == "regulatory_block":
            ok = bool(blocking)
            if not ok:
                catastrophic_fn += 1
        elif expect == "no_serious_safety":
            ok = not serious
            if not ok:
                false_hard_stop += 1
        elif expect == "no_regulatory_block":
            ok = not blocking
            if not ok:
                false_hard_stop += 1

        if not ok:
            failed += 1

        print("STRESS " + json.dumps({
            "case": case["id"],
            "expect": expect,
            "status": "PASS" if ok else "FAIL",
            "serious_safety": len(serious),
            "regulatory_blocks": len(blocking),
            "safety": [
                {
                    "type": _enum_value(getattr(a, "assertion_type", "")),
                    "severity": _enum_value(getattr(a, "severity", "")),
                    "span": getattr(a, "source_sentence", ""),
                } for a in safety
            ],
            "regulatory": [
                {
                    "action": _enum_value(getattr(a, "action", "")),
                    "effect": _enum_value(getattr(a, "market_access_effect", "")),
                    "span": getattr(a, "supporting_text", ""),
                } for a in regulatory
            ],
            "warnings": warnings,
        }, ensure_ascii=False, separators=(",", ":")))

    print(
        f"SUMMARY cases={len(CASES)} passed={len(CASES)-failed} failed={failed} "
        f"catastrophic_fn={catastrophic_fn} false_hard_stop={false_hard_stop} "
        "supabase_reads=0 supabase_writes=0"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
