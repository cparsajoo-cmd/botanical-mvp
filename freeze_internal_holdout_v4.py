"""Freeze a completed, independently referenced RGV v4 holdout exactly once.

The tool refuses to freeze placeholder/model-generated labels, a failed leakage
report, missing snapshot files, or a second freeze over an existing manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from botanical_rd_candidate_engine import DECISION_ENGINE_VERSION
from check_internal_holdout_v4_leakage import evaluate_leakage
from internal_holdout_v4 import extract_publication_identifiers, sha256_file, validate_reference_cases_document

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "gold_corpus/scientific_validity/rgv_v4"
DEFAULT_CASES = BASE / "reference_cases.json"
DEFAULT_MANIFEST = BASE / "FREEZE_MANIFEST.json"


def build_freeze_manifest(cases_path: Path, *, repo_root: Path = ROOT) -> dict:
    document = json.loads(cases_path.read_text(encoding="utf-8"))
    readiness = validate_reference_cases_document(document, require_complete_labels=True)
    if not readiness.ready:
        raise ValueError("Holdout is not freeze-ready: " + "; ".join(readiness.errors))
    if document.get("labels_visible_to_engine_before_first_execution") is not False:
        raise ValueError("labels_visible_to_engine_before_first_execution must be explicitly false")
    if document.get("used_for_engine_remediation") is not False:
        raise ValueError("used_for_engine_remediation must be explicitly false")
    if document.get("reference_defining_evidence_excluded_from_engine_input") is not True:
        raise ValueError("reference_defining_evidence_excluded_from_engine_input must be explicitly true")

    leakage = evaluate_leakage(document, repo_root=repo_root)
    if leakage["status"] != "pass":
        raise ValueError("Leakage check failed: " + "; ".join(leakage["blockers"]))
    if document.get("manual_study_overlap_review_complete") is not True:
        raise ValueError("manual_study_overlap_review_complete must be true before freeze")

    files = {cases_path.relative_to(BASE).as_posix(): sha256_file(cases_path)}
    snapshots_dir = BASE / "snapshots"
    for case in document["cases"]:
        rel = str(case.get("engine_input_snapshot") or "").strip()
        if not rel:
            raise ValueError(f"{case.get('case_id')}: engine_input_snapshot is required before freeze")
        path = BASE / rel
        if not path.exists():
            raise ValueError(f"{case.get('case_id')}: missing engine input snapshot {rel}")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        reference_ids = extract_publication_identifiers(case.get("reference_evidence") or [])
        engine_ids = extract_publication_identifiers(snapshot)
        for kind in ("dois", "pmids", "ncts"):
            shared = reference_ids[kind] & engine_ids[kind]
            if shared:
                raise ValueError(
                    f"{case.get('case_id')}: reference-defining {kind.upper()} also appears in engine input: {sorted(shared)}"
                )
        files[rel] = sha256_file(path)

    now = datetime.now(timezone.utc).isoformat()
    class_distribution = {}
    for case in document["cases"]:
        label = case["expected_decision"]
        class_distribution[label] = class_distribution.get(label, 0) + 1
    return {
        "schema_version": "rgv4-freeze-manifest/1.0.0",
        "freeze_id": f"rgv4-{now}",
        "frozen_on_utc": now,
        "dataset_name": "reference_grounded_validation_v4",
        "dataset_status_at_freeze": "independent_frozen",
        "engine_version_frozen_for_first_run": DECISION_ENGINE_VERSION,
        "n_cases": len(document["cases"]),
        "class_distribution": class_distribution,
        "reference_labels_frozen_before_engine_execution": True,
        "reference_established_independently_of_platform_output": True,
        "reference_defining_evidence_excluded_from_engine_input": True,
        "labels_visible_to_engine_before_first_execution": False,
        "used_for_engine_remediation": False,
        "leakage_check_status": "pass",
        "manual_study_overlap_review_complete": True,
        "file_hashes": files,
        "anti_overfitting_rule": "After the first engine output is inspected, RGV v4 immediately becomes exposed/regression data. Any remediation based on it requires a new untouched holdout for a new independent estimate.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = ap.parse_args()
    if args.manifest.exists():
        raise SystemExit(f"Refusing to overwrite existing freeze manifest: {args.manifest}")
    manifest = build_freeze_manifest(args.cases)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print(args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
