"""CLI for expert ranking calibration. Never edits production configuration.

Usage:
  python ranking_calibration_cli.py readiness expert_ranking_benchmark.json
  python ranking_calibration_cli.py search expert_ranking_benchmark.json
  python ranking_calibration_cli.py holdout expert_ranking_benchmark.json
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

from ranking_calibration import (
    CalibrationDataError,
    calibration_readiness,
    evaluate_expert_benchmark,
    search_candidate_configuration,
)


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in {"readiness", "search", "holdout"}:
        print("usage: ranking_calibration_cli.py {readiness|search|holdout} BENCHMARK.json")
        return 2
    command, path = argv
    benchmark = _load(path)
    try:
        if command == "readiness":
            result = calibration_readiness(benchmark)
        elif command == "search":
            result = asdict(search_candidate_configuration(benchmark))
        else:
            proposal = benchmark.get("candidate_configuration")
            if not isinstance(proposal, dict):
                raise CalibrationDataError(
                    "benchmark must contain candidate_configuration with weights and strong_threshold before holdout evaluation"
                )
            result = evaluate_expert_benchmark(
                benchmark,
                weights=proposal["weights"],
                strong_threshold=float(proposal["strong_threshold"]),
                split="holdout",
            )
    except CalibrationDataError as exc:
        print(json.dumps({"status": "not_ready", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
