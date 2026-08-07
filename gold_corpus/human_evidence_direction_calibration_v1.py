from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
from evidence_interpretation import classify_evidence_direction

DATA_PATH = Path(__file__).with_name("human_evidence_direction_calibration_v1.json")

def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]

def evaluate():
    rows = []
    for record in load_records():
        actual = classify_evidence_direction(record["text"])[0]
        rows.append({
            "record_id": record["record_id"],
            "pmid": record["pmid"],
            "set": record["set"],
            "expected": record["expected_direction"],
            "actual": actual,
            "correct": actual == record["expected_direction"],
        })
    by_expected = {}
    for label in ("positive", "null", "negative", "mixed"):
        group = [r for r in rows if r["expected"] == label]
        by_expected[label] = {
            "correct": sum(r["correct"] for r in group),
            "total": len(group),
        }
    by_set = {}
    for name in ("original", "extension_01"):
        group = [r for r in rows if r["set"] == name]
        by_set[name] = {
            "correct": sum(r["correct"] for r in group),
            "total": len(group),
        }
    correct = sum(r["correct"] for r in rows)
    return {
        "calibration_set_id": "human-evidence-direction-calibration-v1",
        "record_count": len(rows),
        "accuracy": {"correct": correct, "total": len(rows), "value": correct / len(rows)},
        "by_expected_direction": by_expected,
        "by_source_set": by_set,
        "confusion": [
            {"expected": e, "actual": a, "count": n}
            for (e, a), n in sorted(Counter((r["expected"], r["actual"]) for r in rows).items())
        ],
        "rows": rows,
    }
