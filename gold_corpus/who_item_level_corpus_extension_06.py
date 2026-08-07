from __future__ import annotations
import json
from pathlib import Path

DATA_PATH = Path(__file__).with_name("who_item_level_corpus_extension_06.json")

def load_records():
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))["records"]

def coverage():
    records = load_records()
    return {
        "total": len(records),
        "unique_monographs": len({(r["volume"], r["monograph"]) for r in records}),
        "who_hosted": sum(r["source_url"].startswith("https://iris.who.int/") for r in records),
        "item_level_verified": sum(r["verification_level"] == "WHO_hosted_item_level_text_verified" for r in records),
    }
