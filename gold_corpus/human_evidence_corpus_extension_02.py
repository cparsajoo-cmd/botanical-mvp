from __future__ import annotations
import json
from pathlib import Path
from evidence_interpretation import classify_evidence_direction
DATA_PATH=Path(__file__).with_name("human_evidence_corpus_extension_02.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def evaluate():
    rows=[]
    for r in load_records():
        p=classify_evidence_direction(r["evidence_text"])[0]
        rows.append({"record_id":r["record_id"],"pmid":r["pmid"],"expected_direction":r["expected_direction"],"predicted_direction":p,"correct":p==r["expected_direction"]})
    by={}
    for label in ("positive","null","negative","mixed"):
        g=[x for x in rows if x["expected_direction"]==label]
        by[label]={"correct":sum(x["correct"] for x in g),"total":len(g)}
    c=sum(x["correct"] for x in rows)
    return {"corpus_extension_id":"human-evidence-corpus-extension-02","accuracy":{"correct":c,"total":len(rows),"value":c/len(rows)},"by_expected_direction":by,"rows":rows}
