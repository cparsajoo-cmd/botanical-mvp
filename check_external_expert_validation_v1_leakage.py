"""Pre-freeze identifier leakage check for External Expert Validation v1.

Exact DOI/PMID/NCT overlap is blocked.  Ambiguous study-level overlap remains a
mandatory human review because title similarity is not reliable enough to infer
underlying-study identity automatically.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from external_expert_validation import validate_evidence_packet
from internal_holdout_v4 import extract_publication_identifiers

ROOT = Path(__file__).resolve().parent
DEFAULT_PACKET = ROOT / "gold_corpus/external_expert_validation_v1/evidence_records.json"
EXTERNAL_DIR = (ROOT / "gold_corpus/external_expert_validation_v1").resolve()


def _historical_json_files(root: Path):
    for path in root.rglob("*.json"):
        resolved = path.resolve()
        if EXTERNAL_DIR == resolved or EXTERNAL_DIR in resolved.parents:
            continue
        if any(part in {".git", ".pytest_cache", "__pycache__"} for part in path.parts):
            continue
        text = path.as_posix().lower()
        if any(token in text for token in ("gold_corpus", "gold_cases", "holdout", "validation")):
            yield path


def evaluate_external_leakage(document: dict[str, Any], *, repo_root: Path = ROOT) -> dict[str, Any]:
    structural = validate_evidence_packet(document, require_freeze_ready=False)
    historical = {"dois": set(), "pmids": set(), "ncts": set()}
    files_scanned = 0
    for path in _historical_json_files(repo_root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        files_scanned += 1
        ids = extract_publication_identifiers(payload)
        for kind in historical:
            historical[kind].update(ids[kind])

    candidate = extract_publication_identifiers(document)
    overlap = {kind: sorted(candidate[kind] & historical[kind]) for kind in historical}

    within: dict[str, dict[str, list[str]]] = {}
    records = document.get("records") if isinstance(document.get("records"), list) else []
    for kind in ("dois", "pmids", "ncts"):
        seen: dict[str, list[str]] = {}
        for record in records:
            if not isinstance(record, dict):
                continue
            for ident in extract_publication_identifiers(record)[kind]:
                seen.setdefault(ident, []).append(str(record.get("record_id") or ""))
        within[kind] = {ident: ids for ident, ids in seen.items() if len(ids) > 1}

    blockers = list(structural.errors)
    for kind, values in overlap.items():
        if values:
            blockers.append(f"Historical {kind.upper()} overlap detected")
    for kind, values in within.items():
        if values:
            blockers.append(f"Within-study duplicate {kind.upper()} identifiers detected")

    return {
        "schema_version": "external-expert-validation-leakage-v1/1.0.0",
        "dataset_name": "external_expert_validation_v1",
        "status": "pass" if not blockers else "fail",
        "historical_files_scanned": files_scanned,
        "historical_identifier_overlap": overlap,
        "within_dataset_duplicate_identifiers": within,
        "manual_study_overlap_review_required": True,
        "manual_review_note": (
            "Shared-study identity without a shared DOI/PMID/NCT cannot be ruled out automatically; "
            "a qualified human must review secondary publications and related trial records before freeze."
        ),
        "blockers": blockers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    document = json.loads(args.packet.read_text(encoding="utf-8"))
    report = evaluate_external_leakage(document)
    output = args.output or args.packet.with_name("leakage_report.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    print(report["status"])
    for blocker in report["blockers"]:
        print(f"BLOCKER: {blocker}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
