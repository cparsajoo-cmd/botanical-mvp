"""Freeze the prospective External Expert Validation v1 evidence packet.

The freeze is write-once and records hashes plus the exact engine version that
must be used for the first blind platform execution.  It cannot manufacture or
complete missing scientific records or expert labels.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from check_external_expert_validation_v1_leakage import evaluate_external_leakage
from external_expert_validation import (
    current_engine_version_from_source,
    sha256_file,
    validate_evidence_packet,
    write_json_exclusive,
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "gold_corpus/external_expert_validation_v1"
DEFAULT_PACKET = DATA_DIR / "evidence_records.json"
DEFAULT_MANIFEST = DATA_DIR / "FREEZE_MANIFEST.json"


def freeze(packet_path: Path = DEFAULT_PACKET, manifest_path: Path = DEFAULT_MANIFEST) -> Path:
    document = json.loads(packet_path.read_text(encoding="utf-8"))
    readiness = validate_evidence_packet(document, require_freeze_ready=True)
    if not readiness.valid:
        raise ValueError("Evidence packet is not freeze-ready: " + "; ".join(readiness.errors))

    leakage = evaluate_external_leakage(document, repo_root=ROOT)
    if leakage["status"] != "pass":
        raise ValueError("Leakage check failed: " + "; ".join(leakage["blockers"]))
    if document.get("manual_study_overlap_review_complete") is not True:
        raise ValueError("manual_study_overlap_review_complete must be true before freeze")

    engine_version = current_engine_version_from_source(ROOT)
    manifest = {
        "schema_version": "external-expert-validation-freeze-v1/1.0.0",
        "dataset_name": "external_expert_validation_v1",
        "dataset_status_at_freeze": "independent_frozen",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(document["records"]),
        "engine_version_target": engine_version,
        "labels_visible_to_platform_before_first_execution": False,
        "first_platform_result_previously_inspected": False,
        "used_for_remediation": False,
        "evidence_packet_path": packet_path.relative_to(ROOT).as_posix(),
        "file_hashes": {
            packet_path.relative_to(DATA_DIR).as_posix(): sha256_file(packet_path),
        },
        "leakage_summary": {
            "historical_files_scanned": leakage["historical_files_scanned"],
            "historical_identifier_overlap": leakage["historical_identifier_overlap"],
            "manual_study_overlap_review_complete": True,
        },
    }
    write_json_exclusive(manifest_path, manifest)
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    path = freeze(args.packet, args.manifest)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
