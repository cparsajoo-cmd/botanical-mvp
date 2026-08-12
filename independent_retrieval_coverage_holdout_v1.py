"""One-shot frozen holdout for Retrieval Coverage / Source Coverage policy.

This validation intentionally performs no network or database I/O.  It tests
whether unseen combinations of source completion/failure, market authority
coverage, and unfinished collection states are propagated into the same
production retrieval-coverage gate used by downstream candidate decisions.

The case file is hash-frozen before the first run. Once executed, it becomes a
regression set and must not be reused as a blind validation after code tuning.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from retrieval_coverage import assess_retrieval_coverage
from connector_session_observability import build_connector_session_observability
from botanical_rd_candidate_engine import apply_retrieval_coverage_guard

ROOT = Path(__file__).resolve().parent
CASE_FILE = ROOT / "independent_retrieval_coverage_holdout_v1_cases.json"
RESULT_FILE = ROOT / "independent_retrieval_coverage_holdout_v1_result.json"
FROZEN_CASE_FILE_SHA256 = "8888c8b79d6c2184f065805205096135c642c63a43c4c1ffc6363cca378f8b77"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ratio(n: int, d: int):
    return None if not d else n / d


def _row(final_status: str) -> dict:
    return {
        "Alternative_Plant": "Heldout species",
        "Final_Decision_Status": final_status,
        "Decision_Class": "heldout baseline",
        "Eligible_For_Normal_Ranking": final_status in {"GO", "GO WITH CAUTION"},
        "Ranking_Partition": "normal",
        "Score_Validity": "valid",
        "Requires_Expert_Review": final_status == "EXPERT REVIEW REQUIRED",
        "Go_Investigate_Hold_NoGo": "Go" if final_status in {"GO", "GO WITH CAUTION"} else "Hold",
        "Confidence_Note": "",
        "R&D_Opportunity_Score": 80.0,
    }


def main() -> int:
    actual_hash = _sha256(CASE_FILE)
    if actual_hash != FROZEN_CASE_FILE_SHA256:
        raise SystemExit("FROZEN CASE FILE HASH MISMATCH — refusing to run")

    payload = json.loads(CASE_FILE.read_text(encoding="utf-8"))
    cases = payload["cases"]

    coverage_total = coverage_ok = 0
    decision_total = decision_ok = 0
    hard_no_go_total = hard_no_go_ok = 0
    pubmed_obs_total = pubmed_obs_ok = 0
    false_go_under_blocking_coverage = 0
    parse_errors = 0
    rows = []

    for case in cases:
        saved_records = [
            {"source": source, "title": f"heldout-{i}"}
            for i, source in enumerate(case.get("saved_sources") or [])
        ]
        collection_result = {
            "sources_checked": case.get("sources_checked") or [],
            "saved_records": saved_records,
            "errors": case.get("errors") or [],
        }

        error = None
        actual_status = None
        actual_final = None
        pubmed_records = None
        try:
            cov = assess_retrieval_coverage(
                collection_result if case.get("collection_attempted", True) else None,
                market=case.get("market", ""),
                collection_finished=bool(case.get("collection_finished", True)),
                collection_attempted=bool(case.get("collection_attempted", True)),
            )
            actual_status = cov["status"]
            coverage_total += 1
            coverage_ok += int(actual_status == case["expected_status"])

            frame = pd.DataFrame([_row(case["input_final_decision"])])
            guarded = apply_retrieval_coverage_guard(
                frame, {"Heldout species": cov}
            )
            actual_final = str(guarded.iloc[0]["Final_Decision_Status"])
            decision_total += 1
            decision_ok += int(actual_final == case["expected_final_decision"])

            if case["input_final_decision"] in {"NO GO SAFETY", "NO GO REGULATORY"}:
                hard_no_go_total += 1
                hard_no_go_ok += int(actual_final == case["input_final_decision"])

            if actual_status in {"INCOMPLETE", "NOT_ASSESSABLE"} and actual_final in {"GO", "GO WITH CAUTION"}:
                false_go_under_blocking_coverage += 1

            if "PubMed" in (case.get("saved_sources") or []):
                obs = build_connector_session_observability(collection_result)
                pubmed = next(c for c in obs["connectors"] if c["connector_name"] == "PubMed")
                pubmed_records = int(pubmed["records_saved"])
                pubmed_obs_total += 1
                pubmed_obs_ok += int(pubmed_records == (case.get("saved_sources") or []).count("PubMed"))
        except Exception as exc:
            parse_errors += 1
            error = f"{type(exc).__name__}: {exc}"

        row = {
            "id": case["id"],
            "market": case.get("market"),
            "expected_coverage": case.get("expected_status"),
            "actual_coverage": actual_status,
            "input_final_decision": case.get("input_final_decision"),
            "expected_final_decision": case.get("expected_final_decision"),
            "actual_final_decision": actual_final,
            "pubmed_records_observed": pubmed_records,
            "error": error,
        }
        rows.append(row)
        print("CASE " + json.dumps(row, ensure_ascii=False, separators=(",", ":")))

    summary = {
        "benchmark_id": payload["benchmark_id"],
        "cases": len(cases),
        "coverage_status_accuracy": _ratio(coverage_ok, coverage_total),
        "decision_guard_accuracy": _ratio(decision_ok, decision_total),
        "hard_no_go_preservation": _ratio(hard_no_go_ok, hard_no_go_total),
        "pubmed_observability_accuracy": _ratio(pubmed_obs_ok, pubmed_obs_total),
        "false_go_under_incomplete_or_unassessable": false_go_under_blocking_coverage,
        "parse_errors": parse_errors,
        "frozen_case_file_sha256": FROZEN_CASE_FILE_SHA256,
        "supabase_reads": 0,
        "supabase_writes": 0,
    }
    checks = {
        "coverage_status_accuracy==1.0": summary["coverage_status_accuracy"] == 1.0,
        "decision_guard_accuracy==1.0": summary["decision_guard_accuracy"] == 1.0,
        "hard_no_go_preservation==1.0": summary["hard_no_go_preservation"] == 1.0,
        "pubmed_observability_accuracy==1.0": summary["pubmed_observability_accuracy"] == 1.0,
        "false_go_under_incomplete_or_unassessable==0": false_go_under_blocking_coverage == 0,
        "parse_errors==0": parse_errors == 0,
    }
    summary["checks"] = checks
    summary["pass"] = all(checks.values())
    RESULT_FILE.write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
