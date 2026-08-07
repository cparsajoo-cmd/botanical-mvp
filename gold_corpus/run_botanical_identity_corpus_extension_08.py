from __future__ import annotations
import json
from pathlib import Path
try:
    from .botanical_identity_corpus_extension_08 import coverage
except ImportError:
    from botanical_identity_corpus_extension_08 import coverage
if __name__=="__main__":
    result=coverage()
    Path(__file__).with_name("botanical_identity_corpus_extension_08_run.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
