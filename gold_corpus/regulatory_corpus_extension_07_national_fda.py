from __future__ import annotations
import json
from pathlib import Path
DATA_PATH=Path(__file__).with_name("regulatory_corpus_extension_07_national_fda.json")
def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]
def coverage():
    records=load_records()
    return {
        "total":len(records),
        "mhra":sum(r["authority"]=="MHRA" for r in records),
        "fda":sum(r["authority"]=="FDA" for r in records),
        "prohibition_like":sum("PROHIBITION" in r["regulatory_category"] for r in records),
        "dose_restriction":sum(r["regulatory_category"]=="DOSE_RESTRICTION" for r in records),
        "pharmacy_only":sum(r["regulatory_category"]=="PHARMACY_ONLY" for r in records),
    }
