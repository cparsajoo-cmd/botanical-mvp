from __future__ import annotations
import json
from pathlib import Path
from evidence_interpretation import classify_evidence_direction
DATA_PATH=Path(__file__).with_name("human_evidence_direction_external_validation_v2.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def evaluate():
    rows=[]
    for r in load_records():
        actual=classify_evidence_direction(r["benchmark_text"])[0]
        rows.append({"record_id":r["record_id"],"pmid":r["pmid"],"expected":r["expected_direction"],"actual":actual,"correct":actual==r["expected_direction"]})
    correct=sum(x["correct"] for x in rows)
    return {"benchmark_id":"human-evidence-direction-external-validation-v2","accuracy":{"correct":correct,"total":len(rows),"value":correct/len(rows)},"rows":rows}
