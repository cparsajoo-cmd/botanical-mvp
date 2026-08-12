"""One-shot frozen validation for Preparation Intelligence / Transferability.

Scope:
  raw study-style text -> LLM extraction of preparation/part/route/dose
  -> the SAME authoritative evaluate_applicability() used by production.

The case file is hash-frozen before the first API run. No Supabase/database
module is imported. Once executed, this benchmark is regression-only and must
not be used as a blind validation again after any code tuning.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

from llm_extractor import extract_evidence_with_llm
from standard_evidence_builder import (
    build_transferability_target_context,
    canonical_administration_route,
    canonical_plant_part,
    evaluate_applicability,
    evidence_transferability_fields,
    parse_dose_value_unit,
    preparation_category_from_text,
)

ROOT = Path(__file__).resolve().parent
CASE_FILE = ROOT / "independent_preparation_transferability_holdout_v1_cases.json"
FROZEN_CASE_FILE_SHA256 = "7a5785fa6133920003d4cf13664c3f2ebb96eba7d3a2475a4c4a60dc4155094a"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ratio(n: int, d: int):
    return None if not d else n / d


def _norm(value) -> str:
    return str(value or "").strip().lower()


def _close(a, b, tol=1e-9):
    if a is None or b is None:
        return a is None and b is None
    try:
        return math.isclose(float(a), float(b), rel_tol=tol, abs_tol=tol)
    except Exception:
        return False


def main() -> int:
    if _sha256(CASE_FILE) != FROZEN_CASE_FILE_SHA256:
        raise SystemExit("FROZEN CASE FILE HASH MISMATCH — refusing to run")
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise SystemExit("OPENAI_API_KEY is required")

    payload = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    cases = payload["cases"]

    parse_errors = 0
    field_total = field_ok = 0
    prep_total = prep_ok = 0
    route_total = route_ok = 0
    part_total = part_ok = 0
    dose_total = dose_ok = 0
    applicability_total = applicability_ok = 0
    mismatch_pos = mismatch_tp = 0
    false_full_match = 0
    rows = []

    for case in cases:
        rec = {"Source_Title": case["title"], "Notes": case["text"]}
        error = None
        extracted = {}
        actual_class = None
        dimensions = {}
        extracted_dose_value = None
        extracted_dose_unit = ""

        checks = {}
        try:
            target = case["target"]
            extracted = extract_evidence_with_llm(
                rec,
                selected_dosage_form=(
                    target.get("dosage_form")
                    or target.get("target_preparation")
                    or ""
                ),
                selected_indication=target.get("target_indication", ""),
            )

            expected = case["expected"]

            # Extraction checks. Plant part / route compare canonical spelling;
            # dose is parsed with the same conservative parser used in production.
            actual_prep_category = _norm(extracted.get("preparation_category"))
            expected_prep_categories = {_norm(x) for x in expected.get("preparation_category", [])}
            prep_pass = actual_prep_category in expected_prep_categories
            checks["preparation_category"] = prep_pass
            prep_total += 1; prep_ok += int(prep_pass)

            actual_route = canonical_administration_route(extracted.get("administration_route"))
            expected_routes = {canonical_administration_route(x) for x in expected.get("route", [])}
            route_pass = actual_route in expected_routes
            checks["route"] = route_pass
            route_total += 1; route_ok += int(route_pass)

            actual_part = canonical_plant_part(extracted.get("plant_part"))
            expected_parts = {canonical_plant_part(x) for x in expected.get("plant_part", [])}
            part_pass = actual_part in expected_parts
            checks["plant_part"] = part_pass
            part_total += 1; part_ok += int(part_pass)

            extracted_dose_value, extracted_dose_unit = parse_dose_value_unit(
                extracted.get("dose") or ""
            )
            expected_value = expected.get("dose_value")
            expected_unit = _norm(expected.get("dose_unit"))
            if expected_value is None:
                dose_pass = extracted_dose_value is None
            else:
                dose_pass = (
                    _close(extracted_dose_value, expected_value)
                    and _norm(extracted_dose_unit) == expected_unit
                )
            checks["dose"] = dose_pass
            dose_total += 1; dose_ok += int(dose_pass)

            field_total += 4
            field_ok += sum(int(v) for v in checks.values())

            # Mimic the persisted production path: the canonical Preparation
            # text is stored; category is later re-derived deterministically.
            # An LLM label of "other"/"unknown" is not treated as a concrete
            # parent category.
            evidence_fields = evidence_transferability_fields(
                species="Heldout species",
                plant_part=extracted.get("plant_part") or "",
                preparation=extracted.get("preparation") or "",
                route=extracted.get("administration_route") or "",
                dose=extracted.get("dose") or "",
                indication_match_type="heldout_exact_indication",
            )
            target_context = build_transferability_target_context(
                indication=target.get("target_indication", ""),
                dosage_form=target.get("dosage_form", ""),
                standardized_project=target,
            )
            result = evaluate_applicability(evidence_fields, target_context)
            actual_class = str(result.get("Applicability_Classification") or "UNKNOWN")
            dimensions = result.get("Dimension_Status", {})
            accepted = set(case.get("applicability_accept") or [])
            class_pass = actual_class in accepted
            applicability_total += 1
            applicability_ok += int(class_pass)

            if accepted == {"MISMATCH"}:
                mismatch_pos += 1
                mismatch_tp += int(actual_class == "MISMATCH")
            if "MATCH" not in accepted and actual_class == "MATCH":
                false_full_match += 1
        except Exception as exc:
            parse_errors += 1
            error = str(exc)
            class_pass = False

        row = {
            "id": case["id"],
            "extracted_preparation": extracted.get("preparation"),
            "extracted_preparation_category": extracted.get("preparation_category"),
            "derived_preparation_category": preparation_category_from_text(extracted.get("preparation")),
            "extracted_plant_part": extracted.get("plant_part"),
            "extracted_route": extracted.get("administration_route"),
            "extracted_dose": extracted.get("dose"),
            "parsed_dose_value": extracted_dose_value,
            "parsed_dose_unit": extracted_dose_unit,
            "field_checks": checks,
            "applicability": actual_class,
            "applicability_accept": case.get("applicability_accept"),
            "applicability_pass": class_pass,
            "dimension_status": dimensions,
            "error": error,
        }
        rows.append(row)
        print("CASE " + json.dumps(row, ensure_ascii=False, separators=(",", ":")))

    summary = {
        "benchmark_id": payload["benchmark_id"],
        "cases": len(cases),
        "field_accuracy": _ratio(field_ok, field_total),
        "preparation_category_accuracy": _ratio(prep_ok, prep_total),
        "route_accuracy": _ratio(route_ok, route_total),
        "plant_part_accuracy": _ratio(part_ok, part_total),
        "dose_accuracy": _ratio(dose_ok, dose_total),
        "applicability_accuracy": _ratio(applicability_ok, applicability_total),
        "confirmed_mismatch_sensitivity": _ratio(mismatch_tp, mismatch_pos),
        "false_full_match": false_full_match,
        "parse_errors": parse_errors,
        "frozen_case_file_sha256": FROZEN_CASE_FILE_SHA256,
        "supabase_reads": 0,
        "supabase_writes": 0,
    }
    checks = {
        "field_accuracy>=0.90": summary["field_accuracy"] is not None and summary["field_accuracy"] >= 0.90,
        "preparation_category_accuracy>=0.90": summary["preparation_category_accuracy"] is not None and summary["preparation_category_accuracy"] >= 0.90,
        "route_accuracy>=0.95": summary["route_accuracy"] is not None and summary["route_accuracy"] >= 0.95,
        "plant_part_accuracy>=0.90": summary["plant_part_accuracy"] is not None and summary["plant_part_accuracy"] >= 0.90,
        "dose_accuracy>=0.85": summary["dose_accuracy"] is not None and summary["dose_accuracy"] >= 0.85,
        "applicability_accuracy>=0.90": summary["applicability_accuracy"] is not None and summary["applicability_accuracy"] >= 0.90,
        "confirmed_mismatch_sensitivity==1.0": summary["confirmed_mismatch_sensitivity"] == 1.0,
        "false_full_match==0": false_full_match == 0,
        "parse_errors==0": parse_errors == 0,
    }
    summary["checks"] = checks
    summary["pass"] = all(checks.values())

    Path("independent_preparation_transferability_holdout_v1_result.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
