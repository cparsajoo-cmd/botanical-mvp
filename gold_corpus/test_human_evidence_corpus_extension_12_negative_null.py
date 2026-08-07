import json
from pathlib import Path
from gold_corpus.human_evidence_corpus_extension_12_negative_null import load_records,evaluate

def _prior_pmids():
    here=Path(__file__).parent
    result=set()
    for p in here.glob("human_evidence*.json"):
        if p.name=="human_evidence_corpus_extension_12_negative_null.json" or p.name.endswith("_run.json"):
            continue
        try: data=json.loads(p.read_text(encoding="utf-8"))
        except Exception: continue
        result.update(str(r["pmid"]) for r in data.get("records",[]) if r.get("pmid"))
    return result

def test_extension_12_has_12_unique_pubmed_records():
    r=load_records()
    assert len(r)==12
    pmids=[x["pmid"] for x in r]
    assert len(set(pmids))==12
    assert all(p.isdigit() for p in pmids)
    assert all(x["source_url"]==f"https://pubmed.ncbi.nlm.nih.gov/{x['pmid']}/" for x in r)

def test_extension_12_zero_overlap_with_prior_human_corpus():
    assert {r["pmid"] for r in load_records()}.isdisjoint(_prior_pmids())

def test_extension_12_is_balanced_null_negative():
    counts={}
    for r in load_records(): counts[r["expected_direction"]]=counts.get(r["expected_direction"],0)+1
    assert counts=={"null":6,"negative":6}

def test_extension_12_discloses_curated_text():
    assert all(r["text_origin"]=="curated_summary_from_pubmed_abstract" for r in load_records())

def test_extension_12_contains_multiple_botanicals_and_designs():
    r=load_records()
    assert len({x["botanical"] for x in r})>=7
    assert len({x["study_design"] for x in r})>=4

def test_extension_12_is_measurement_only():
    x=evaluate()
    assert x["accuracy"]["total"]==12
    assert 0<=x["accuracy"]["value"]<=1
