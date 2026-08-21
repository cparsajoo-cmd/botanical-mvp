"""Verify RGV v4 freeze integrity and first-run engine-version lock."""
from __future__ import annotations

import json
from pathlib import Path

from botanical_rd_candidate_engine import DECISION_ENGINE_VERSION
from internal_holdout_v4 import verify_manifest_hashes

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "gold_corpus/scientific_validity/rgv_v4"
MANIFEST = BASE / "FREEZE_MANIFEST.json"


def verify_execution_readiness() -> tuple[bool, list[str]]:
    errors = []
    if not MANIFEST.exists():
        return False, ["RGV v4 has not been frozen; FREEZE_MANIFEST.json is absent"]
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    integrity = verify_manifest_hashes(BASE, manifest)
    errors.extend(integrity.errors)
    required = str(manifest.get("engine_version_frozen_for_first_run") or "")
    if DECISION_ENGINE_VERSION != required:
        errors.append(
            f"Engine-version mismatch: frozen first run requires {required}, current engine is {DECISION_ENGINE_VERSION}"
        )
    if manifest.get("dataset_status_at_freeze") != "independent_frozen":
        errors.append("Freeze manifest does not declare independent_frozen status")
    return not errors, errors


def main() -> int:
    ok, errors = verify_execution_readiness()
    if ok:
        print("RGV v4 freeze integrity and engine-version lock verified.")
        return 0
    for error in errors:
        print(f"BLOCKER: {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
