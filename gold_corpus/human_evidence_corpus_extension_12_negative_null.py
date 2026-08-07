from __future__ import annotations
import json
from pathlib import Path
from evidence_interpretation import classify_evidence_direction
DATA_PATH=Path(__file__).with_name("human_evidence_corpus_extension_12_negative_null.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def evaluate():
    rows=[]
    for r in load_records():
        predicted=classify_evidence_direction(r["evidence_text"])[0]
        rows.append({
            "record_id":r["record_id"],"pmid":r["pmid"],
            "expected_direction":r["expected_direction"],
            "predicted_direction":predicted,
            "correct":predicted==r["expected_direction"],
        })
    correct=sum(r["correct"] for r in rows)
    by={}
    for label in ("positive","null","negative","mixed"):
        g=[r for r in rows if r["expected_direction"]==label]
        by[label]={"correct":sum(r["correct"] for r in g),"total":len(g)}
    return {
        "corpus_extension_id":"human-evidence-corpus-extension-12-negative-null",
        "accuracy":{"correct":correct,"total":len(rows),"value":correct/len(rows)},
        "by_expected_direction":by,
        "rows":rows,
    }
