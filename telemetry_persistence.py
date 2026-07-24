"""
Sprint 6A.2 — Persistent Connector Telemetry.

WHAT THIS IS
A small, additive persistence layer for Sprint 6A.1's already-computed
Connector_Session_Observability object. It reads that object's
"connectors" list — nothing else — and writes exactly one row per
connector entry to a DEDICATED Supabase table
(TELEMETRY_TABLE_NAME = "connector_telemetry"), never the
evidence_records/sources tables scientific evidence uses.

APPROVED PERSISTENCE UNIT (from the Sprint 6A.2 design review)
One row = one connector's outcome, within one collection session.
Not per plant. Not per connector execution. This module performs NO
new aggregation — every field it writes is read directly from a
connector entry Sprint 6A.1 already built; if a per-plant or
per-execution view is ever wanted, that is a different, later, and
separately-approved capability, not something this module derives by
re-inspecting raw collection data.

WHY THIS NEVER TOUCHES SPRINT 6A.1, CONNECTORS, OR THE COLLECTION WORKFLOW
This module's only input is the dict connector_session_observability.
build_connector_session_observability() already returns. It never
imports any *_connector.py file, never imports multi_source_collector,
and never reads saved_records/errors directly — it only reads the
already-normalized "connectors" list. If Sprint 6A.1's normalization
is ever wrong, that's a Sprint 6A.1 concern to fix in that module; this
one has no opinion on it and cannot diverge from it, because it
performs no independent classification of anything.

SESSION IDENTIFIER
_new_session_id() returns a fresh, random UUID per call — a PURE
grouping key. It is not a business identifier, not a scientific
identifier, and carries no meaning beyond "these rows came from the
same collect_connector telemetry call." Every row built from the same
observability object shares one session_id; two separate calls (two
separate collection sessions) always get two different ones.

recorded_at — TIMESTAMP SEMANTICS, READ THIS BEFORE USING THE FIELD
recorded_at is the time this module wrote the row — NOT when any
connector executed, NOT when Step 2's collection started or finished.
This distinction matters because Sprint 6A.1 itself has NO execution
timestamp anywhere (confirmed in the Sprint 6A.2 audit) — there is
nothing to persist that would mean "when the connector ran." Do not
read recorded_at as a proxy for that; it only ever answers "when was
this telemetry row written," which in practice is very close to (but
not identical to, and not guaranteed to be) when Step 2's collection
finished.

WHY TELEMETRY AND EVIDENCE ARE COMPLETELY SEPARATE CONCERNS
Telemetry describes THIS MODULE'S OWN infrastructure — which connector
ran, whether it succeeded, how many records it produced this session.
It is operational metadata about the collection process itself. It is
NOT scientific evidence, has no Scientific_Name/Evidence_Level/
compound/target fields, and is never read by botanical_rd_candidate_engine.py,
structured_rationale.py, or any scoring/recommendation code. The two
concerns share no table, no schema, and no code path.

FAILURE POLICY
persist_connector_telemetry() NEVER raises. Every failure — including
"the connector_telemetry table doesn't exist yet in this Supabase
project" (expected until a human creates it, exactly like every other
table in this repository, which are all created outside version
control) — is caught and returned as a status dict, never propagated.
Telemetry is best-effort infrastructure; it must never interrupt
scientific evidence collection or block Step 2's page.

REQUIRED TABLE (created outside this repository, like every other
Supabase table here — no migration/SQL file exists anywhere in this
codebase for any table, and this module does not introduce one)
`connector_telemetry`, with columns matching exactly the keys built in
_build_telemetry_rows() below: session_id, connector_name,
connector_type, execution_status, configuration_status, records_saved,
error_count, error_types, error_messages, cache_observability,
recorded_at. Until that table exists, persist_connector_telemetry()
degrades to {"status": "unavailable", ...} — Step 2 continues normally
either way.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

TELEMETRY_TABLE_NAME = "connector_telemetry"

# Fields read from EACH entry in observability["connectors"] — all of
# them already computed by Sprint 6A.1, none recomputed here. Kept as
# an explicit list (not "whatever keys happen to be present") so a
# future change to Sprint 6A.1's shape can't silently start persisting
# an unreviewed new field.
_PERSISTED_CONNECTOR_FIELDS = [
    "connector_name", "connector_type", "execution_status",
    "configuration_status", "records_saved", "error_count",
    "error_types", "error_messages", "cache_observability",
    "limitations",
]


def _new_session_id() -> str:
    """A pure grouping key — see module docstring. Not a business or
    scientific identifier."""
    return str(uuid.uuid4())


def _build_telemetry_rows(observability: dict, session_id: str) -> list:
    """One row per connector entry in observability["connectors"] —
    reads ONLY Sprint 6A.1's already-computed fields. Performs no new
    aggregation, no raw saved_records/errors inspection. `recorded_at`
    is persistence time, not execution time (see module docstring)."""
    if not observability:
        return []

    recorded_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for connector in observability.get("connectors", []) or []:
        row = {field: connector.get(field) for field in _PERSISTED_CONNECTOR_FIELDS}
        row["session_id"] = session_id
        row["recorded_at"] = recorded_at
        rows.append(row)
    return rows


def persist_connector_telemetry(observability: dict, supabase_client=None) -> dict:
    """Sprint 6A.2 — the ONE function this module exists to provide.

    Persists Sprint 6A.1's Connector_Session_Observability, one row per
    connector, to the dedicated `connector_telemetry` table. Never
    raises — every failure mode (missing table, network issue, missing
    credentials) is caught and reported in the returned summary, never
    propagated to the caller. Telemetry is best-effort; Step 2's
    scientific evidence collection must never be interrupted by it.

    Returns:
      {
        "status": "persisted" | "unavailable",
        "session_id": str,
        "rows_attempted": int,
        "rows_persisted": int,
        "detail": str,   # human-readable, safe to show in the UI —
                          # never a raw SQL error or credential value.
      }
    """
    session_id = _new_session_id()
    rows = _build_telemetry_rows(observability, session_id)

    if not rows:
        return {
            "status": "persisted",
            "session_id": session_id,
            "rows_attempted": 0,
            "rows_persisted": 0,
            "detail": "No connector entries to persist.",
        }

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        supabase_client.table(TELEMETRY_TABLE_NAME).insert(rows).execute()

        return {
            "status": "persisted",
            "session_id": session_id,
            "rows_attempted": len(rows),
            "rows_persisted": len(rows),
            "detail": f"{len(rows)} connector telemetry row(s) persisted.",
        }
    except Exception:
        # Deliberately generic in the returned detail — never surfaces
        # a raw exception message, which could contain a connection
        # string, credential fragment, or internal stack detail. The
        # UI layer is instructed to show only "Telemetry persistence
        # unavailable," never this detail string verbatim either.
        return {
            "status": "unavailable",
            "session_id": session_id,
            "rows_attempted": len(rows),
            "rows_persisted": 0,
            "detail": "Telemetry persistence unavailable this session "
                      "(table may not exist yet, or the database is unreachable).",
        }
