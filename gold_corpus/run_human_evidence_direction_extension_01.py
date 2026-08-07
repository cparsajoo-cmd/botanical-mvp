
from __future__ import annotations
import json
from pathlib import Path
from human_evidence_direction_extension_01 import evaluate

if __name__ == "__main__":
    result = evaluate()
    out = Path(__file__).with_name("human_evidence_direction_extension_01_run.json")
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
