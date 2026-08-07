import json
from pathlib import Path
from gold_corpus.human_evidence_corpus_extension_03_observational import load_records,evaluate

def _all_other_human_pmids():
    here=Path(__file__).parent
    result=set()
    for p in here.glob("human_evidence*.json"):
        if p.name=="human_evidence_corpus_extension_03_observational.json" or p.name.endswith("_run.json"):
            continue
        try: data=json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        result.update(str(r["pmid"]) for r in data.get("records",[]) if r.get("pmid"))
    return result

def test_extension_03_has_12_unique_real_pubmed_records():
    records=load_records()
    assert len(records)==12
    pmids=[r["pmid"] for r in records]
    assert len(set(pmids))==12
    assert all(p.isdigit() for p in pmids)
    assert all(r["source_url"]==f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/" for r in records)

def test_extension_03_is_disjoint_from_prior_human_corpus():
    assert {r["pmid"] for r in load_records()}.isdisjoint(_all_other_human_pmids())

def test_extension_03_is_observational_not_rct_extension():
    assert all("observational" in r["study_design"] or "cohort" in r["study_design"] for r in load_records())

def test_extension_03_direction_distribution():
    counts={}
    for r in load_records(): counts[r["expected_direction"]]=counts.get(r["expected_direction"],0)+1
    assert counts=={"positive":6,"null":3,"mixed":3}

def test_extension_03_curated_text_is_disclosed():
    assert all(r["text_origin"]=="curated_summary_from_pubmed_abstract" for r in load_records())

def test_extension_03_is_measurement_only():
    result=evaluate()
    assert result["accuracy"]["total"]==12
    assert 0<=result["accuracy"]["value"]<=1
