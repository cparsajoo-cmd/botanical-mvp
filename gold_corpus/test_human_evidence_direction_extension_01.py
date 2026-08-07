
from human_evidence_direction_extension_01 import load_records, evaluate

def test_extension_has_12_real_pubmed_records():
    records = load_records()
    assert len(records) == 12
    assert all(r["pmid"].isdigit() for r in records)
    assert all(r["source_url"] == f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/" for r in records)

def test_extension_direction_distribution_is_intentional():
    records = load_records()
    counts = {}
    for r in records:
        counts[r["expected_direction"]] = counts.get(r["expected_direction"], 0) + 1
    assert counts == {"positive":3, "null":2, "negative":4, "mixed":3}

def test_curated_summaries_are_disclosed_not_mislabeled_verbatim():
    records = load_records()
    curated = [r for r in records if r["text_origin"] == "curated_summary_from_abstract"]
    assert len(curated) == 3
    assert all(r["expected_direction"] == "mixed" for r in curated)

def test_extension_is_direction_only():
    result = evaluate()
    assert result["direction_accuracy"]["total"] == 12
    assert "study_design_accuracy" not in result

def test_benchmark_is_measurement_not_pass_threshold():
    result = evaluate()
    # Deliberately no minimum-accuracy assertion: failures are benchmark findings, not reasons to tune truth.
    assert 0.0 <= result["direction_accuracy"]["value"] <= 1.0
