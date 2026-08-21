"""Conservative pre-freeze leakage checker for the future RGV v4 holdout.

Checks exact case-context overlap plus DOI/PMID/NCT overlap against historical
validation material already present in the repository.  It deliberately does
not infer study identity from title similarity; ambiguous possible linkage is
reported for human review rather than fabricated as a match.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from internal_holdout_v4 import case_key, extract_publication_identifiers, validate_reference_cases_document

ROOT = Path(__file__).resolve().parent
DEFAULT_CASES = ROOT / "gold_corpus/scientific_validity/rgv_v4/reference_cases.json"
RGV4_DIR = (ROOT / "gold_corpus/scientific_validity/rgv_v4").resolve()


def _json_files_for_historical_scan(root: Path):
    excluded_rgv4 = (root / "gold_corpus/scientific_validity/rgv_v4").resolve()
    for path in root.rglob("*.json"):
        resolved = path.resolve()
        if excluded_rgv4 == resolved or excluded_rgv4 in resolved.parents:
            continue
        if any(part in {".git", ".pytest_cache", "__pycache__"} for part in path.parts):
            continue
        name = path.name.lower()
        text = path.as_posix().lower()
        if any(token in text for token in ("gold_corpus", "gold_cases", "holdout", "validation")):
            yield path


def _historical_index(root: Path) -> dict[str, Any]:
    index = {"dois": set(), "pmids": set(), "ncts": set(), "case_keys": set(), "files_scanned": 0}
    for path in _json_files_for_historical_scan(root):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        index["files_scanned"] += 1
        ids = extract_publication_identifiers(payload)
        for kind in ("dois", "pmids", "ncts"):
            index[kind].update(ids[kind])

        candidates = []
        if isinstance(payload, dict):
            if isinstance(payload.get("cases"), list):
                candidates.extend(payload["cases"])
            candidates.append(payload)
        elif isinstance(payload, list):
            candidates.extend(payload)
        for obj in candidates:
            if isinstance(obj, dict):
                ck = case_key(obj)
                if all(ck[:2]):
                    index["case_keys"].add(ck)
    return index


def evaluate_leakage(document: dict[str, Any], *, repo_root: Path = ROOT) -> dict[str, Any]:
    structural = validate_reference_cases_document(document, require_complete_labels=False)
    historical = _historical_index(repo_root)
    cases = document.get("cases") if isinstance(document.get("cases"), list) else []

    candidate_ids = extract_publication_identifiers(document)
    exact_case_overlaps = []
    for case in cases:
        if isinstance(case, dict):
            ck = case_key(case)
            if ck in historical["case_keys"]:
                exact_case_overlaps.append({"case_id": case.get("case_id"), "case_key": list(ck)})

    overlap = {
        "dois": sorted(candidate_ids["dois"] & historical["dois"]),
        "pmids": sorted(candidate_ids["pmids"] & historical["pmids"]),
        "ncts": sorted(candidate_ids["ncts"] & historical["ncts"]),
    }
    within_candidate_duplicate_ids = {}
    for kind in ("dois", "pmids", "ncts"):
        seen = {}
        for case in cases:
            if not isinstance(case, dict):
                continue
            ids = extract_publication_identifiers(case)[kind]
            for ident in ids:
                seen.setdefault(ident, []).append(case.get("case_id"))
        within_candidate_duplicate_ids[kind] = {
            ident: ids for ident, ids in seen.items() if len(ids) > 1
        }

    explicit_study_ids = {}
    for case in cases:
        if not isinstance(case, dict):
            continue
        sid = str(case.get("study_identity") or "").strip()
        if sid:
            explicit_study_ids.setdefault(sid, []).append(case.get("case_id"))
    duplicate_study_ids = {sid: ids for sid, ids in explicit_study_ids.items() if len(ids) > 1}

    blockers = []
    blockers.extend(structural.errors)
    if exact_case_overlaps:
        blockers.append("Exact historical case-context overlap detected")
    for kind, values in overlap.items():
        if values:
            blockers.append(f"Historical {kind.upper()} overlap detected")
    for kind, values in within_candidate_duplicate_ids.items():
        if values:
            blockers.append(f"Within-holdout duplicate {kind.upper()} identifiers detected")
    if duplicate_study_ids:
        blockers.append("Within-holdout duplicate explicit study_identity values detected")

    return {
        "schema_version": "rgv4-leakage-report/1.0.0",
        "dataset_name": "reference_grounded_validation_v4",
        "status": "pass" if not blockers else "fail",
        "historical_files_scanned": historical["files_scanned"],
        "exact_case_overlaps": exact_case_overlaps,
        "historical_identifier_overlap": overlap,
        "within_holdout_duplicate_identifiers": within_candidate_duplicate_ids,
        "within_holdout_duplicate_study_identity": duplicate_study_ids,
        "manual_review_required": [
            "Possible study-level linkage without a shared DOI/PMID/NCT/study_identity cannot be ruled out automatically.",
            "Human review must confirm that secondary publications do not recreate an already-used underlying trial.",
        ],
        "blockers": blockers,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    document = json.loads(args.cases.read_text(encoding="utf-8"))
    report = evaluate_leakage(document)
    output = args.output or args.cases.with_name("leakage_report.json")
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(output)
    print(report["status"])
    if report["blockers"]:
        for blocker in report["blockers"]:
            print(f"BLOCKER: {blocker}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
