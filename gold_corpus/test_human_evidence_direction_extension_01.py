from gold_corpus.human_evidence_direction_extension_01 import load_records, evaluate
import json
from pathlib import Path

def test_extension_has_12_unique_real_pubmed_records():
    records = load_records()
    assert len(records) == 12
    pmids = [r["pmid"] for r in records]
    assert len(set(pmids)) == 12
    assert all(pmid.isdigit() for pmid in pmids)
    assert all(r["source_url"] == f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/" for r in records)

def test_extension_is_disjoint_from_original_frozen_benchmark():
    original = json.loads(
        Path(__file__).with_name("human_evidence_direction_benchmark.json").read_text(encoding="utf-8")
    )
    original_pmids = {r["pmid"] for r in original["records"]}
    extension_pmids = {r["pmid"] for r in load_records()}
    assert original_pmids.isdisjoint(extension_pmids)

def test_extension_direction_distribution_is_intentional():
    counts = {}
    for r in load_records():
        counts[r["expected_direction"]] = counts.get(r["expected_direction"], 0) + 1
    assert counts == {"positive": 3, "null": 2, "negative": 4, "mixed": 3}

def test_curated_summaries_are_explicitly_disclosed():
    curated = [r for r in load_records() if r["text_origin"] == "curated_summary_from_abstract"]
    assert curated
    assert all(r["expected_direction"] == "mixed" for r in curated)

def test_benchmark_is_measurement_not_pass_threshold():
    result = evaluate()
    assert result["direction_accuracy"]["total"] == 12
    assert 0.0 <= result["direction_accuracy"]["value"] <= 1.0
