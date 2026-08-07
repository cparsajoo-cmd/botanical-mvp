"""Benchmark-only evaluator for real human evidence direction examples.

This module deliberately DOES NOT alter evidence_interpretation.py or any production
engine behavior. It records the frozen baseline of the existing classifier against
curated, traceable human-study language.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from evidence_interpretation import classify_evidence_direction, classify_study_design

CORPUS_DIR = Path(__file__).resolve().parent
DATA_PATH = CORPUS_DIR / "human_evidence_direction_benchmark.json"
RUN_PATH = CORPUS_DIR / "human_evidence_direction_benchmark_run.json"


def _ratio(n: int, d: int):
    return {"numerator": n, "denominator": d, "value": (n / d if d else None)}


def load_benchmark() -> dict:
    return json.loads(DATA_PATH.read_text())


def evaluate_benchmark() -> dict:
    data = load_benchmark()
    rows = []
    for record in data["records"]:
        direction, pos, null, neg = classify_evidence_direction(record["benchmark_text"])
        design = classify_study_design(record["benchmark_text"])
        rows.append({
            "record_id": record["record_id"],
            "pmid": record.get("pmid"),
            "taxon": record["taxon"],
            "expected_direction": record["direction_expected"],
            "actual_direction": direction,
            "direction_match": direction == record["direction_expected"],
            "expected_study_design": record["study_design_expected"],
            "actual_study_design": design,
            "study_design_match": design == record["study_design_expected"],
            "matched_positive": pos,
            "matched_null": null,
            "matched_negative": neg,
        })

    by_expected = defaultdict(list)
    for row in rows:
        by_expected[row["expected_direction"]].append(row)

    direction_by_label = {
        label: _ratio(sum(r["direction_match"] for r in group), len(group))
        for label, group in sorted(by_expected.items())
    }
    confusion = Counter((r["expected_direction"], r["actual_direction"]) for r in rows)

    return {
        "benchmark_version": data["benchmark_version"],
        "record_count": len(rows),
        "direction_accuracy": _ratio(sum(r["direction_match"] for r in rows), len(rows)),
        "study_design_accuracy": _ratio(sum(r["study_design_match"] for r in rows), len(rows)),
        "direction_accuracy_by_expected_label": direction_by_label,
        "direction_confusion": [
            {"expected": e, "actual": a, "count": n}
            for (e, a), n in sorted(confusion.items())
        ],
        "rows": rows,
        "interpretation": (
            "This is a frozen baseline diagnostic on real human-study language. "
            "No accuracy threshold is used to tune or modify production logic."
        ),
    }


def write_run(path: Path | None = None) -> Path:
    target = path or RUN_PATH
    target.write_text(json.dumps(evaluate_benchmark(), indent=2) + "\n")
    return target
