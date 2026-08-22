"""Score completed External Expert Validation v1 artifacts.

The first blind evaluation is write-once.  Later runs can only be explicitly
recorded as regression runs.  Original expert label files are never modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from external_expert_validation import (
    build_external_validation_metrics,
    read_json,
    sha256_file,
    validate_adjudication,
    validate_evidence_packet,
    validate_expert_labels,
    validate_platform_output,
    write_json_exclusive,
)
from validation_provenance import DatasetStatus, persist_validation_run

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "gold_corpus/external_expert_validation_v1"
FIRST_MARKER = DATA_DIR / "FIRST_EVALUATION_COMPLETE.json"


def _require(check, label: str) -> None:
    if not check.valid:
        raise ValueError(f"{label} invalid: " + "; ".join(check.errors))


def _verify_freeze(manifest: dict[str, Any], packet_path: Path) -> None:
    hashes = manifest.get("file_hashes") or {}
    expected = hashes.get(packet_path.relative_to(DATA_DIR).as_posix())
    if not expected:
        raise ValueError("Freeze manifest does not contain evidence packet hash")
    if sha256_file(packet_path) != expected:
        raise ValueError("Frozen evidence packet hash mismatch")


def score(
    *,
    packet_path: Path,
    manifest_path: Path,
    expert_a_path: Path,
    expert_b_path: Path,
    adjudication_path: Path,
    platform_output_path: Path,
    run_kind: str,
) -> Path:
    packet = read_json(packet_path)
    manifest = read_json(manifest_path)
    expert_a = read_json(expert_a_path)
    expert_b = read_json(expert_b_path)
    adjudication = read_json(adjudication_path)
    platform = read_json(platform_output_path)

    _require(validate_evidence_packet(packet, require_freeze_ready=True), "evidence packet")
    _verify_freeze(manifest, packet_path)
    ids = [str(r["record_id"]) for r in packet["records"]]
    _require(validate_expert_labels(expert_a, evidence_record_ids=ids, require_complete=True), "expert A labels")
    _require(validate_expert_labels(expert_b, evidence_record_ids=ids, require_complete=True), "expert B labels")
    if expert_a.get("expert_code") == expert_b.get("expert_code"):
        raise ValueError("Expert A and Expert B must have different expert_code values")
    _require(validate_adjudication(adjudication, evidence_record_ids=ids, require_complete=True), "adjudication")
    _require(validate_platform_output(platform, evidence_record_ids=ids, require_complete=True), "platform output")

    frozen_engine = str(manifest.get("engine_version_target") or "")
    actual_engine = str(platform.get("engine_version") or "")
    if run_kind == "first_blind":
        if FIRST_MARKER.exists():
            raise FileExistsError("First external evaluation has already been completed; use --run-kind regression for later runs")
        if actual_engine != frozen_engine:
            raise ValueError(f"First blind run engine mismatch: frozen={frozen_engine}, platform={actual_engine}")
        if platform.get("reference_labels_visible_to_platform_before_execution") is not False:
            raise ValueError("First blind platform execution must remain blinded to reference labels")
        dataset_status = DatasetStatus.INDEPENDENT_FROZEN
        labels_visible = False
        results_inspected = False
        used_for_remediation = False
    elif run_kind == "regression":
        if not FIRST_MARKER.exists():
            raise ValueError("Regression status is only valid after the first external evaluation exists")
        dataset_status = DatasetStatus.REGRESSION
        labels_visible = True
        results_inspected = True
        used_for_remediation = True
    else:
        raise ValueError("run_kind must be 'first_blind' or 'regression'")

    metrics = build_external_validation_metrics(
        expert_a_labels=expert_a,
        expert_b_labels=expert_b,
        adjudication=adjudication,
        platform_output=platform,
    )
    payload = {
        "schema_version": "external-expert-validation-result-v1/1.0.0",
        "dataset_name": "external_expert_validation_v1",
        "run_kind": run_kind,
        "metrics": metrics,
        "artifact_hashes": {
            "evidence_packet": sha256_file(packet_path),
            "expert_a_labels": sha256_file(expert_a_path),
            "expert_b_labels": sha256_file(expert_b_path),
            "adjudication": sha256_file(adjudication_path),
            "platform_output": sha256_file(platform_output_path),
        },
    }
    overall = {
        field: value["agreement"]
        for field, value in metrics["platform_vs_adjudicated_reference"].items()
    }
    safety_reg = {
        "serious_safety": metrics["serious_safety_metrics"],
        "regulatory": metrics["regulatory_metrics"],
    }
    artifact, _, _ = persist_validation_run(
        repo_root=ROOT,
        dataset_name="external_expert_validation_v1",
        dataset_version="1.0.0",
        dataset_status=dataset_status,
        engine_version=actual_engine,
        result_payload=payload,
        labels_visible_before_execution=labels_visible,
        results_previously_inspected=results_inspected,
        used_for_remediation=used_for_remediation,
        run_kind="external_expert_blind_validation" if run_kind == "first_blind" else "external_expert_regression",
        overall_result=overall,
        per_class_metrics=metrics["platform_vs_adjudicated_reference"],
        safety_regulatory_metrics=safety_reg,
        notes="External expert study tooling; original expert files preserved and hashed.",
    )

    if run_kind == "first_blind":
        marker = {
            "schema_version": "external-expert-validation-first-evaluation-marker/1.0.0",
            "dataset_name": "external_expert_validation_v1",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": actual_engine,
            "immutable_result_artifact": artifact.relative_to(ROOT).as_posix(),
            "status_after_result_inspection": "exposed",
            "future_status_if_used_for_remediation": "regression",
        }
        write_json_exclusive(FIRST_MARKER, marker)
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=DATA_DIR / "evidence_records.json")
    parser.add_argument("--manifest", type=Path, default=DATA_DIR / "FREEZE_MANIFEST.json")
    parser.add_argument("--expert-a", type=Path, required=True)
    parser.add_argument("--expert-b", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--platform-output", type=Path, required=True)
    parser.add_argument("--run-kind", choices=("first_blind", "regression"), default="first_blind")
    args = parser.parse_args()
    result = score(
        packet_path=args.packet,
        manifest_path=args.manifest,
        expert_a_path=args.expert_a,
        expert_b_path=args.expert_b,
        adjudication_path=args.adjudication,
        platform_output_path=args.platform_output,
        run_kind=args.run_kind,
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
