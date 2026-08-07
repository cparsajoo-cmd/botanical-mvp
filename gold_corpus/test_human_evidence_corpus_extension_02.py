import json
from pathlib import Path
from gold_corpus.human_evidence_corpus_extension_02 import load_records,evaluate
def _prior_pmids():
    here=Path(__file__).parent
    names=["human_evidence_direction_benchmark.json","human_evidence_direction_extension_01.json","human_evidence_direction_external_validation_v2.json"]
    s=set()
    for name in names:
        d=json.loads((here/name).read_text(encoding="utf-8"))
        s.update(str(r["pmid"]) for r in d["records"] if r.get("pmid"))
    return s
def test_extension_02_contains_20_unique_pubmed_records():
    rec=load_records(); assert len(rec)==20
    pm=[r["pmid"] for r in rec]; assert len(set(pm))==20
    assert all(p.isdigit() for p in pm)
    assert all(r["source_url"]==f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/" for r in rec)
def test_extension_02_has_no_overlap_with_prior_frozen_sets():
    assert {r["pmid"] for r in load_records()}.isdisjoint(_prior_pmids())
def test_extension_02_direction_distribution():
    c={}
    for r in load_records(): c[r["expected_direction"]]=c.get(r["expected_direction"],0)+1
    assert c=={"positive":6,"null":5,"negative":4,"mixed":5}
def test_extension_02_discloses_curated_text():
    assert all(r["text_origin"]=="curated_summary_from_pubmed_abstract" for r in load_records())
def test_extension_02_is_measurement_not_tuning_threshold():
    x=evaluate(); assert x["accuracy"]["total"]==20; assert 0<=x["accuracy"]["value"]<=1
