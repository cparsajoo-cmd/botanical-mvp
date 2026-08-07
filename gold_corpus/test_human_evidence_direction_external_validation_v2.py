import json
from pathlib import Path
from gold_corpus.human_evidence_direction_external_validation_v2 import load_records,evaluate
def test_external_v2_has_8_unique_real_pubmed_records():
    records=load_records(); assert len(records)==8; assert len({r["pmid"] for r in records})==8; assert all(r["source_url"]==f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/" for r in records)
def test_external_v2_is_disjoint_from_calibration_v1():
    calibration=json.loads(Path(__file__).with_name("human_evidence_direction_calibration_v1.json").read_text()); assert {r["pmid"] for r in load_records()}.isdisjoint({r["pmid"] for r in calibration["records"]})
def test_external_v2_labels_are_balanced():
    counts={};
    for r in load_records(): counts[r["expected_direction"]]=counts.get(r["expected_direction"],0)+1
    assert counts=={"positive":2,"null":2,"negative":2,"mixed":2}
def test_external_v2_saved_run_matches_current_classifier():
    path=Path(__file__).with_name("human_evidence_direction_external_validation_v2_run.json")
    if path.exists(): assert json.loads(path.read_text())["accuracy"]==evaluate()["accuracy"]
