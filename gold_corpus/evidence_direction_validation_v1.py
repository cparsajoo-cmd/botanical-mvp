"""Development benchmark for Stage 1 evidence-direction hardening.

This module is validation-only. Production code must never import this module or
its labels. The benchmark measures field-level Evidence Direction agreement,
per-class recall, confusion, and explicit errors across the repository's existing
canonical taxonomy: positive, negative, null, mixed, unclear.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evidence_interpretation import classify_evidence_direction

DATA_PATH = Path(__file__).with_name("evidence_direction_validation_v1.json")
RUN_PATH = Path(__file__).with_name("evidence_direction_validation_v1_run.json")


def load_benchmark() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def evaluate() -> dict:
    benchmark = load_benchmark()
    labels = list(benchmark["taxonomy"])
    rows = []
    for record in benchmark["records"]:
        actual, positive_hits, null_hits, negative_hits = classify_evidence_direction(record["text"])
        rows.append({
            "id": record["id"],
            "origin": record["origin"],
            "expected": record["expected"],
            "actual": actual,
            "correct": actual == record["expected"],
            "matched_positive": positive_hits,
            "matched_null": null_hits,
            "matched_negative": negative_hits,
        })

    confusion = Counter((row["expected"], row["actual"]) for row in rows)
    per_class_recall = {}
    for label in labels:
        class_rows = [row for row in rows if row["expected"] == label]
        correct = sum(row["correct"] for row in class_rows)
        total = len(class_rows)
        per_class_recall[label] = {
            "correct": correct,
            "total": total,
            "recall": correct / total if total else None,
        }

    correct = sum(row["correct"] for row in rows)
    total = len(rows)
    return {
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_version": benchmark["benchmark_version"],
        "status": benchmark["status"],
        "record_count": total,
        "agreement": {"correct": correct, "total": total, "value": correct / total if total else None},
        "per_class_recall": per_class_recall,
        "confusion_matrix": {
            expected: {actual: confusion.get((expected, actual), 0) for actual in labels}
            for expected in labels
        },
        "errors": [row for row in rows if not row["correct"]],
        "rows": rows,
        "interpretation": (
            "Development benchmark only. It is not an independent scientific-validation estimate and "
            "must not be used as external ground truth."
        ),
    }


def write_run(path: Path | None = None) -> Path:
    target = path or RUN_PATH
    target.write_text(json.dumps(evaluate(), indent=2) + "\n", encoding="utf-8")
    return target
