from __future__ import annotations
import json
from pathlib import Path
try:
    from .dose_preparation_corpus_extension_10 import coverage
except ImportError:
    from dose_preparation_corpus_extension_10 import coverage
if __name__=="__main__":
    result=coverage()
    Path(__file__).with_name("dose_preparation_corpus_extension_10_run.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
