from gold_corpus.human_evidence_direction_calibration_v1 import load_records, evaluate

def test_calibration_v1_has_24_unique_pmids():
    records = load_records()
    assert len(records) == 24
    assert len({r["pmid"] for r in records}) == 24

def test_calibration_v1_contains_two_equal_sized_frozen_sets():
    records = load_records()
    assert sum(r["set"] == "original" for r in records) == 12
    assert sum(r["set"] == "extension_01" for r in records) == 12

def test_calibration_v1_preserves_all_four_direction_classes():
    labels = {r["expected_direction"] for r in load_records()}
    assert labels == {"positive", "null", "negative", "mixed"}

def test_calibration_v1_is_measurement_only():
    result = evaluate()
    assert result["record_count"] == 24
    assert 0.0 <= result["accuracy"]["value"] <= 1.0
