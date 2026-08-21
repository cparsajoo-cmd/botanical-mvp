import ast
from pathlib import Path

from gold_corpus.evidence_direction_validation_v1 import evaluate, load_benchmark


def test_benchmark_uses_existing_five_class_taxonomy_and_is_balanced():
    benchmark = load_benchmark()
    assert benchmark["taxonomy"] == ["positive", "negative", "null", "mixed", "unclear"]
    counts = {label: 0 for label in benchmark["taxonomy"]}
    for record in benchmark["records"]:
        counts[record["expected"]] += 1
    assert counts == {"positive": 5, "negative": 5, "null": 5, "mixed": 5, "unclear": 5}


def test_benchmark_has_unique_ids_and_no_case_specific_production_dependency():
    benchmark = load_benchmark()
    ids = [record["id"] for record in benchmark["records"]]
    assert len(ids) == len(set(ids)) == 25

    production_path = Path(__file__).resolve().parents[1] / "evidence_interpretation.py"
    production_source = production_path.read_text(encoding="utf-8")
    assert "evidence_direction_validation_v1" not in production_source
    assert not any(record_id in production_source for record_id in ids)


def test_evaluator_reports_confusion_recall_and_explicit_errors():
    result = evaluate()
    assert result["record_count"] == 25
    assert set(result["per_class_recall"]) == {"positive", "negative", "null", "mixed", "unclear"}
    assert set(result["confusion_matrix"]) == {"positive", "negative", "null", "mixed", "unclear"}
    assert isinstance(result["errors"], list)
    for error in result["errors"]:
        assert error["expected"] != error["actual"]


def test_validation_module_is_not_imported_by_production_resolver():
    production_path = Path(__file__).resolve().parents[1] / "evidence_interpretation.py"
    tree = ast.parse(production_path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any("evidence_direction_validation_v1" in name for name in imported)
