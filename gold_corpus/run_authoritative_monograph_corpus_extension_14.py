from __future__ import annotations
import json
from pathlib import Path
try:
    from .authoritative_monograph_corpus_extension_14 import coverage
except ImportError:
    from authoritative_monograph_corpus_extension_14 import coverage
if __name__=="__main__":
    result=coverage()
    Path(__file__).with_name("authoritative_monograph_corpus_extension_14_run.json").write_text(
        json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
