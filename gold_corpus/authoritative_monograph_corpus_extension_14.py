from __future__ import annotations
import json
from pathlib import Path
DATA_PATH=Path(__file__).with_name("authoritative_monograph_corpus_extension_14.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def coverage():
    r=load_records()
    return {
        "total":len(r),
        "ema_hmpc":sum(x["source_family"]=="EMA_HMPC" for x in r),
        "unique_urls":len({x["source_url"] for x in r}),
        "unique_herbal_drugs":len({x["herbal_drug"] for x in r}),
        "finalised":sum(x["assessment_status"]=="F: Assessment finalised" for x in r),
    }
