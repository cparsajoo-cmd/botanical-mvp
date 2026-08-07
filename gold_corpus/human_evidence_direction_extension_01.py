
from __future__ import annotations
import json
from pathlib import Path
from evidence_interpretation import classify_evidence_direction

DATA_PATH = Path(__file__).with_name("human_evidence_direction_extension_01.json")

def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]

def evaluate():
    rows = []
    for record in load_records():
        predicted_direction = classify_evidence_direction(record["evidence_text"])[0]
        rows.append({
            "id": record["id"],
            "pmid": record["pmid"],
            "expected_direction": record["expected_direction"],
            "predicted_direction": predicted_direction,
            "direction_correct": predicted_direction == record["expected_direction"],
        })
    n = len(rows)
    direction_ok = sum(r["direction_correct"] for r in rows)
    by_label = {}
    for label in ("positive","null","negative","mixed"):
        group = [r for r in rows if r["expected_direction"] == label]
        by_label[label] = {
            "correct": sum(r["direction_correct"] for r in group),
            "total": len(group),
        }
    return {
        "benchmark_id": "human-evidence-direction-extension-01",
        "records": rows,
        "direction_accuracy": {"correct":direction_ok,"total":n,"value":direction_ok/n if n else 0.0},
        "by_expected_direction": by_label,
    }
