from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path

from gold_corpus.e2e_snapshot_pilot import build_pilot_evaluation_run


def _jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def main(output: str = "gold_corpus/e2e_snapshots/pilot_evaluation_run.json"):
    run = build_pilot_evaluation_run()
    payload = _jsonable(asdict(run))
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(path)
    for case in run.case_results:
        print(case.case_id, "failures=", len(case.failures), "decision=", case.decision_class)
    return run


if __name__ == "__main__":
    main()
