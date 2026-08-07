from __future__ import annotations
import json
from pathlib import Path
try:
    from .regulatory_corpus_extension_07_national_fda import coverage
except ImportError:
    from regulatory_corpus_extension_07_national_fda import coverage
if __name__=="__main__":
    result=coverage()
    Path(__file__).with_name("regulatory_corpus_extension_07_national_fda_run.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
