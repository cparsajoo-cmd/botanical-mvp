from __future__ import annotations
import json
from pathlib import Path

DATA_PATH=Path(__file__).with_name("authoritative_monograph_corpus_extension_05.json")

def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]

def coverage():
    records=load_records()
    return {
        "total":len(records),
        "by_source_family":{
            "EMA_HMPC":sum(r["source_family"]=="EMA_HMPC" for r in records),
            "ESCOP_MONOGRAPH":sum(r["source_family"]=="ESCOP_MONOGRAPH" for r in records),
        },
        "unique_urls":len({r["source_url"] for r in records}),
        "unique_botanical_names":len({r["botanical_name"] for r in records}),
    }
