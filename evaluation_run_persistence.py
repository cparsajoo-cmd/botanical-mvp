"""
Validation Architecture v3 — Phase 2: EvaluationRun Persistence.

Append-only, same pattern as every other persistence module in this
repository. Unlike gold_case_persistence.py/validation_protocol_persistence.py,
there is no "draft" concept here — an EvaluationRun is only ever
created once fully computed by evaluation_run.build_evaluation_run(),
so persist_evaluation_run() has nothing partial to allow saving.

REQUIRED TABLE (created outside this repository, like every other
Supabase table here): `evaluation_runs`, with columns: evaluation_run_id,
engine_version, gold_set_version, execution_timestamp,
dataset_snapshot_hash, case_count, evaluation_run_json (full
EvaluationRun content, JSON-serialized).
"""

from __future__ import annotations

import json
from dataclasses import asdict

from evaluation_run import EvaluationRun
from metric_report import MetricReport, MetricType, MetricStatus

EVALUATION_RUN_TABLE_NAME = "evaluation_runs"


def _metric_report_to_dict(report: MetricReport) -> dict:
    d = asdict(report)
    d["metric_type"] = report.metric_type.value
    d["status"] = report.status.value
    return d


def _evaluation_run_to_dict(run: EvaluationRun) -> dict:
    return {
        "evaluation_run_id": run.evaluation_run_id,
        "engine_version": run.engine_version,
        "gold_set_version": run.gold_set_version,
        "execution_timestamp": run.execution_timestamp.isoformat(),
        "dataset_snapshot_hash": run.dataset_snapshot_hash,
        "dataset_split_used": run.dataset_split_used,
        "case_count": run.case_count,
        "inexecutable_case_ids": list(run.inexecutable_case_ids),
        "results": [_metric_report_to_dict(r) for r in run.results],
    }


def persist_evaluation_run(run: EvaluationRun, supabase_client=None) -> dict:
    """The ONE write function this module exists to provide.
    Append-only — the same evaluation_run_id is never overwritten (a
    caller who wants to re-run should call build_evaluation_run()
    again, which produces a fresh evaluation_run_id). Never raises;
    database/connectivity failures degrade to a status dict.

    Returns:
      {"status": "persisted" | "unavailable", "evaluation_run_id": str,
       "detail": str}
    """
    payload = _evaluation_run_to_dict(run)
    row = {
        "evaluation_run_id": run.evaluation_run_id,
        "engine_version": run.engine_version,
        "gold_set_version": run.gold_set_version,
        "execution_timestamp": run.execution_timestamp.isoformat(),
        "dataset_snapshot_hash": run.dataset_snapshot_hash,
        "case_count": run.case_count,
        "evaluation_run_json": json.dumps(payload, default=str),
    }

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        supabase_client.table(EVALUATION_RUN_TABLE_NAME).insert(row).execute()

        return {
            "status": "persisted",
            "evaluation_run_id": run.evaluation_run_id,
            "detail": f"EvaluationRun {run.evaluation_run_id!r} persisted.",
        }
    except Exception:
        return {
            "status": "unavailable",
            "evaluation_run_id": run.evaluation_run_id,
            "detail": "EvaluationRun persistence unavailable this session "
                      "(table may not exist yet, or the database is unreachable).",
        }


def load_evaluation_run_summary(evaluation_run_id: str, supabase_client=None):
    """Loads the raw persisted row (dict) for one evaluation_run_id —
    deliberately returns the stored dict rather than reconstructing a
    full EvaluationRun object (MetricReport's nested dataclasses make
    a lossless reconstruction more involved than this Phase 2 delivery
    needs; the persisted JSON itself remains the durable, complete
    record). Returns None on any failure or missing record."""
    if not evaluation_run_id:
        return None

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        response = (
            supabase_client.table(EVALUATION_RUN_TABLE_NAME)
            .select("*").eq("evaluation_run_id", evaluation_run_id).execute()
        )
        rows = response.data or []
        if not rows:
            return None
        return json.loads(rows[0]["evaluation_run_json"])
    except Exception:
        return None
