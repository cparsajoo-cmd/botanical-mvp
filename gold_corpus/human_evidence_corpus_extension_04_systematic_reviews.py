from __future__ import annotations
import json
from pathlib import Path
from evidence_interpretation import classify_evidence_direction

DATA_PATH = Path(__file__).with_name("human_evidence_corpus_extension_04_systematic_reviews.json")

def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]

def evaluate():
    rows = []
    for record in load_records():
        predicted = classify_evidence_direction(record["evidence_text"])[0]
        rows.append({
            "record_id": record["record_id"],
            "pmid": record["pmid"],
            "expected_direction": record["expected_direction"],
            "predicted_direction": predicted,
            "correct": predicted == record["expected_direction"],
        })
    correct = sum(row["correct"] for row in rows)
    by_label = {}
    for label in ("positive", "null", "negative", "mixed"):
        group = [row for row in rows if row["expected_direction"] == label]
        by_label[label] = {
            "correct": sum(row["correct"] for row in group),
            "total": len(group),
        }
    return {
        "corpus_extension_id": "human-evidence-corpus-extension-04-systematic-reviews",
        "accuracy": {"correct": correct, "total": len(rows), "value": correct / len(rows)},
        "by_expected_direction": by_label,
        "rows": rows,
    }
