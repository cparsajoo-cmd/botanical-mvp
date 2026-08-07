"""Diagnostics for the frozen-snapshot E2E pilot.

Benchmark-only analysis. This module does not modify production logic, GoldCase
truth, source precedence, scoring, safety rules, regulatory rules, or market logic.

Purpose:
1. Separate the mixed-domain `evidence_direction_accuracy` metric from the
   narrower scientific-result use for which `evidence_interpretation.py` was
   designed.
2. Causally localize serious-safety failures after successful critical-source
   retrieval.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = CORPUS_DIR / "gold_corpus_manifest.json"
PILOT_RUN_PATH = CORPUS_DIR / "e2e_snapshots" / "pilot_evaluation_run.json"

STUDY_RESULT_SOURCE_TYPES = {"SYSTEMATIC_REVIEW"}


@dataclass(frozen=True)
class ProportionDiagnostic:
    numerator: int
    denominator: int
    value: Optional[float]


def _ratio(num: int, den: int) -> ProportionDiagnostic:
    return ProportionDiagnostic(num, den, (num / den if den else None))


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _case_by_id(manifest: dict) -> dict[str, dict]:
    return {row["case_id"]: row for row in manifest["cases"]}


def _source_type_by_reference(manifest: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for case in manifest["cases"]:
        for src in case.get("critical_sources", []):
            out[src["reference_id"]] = src.get("source_type") or ""
    return out


def build_diagnostics() -> dict:
    manifest = _load(MANIFEST_PATH)
    run = _load(PILOT_RUN_PATH)
    cases = _case_by_id(manifest)
    source_types = _source_type_by_reference(manifest)

    rows = []
    for result in run["case_results"]:
        case = cases[result["case_id"]]
        for check in result.get("classification_checks", []):
            expected = check.get("expected", {}).get("evidence_direction")
            if expected is None:
                continue
            actual = check.get("actual", {}).get("evidence_direction")
            ref_id = check["reference_id"]
            source_type = source_types.get(ref_id, "")
            rows.append({
                "case_id": result["case_id"],
                "domain": case.get("domain"),
                "assertion_type": case.get("assertion_type"),
                "reference_id": ref_id,
                "source_type": source_type,
                "expected": expected,
                "actual": actual,
                "match": actual == expected,
                "indication_domain": case.get("domain") == "Indication/Evidence",
                "study_result_eligible": (
                    case.get("domain") == "Indication/Evidence"
                    and source_type in STUDY_RESULT_SOURCE_TYPES
                ),
            })

    raw = _ratio(sum(r["match"] for r in rows), len(rows))
    indication_rows = [r for r in rows if r["indication_domain"]]
    indication = _ratio(sum(r["match"] for r in indication_rows), len(indication_rows))
    study_rows = [r for r in rows if r["study_result_eligible"]]
    study = _ratio(sum(r["match"] for r in study_rows), len(study_rows))
    excluded = [r for r in rows if not r["study_result_eligible"]]

    safety_rows = []
    for result in run["case_results"]:
        counts = result.get("source_counts", {})
        if counts.get("safety_critical_total", 0) <= 0:
            continue
        safety_failure = next(
            (f for f in result.get("failures", []) if f.get("code") == "SERIOUS_SAFETY_EVIDENCE_IGNORED"),
            None,
        )
        safety_rows.append({
            "case_id": result["case_id"],
            "safety_critical_total": counts.get("safety_critical_total", 0),
            "safety_critical_retrieved": counts.get("safety_critical_retrieved", 0),
            "safety_gate_failed": bool(counts.get("safety_gate_failed", 0)),
            "false_negative": bool(safety_failure),
            "failure_code": safety_failure.get("code") if safety_failure else None,
            "gate_result": (result.get("gate_results") or {}).get("safety"),
        })

    safety_total = sum(r["safety_critical_total"] for r in safety_rows)
    safety_retrieved = sum(r["safety_critical_retrieved"] for r in safety_rows)
    safety_cases = len(safety_rows)
    safety_fn = sum(r["false_negative"] for r in safety_rows)

    return {
        "diagnostic_version": "gold-corpus-e2e-diagnostics/1",
        "source_pilot_run": "gold_corpus/e2e_snapshots/pilot_evaluation_run.json",
        "direction_diagnostics": {
            "raw_mixed_domain_accuracy": asdict(raw),
            "indication_domain_accuracy": asdict(indication),
            "study_result_eligible_accuracy": asdict(study),
            "study_result_eligible_source_types": sorted(STUDY_RESULT_SOURCE_TYPES),
            "rows": rows,
            "excluded_from_study_result_metric": excluded,
            "interpretation": (
                "The mixed-domain metric is descriptive only. Safety/regulatory assertion presence and "
                "monograph indication statements are not equivalent to study-result direction. The narrower "
                "study-result diagnostic is reported separately without changing production classifiers."
            ),
        },
        "safety_diagnostics": {
            "critical_source_recall": asdict(_ratio(safety_retrieved, safety_total)),
            "serious_safety_false_negative_rate": asdict(_ratio(safety_fn, safety_cases)),
            "cases": safety_rows,
            "causal_interpretation": (
                "If a serious safety critical source is retrieved but the safety gate does not fail, the miss "
                "is downstream of retrieval. This diagnostic records the failure; it does not tune the engine."
            ),
        },
    }


def write_diagnostics(path: Path | None = None) -> Path:
    target = path or (CORPUS_DIR / "e2e_snapshots" / "pilot_diagnostics.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_diagnostics(), indent=2, ensure_ascii=False) + "\n")
    return target
