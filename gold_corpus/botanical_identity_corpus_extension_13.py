from __future__ import annotations
import json
from pathlib import Path
DATA_PATH=Path(__file__).with_name("botanical_identity_corpus_extension_13.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def coverage():
    r=load_records()
    return {
        "total":len(r),
        "accepted":sum(x["taxonomic_status"]=="accepted" for x in r),
        "synonym":sum(x["taxonomic_status"]=="synonym" for x in r),
        "unique_urls":len({x["source_url"] for x in r}),
        "unique_families":len({x["family"] for x in r}),
    }
