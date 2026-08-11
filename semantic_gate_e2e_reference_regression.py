"""End-to-end reference regression with record-level semantic gates enabled.

This is deliberately a REGRESSION/INTEGRATION check, not a new blind-validity
claim.  It reuses already-exposed frozen case sets and injects only the new
record-level LLM safety/regulatory assertion payload before running the normal
BotanicalRDCandidateEngine and deterministic final-decision policy.

No Supabase access is performed.  No database writes are performed.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine, DECISION_ENGINE_VERSION
from decision_benchmark_v1 import compute_metrics
from end_to_end_validation import _build_plant_df, _norm_taxon
from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from llm_extractor import extract_gate_assertions_with_llm
from scientific_decision_validation import DecisionComparison

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "gold_corpus" / "scientific_validity" / "final_holdout_v1"

HARD_SAFETY = FinalDecisionStatus.NO_GO_SAFETY
HARD_REG = FinalDecisionStatus.NO_GO_REGULATORY
HARD = {HARD_SAFETY, HARD_REG}


def _to_row(record: Dict[str, Any], indication: str, semantic_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Transport the frozen snapshot record plus additive semantic payload.

    The original record is never mutated and the LLM payload is kept in its
    dedicated compatibility column consumed by botanical_rd_candidate_engine.
    """
    return {
        "Evidence_Record_ID": record["reference_id"],
        "Scientific_Name": record["scientific_name"],
        "Target_Indication": record.get("target_indication") or indication,
        "Dosage_Form": "oral",
        "Target_Market": "EU",
        "Notes": record["notes"],
        "Source_Type": record.get("source_type", ""),
        "Source_Title": record.get("source_title", ""),
        "Source_URL": record.get("source_url", ""),
        "PMID": record.get("pmid", ""),
        "Study_Type": record.get("study_design", ""),
        "Evidence_Level": record.get("evidence_quality", ""),
        "Source_Authority": record.get("source_authority", ""),
        "Source_Year": record.get("publication_year", ""),
        "Primary_Outcome": record.get("primary_outcome", ""),
        "Comparator": record.get("comparator", ""),
        "Risk_of_Bias": record.get("risk_of_bias", ""),
        # Additive only.  The source Notes / metadata above remain untouched.
        "LLM_Gate_Assertions": json.dumps(semantic_payload, ensure_ascii=False),
    }


def _context(case: Dict[str, Any], record: Dict[str, Any]) -> str:
    return (
        f"Botanical: {case['botanical']}\n"
        f"Indication: {case['indication']}\n"
        f"Dosage form: oral\n"
        f"Target market: EU\n"
        f"Record scientific name: {record.get('scientific_name', '')}"
    )


def _extract_for_case(case: Dict[str, Any], snapshot: Dict[str, Any]) -> tuple[pd.DataFrame, List[Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    audit: List[Dict[str, Any]] = []

    for record in snapshot["records"]:
        llm_record = {
            "Source_Title": record.get("source_title", ""),
            "Notes": record.get("notes", ""),
            "Source_URL": record.get("source_url", ""),
            "PMID": record.get("pmid", ""),
        }
        payload = extract_gate_assertions_with_llm(
            llm_record,
            candidate_context=_context(case, record),
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"Semantic extractor returned non-object for {case['case_id']} / {record['reference_id']}")

        safety = payload.get("safety_assertions") or []
        regulatory = payload.get("regulatory_assertions") or []
        audit.append(
            {
                "reference_id": record["reference_id"],
                "safety_assertions": len(safety),
                "regulatory_assertions": len(regulatory),
                "serious_assertions": sum(
                    1 for x in safety
                    if isinstance(x, dict) and str(x.get("seriousness", "")).lower() == "serious"
                ),
                "blocking_assertions": sum(
                    1 for x in regulatory
                    if isinstance(x, dict)
                    and str(x.get("market_access_effect", "")).lower() == "blocks_market_access"
                ),
            }
        )
        rows.append(_to_row(record, case["indication"], payload))

    return pd.DataFrame(rows), audit


def _status_name(status: FinalDecisionStatus | None) -> str | None:
    return None if status is None else status.value


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", choices=["v2", "v3"], default="v3")
    args = ap.parse_args()
    tag = args.tag

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required")

    labels_path = BASE / f"frozen_reference_labels_{tag}.json"
    if not labels_path.exists():
        raise SystemExit(f"Missing frozen labels: {labels_path}")

    refs = json.loads(labels_path.read_text(encoding="utf-8"))["cases"]

    rows: List[Dict[str, Any]] = []
    comparisons: List[DecisionComparison] = []
    total_records = 0
    total_serious_assertions = 0
    total_blocking_assertions = 0

    safety_expected = safety_tp = 0
    reg_expected = reg_tp = 0
    catastrophic_fn = 0
    false_hard_stop = 0
    expert_expected = expert_correct = 0

    for case in refs:
        snap_path = BASE / "snapshots" / f"{case['case_id']}.json"
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))

        evidence_df, audit = _extract_for_case(case, snapshot)
        total_records += len(audit)
        total_serious_assertions += sum(x["serious_assertions"] for x in audit)
        total_blocking_assertions += sum(x["blocking_assertions"] for x in audit)

        engine = BotanicalRDCandidateEngine(
            plant_compounds_df=_build_plant_df(snapshot["candidate_pool"], case["indication"]),
            compound_profiles_df=pd.DataFrame(),
            scientific_evidence_df=pd.DataFrame(),
            evidence_df=evidence_df,
            use_live_search=False,
        )
        out = engine.run(indication=case["indication"], dosage_form="oral", market="EU")
        target = _norm_taxon(case["botanical"])
        target_rows = out[out["Alternative_Plant"].map(_norm_taxon) == target]
        actual = None if target_rows.empty else final_status_from_engine_row(target_rows.iloc[0])
        expected = FinalDecisionStatus(case["expected"])
        match = actual == expected

        if expected == HARD_SAFETY:
            safety_expected += 1
            if actual == HARD_SAFETY:
                safety_tp += 1
            else:
                catastrophic_fn += 1
        elif expected == HARD_REG:
            reg_expected += 1
            if actual == HARD_REG:
                reg_tp += 1
            else:
                catastrophic_fn += 1

        if expected not in HARD and actual in HARD:
            false_hard_stop += 1

        if expected == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED:
            expert_expected += 1
            if actual == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED:
                expert_correct += 1

        row = {
            "case_id": case["case_id"],
            "botanical": case["botanical"],
            "expected": expected.value,
            "actual": _status_name(actual),
            "match": match,
            "records": len(audit),
            "semantic_serious": sum(x["serious_assertions"] for x in audit),
            "semantic_regulatory_blocks": sum(x["blocking_assertions"] for x in audit),
        }
        rows.append(row)
        comparisons.append(DecisionComparison(case["case_id"], expected, actual, match))
        print("E2E " + json.dumps(row, ensure_ascii=False, sort_keys=True))

    metrics = compute_metrics(comparisons)
    safety_sensitivity = None if safety_expected == 0 else safety_tp / safety_expected
    regulatory_sensitivity = None if reg_expected == 0 else reg_tp / reg_expected
    expert_review_recall = None if expert_expected == 0 else expert_correct / expert_expected

    summary = {
        "tag": tag,
        "claim": "EXPOSED_REFERENCE_REGRESSION_NOT_BLIND_VALIDATION",
        "engine_version": DECISION_ENGINE_VERSION,
        "cases": len(refs),
        "evidence_records_llm_processed": total_records,
        "semantic_serious_assertions": total_serious_assertions,
        "semantic_regulatory_blocks": total_blocking_assertions,
        "accuracy": metrics.accuracy,
        "macro_f1": metrics.macro_f1,
        "catastrophic_fn": catastrophic_fn,
        "false_hard_stop": false_hard_stop,
        "safety_sensitivity": safety_sensitivity,
        "regulatory_sensitivity": regulatory_sensitivity,
        "expert_review_recall": expert_review_recall,
        "supabase_reads": 0,
        "supabase_writes": 0,
        "openai_calls": total_records,
    }

    payload = {
        "version": "semantic-gate-e2e-reference-regression/1.0.0",
        "summary": summary,
        "metrics": asdict(metrics),
        "rows": rows,
    }
    output_path = ROOT / f"semantic_gate_e2e_reference_regression_{tag}.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print("SUMMARY " + " ".join(f"{k}={v}" for k, v in summary.items()))
    print(f"RESULT_FILE {output_path.name}")

    # Integration gate: catastrophic misses or false hard-stops are safety-critical.
    # Overall accuracy is reported, not used here to hide/override safety failures.
    if catastrophic_fn != 0 or false_hard_stop != 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
