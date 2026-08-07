from __future__ import annotations
import json
from pathlib import Path
DATA_PATH=Path(__file__).with_name("dose_preparation_corpus_extension_10.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def coverage():
    r=load_records()
    return {
        "total":len(r),
        "unique_botanicals":len({x["botanical_name"] for x in r}),
        "unique_preparations":len({(x["botanical_name"],x["preparation"]) for x in r}),
        "routes":sorted({x["route"] for x in r}),
        "with_explicit_numeric_dose":sum(any(ch.isdigit() for ch in x["dose"]) for x in r),
    }
