from __future__ import annotations
import json
from pathlib import Path
try:
    from .human_evidence_direction_external_validation_v2 import evaluate
except ImportError:
    from human_evidence_direction_external_validation_v2 import evaluate
if __name__=="__main__":
    r=evaluate(); out=Path(__file__).with_name("human_evidence_direction_external_validation_v2_run.json"); out.write_text(json.dumps(r,indent=2)+"\n"); print(json.dumps(r,indent=2))
