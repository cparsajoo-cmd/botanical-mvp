import json
from pathlib import Path
from gold_corpus.human_evidence_corpus_extension_04_systematic_reviews import load_records, evaluate

def _existing_pmids_except_extension_04():
    here = Path(__file__).parent
    pmids = set()
    for path in here.glob("human_evidence*.json"):
        if path.name == "human_evidence_corpus_extension_04_systematic_reviews.json" or path.name.endswith("_run.json"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        pmids.update(str(r["pmid"]) for r in data.get("records", []) if r.get("pmid"))
    return pmids

def test_extension_04_has_18_unique_pubmed_records():
    records = load_records()
    assert len(records) == 18
    pmids = [r["pmid"] for r in records]
    assert len(set(pmids)) == 18
    assert all(pmid.isdigit() for pmid in pmids)
    assert all(r["source_url"] == f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/" for r in records)

def test_extension_04_has_zero_overlap_with_prior_human_corpus():
    assert {r["pmid"] for r in load_records()}.isdisjoint(_existing_pmids_except_extension_04())

def test_extension_04_is_high_level_evidence_only():
    allowed = {"systematic_review", "meta_analysis", "systematic_review_meta_analysis", "umbrella_review"}
    assert all(r["study_design"] in allowed for r in load_records())

def test_extension_04_direction_distribution():
    counts = {}
    for record in load_records():
        counts[record["expected_direction"]] = counts.get(record["expected_direction"], 0) + 1
    assert counts == {"positive": 8, "negative": 2, "mixed": 8}

def test_extension_04_curator_summaries_are_disclosed():
    assert all(r["text_origin"] == "curated_summary_from_pubmed_abstract" for r in load_records())

def test_extension_04_is_measurement_only():
    result = evaluate()
    assert result["accuracy"]["total"] == 18
    assert 0.0 <= result["accuracy"]["value"] <= 1.0
