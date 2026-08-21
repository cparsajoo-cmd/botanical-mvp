"""Stage 5 tooling for a clean future internal Reference-Grounded Validation v4.

This module is validation infrastructure only.  It does not change retrieval,
scoring, safety/regulatory gates, eligibility, or final-decision policy.

RGV v4 is intentionally NOT populated with model-authored scientific ground
truth.  A case becomes freeze-eligible only after an independently established
reference assessment has been supplied and leakage checks pass.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

CANONICAL_DECISIONS = {
    "GO",
    "GO WITH CAUTION",
    "EXPERT REVIEW REQUIRED",
    "NO GO SAFETY",
    "NO GO REGULATORY",
    "INSUFFICIENT EVIDENCE",
}

_PMID_RE = re.compile(r"\bPMID\s*[:#]?\s*(\d{5,10})\b", re.I)
_NCT_RE = re.compile(r"\b(NCT\d{8})\b", re.I)
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)


@dataclass(frozen=True)
class HoldoutReadiness:
    ready: bool
    errors: tuple[str, ...]


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _norm_doi(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    return text.rstrip(".,; )]")


def _norm_pmid(value: Any) -> str:
    m = re.search(r"\d{5,10}", str(value or ""))
    return m.group(0) if m else ""


def _norm_nct(value: Any) -> str:
    m = _NCT_RE.search(str(value or ""))
    return m.group(1).upper() if m else ""


def extract_publication_identifiers(value: Any) -> dict[str, set[str]]:
    """Extract DOI/PMID/NCT identifiers conservatively from nested JSON-like data."""
    out = {"dois": set(), "pmids": set(), "ncts": set()}

    def visit(obj: Any) -> None:
        if isinstance(obj, Mapping):
            for key, val in obj.items():
                key_l = str(key).lower()
                vals = val if isinstance(val, list) else [val]
                if key_l in {"doi", "dois"}:
                    for item in vals:
                        doi = _norm_doi(item)
                        if doi:
                            out["dois"].add(doi)
                elif key_l in {"pmid", "pmids"}:
                    for item in vals:
                        pmid = _norm_pmid(item)
                        if pmid:
                            out["pmids"].add(pmid)
                elif key_l in {"nct", "nct_id", "nct_ids", "linked_trial_id", "study_identity"}:
                    for item in vals:
                        nct = _norm_nct(item)
                        if nct:
                            out["ncts"].add(nct)
                visit(val)
        elif isinstance(obj, list):
            for item in obj:
                visit(item)
        elif isinstance(obj, str):
            for m in _PMID_RE.finditer(obj):
                out["pmids"].add(m.group(1))
            for m in _NCT_RE.finditer(obj):
                out["ncts"].add(m.group(1).upper())
            for m in _DOI_RE.finditer(obj):
                doi = _norm_doi(m.group(0))
                if doi:
                    out["dois"].add(doi)

    visit(value)
    return out


def case_key(case: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        _norm_text(case.get("botanical") or case.get("scientific_name")),
        _norm_text(case.get("indication")),
        _norm_text(case.get("jurisdiction")),
        _norm_text(case.get("dosage_form") or case.get("route")),
    )


def validate_reference_cases_document(document: Mapping[str, Any], *, require_complete_labels: bool) -> HoldoutReadiness:
    errors: list[str] = []
    cases = document.get("cases")
    if not isinstance(cases, list):
        return HoldoutReadiness(False, ("'cases' must be a list",))
    if require_complete_labels and not cases:
        errors.append("At least one independently referenced case is required before freeze")

    seen_ids: set[str] = set()
    seen_case_keys: set[tuple[str, str, str, str]] = set()
    for i, case in enumerate(cases):
        prefix = f"cases[{i}]"
        if not isinstance(case, Mapping):
            errors.append(f"{prefix} must be an object")
            continue
        cid = str(case.get("case_id") or "").strip()
        if not cid:
            errors.append(f"{prefix}.case_id is required")
        elif cid in seen_ids:
            errors.append(f"Duplicate case_id: {cid}")
        seen_ids.add(cid)

        for field in ("botanical", "indication", "jurisdiction", "dosage_form"):
            if not str(case.get(field) or "").strip():
                errors.append(f"{prefix}.{field} is required")

        ck = case_key(case)
        if all(ck):
            if ck in seen_case_keys:
                errors.append(f"Duplicate case context within RGV v4: {cid or prefix}")
            seen_case_keys.add(ck)

        refs = case.get("reference_evidence")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{prefix}.reference_evidence must contain independently selected source(s)")
        else:
            ids = extract_publication_identifiers(refs)
            has_stable_id = bool(ids["dois"] or ids["pmids"] or ids["ncts"])
            has_locator = any(str(r.get("source_locator") or r.get("url") or "").strip() for r in refs if isinstance(r, Mapping))
            if not (has_stable_id or has_locator):
                errors.append(f"{prefix}.reference_evidence needs a stable identifier or source locator")

        if require_complete_labels:
            expected = str(case.get("expected_decision") or "").strip().upper()
            if expected not in CANONICAL_DECISIONS:
                errors.append(f"{prefix}.expected_decision must use the existing six-class vocabulary")
            if case.get("reference_established_independently_of_platform_output") is not True:
                errors.append(f"{prefix}.reference_established_independently_of_platform_output must be true")
            if case.get("expert_or_authoritative_reference_review_complete") is not True:
                errors.append(f"{prefix}.expert_or_authoritative_reference_review_complete must be true")
            if not str(case.get("reference_rationale") or "").strip():
                errors.append(f"{prefix}.reference_rationale is required")

    return HoldoutReadiness(not errors, tuple(errors))


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_manifest_hashes(base_dir: str | Path, manifest: Mapping[str, Any]) -> HoldoutReadiness:
    base = Path(base_dir)
    errors: list[str] = []
    hashes = manifest.get("file_hashes") or {}
    if not isinstance(hashes, Mapping) or not hashes:
        return HoldoutReadiness(False, ("Freeze manifest contains no file_hashes",))
    for rel, expected in hashes.items():
        path = base / rel
        if not path.exists():
            errors.append(f"Missing frozen file: {rel}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            errors.append(f"Hash mismatch: {rel}")
    return HoldoutReadiness(not errors, tuple(errors))
