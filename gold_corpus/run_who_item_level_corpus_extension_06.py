from __future__ import annotations
import json
from pathlib import Path
try:
    from .who_item_level_corpus_extension_06 import coverage
except ImportError:
    from who_item_level_corpus_extension_06 import coverage

if __name__ == "__main__":
    result = coverage()
    Path(__file__).with_name("who_item_level_corpus_extension_06_run.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))
