import json
from pathlib import Path

from gold_corpus.human_evidence_direction_benchmark import evaluate_benchmark, load_benchmark


def test_benchmark_has_real_traceable_sources_and_all_target_labels():
    data = load_benchmark()
    assert len(data["records"]) >= 12
    labels = {r["direction_expected"] for r in data["records"]}
    assert {"positive", "null", "negative", "mixed"}.issubset(labels)
    for row in data["records"]:
        assert row.get("pmid")
        assert row.get("source_url", "").startswith("https://pubmed.ncbi.nlm.nih.gov/")
        assert row.get("benchmark_text")
        assert row.get("rationale")


def test_benchmark_does_not_encode_expected_label_inside_benchmark_text():
    data = load_benchmark()
    for row in data["records"]:
        assert "expected_direction" not in row["benchmark_text"].lower()


def test_evaluator_returns_one_row_per_frozen_record():
    data = load_benchmark()
    result = evaluate_benchmark()
    assert result["record_count"] == len(data["records"])
    assert len(result["rows"]) == len(data["records"])


def test_metrics_are_computed_not_hardcoded():
    result = evaluate_benchmark()
    matches = sum(row["direction_match"] for row in result["rows"])
    assert result["direction_accuracy"]["numerator"] == matches
    assert result["direction_accuracy"]["denominator"] == len(result["rows"])


def test_each_expected_direction_has_multiple_real_examples():
    data = load_benchmark()
    counts = {}
    for row in data["records"]:
        counts[row["direction_expected"]] = counts.get(row["direction_expected"], 0) + 1
    for label in ("positive", "null", "negative", "mixed"):
        assert counts[label] >= 3


def test_run_file_matches_current_evaluator_if_present():
    run = Path(__file__).with_name("human_evidence_direction_benchmark_run.json")
    if not run.exists():
        return
    saved = json.loads(run.read_text())
    current = evaluate_benchmark()
    assert saved["record_count"] == current["record_count"]
    assert saved["direction_accuracy"] == current["direction_accuracy"]
    assert saved["study_design_accuracy"] == current["study_design_accuracy"]
