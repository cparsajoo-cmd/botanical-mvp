"""
Task 4 — Locked, versioned decision record persistence.

WHAT THIS IS
A small, additive persistence layer for candidate_output_adapter's
already-validated CandidateAssessment records (validate_result_df()'s
output). Writes ONE row per completed analysis to a DEDICATED Supabase
table (DECISION_RECORD_TABLE_NAME = "decision_records"), never the
evidence_records/sources/connector_telemetry tables.

APPROVED PERSISTENCE UNIT
One row = one COMPLETE analysis (all of its validated
CandidateAssessment records, serialized together as one JSON blob),
identified by analysis_id. This module performs no new scoring or
validation — every field it writes is read directly from records
candidate_output_adapter.validate_result_df() already built.

WHY THIS NEVER TOUCHES candidate_output_adapter.py, run(), OR SCORING
This module's only input is the `records: list[CandidateAssessment]`
list validate_result_df() already returns. It never imports
botanical_rd_candidate_engine.py, never re-runs any scoring or
validation, and never recomputes a CandidateAssessment field — it only
reads the already-validated fields. It is called explicitly, from the
UI, after validate_result_df() already succeeded — never automatically
from inside validate_result_df() itself, so validation stays usable
even in an environment with no configured Supabase persistence.

LOCK SEMANTICS — READ THIS BEFORE USING THIS MODULE
"Locked" here is an APPLICATION-LEVEL guarantee, not a database
constraint — this repository creates every table outside version
control, with no migration/SQL file anywhere (see
telemetry_persistence.py's own documented precedent, which this module
follows exactly). persist_decision_record() NEVER issues an update or
upsert — it only ever INSERTS a new row. If the same analysis_id is
persisted twice (e.g. the same analysis re-run), the second call
inserts a SECOND row with a later created_at — an additional version,
never an overwrite of the first. "Current" is defined as the row with
the latest created_at for a given analysis_id. There is no update or
delete path anywhere in this module.

FAILURE POLICY
persist_decision_record() and load_decision_record() NEVER raise — the
same policy as telemetry_persistence.persist_connector_telemetry():
every failure (including "the decision_records table doesn't exist
yet") is caught and returned as a status dict (or None, for the read
path), never propagated. Decision-record persistence is best-effort;
it must never interrupt or block the existing candidate-review
workflow.

REQUIRED TABLE (created outside this repository, like every other
Supabase table here — no migration/SQL file exists anywhere in this
codebase for any table, and this module does not introduce one)
`decision_records`, with columns: analysis_id, created_at,
scoring_config_version, indication, project_id, candidate_count,
records (a JSON-serialized list of the persisted CandidateAssessment
fields — see _PERSISTED_RECORD_FIELDS). Until that table exists,
persist_decision_record() degrades to {"status": "unavailable", ...}
and load_decision_record() returns None — the calling page continues
normally either way.

TASK 12.1 — CANDIDATE-LEVEL EVIDENCE TRACEABILITY (applicability_summary)
`applicability_summary` (Task 10.2's dict — counts by
EvidenceApplicability category, strongest_category, critical_mismatches,
missing_dimensions, and, critically, evidence_record_ids: the exact
evidence_records primary keys that backed this candidate) is now
included in _PERSISTED_RECORD_FIELDS. This requires NO new Supabase
column and NO migration — `records` is already a JSON-serialized blob
column, so a new key inside each serialized record's dict is simply
new content in an already-flexible column, not a schema change.

This is an ADDITIVE AUDIT SNAPSHOT, not a new source of truth.
`evidence_records` remains the one place evidence content actually
lives; a persisted decision record's `applicability_summary` is a
frozen copy of what CandidateAssessment.applicability_summary held at
persistence time, useful for tracing "which evidence_records rows fed
this decision" without re-running the analysis, not for re-deriving or
re-validating scientific content later. Never re-appraised, never
recomputed here — read from the already-validated CandidateAssessment
exactly like every other field in this allowlist.

Deliberately still does NOT persist: full ScientificEvidence objects
(would duplicate evidence_records' own content — out of scope, see the
Task 12 audit §9), or any evidence-to-gate causal attribution (which
gate outcome was driven by which specific evidence item) — this task
provides candidate-level traceability only, not that link.

STABILIZATION NOTE (post-Task-13.2C review) — `applicability_summary`
is persisted here as the COMPLETE dict CandidateAssessment already
carries, not a filtered subset. That dict includes an `evidence_items`
key (a list of {evidence_record_id, classification,
detected_mismatches, missing_dimensions} — added in the Task 10.2
correction purely so _merge_applicability_summaries() could recompute
exact per-record counts when a candidate matches multiple compounds).
`evidence_items` therefore rides along into every persisted decision
record too. This is ACCEPTED, not accidental: it is a strictly more
granular restatement of data already summarized elsewhere in the same
dict (`counts`, `critical_mismatches`, `missing_dimensions`,
`evidence_record_ids`) — persisting it causes no duplication of
authoritative data (evidence_records is still the only source of
truth) and provides useful historical, record-level traceability for
free. Do not strip it out without a deliberate, separately-reviewed
decision — see test_evidence_items_preserved_unchanged_in_persisted_
decision_record() in test_decision_record_persistence.py, which locks
this as current, intended behavior.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

DECISION_RECORD_TABLE_NAME = "decision_records"

# Fields persisted per CandidateAssessment record — kept as an
# explicit allowlist (not "every dataclass field") so a future field
# added to CandidateAssessment doesn't silently start being persisted
# without review, mirroring telemetry_persistence.py's
# _PERSISTED_CONNECTOR_FIELDS precedent exactly.
_PERSISTED_RECORD_FIELDS = [
    "reference_plant", "reference_compound", "alternative_plant",
    "alternative_compound", "indication", "dosage_form", "target_market",
    "rd_opportunity_score", "decision_class", "evidence_confidence",
    "gate_results", "scoring_config_version",
    # Task 12.1 — candidate-level evidence traceability. Additive only;
    # already computed by _summarize_applicability()/
    # _merge_applicability_summaries() (botanical_rd_candidate_engine.py)
    # and already validated onto CandidateAssessment by
    # candidate_output_adapter.py — this allowlist entry is the only
    # change Task 12.1 makes anywhere in the pipeline.
    "applicability_summary",
    # Task 15 — decision-engine logic version (see
    # botanical_rd_candidate_engine.DECISION_ENGINE_VERSION). Deliberately
    # a SEPARATE allowlist entry from scoring_config_version above, not
    # a replacement or merge of it — the two identify different things
    # (which LOGIC version vs. which scoring WEIGHTS) and must remain
    # independently readable. Additive only; already computed and
    # attached to every candidate row by botanical_rd_candidate_engine.run(),
    # already validated onto CandidateAssessment by
    # candidate_output_adapter.py — this allowlist entry is the only
    # change Task 15 makes to this module's persisted-field set. None
    # on any record persisted before this field existed (backward
    # compatible, same degrade-to-None convention as every other field
    # in this allowlist) — never fabricated as "1.0.0" for an old
    # record that never actually carried a version.
    "decision_engine_version",
]


def _new_analysis_id() -> str:
    """A pure grouping key — see module docstring. Not a business or
    scientific identifier."""
    return str(uuid.uuid4())


def _serialize_record(record) -> dict:
    """Reads ONLY the allowlisted fields already present on a
    validated CandidateAssessment — no new computation, no
    recalculation of any field."""
    if is_dataclass(record) and not isinstance(record, type):
        as_dict = asdict(record)
    elif isinstance(record, dict):
        as_dict = record
    else:
        as_dict = {}
    return {field: as_dict.get(field) for field in _PERSISTED_RECORD_FIELDS}


def _resolve_scoring_config_version(records: list):
    for record in records:
        version = (
            record.get("scoring_config_version")
            if isinstance(record, dict)
            else getattr(record, "scoring_config_version", None)
        )
        if version:
            return version
    return None


def persist_decision_record(
    records: list,
    indication: str,
    project_id: str = "unspecified-run",
    analysis_id: str = None,
    supabase_client=None,
) -> dict:
    """The ONE write function this module exists to provide.

    Persists a completed, already-validated set of CandidateAssessment
    records (candidate_output_adapter.validate_result_df()'s output)
    as ONE row in the dedicated `decision_records` table. Never raises.
    Append-only — see module docstring's LOCK SEMANTICS section.

    Returns:
      {
        "status": "persisted" | "unavailable",
        "analysis_id": str,
        "candidate_count": int,
        "detail": str,   # human-readable, safe to show in the UI —
                          # never a raw SQL error or credential value.
      }
    """
    resolved_analysis_id = analysis_id or _new_analysis_id()

    if not records:
        return {
            "status": "persisted",
            "analysis_id": resolved_analysis_id,
            "candidate_count": 0,
            "detail": "No validated records to persist.",
        }

    row = {
        "analysis_id": resolved_analysis_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scoring_config_version": _resolve_scoring_config_version(records),
        "indication": indication,
        "project_id": project_id,
        "candidate_count": len(records),
        "records": json.dumps([_serialize_record(r) for r in records], default=str),
    }

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        # Append-only: always insert, never update/upsert — see LOCK
        # SEMANTICS above. Two calls with the same analysis_id produce
        # two rows, never an overwrite of an existing one.
        supabase_client.table(DECISION_RECORD_TABLE_NAME).insert(row).execute()

        return {
            "status": "persisted",
            "analysis_id": resolved_analysis_id,
            "candidate_count": len(records),
            "detail": f"Decision record persisted ({len(records)} candidate(s)).",
        }
    except Exception:
        # Deliberately generic in the returned detail — never surfaces
        # a raw exception message, which could contain a connection
        # string, credential fragment, or internal stack detail — same
        # discipline as telemetry_persistence.py's own failure path.
        return {
            "status": "unavailable",
            "analysis_id": resolved_analysis_id,
            "candidate_count": len(records),
            "detail": "Decision-record persistence unavailable this session "
                      "(table may not exist yet, or the database is unreachable).",
        }


def load_decision_record(analysis_id: str, supabase_client=None):
    """The ONE read function this module exists to provide — a minimal
    lookup by analysis_id, reusing the same table/select/execute
    pattern already established in database.py's Supabase read
    functions (e.g. load_evidence_records()). Never raises: returns
    None on any failure (missing table, unreachable database, no
    matching analysis_id) — never a fabricated or partial record.

    If more than one row shares this analysis_id (a re-persisted
    analysis — see LOCK SEMANTICS above), returns the one with the
    latest created_at, exactly matching this module's own definition
    of "current".
    """
    if not analysis_id:
        return None

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        response = (
            supabase_client.table(DECISION_RECORD_TABLE_NAME)
            .select("*")
            .eq("analysis_id", analysis_id)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None

        rows_sorted = sorted(rows, key=lambda r: r.get("created_at") or "", reverse=True)
        latest = rows_sorted[0]

        records_field = latest.get("records")
        if isinstance(records_field, str):
            try:
                latest = {**latest, "records": json.loads(records_field)}
            except (TypeError, ValueError):
                pass

        return latest
    except Exception:
        return None
