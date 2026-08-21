"""One-time guarded RGV v4 execution using the existing decision engine path.

The runner is inert until independently authored cases have been frozen. It
reuses the same row-construction/LLM extraction helper as the existing RGV
runner so Stage 5 does not create a parallel scientific decision architecture.
After a successful first run it writes immutable provenance and a write-once
marker; any later invocation is refused and the dataset is exposed thereafter.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine, DECISION_ENGINE_VERSION
from decision_benchmark_v1 import compute_metrics
from end_to_end_validation import _build_plant_df, _norm_taxon
from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from run_final_reference_holdout_v1 import to_row
from scientific_decision_validation import DecisionComparison
from scientific_validity_release_gate import ReferenceValidationProtocol, evaluate_reference_grounded_release
from validation_provenance import DatasetStatus, persist_validation_run
from validation_risk_metrics import compute_high_risk_metrics_from_confusion_matrix
from verify_internal_holdout_v4_freeze import BASE, MANIFEST, verify_execution_readiness

ROOT = Path(__file__).resolve().parent
CASES = BASE / "reference_cases.json"
FIRST_RUN_MARKER = BASE / "FIRST_BLIND_RUN_RECORDED.json"


def _record_first_run(artifact: Path, metrics: dict, gate_payload: dict) -> None:
    marker = {
        "schema_version": "rgv4-first-blind-run-marker/1.0.0",
        "dataset_name": "reference_grounded_validation_v4",
        "status_after_output_inspection": "exposed",
        "permitted_subsequent_use": "regression",
        "engine_version": DECISION_ENGINE_VERSION,
        "immutable_result_artifact": artifact.relative_to(ROOT).as_posix(),
        "accuracy": metrics.get("accuracy"),
        "macro_f1": metrics.get("macro_f1"),
        "release_gate_releasable": gate_payload.get("releasable"),
        "warning": "This marker makes the first blind execution historical. Do not overwrite it or reinterpret any later rerun as independent validation.",
    }
    with FIRST_RUN_MARKER.open("x", encoding="utf-8") as handle:
        json.dump(marker, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> int:
    if FIRST_RUN_MARKER.exists():
        print("BLOCKER: RGV v4 first blind run is already recorded; dataset is exposed/regression-only.")
        return 1
    ok, errors = verify_execution_readiness()
    if not ok:
        for error in errors:
            print(f"BLOCKER: {error}")
        return 1

    document = json.loads(CASES.read_text(encoding="utf-8"))
    refs = document["cases"]
    rows = []
    comps = []
    for case in refs:
        snapshot = json.loads((BASE / case["engine_input_snapshot"]).read_text(encoding="utf-8"))
        evidence = pd.DataFrame([
            to_row(record, case["indication"], case.get("jurisdiction") or "EU")
            for record in snapshot.get("records", [])
        ])
        engine = BotanicalRDCandidateEngine(
            plant_compounds_df=_build_plant_df(snapshot["candidate_pool"], case["indication"]),
            compound_profiles_df=pd.DataFrame(),
            scientific_evidence_df=pd.DataFrame(),
            evidence_records_df=pd.DataFrame(),
            evidence_df=evidence,
            use_live_search=False,
        )
        out = engine.run(
            indication=case["indication"],
            dosage_form=case["dosage_form"],
            market=case["jurisdiction"],
        )
        target = _norm_taxon(case["botanical"])
        target_rows = out[out["Alternative_Plant"].map(_norm_taxon) == target]
        actual = None if target_rows.empty else final_status_from_engine_row(target_rows.iloc[0])
        expected = FinalDecisionStatus(case["expected_decision"])
        match = actual == expected
        rows.append({
            "case_id": case["case_id"],
            "botanical": case["botanical"],
            "expected": expected.value,
            "actual": None if actual is None else actual.value,
            "match": match,
        })
        comps.append(DecisionComparison(case["case_id"], expected, actual, match))

    metrics = compute_metrics(comps)
    metrics_dict = asdict(metrics)
    class_support = {}
    for case in refs:
        class_support[case["expected_decision"]] = class_support.get(case["expected_decision"], 0) + 1
    protocol = ReferenceValidationProtocol(
        benchmark_id="reference-grounded-validation-v4",
        reference_frozen_before_engine_run=True,
        engine_blinded_to_reference_labels=True,
        remediation_cases_excluded=True,
        reference_evidence_excluded_from_engine_input=True,
        provenance_complete=True,
        n_cases=len(refs),
        class_support=class_support,
        reference_source_support={case["case_id"]: len(case.get("reference_evidence") or []) for case in refs},
    )
    gate = evaluate_reference_grounded_release(protocol, metrics)
    gate_payload = {
        "releasable": gate.releasable,
        "claim": gate.claim,
        "blockers": list(gate.blockers),
        "warnings": list(gate.warnings),
    }
    high_risk = compute_high_risk_metrics_from_confusion_matrix(
        metrics_dict["confusion_matrix"], n_scored=metrics_dict.get("n_scored")
    ).to_dict()
    payload = {
        "version": "reference-grounded-validation-v4/1.0.0",
        "engine_version": DECISION_ENGINE_VERSION,
        "rows": rows,
        "metrics": metrics_dict,
        "release_gate": gate_payload,
    }
    artifact, registry, _ = persist_validation_run(
        repo_root=ROOT,
        dataset_name="reference_grounded_validation_v4",
        dataset_version="v4",
        dataset_status=DatasetStatus.INDEPENDENT_FROZEN,
        engine_version=DECISION_ENGINE_VERSION,
        result_payload=payload,
        labels_visible_before_execution=False,
        results_previously_inspected=False,
        used_for_remediation=False,
        run_kind="first_blind_internal_holdout",
        overall_result={
            "n_scored": metrics_dict.get("n_scored"),
            "n_correct": metrics_dict.get("n_correct"),
            "accuracy": metrics_dict.get("accuracy"),
            "macro_f1": metrics_dict.get("macro_f1"),
            "releasable": gate.releasable,
        },
        per_class_metrics=metrics_dict.get("per_class_recall") or {},
        safety_regulatory_metrics=high_risk,
        notes="One-time RGV v4 blind internal holdout. Immediately exposed after result inspection; later reruns are regression only.",
    )
    _record_first_run(artifact, metrics_dict, gate_payload)
    print(json.dumps({
        "engine_version": DECISION_ENGINE_VERSION,
        "immutable_output_artifact": artifact.relative_to(ROOT).as_posix(),
        "validation_registry": registry.relative_to(ROOT).as_posix(),
        "first_blind_run_marker": FIRST_RUN_MARKER.relative_to(ROOT).as_posix(),
        "metrics": metrics_dict,
        "release_gate": gate_payload,
    }, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
