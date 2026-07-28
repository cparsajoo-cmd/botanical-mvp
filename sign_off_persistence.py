"""
Task 8 — Structured Expert Sign-Off Persistence.

WHAT THIS IS
A small, additive persistence layer for expert_sign_off.py's
ExpertSignOff records. Writes ONE row per sign-off to a DEDICATED
Supabase table (SIGN_OFF_TABLE_NAME = "expert_sign_offs"), never the
decision_records/evidence_records/sources/connector_telemetry tables.
Same architectural separation as telemetry_persistence.py /
decision_record_persistence.py: data contract and validation logic
live in expert_sign_off.py; I/O lives here.

WHY persist_sign_off() CAN RAISE (UNLIKE THIS REPO'S OTHER PERSISTENCE
FUNCTIONS)
telemetry_persistence.persist_connector_telemetry() and
decision_record_persistence.persist_decision_record() never raise,
because telemetry and decision-record snapshots are best-effort
infrastructure that must never block the underlying workflow (Step 2's
evidence collection, or an already-completed analysis). A sign-off is
different in kind: persisting an INCOMPLETE sign-off as if it were
final is exactly the R18 failure mode ("review becomes nominal rather
than meaningful") this whole task exists to prevent. So
persist_sign_off() deliberately raises IncompleteSignOffError (via
expert_sign_off.require_meaningful_sign_off()) BEFORE attempting any
database write, rather than writing a partial record and returning a
status the caller might not check. Database/connectivity failures
AFTER that check still degrade to a status dict, never raise — see
below.

LOCK SEMANTICS
Same append-only guarantee as decision_record_persistence.py: this
module only ever INSERTS. There is no update or delete path. If the
same candidate is signed off more than once (e.g. a second reviewer,
or the same reviewer revising an earlier sign-off), each call inserts
a SEPARATE row — the full sign-off history for a candidate is the
complete set of rows sharing its analysis_id/reference_plant/
alternative_plant, not a single mutable record.

REQUIRED TABLE (created outside this repository, like every other
Supabase table here — no migration/SQL file exists anywhere in this
codebase for any table, and this module does not introduce one)
`expert_sign_offs`, with columns matching sign_off_to_dict()'s keys
plus `recorded_at` (persistence time, added here — see
expert_sign_off.sign_off_to_dict() for every other column). Until that
table exists, persist_sign_off() degrades to
{"status": "unavailable", ...} for the database-write failure mode —
but still raises IncompleteSignOffError for an incomplete sign-off
regardless of whether the table exists, since that check happens
first and needs no database access.
"""

from __future__ import annotations

from datetime import datetime, timezone

from expert_sign_off import (
    ExpertSignOff,
    require_meaningful_sign_off,
    require_authorized_sign_off,
    sign_off_to_dict,
)

SIGN_OFF_TABLE_NAME = "expert_sign_offs"


def _write_sign_off_row(sign_off: ExpertSignOff, supabase_client=None) -> dict:
    """Shared DB-write logic for persist_sign_off() and (Task 9)
    persist_authorized_sign_off() — both call this ONLY after their
    own respective completeness/authorization check has already
    passed (require_meaningful_sign_off() / require_authorized_sign_off()),
    so this helper itself performs no validation and assumes
    `sign_off` is already known-good. Never raises: database/
    connectivity failures degrade to a status dict, same as this
    repo's other persistence functions' failure path.
    """
    row = sign_off_to_dict(sign_off)
    row["recorded_at"] = datetime.now(timezone.utc).isoformat()

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        # Append-only: always insert, never update/upsert — see LOCK
        # SEMANTICS above.
        supabase_client.table(SIGN_OFF_TABLE_NAME).insert(row).execute()

        return {
            "status": "persisted",
            "reference_plant": sign_off.reference_plant,
            "alternative_plant": sign_off.alternative_plant,
            "disposition": sign_off.disposition.value,
            "detail": "Expert sign-off persisted.",
        }
    except Exception:
        # Deliberately generic in the returned detail — never surfaces
        # a raw exception message, which could contain a connection
        # string, credential fragment, or internal stack detail — same
        # discipline as telemetry_persistence.py's own failure path.
        return {
            "status": "unavailable",
            "reference_plant": sign_off.reference_plant,
            "alternative_plant": sign_off.alternative_plant,
            "disposition": sign_off.disposition.value,
            "detail": "Sign-off persistence unavailable this session "
                      "(table may not exist yet, or the database is unreachable).",
        }


def persist_sign_off(sign_off: ExpertSignOff, supabase_client=None) -> dict:
    """The ONE write function this module exists to provide.

    Raises expert_sign_off.IncompleteSignOffError if `sign_off` does
    not satisfy is_meaningful_sign_off() — see module docstring for
    why this function, unlike this repo's other persistence functions,
    does not swallow that failure into a status dict. Only database/
    connectivity failures AFTER that check produce a
    {"status": "unavailable", ...} return instead of a raise.

    Returns:
      {
        "status": "persisted" | "unavailable",
        "reference_plant": str,
        "alternative_plant": str,
        "disposition": str,
        "detail": str,   # human-readable, safe to show in the UI —
                          # never a raw SQL error or credential value.
      }
    """
    require_meaningful_sign_off(sign_off)
    return _write_sign_off_row(sign_off, supabase_client)


def persist_authorized_sign_off(
    sign_off: ExpertSignOff, required_domains: set, supabase_client=None
) -> dict:
    """Task 9 — same contract as persist_sign_off() above, plus a
    role-authorization check: raises
    expert_sign_off.UnauthorizedReviewerError (a subclass of
    IncompleteSignOffError) if the reviewer's asserted role does not
    cover every domain in `required_domains` (see
    user_roles.required_domains_for_candidate() for how to derive that
    set from a candidate row's Safety_Flags/Regulatory_Barriers/
    Market_Status).

    persist_sign_off() itself is INTENTIONALLY left as-is (not made to
    require a role check) — a caller that has no domain-requirement
    context to supply (e.g. a migration script backfilling historical
    sign-offs, or a context where role authorization is enforced
    upstream instead) can still use the base function. This one is for
    the normal, forward-looking case: every NEW sign-off collected
    through a UI that knows what domains a candidate touches should
    call this one instead of the base function.
    """
    require_authorized_sign_off(sign_off, required_domains)
    return _write_sign_off_row(sign_off, supabase_client)


def load_sign_offs_for_candidate(
    analysis_id: str, reference_plant: str, alternative_plant: str, supabase_client=None
) -> list:
    """Every persisted sign-off for one candidate row, most recent
    first — the full history (see module docstring's LOCK SEMANTICS),
    not just the latest. Returns [] on any failure (missing table,
    unreachable database, no matching rows) — never raises, since this
    is a read path with no "must be meaningful" requirement to enforce
    (that requirement is enforced at write time, by persist_sign_off()
    above)."""
    if not analysis_id or not reference_plant or not alternative_plant:
        return []

    try:
        if supabase_client is None:
            from supabase_client import get_supabase_client
            supabase_client = get_supabase_client()

        response = (
            supabase_client.table(SIGN_OFF_TABLE_NAME)
            .select("*")
            .eq("analysis_id", analysis_id)
            .eq("reference_plant", reference_plant)
            .eq("alternative_plant", alternative_plant)
            .execute()
        )
        rows = response.data or []
        # Sorted here in Python (most recent first), rather than
        # relying on a chained .order() call — keeps this function
        # portable across supabase-py client versions and matches the
        # shape of this repo's existing fake test client (see
        # test_sign_off_persistence.py's _FakeTable), which only
        # implements insert/select/eq/execute.
        return sorted(rows, key=lambda r: r.get("recorded_at") or "", reverse=True)
    except Exception:
        return []
