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

from database import _missing_postgrest_column
from deduplication_engine import compute_evidence_identity
from score_breakdown_schema import parse_score_breakdown

DECISION_RECORD_TABLE_NAME = "decision_records"

# Phase 4 (IMPLEMENTATION_PLAN.md) — reproducibility metadata columns added
# by migrations/0004_add_decision_metadata.sql. Same optional-column
# fallback pattern as database.py's _OPTIONAL_EVIDENCE_COLUMNS (Task 10.2 /
# Phase 2 precedent): an unmigrated decision_records table must not make
# this insert fail outright, only degrade to omitting these columns.
_OPTIONAL_METADATA_COLUMNS = {
    "scoring_model_version", "evidence_snapshot_id", "evidence_snapshot_status",
    "normalization_version", "validation_version", "discovery_mode",
    "dosage_form", "market", "candidate_set_fingerprint",
}

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
    # GRADE-informed clinical-evidence certainty (see
    # data_contracts.CandidateAssessment.grade_certainty and
    # grade_certainty_classifier.py for the full documented method).
    # Additive only; already validated onto CandidateAssessment by
    # candidate_output_adapter.py — this allowlist entry is the only
    # change made anywhere in the persistence pipeline to close the
    # previously-broken result_df -> CandidateAssessment ->
    # decision_records path for this field. None on any record
    # persisted before this field existed.
    "grade_certainty", "grade_certainty_rationale",
    # PHASE 2 (review round, issue 2) — the raw Score_Breakdown value
    # CandidateAssessment already carries (data_contracts.py's
    # `score_breakdown` field) was never persisted before this change.
    # Additive only: reads an existing field verbatim, computes/changes
    # no score, weight, or ranking. This is what makes
    # _build_score_context() below possible without inventing any new
    # upstream computation.
    "score_breakdown",
    # PHASE 2 (review round 3, issue 3) — DERIVED, not a raw
    # CandidateAssessment field. Listed here anyway so this allowlist
    # stays the single, complete statement of "every key a persisted
    # record can contain" — see _serialize_record(), which computes
    # this one key specially via _build_score_context(). Deliberately
    # named "score_context", not "score_contributions": see
    # _build_score_context()'s docstring for why a per-component
    # structure was REMOVED in this review round (it implied a causal
    # link — "this evidence drove this component's score" — the engine
    # does not actually provide).
    "score_context",
]


def _new_analysis_id() -> str:
    """A pure grouping key — see module docstring. Not a business or
    scientific identifier."""
    return str(uuid.uuid4())


def _serialize_record(record, evidence_df=None) -> dict:
    """Reads ONLY the allowlisted fields already present on a
    validated CandidateAssessment — no new computation, no
    recalculation of any field — EXCEPT the additive `score_context`
    key (also listed in _PERSISTED_RECORD_FIELDS, so this remains the
    single complete statement of every key a persisted record can
    contain), which is DERIVED (never recomputed scoring) from two
    already-persisted fields on the very same allowlist
    (`score_breakdown`, `applicability_summary`); see
    _build_score_context()'s docstring for exactly what it does and
    does not do, and PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md section 3
    for why this is deliberately candidate-level, not per-component.
    """
    if is_dataclass(record) and not isinstance(record, type):
        as_dict = asdict(record)
    elif isinstance(record, dict):
        as_dict = record
    else:
        as_dict = {}
    serialized = {
        field: as_dict.get(field)
        for field in _PERSISTED_RECORD_FIELDS
        if field != "score_context"
    }
    serialized["score_context"] = _build_score_context(as_dict, evidence_df)
    return serialized


def _build_score_context(as_dict: dict, evidence_df) -> dict:
    """PHASE 2 (review round 3, issue 3) — REPLACES this module's
    original `_build_score_contributions()`.

    WHY THE ORIGINAL SHAPE WAS WRONG
    The original delivery attached the SAME evidence_record_ids to
    EVERY score component, wrapped in a `{"component": ..., "value":
    ..., "evidence_record_ids": [...], ...}` list. Even with the
    granularity caveat documented in prose, that SHAPE itself implies a
    causal link a reader (or any downstream code) could reasonably
    take at face value: "this evidence backed THIS component." No such
    per-component attribution exists anywhere in
    botanical_rd_candidate_engine.py — see
    PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md section 3e. A data shape that
    LOOKS like fine-grained traceability but isn't is worse than no
    shape at all; the review round 3 audit correctly identified this as
    fabricated structure, not honest metadata.

    WHAT THIS FUNCTION ACTUALLY DOES, STATED PLAINLY
    Returns ONE candidate-level structure — never one entry per
    component:

        {
            "score_breakdown": {<component>: <value>, ...},
            "candidate_evidence_record_ids": [...],
            "candidate_evidence_identities": [...],
            "attribution_level": "candidate",
            "component_attribution_available": False,
        }

    `score_breakdown` here is the SAME already-computed value, merely
    parsed into a dict via the existing
    score_breakdown_schema.parse_score_breakdown() for readability —
    not recomputed. `candidate_evidence_record_ids` is Task 12.1's
    existing `applicability_summary["evidence_record_ids"]`, READ
    VERBATIM (order preserved, nothing added, nothing removed).
    `candidate_evidence_identities` is the SAME list, each id mapped
    through deduplication_engine.compute_evidence_identity() (when
    `evidence_df` is available) and then reduced to distinct values —
    this is legitimate, honest deduplication: catching the case where
    the SAME article reached this candidate through two different
    evidence_records rows (e.g. PubMed and Europe PMC each
    independently saved) collapses to one identity in this list. It is
    NOT claimed to prevent duplicate SCORE — the score itself was
    already computed upstream by the frozen scoring engine before this
    module ever sees the record; this list is read-time/persist-time
    metadata about the evidence set, not a scoring-time guard.
    `attribution_level` and `component_attribution_available` exist so
    no downstream consumer of this JSON blob can mistake "candidate-
    level" for "per-component" — the second field is hard-coded False,
    never conditionally True, because no scoring-engine change was made
    in this phase.

    WHAT THIS DOES NOT DO, STATED PLAINLY (see the implementation
    report for the full discussion)
    - Does NOT prevent a duplicate evidence row from contributing twice
      to the ORIGINAL score_breakdown value itself — that value was
      already computed by botanical_rd_candidate_engine.py before this
      record ever reaches this module. Duplicate ARTICLE/EVIDENCE
      prevention BEFORE scoring happens at the database/read-time layer
      (database._find_existing_evidence_by_identity()/
      _find_existing_evidence_by_fuzzy_title(),
      deduplication_engine.deduplicate_evidence()) — see the
      implementation report's explicit "before scoring" vs. "inside
      scoring" distinction.
    - Does NOT attribute any evidence to any individual component.
    - Does NOT call score_breakdown_schema.dedupe_score_contributions()
      — that utility remains available, tested, and unused in
      production; using it here would require exactly the fabricated
      per-component pairing this function was rewritten to remove.

    WHEN THIS RETURNS EMPTY-ISH VALUES
    - No `score_breakdown` on the record -> `score_breakdown: {}`,
      empty id/identity lists.
    - No `applicability_summary`/`evidence_record_ids` -> empty id/
      identity lists (never fabricated ids).
    - `evidence_df` not supplied -> `candidate_evidence_identities`
      falls back to the raw evidence_record_id strings themselves
      (id-level distinctness only, not article-level — documented as a
      limitation in the implementation report).
    """
    score_breakdown = as_dict.get("score_breakdown")
    components = parse_score_breakdown(score_breakdown)

    applicability_summary = as_dict.get("applicability_summary") or {}
    evidence_record_ids = list(applicability_summary.get("evidence_record_ids") or [])

    id_to_identity = {}
    if evidence_df is not None and evidence_record_ids:
        try:
            id_column = evidence_df["Evidence_Record_ID"].astype(str)
            for record_id in evidence_record_ids:
                matches = evidence_df[id_column == str(record_id)]
                if not matches.empty:
                    id_to_identity[record_id] = compute_evidence_identity(
                        matches.iloc[0].to_dict()
                    )
        except Exception:
            # Defensive only — an unexpected evidence_df shape must
            # degrade to id-level identity below, never raise and never
            # block persistence of the rest of the decision record.
            id_to_identity = {}

    seen_identities = set()
    deduped_ids = []
    deduped_identities = []
    for record_id in evidence_record_ids:
        identity = id_to_identity.get(record_id, str(record_id))
        if identity in seen_identities:
            continue
        seen_identities.add(identity)
        deduped_ids.append(record_id)
        deduped_identities.append(identity)

    return {
        "score_breakdown": components,
        "candidate_evidence_record_ids": deduped_ids,
        "candidate_evidence_identities": deduped_identities,
        "attribution_level": "candidate",
        "component_attribution_available": False,
    }


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


def _insert_decision_record_with_optional_schema_fallback(supabase_client, row: dict):
    """Same pattern as database.py's _insert_evidence_with_optional_schema_fallback
    (Task 10.2 / Phase 2 precedent), reused here for decision_records' Phase 4
    metadata columns instead of duplicating the retry logic. Core fields
    (analysis_id, created_at, scoring_config_version, indication, project_id,
    candidate_count, records) are never removed — only the Phase 4 optional
    metadata columns are dropped, one at a time, if the table doesn't have
    them yet.
    """
    current = dict(row)
    for _ in range(len(_OPTIONAL_METADATA_COLUMNS) + 1):
        try:
            return supabase_client.table(DECISION_RECORD_TABLE_NAME).insert(current).execute()
        except Exception as exc:
            missing = _missing_postgrest_column(exc)
            if missing not in _OPTIONAL_METADATA_COLUMNS or missing not in current:
                raise
            current.pop(missing, None)
    raise RuntimeError("Unable to insert decision record after schema fallback")


def persist_decision_record(
    records: list,
    indication: str,
    project_id: str = "unspecified-run",
    analysis_id: str = None,
    supabase_client=None,
    decision_metadata: dict = None,
    evidence_df=None,
) -> dict:
    """The ONE write function this module exists to provide.

    evidence_df (PHASE 2 review round, issue 2; optional, default None,
    every pre-existing caller unaffected): the same evidence DataFrame
    the calling page already has in hand (e.g. step_rd_candidates.py's
    _get_evidence_df()), passed through so _build_score_contributions()
    can compute article-level evidence_identity for each candidate's
    evidence_record_ids instead of only id-level identity. See
    _build_score_contributions()'s docstring for exactly what changes
    when this is/isn't supplied.

    Persists a completed, already-validated set of CandidateAssessment
    records (candidate_output_adapter.validate_result_df()'s output)
    as ONE row in the dedicated `decision_records` table. Never raises.
    Append-only — see module docstring's LOCK SEMANTICS section.

    decision_metadata (Phase 4, optional): the EXACT dict
    decision_metadata.build_decision_metadata() returned for this same
    decision run — passed straight through and only ever read here, never
    recomputed. This is what makes "the final report and the persisted
    decision record use the same metadata object" true: both this
    function and pharma_report_generator.generate_pharma_report() are
    given the identical dict by their shared caller (step_rd_candidates.py),
    not two independently-built ones. When None (every pre-Phase-4 caller,
    unchanged), the Phase 4 metadata columns are simply omitted from the
    row — no fabricated version strings, no guessed snapshot id.

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

    # Post-Phase-4-review correction: when decision_metadata is supplied,
    # its decision_timestamp becomes this row's created_at instead of an
    # independently-generated timestamp — otherwise the report (which
    # renders decision_metadata["decision_timestamp"] verbatim) and the
    # persisted record could describe two different instants for what is
    # supposed to be the same decision. No new column is added: created_at
    # already means exactly this (see migrations/0004's own note on why
    # decision_timestamp was deliberately not given a separate column).
    # Backward compatible: a caller without decision_metadata (every
    # pre-Phase-4 call site) still gets an automatically generated
    # created_at, unchanged from before.
    created_at = (
        decision_metadata.get("decision_timestamp") if decision_metadata else None
    ) or datetime.now(timezone.utc).isoformat()

    row = {
        "analysis_id": resolved_analysis_id,
        "created_at": created_at,
        "scoring_config_version": _resolve_scoring_config_version(records),
        "indication": indication,
        "project_id": project_id,
        "candidate_count": len(records),
        "records": json.dumps([_serialize_record(r, evidence_df) for r in records], default=str),
    }
    if decision_metadata:
        for field in _OPTIONAL_METADATA_COLUMNS:
            if field in decision_metadata:
                row[field] = decision_metadata[field]

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        # Append-only: always insert, never update/upsert — see LOCK
        # SEMANTICS above. Two calls with the same analysis_id produce
        # two rows, never an overwrite of an existing one.
        _insert_decision_record_with_optional_schema_fallback(supabase_client, row)

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
