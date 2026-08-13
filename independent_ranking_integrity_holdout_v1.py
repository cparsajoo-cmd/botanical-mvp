"""Frozen engineering-integrity holdout for Phase 7 ranking changes.

This is deliberately NOT an expert calibration benchmark. Passing it proves
basic ranking invariants and real bounded-weight sensitivity wiring only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

import candidate_shortlisting as cs
from phase5_scoring_config import RANKING_CALIBRATION_STATUS
from ranking_score_model import score_from_breakdown
from ranking_calibration import CalibrationDataError, search_candidate_configuration
from scoring_sensitivity_report import build_bounded_weight_robustness

CASES = Path(__file__).with_name("independent_ranking_integrity_holdout_v1_cases.json")


def _robust_df(a, b):
    return pd.DataFrame([
        {"Reference_Plant":"Ref","Reference_Compound":"Cmp","Alternative_Plant":"A","R&D_Opportunity_Score":sum(a.values()),"Score_Breakdown":a,"Eligible_For_Normal_Ranking":True},
        {"Reference_Plant":"Ref","Reference_Compound":"Cmp","Alternative_Plant":"B","R&D_Opportunity_Score":sum(b.values()),"Score_Breakdown":b,"Eligible_For_Normal_Ranking":True},
    ])


def run():
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    results = []
    for case in payload["cases"]:
        typ = case["type"]
        ok = False
        detail = {}
        if typ == "identity":
            expected = round(max(0.0, min(100.0, sum(case["breakdown"].values()))), 1)
            actual = score_from_breakdown(case["breakdown"])
            ok = actual == expected
            detail = {"actual": actual, "expected": expected}
        elif typ == "dominance":
            sa, sb = score_from_breakdown(case["a"]), score_from_breakdown(case["b"])
            obj = build_bounded_weight_robustness(_robust_df(case["a"], case["b"])).iloc[0]
            ok = sa > sb and obj.get("winner_retention_fraction") == 1.0
            detail = {"score_a": sa, "score_b": sb, "stability": obj.get("stability_level")}
        elif typ == "genus":
            frame = pd.DataFrame([
                {"Alternative_Plant":"Salvia alpha","Scientific_Triage_Status":"Shortlist","Overall_Score":case["score_a"],"R&D_Opportunity_Score":case["score_a"],"Go_Investigate_Hold_NoGo":"Go","Decision_Class_AH":"B","Indication_Relevance_Score":30,"Evidence_Quality_Score":25,"Compound_Quality_Score":4,"Traceable_Source_Count":3,"Safety_Regulatory_Score":15},
                {"Alternative_Plant":"Salvia beta","Scientific_Triage_Status":"Shortlist","Overall_Score":case["score_b"],"R&D_Opportunity_Score":case["score_b"],"Go_Investigate_Hold_NoGo":"Go","Decision_Class_AH":"B","Indication_Relevance_Score":30,"Evidence_Quality_Score":24,"Compound_Quality_Score":4,"Traceable_Source_Count":3,"Safety_Regulatory_Score":15},
            ])
            out = cs._prune_near_duplicate_congeners(frame)
            ok = list(out["Scientific_Triage_Status"]) == ["Shortlist", "Shortlist"] and list(out["Overall_Score"]) == [case["score_a"], case["score_b"]]
            detail = {"statuses": list(out["Scientific_Triage_Status"]), "scores": list(out["Overall_Score"])}
        elif typ == "strength":
            p = cs._derive_evidence_confidence(case["indication"], case["positive"])
            c = cs._derive_evidence_confidence(case["indication"], case["comparison"])
            ok = p > c
            detail = {"positive_index": p, "comparison_index": c}
        elif typ in {"sensitive", "robust"}:
            obj = build_bounded_weight_robustness(_robust_df(case["a"], case["b"])).iloc[0]
            if typ == "sensitive":
                ok = obj.get("winner_changed_in_scenarios", 0) > 0
            else:
                ok = obj.get("winner_retention_fraction") == 1.0
            detail = {"stability": obj.get("stability_level"), "retention": obj.get("winner_retention_fraction")}
        elif typ == "calibration_guard":
            try:
                search_candidate_configuration({"pairs": [], "threshold_cases": []}, multipliers=(1.0,), thresholds=(78,))
            except CalibrationDataError:
                ok = RANKING_CALIBRATION_STATUS == "PROVISIONAL_PENDING_EXPERT_CALIBRATION"
            detail = {"calibration_status": RANKING_CALIBRATION_STATUS}
        results.append({"id": case["id"], "type": typ, "pass": bool(ok), **detail})

    passed = sum(int(r["pass"]) for r in results)
    summary = {
        "benchmark_id": payload["benchmark_id"],
        "cases": len(results),
        "passed": passed,
        "accuracy": passed / len(results),
        "expert_calibration_claim": False,
        "calibration_status": RANKING_CALIBRATION_STATUS,
        "frozen_case_file_sha256": hashlib.sha256(CASES.read_bytes()).hexdigest(),
        "pass": passed == len(results),
    }
    for row in results:
        print("CASE", json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    print("SUMMARY", json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
