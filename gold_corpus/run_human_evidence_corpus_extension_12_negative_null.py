from __future__ import annotations
import json
from pathlib import Path
try:
    from .human_evidence_corpus_extension_12_negative_null import evaluate
except ImportError:
    from human_evidence_corpus_extension_12_negative_null import evaluate
if __name__=="__main__":
    result=evaluate()
    Path(__file__).with_name("human_evidence_corpus_extension_12_negative_null_run.json").write_text(
        json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
