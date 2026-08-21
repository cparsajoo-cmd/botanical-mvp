"""Append-only provenance for scientific-validation executions.

This module belongs to the validation layer only.  It does not alter candidate
retrieval, scoring, evidence interpretation, safety/regulatory gates, or final
decision policy.

The key invariant is simple: a validation execution receives a new immutable
artifact path.  Historical blind artifacts are never reused as a destination
for later regression/post-remediation runs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Optional


class DatasetStatus(str, Enum):
    INDEPENDENT_FROZEN = "independent_frozen"
    EXPOSED = "exposed"
    REGRESSION = "regression"
    DEVELOPMENT = "development"


@dataclass(frozen=True)
class ValidationRunProvenance:
    dataset_name: str
    dataset_version: str
    dataset_status: str
    engine_version: str
    repository_id: Optional[str]
    run_timestamp: str
    labels_visible_before_execution: bool
    results_previously_inspected: bool
    used_for_remediation: Optional[bool]
    run_kind: str
    overall_result: Mapping[str, Any]
    per_class_metrics: Mapping[str, Any]
    safety_regulatory_metrics: Mapping[str, Any]
    output_artifact_path: str
    historical_blind_result_path: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repository_identifier(repo_root: str | Path) -> Optional[str]:
    """Return git HEAD when available; absence is recorded honestly as None."""
    root = Path(repo_root).resolve()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value or None


def _safe_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in value).strip("-") or "run"


def _timestamp_component(timestamp: str) -> str:
    return timestamp.replace(":", "").replace("+", "_").replace(".", "-")


def immutable_run_path(
    repo_root: str | Path,
    *,
    dataset_name: str,
    engine_version: str,
    timestamp: Optional[str] = None,
) -> Path:
    ts = timestamp or utc_now_iso()
    return (
        Path(repo_root).resolve()
        / "gold_corpus"
        / "validation_runs"
        / _safe_component(dataset_name)
        / f"{_timestamp_component(ts)}__engine-{_safe_component(engine_version)}.json"
    )


def write_immutable_json(path: str | Path, payload: Mapping[str, Any]) -> Path:
    """Write once using exclusive creation; never replace an existing artifact."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
        handle.write("\n")
    return target


def append_registry_record(repo_root: str | Path, record: ValidationRunProvenance) -> Path:
    """Append one machine-readable JSONL provenance record."""
    registry = Path(repo_root).resolve() / "gold_corpus" / "validation_run_registry.jsonl"
    registry.parent.mkdir(parents=True, exist_ok=True)
    with registry.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n")
    return registry


def persist_validation_run(
    *,
    repo_root: str | Path,
    dataset_name: str,
    dataset_version: str,
    dataset_status: DatasetStatus | str,
    engine_version: str,
    result_payload: Mapping[str, Any],
    labels_visible_before_execution: bool,
    results_previously_inspected: bool,
    used_for_remediation: Optional[bool],
    run_kind: str,
    overall_result: Mapping[str, Any],
    per_class_metrics: Mapping[str, Any],
    safety_regulatory_metrics: Mapping[str, Any],
    historical_blind_result_path: Optional[str] = None,
    notes: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> tuple[Path, Path, ValidationRunProvenance]:
    """Persist a new immutable execution artifact and append its provenance.

    ``dataset_status`` describes the dataset *at this execution*.  A dataset
    whose original run was independent becomes ``exposed``/``regression`` for
    subsequent executions after labels/results have been seen.
    """
    root = Path(repo_root).resolve()
    ts = timestamp or utc_now_iso()
    status = dataset_status.value if isinstance(dataset_status, DatasetStatus) else str(dataset_status)
    if status not in {x.value for x in DatasetStatus}:
        raise ValueError(f"Unsupported dataset status: {status}")
    if status == DatasetStatus.INDEPENDENT_FROZEN.value:
        incompatible = []
        if labels_visible_before_execution:
            incompatible.append("labels were visible before execution")
        if results_previously_inspected:
            incompatible.append("results were previously inspected")
        if used_for_remediation:
            incompatible.append("dataset was used for remediation")
        if incompatible:
            raise ValueError(
                "Cannot record dataset_status='independent_frozen': " + "; ".join(incompatible)
            )

    artifact = immutable_run_path(
        root, dataset_name=dataset_name, engine_version=engine_version, timestamp=ts
    )
    payload = dict(result_payload)
    payload["validation_provenance"] = {
        "dataset_name": dataset_name,
        "dataset_version": dataset_version,
        "dataset_status": status,
        "engine_version": engine_version,
        "run_timestamp": ts,
        "labels_visible_before_execution": bool(labels_visible_before_execution),
        "results_previously_inspected": bool(results_previously_inspected),
        "used_for_remediation": used_for_remediation,
        "run_kind": run_kind,
        "historical_blind_result_path": historical_blind_result_path,
    }
    write_immutable_json(artifact, payload)

    relative_artifact = artifact.relative_to(root).as_posix()
    record = ValidationRunProvenance(
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        dataset_status=status,
        engine_version=engine_version,
        repository_id=repository_identifier(root),
        run_timestamp=ts,
        labels_visible_before_execution=bool(labels_visible_before_execution),
        results_previously_inspected=bool(results_previously_inspected),
        used_for_remediation=used_for_remediation,
        run_kind=run_kind,
        overall_result=dict(overall_result),
        per_class_metrics=dict(per_class_metrics),
        safety_regulatory_metrics=dict(safety_regulatory_metrics),
        output_artifact_path=relative_artifact,
        historical_blind_result_path=historical_blind_result_path,
        notes=notes,
    )
    registry = append_registry_record(root, record)
    return artifact, registry, record
