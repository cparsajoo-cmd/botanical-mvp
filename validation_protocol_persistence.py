"""
Validation Protocol Persistence.

WHAT THIS IS
A small, additive persistence layer for validation_case_protocol.py's
ValidationCaseProtocol. Writes ONE row per save to a DEDICATED
Supabase table (VALIDATION_PROTOCOL_TABLE_NAME =
"validation_case_protocols"), never the decision_records/
evidence_records/expert_sign_offs tables. Same architectural
separation as sign_off_persistence.py / decision_record_persistence.py:
data contract, locking, and serialization logic live in
validation_case_protocol.py; I/O lives here.

WHY THIS DOES NOT REQUIRE THE PROTOCOL TO BE LOCKED (UNLIKE
sign_off_persistence.persist_sign_off())
expert_sign_off.persist_sign_off() refuses to persist an incomplete
sign-off, because a sign-off IS a completed act — there is no such
thing as a valid "draft" sign-off, only a finished one or an unfinished
one that isn't a sign-off yet. A validation protocol is different in
kind: Appendix A's four elements (decision context, candidate set,
reference corpus, expert panel) are typically filled in over separate
sessions — decision context today, candidates next week, a corpus and
an expert panel later. Refusing to save anything short of a fully
locked protocol would make it impossible to preserve that work between
sessions. Readiness enforcement stays entirely in
validation_case_protocol.py's lock_protocol() (which still refuses to
LOCK an incomplete protocol) — this module has no opinion on
readiness, exactly like decision_record_persistence.py has no opinion
on whether a CandidateAssessment's score is scientifically defensible.

PROTOCOL IDENTITY AND HISTORY
protocol_id is a pure grouping key (like decision_record_persistence's
analysis_id / telemetry_persistence's session_id) — persist_protocol()
assigns a new one on first save (protocol.protocol_id is None) and the
caller must reuse the SAME protocol_id (persist_protocol() returns it)
on every subsequent save of the same evolving protocol, or each save
starts an unrelated new lineage instead of extending one.

LOCK SEMANTICS
Append-only, same guarantee as decision_record_persistence.py: this
module only ever INSERTS. There is no update or delete path. Two
saves with the same protocol_id produce two rows, never an overwrite
— "current" is defined as the row with the latest saved_at for a
given protocol_id (see load_protocol() below).

FAILURE POLICY
persist_protocol()/load_protocol()/load_protocol_history() never
raise — the same policy as this repo's other persistence modules.
Every failure (including "the table doesn't exist yet") is caught and
reported as a status dict (or None/[] for the read paths), never
propagated.

REQUIRED TABLE (created outside this repository, like every other
Supabase table here — no migration/SQL file exists anywhere in this
codebase for any table, and this module does not introduce one)
`validation_case_protocols`, with columns: protocol_id, case_name,
readiness, locked, saved_at, protocol_json (the full
validation_case_protocol.protocol_to_dict() output, JSON-serialized).
Until that table exists, persist_protocol() degrades to
{"status": "unavailable", ...} and the read paths degrade to None/[].
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from validation_case_protocol import (
    ValidationCaseProtocol,
    gap_report,
    protocol_to_dict,
    protocol_from_dict,
)

VALIDATION_PROTOCOL_TABLE_NAME = "validation_case_protocols"


def _new_protocol_id() -> str:
    """A pure grouping key — see module docstring. Not a business or
    scientific identifier."""
    return str(uuid.uuid4())


def persist_protocol(protocol: ValidationCaseProtocol, supabase_client=None) -> dict:
    """The ONE write function this module exists to provide.

    Always allowed regardless of readiness — see module docstring for
    why this is deliberately unlike expert_sign_off's persist
    functions. Never raises; database/connectivity failures degrade
    to a status dict.

    Returns:
      {
        "status": "persisted" | "unavailable",
        "protocol_id": str,   # newly assigned if this was the first save
        "readiness": str,     # ProtocolReadiness value at save time
        "detail": str,        # human-readable, safe to show in the UI —
                               # never a raw SQL error or credential value.
      }
    """
    resolved_id = protocol.protocol_id or _new_protocol_id()
    readiness = gap_report(protocol)["readiness"].value

    payload = protocol_to_dict(protocol)
    payload["protocol_id"] = resolved_id

    row = {
        "protocol_id": resolved_id,
        "case_name": protocol.case_name,
        "readiness": readiness,
        "locked": protocol.locked,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "protocol_json": json.dumps(payload, default=str),
    }

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        # Append-only: always insert, never update/upsert — see LOCK
        # SEMANTICS above.
        supabase_client.table(VALIDATION_PROTOCOL_TABLE_NAME).insert(row).execute()

        return {
            "status": "persisted",
            "protocol_id": resolved_id,
            "readiness": readiness,
            "detail": f"Validation protocol '{protocol.case_name}' persisted ({readiness}).",
        }
    except Exception:
        # Deliberately generic in the returned detail — never surfaces
        # a raw exception message, which could contain a connection
        # string, credential fragment, or internal stack detail — same
        # discipline as this repo's other persistence functions.
        return {
            "status": "unavailable",
            "protocol_id": resolved_id,
            "readiness": readiness,
            "detail": "Validation-protocol persistence unavailable this session "
                      "(table may not exist yet, or the database is unreachable).",
        }


def load_protocol(protocol_id: str, supabase_client=None):
    """Loads the MOST RECENT saved version of a protocol by
    protocol_id, reconstructed as a ValidationCaseProtocol via
    validation_case_protocol.protocol_from_dict(). Returns None on any
    failure (missing table, unreachable database, no matching rows,
    malformed stored JSON) — never raises."""
    if not protocol_id:
        return None

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        response = (
            supabase_client.table(VALIDATION_PROTOCOL_TABLE_NAME)
            .select("*")
            .eq("protocol_id", protocol_id)
            .execute()
        )
        rows = response.data or []
        if not rows:
            return None

        # Sorted here in Python (most recent first), rather than
        # relying on a chained .order() call — keeps this function
        # portable across supabase-py client versions, same reasoning
        # as sign_off_persistence.load_sign_offs_for_candidate().
        latest = sorted(rows, key=lambda r: r.get("saved_at") or "", reverse=True)[0]
        payload = json.loads(latest["protocol_json"])
        return protocol_from_dict(payload)
    except Exception:
        return None


def load_protocol_history(protocol_id: str, supabase_client=None) -> list:
    """Every saved version for one protocol_id, most recent first —
    the full draft-to-locked history, not just the latest. Returns []
    on any failure — never raises."""
    if not protocol_id:
        return []

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        response = (
            supabase_client.table(VALIDATION_PROTOCOL_TABLE_NAME)
            .select("*")
            .eq("protocol_id", protocol_id)
            .execute()
        )
        rows = response.data or []
        rows_sorted = sorted(rows, key=lambda r: r.get("saved_at") or "", reverse=True)
        return [protocol_from_dict(json.loads(r["protocol_json"])) for r in rows_sorted]
    except Exception:
        return []
