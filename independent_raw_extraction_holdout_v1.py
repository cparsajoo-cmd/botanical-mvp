"""One-shot held-out validation of the live LLM extraction layer.

Scope: raw source summary -> structured evidence direction plus semantic
safety/regulatory assertions.  The cases were frozen before the first call to
this extractor and were not used to tune llm_extractor.py or
semantic_gate_assertions.py.  No database/Supabase module is imported.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from llm_extractor import extract_evidence_with_llm, extract_gate_assertions_with_llm
from semantic_gate_assertions import parse_semantic_gate_payload

ROOT = Path(__file__).resolve().parent
CASE_FILE = ROOT / "independent_raw_extraction_holdout_v1_cases.json"
FROZEN_CASE_FILE_SHA256 = "a01e26eeb79210f4471690dfc5effd32b6da8ebdf6c426722ccb21a9518bc960"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _enum(value) -> str:
    return str(getattr(value, "value", value)).strip().lower()


def _ratio(n: int, d: int):
    return None if not d else n / d


def main() -> int:
    if _sha256(CASE_FILE) != FROZEN_CASE_FILE_SHA256:
        raise SystemExit("FROZEN CASE FILE HASH MISMATCH — refusing to run")
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise SystemExit("OPENAI_API_KEY is required")

    payload = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    cases = payload["cases"]

    catastrophic_fn = 0
    false_hard_stop = 0
    parse_errors = 0
    direction_total = direction_ok = 0
    safety_pos = safety_tp = safety_neg = safety_tn = 0
    reg_pos = reg_tp = reg_neg = reg_tn = 0
    rows = []

    for case in cases:
        rec = {"Source_Title": case["title"], "Notes": case["text"]}
        serious = []
        blocking = []
        warnings = []
        gate_error = None
        try:
            raw_gate = extract_gate_assertions_with_llm(
                rec,
                candidate_context=(
                    f'{case["botanical"]} | oral | EU | {case["indication"]}'
                ),
            )
            safety, regulatory, warnings = parse_semantic_gate_payload(
                raw_gate,
                source_text=case["text"],
                evidence_record_id=case["id"],
                authority="held-out external source",
                source_url="",
            )
            serious = [
                a for a in safety if _enum(getattr(a, "severity", "")) == "serious"
            ]
            blocking = [a for a in regulatory if bool(getattr(a, "blocking", False))]
        except Exception as exc:  # keep a schema/API failure visible as validation failure
            parse_errors += 1
            gate_error = str(exc)

        if case["gate_expect"] == "serious_safety":
            safety_pos += 1
            if serious:
                safety_tp += 1
            else:
                catastrophic_fn += 1
        else:
            safety_neg += 1
            if not serious:
                safety_tn += 1
            else:
                false_hard_stop += 1

        if case["gate_expect"] == "regulatory_block":
            reg_pos += 1
            if blocking:
                reg_tp += 1
            else:
                catastrophic_fn += 1
        else:
            reg_neg += 1
            if not blocking:
                reg_tn += 1
            else:
                false_hard_stop += 1

        extracted_direction = None
        direction_pass = None
        direction_error = None
        accepted = case.get("direction_accept")
        if accepted:
            direction_total += 1
            try:
                evidence = extract_evidence_with_llm(
                    rec,
                    selected_dosage_form="oral",
                    selected_indication=case["indication"],
                )
                extracted_direction = str(
                    evidence.get("result_direction") or "Unknown"
                ).strip()
                direction_pass = extracted_direction in accepted
                if direction_pass:
                    direction_ok += 1
            except Exception as exc:
                parse_errors += 1
                direction_error = str(exc)
                direction_pass = False

        row = {
            "id": case["id"],
            "gate_expect": case["gate_expect"],
            "serious_safety": len(serious),
            "regulatory_blocks": len(blocking),
            "gate_error": gate_error,
            "direction": extracted_direction,
            "direction_accept": accepted,
            "direction_pass": direction_pass,
            "direction_error": direction_error,
            "warnings": warnings,
        }
        rows.append(row)
        print("CASE " + json.dumps(row, ensure_ascii=False, separators=(",", ":")))

    direction_accuracy = _ratio(direction_ok, direction_total)
    summary = {
        "benchmark_id": payload["benchmark_id"],
        "cases": len(cases),
        "direction_cases": direction_total,
        "direction_accuracy": direction_accuracy,
        "serious_safety_sensitivity": _ratio(safety_tp, safety_pos),
        "serious_safety_specificity": _ratio(safety_tn, safety_neg),
        "regulatory_block_sensitivity": _ratio(reg_tp, reg_pos),
        "regulatory_block_specificity": _ratio(reg_tn, reg_neg),
        "catastrophic_fn": catastrophic_fn,
        "false_hard_stop": false_hard_stop,
        "parse_errors": parse_errors,
        "frozen_case_file_sha256": FROZEN_CASE_FILE_SHA256,
        "supabase_reads": 0,
        "supabase_writes": 0,
    }
    checks = {
        "direction_accuracy>=0.80": direction_accuracy is not None and direction_accuracy >= 0.80,
        "serious_safety_sensitivity==1.0": summary["serious_safety_sensitivity"] == 1.0,
        "serious_safety_specificity==1.0": summary["serious_safety_specificity"] == 1.0,
        "regulatory_block_sensitivity==1.0": summary["regulatory_block_sensitivity"] == 1.0,
        "regulatory_block_specificity==1.0": summary["regulatory_block_specificity"] == 1.0,
        "catastrophic_fn==0": catastrophic_fn == 0,
        "false_hard_stop==0": false_hard_stop == 0,
        "parse_errors==0": parse_errors == 0,
    }
    summary["checks"] = checks
    summary["pass"] = all(checks.values())

    Path("independent_raw_extraction_holdout_v1_result.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
