"""Phase 4 (IMPLEMENTATION_PLAN.md) — reproducibility metadata.

WHAT THIS IS
build_decision_metadata() is called EXACTLY ONCE per decision run (from
step_rd_candidates.py, right after merge_authoritative_scores() produces
the authoritative report-ready frame). The single dict it returns is then
passed, unchanged, to BOTH generate_pharma_report() (to render a
"Reproducibility" section) and persist_decision_record() (to store it) —
so the report and the persisted record can never describe two different
runs. Nothing downstream recomputes any of these ten fields independently.

VERSION CONSTANTS
Defined once, here, as the single source of truth for "which logic
produced this decision":
  - SCORING_MODEL_VERSION identifies candidate_shortlisting.py's
    authoritative Overall_Score model (Phase 3) — NOT the same thing as
    the legacy row-level Scoring_Config_Version already tracked by
    decision_record_persistence.py, which describes a different,
    still-separate computation (see that module's own docstring on why
    scoring_config_version and decision_engine_version are kept
    independently readable; scoring_model_version follows the same rule).
  - NORMALIZATION_VERSION identifies the evidence-field normalization
    path fixed in Phase 1/2 (score_breakdown_schema.py's single parser;
    evidence_standardizer.py's hand-copied identifier fields).
  - VALIDATION_VERSION identifies the existing, unmodified
    candidate_output_adapter.py contract this phase reuses rather than
    replaces.

EVIDENCE SNAPSHOT — NEVER FABRICATED
compute_evidence_snapshot() hashes the SORTED, DEDUPLICATED set of
Source_Record_IDs actually present on the candidate rows — never the
DataFrame's row order (a fingerprint that changed only because pandas
returned rows in a different order would misrepresent "the evidence
changed" when it didn't). If no candidate row carries a
Source_Record_IDs value, the snapshot is explicitly marked
"unavailable" — never replaced with a random or time-based ID that
would look reproducible without actually being derived from anything.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

# Single source of truth — see module docstring. Bump these here, and
# nowhere else, when the corresponding logic actually changes.
SCORING_MODEL_VERSION = "authoritative-plant-v1.2"
NORMALIZATION_VERSION = "evidence-standardizer-phase2"
VALIDATION_VERSION = "candidate-output-adapter-v1"

_UNAVAILABLE_SNAPSHOT_STATUS = "unavailable"
_COMPUTED_SNAPSHOT_STATUS = "computed"


def _split_ids(raw_value) -> list[str]:
    if raw_value is None:
        return []
    text = str(raw_value).strip()
    if not text or text.lower() in ("nan", "none", ""):
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def compute_evidence_snapshot(report_ready_df) -> dict:
    """Returns {"evidence_snapshot_id": str|None, "status": "computed"|"unavailable"}.

    The ID is sha256 of the sorted, deduplicated set of every
    Source_Record_IDs value across every candidate row — order-independent
    by construction (sorting happens before hashing, regardless of what
    order the DataFrame's rows arrived in). Never fabricated: if no row
    carries any identifier, status is "unavailable" and the id is None.
    """
    if report_ready_df is None or getattr(report_ready_df, "empty", True):
        return {"evidence_snapshot_id": None, "status": _UNAVAILABLE_SNAPSHOT_STATUS}

    if "Source_Record_IDs" not in report_ready_df.columns:
        return {"evidence_snapshot_id": None, "status": _UNAVAILABLE_SNAPSHOT_STATUS}

    all_ids: set[str] = set()
    for raw_value in report_ready_df["Source_Record_IDs"]:
        all_ids.update(_split_ids(raw_value))

    if not all_ids:
        return {"evidence_snapshot_id": None, "status": _UNAVAILABLE_SNAPSHOT_STATUS}

    canonical = "\n".join(sorted(all_ids))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {"evidence_snapshot_id": digest, "status": _COMPUTED_SNAPSHOT_STATUS}


def compute_candidate_set_fingerprint(report_ready_df) -> str | None:
    """A single hash identifying WHICH candidates, with WHICH authoritative
    status/score, made up this decision run. Built from
    (Alternative_Plant, Scientific_Triage_Status, Overall_Score) tuples,
    SORTED before hashing — so re-running the exact same analysis twice
    (even if the DataFrame rows come back in a different order) produces
    the identical fingerprint, and any real change (a candidate added,
    removed, or re-scored) produces a different one. Returns None only
    when there is no candidate data at all to fingerprint.
    """
    if report_ready_df is None or getattr(report_ready_df, "empty", True):
        return None
    if "Alternative_Plant" not in report_ready_df.columns:
        return None

    tuples = []
    for _, row in report_ready_df.iterrows():
        plant = str(row.get("Alternative_Plant", ""))
        status = str(row.get("Scientific_Triage_Status", ""))
        score = row.get("Overall_Score", "")
        tuples.append(f"{plant}|{status}|{score}")

    canonical = "\n".join(sorted(tuples))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_decision_metadata(
    report_ready_df,
    *,
    indication: str,
    dosage_form: str,
    market: str,
    discovery_mode: str,
) -> dict:
    """The ONE call site for reproducibility metadata (Phase 4). Computed
    once per decision run; callers pass the returned dict through
    unchanged to both the report and the persisted decision record —
    never recomputed independently by either.
    """
    snapshot = compute_evidence_snapshot(report_ready_df)
    return {
        "scoring_model_version": SCORING_MODEL_VERSION,
        "evidence_snapshot_id": snapshot["evidence_snapshot_id"],
        "evidence_snapshot_status": snapshot["status"],
        "normalization_version": NORMALIZATION_VERSION,
        "validation_version": VALIDATION_VERSION,
        "decision_timestamp": datetime.now(timezone.utc).isoformat(),
        "discovery_mode": discovery_mode,
        "indication": indication,
        "dosage_form": dosage_form,
        "market": market,
        "candidate_set_fingerprint": compute_candidate_set_fingerprint(report_ready_df),
    }
