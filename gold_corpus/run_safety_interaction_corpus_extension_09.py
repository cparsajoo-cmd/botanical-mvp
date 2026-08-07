from __future__ import annotations
import json
from pathlib import Path
try:
    from .safety_interaction_corpus_extension_09 import coverage
except ImportError:
    from safety_interaction_corpus_extension_09 import coverage
if __name__=="__main__":
    result=coverage()
    Path(__file__).with_name("safety_interaction_corpus_extension_09_run.json").write_text(
        json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
