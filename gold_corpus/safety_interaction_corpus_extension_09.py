from __future__ import annotations
import json
from pathlib import Path
DATA_PATH = Path(__file__).with_name("safety_interaction_corpus_extension_09.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def coverage():
    records=load_records()
    return {
        "total":len(records),
        "ema_family":sum(r["source_family"].startswith("EMA") for r in records),
        "who":sum(r["source_family"]=="WHO_MONOGRAPH" for r in records),
        "interaction_like":sum("INTERACTION" in r["safety_type"] for r in records),
        "contraindication_like":sum("CONTRAINDICATION" in r["safety_type"] for r in records),
        "unique_botanicals":len({r["botanical_name"] for r in records}),
    }
