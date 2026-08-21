"""Create denominator-aware high-risk sidecar reports from stored validation results.

This utility never rewrites the source result file. Historical blind artifacts
remain untouched; the caller must provide a distinct output path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from validation_risk_metrics import compute_high_risk_metrics_from_confusion_matrix
from high_risk_validation_gate import evaluate_targeted_high_risk_regression_gate


def build_report(payload: dict[str, Any], *, source_result_path: str | None = None) -> dict[str, Any]:
    metrics = payload.get("metrics", payload)
    matrix = metrics.get("confusion_matrix")
    if not isinstance(matrix, dict):
        raise ValueError("Stored validation result does not contain metrics.confusion_matrix")
    n_scored = metrics.get("n_scored")
    high_risk = compute_high_risk_metrics_from_confusion_matrix(matrix, n_scored=n_scored)
    gate = evaluate_targeted_high_risk_regression_gate(high_risk)
    return {
        "report_type": "high_risk_validation_metrics_sidecar",
        "source_result_path": source_result_path,
        "source_version": payload.get("version"),
        "high_risk_metrics": high_risk.to_dict(),
        "targeted_regression_gate": {
            "status": gate.status,
            "passed": gate.passed,
            "blockers": list(gate.blockers),
            "notes": list(gate.notes),
        },
        "interpretation": {
            "threshold_scope": "engineering regression threshold / internal scientific target",
            "clinical_validation_claim": False,
            "rule": "Zero false negatives are required only for high-risk target classes represented by reference-positive cases. A missing target class is not evaluable, never a successful zero-FN result.",
        },
    }


def write_sidecar(source: str | Path, output: str | Path) -> dict[str, Any]:
    source = Path(source).resolve()
    output = Path(output).resolve()
    if source == output:
        raise ValueError("Refusing to overwrite the source validation result; choose a distinct sidecar path")
    payload = json.loads(source.read_text(encoding="utf-8"))
    report = build_report(payload, source_result_path=str(source))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_result")
    parser.add_argument("output_sidecar")
    args = parser.parse_args()
    write_sidecar(args.source_result, args.output_sidecar)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
