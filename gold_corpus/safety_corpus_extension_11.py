from __future__ import annotations
import json
from pathlib import Path
DATA_PATH=Path(__file__).with_name("safety_corpus_extension_11.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def coverage():
    r=load_records()
    return {
        "total":len(r),
        "unique_botanicals":len({x["botanical_name"] for x in r}),
        "age_related":sum("AGE" in x["safety_type"] for x in r),
        "pregnancy_lactation":sum("PREGNANCY_LACTATION" in x["safety_type"] for x in r),
        "contraindication_like":sum("CONTRAINDICATION" in x["safety_type"] for x in r),
        "ema_only":all(x["source_family"]=="EMA_HMPC" for x in r),
    }
