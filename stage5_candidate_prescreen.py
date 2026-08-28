"""Stage 5 candidate funnel — a cheap, high-recall pre-screen that runs
BEFORE the expensive per-plant scientific scoring in
:func:`candidate_shortlisting.build_plant_candidate_shortlist`.

WHY THIS MODULE EXISTS
-----------------------
Production Stage 5 traced (see STAGE5_CANDIDATE_FUNNEL_ROOT_CAUSE_REPORT.md)
called ``build_plant_candidate_shortlist()`` on the ENTIRE raw candidate
universe (~2,119 Supabase catalogue plants, ~17,394 raw evidence/association
rows) to decide which ~120 plants deserved commercial-market enrichment, then
called it AGAIN on that ~120-plant subset. Every plant -- including the vast
majority with no meaningful indication signal at all -- paid the full cost of
:func:`candidate_shortlisting._evidence_quality`,
:func:`candidate_shortlisting._scientific_evidence_components`,
:func:`candidate_shortlisting._compound_quality`,
:func:`candidate_shortlisting._mechanism_support`,
:func:`candidate_shortlisting._safety_regulatory` and
:func:`candidate_shortlisting._novelty_market`, and ~120 of those plants paid
it TWICE.

This module inserts a cheap funnel between the raw candidate universe and
that expensive per-plant loop. It deliberately reuses only the ALREADY-CHEAP
per-row classification (:func:`candidate_shortlisting._row_classification`,
the same function the row-level audit loop already runs over every raw row)
-- it never calls any of the six expensive per-plant component functions
above. Supabase remains the internal botanical catalogue; nothing here
replaces it with online-only discovery, and nothing here is indication- or
plant-specific.

ARCHITECTURE
------------
    Supabase catalogue candidates + Stage 2 novel candidates (raw_df)
        |
        v
    cheap per-row classification (reused, not re-derived)
        |
        v
    cheap per-plant aggregation (booleans/counts only)
        |
        v
    MANDATORY (always kept) + EXPLORATORY (budget-capped) + DROP
        |
        v
    UNION with validated Stage 2 novel candidates (never dropped)
        |
        v
    bounded scoring pool  -->  build_plant_candidate_shortlist() ONCE
"""
from __future__ import annotations

import time
from typing import Any, Iterable, Mapping

import pandas as pd

import botanical_taxonomy as _botanical_taxonomy
from candidate_shortlisting import _row_classification, _norm, _is_missing
from stage5_funnel_config import (
    STAGE5_PRESCREEN_DEFAULT_MODE,
    resolve_exploratory_budget,
)

PRESCREEN_STATUS_SENT = "SENT_TO_FULL_SCORING"
PRESCREEN_STATUS_EXCLUDED = "EXCLUDED_BEFORE_FULL_SCORING"

PRESCREEN_REASON_DIRECT_EVIDENCE = "Direct, traceable indication evidence present"
PRESCREEN_REASON_HARD_STOP = "Hard safety/regulatory stop present — routed to full scoring for an auditable Excluded record"
PRESCREEN_REASON_STAGE2_NOVEL = "Validated Stage 2 novel candidate — always sent to full scoring"
PRESCREEN_REASON_EXPLORATORY_KEPT = "Supportive mechanistic/target match retained within the exploratory candidate budget"
PRESCREEN_REASON_EXPLORATORY_BUDGET = "Supportive mechanistic/target match only, and the exploratory candidate budget was already filled by higher-priority candidates"
PRESCREEN_REASON_NO_SIGNAL = "No traceable relevant evidence, no supported target/mechanism, and no direct indication signal"

_CANDIDATE_SOURCE_CATALOGUE = "catalogue"
_CANDIDATE_SOURCE_STAGE2 = "stage2_novel"
_CANDIDATE_SOURCE_BOTH = "both"


def _perf(msg: str) -> None:
    print(f"[PERF] {msg}", flush=True)


def _progress(callback, current: int, total: int, message: str) -> None:
    if callback is None:
        return
    try:
        callback(current, total, message)
    except Exception:
        # Presentation-only hook; must never be able to change or abort the
        # candidate funnel, mirroring the same guard used throughout
        # candidate_shortlisting.py and indication_candidate_discovery.py.
        pass


def _canonical_plant_key(name: object) -> str:
    key = _botanical_taxonomy.taxon_match_key(name)
    if key:
        return key
    # Fallback for names the taxonomy layer cannot resolve (e.g. a free-text
    # common name with no catalogue match yet) -- still deterministic and
    # collision-safe for dedup purposes within a single Stage 5 run.
    return _norm(name)


def _novel_candidate_keys(novel_candidate_plants: Iterable[Mapping[str, Any] | str] | None) -> dict[str, str]:
    """Map canonical plant key -> the original display name for every
    validated Stage 2 novel candidate. Accepts either plain plant-name
    strings or the ``{"Scientific_Name": ...}``-shaped dicts
    ``BotanicalRDCandidateEngine(discovered_candidates=...)`` already
    consumes, so callers can pass the same list they pass to the engine.
    """
    out: dict[str, str] = {}
    for item in novel_candidate_plants or []:
        if isinstance(item, Mapping):
            name = item.get("Scientific_Name") or item.get("Alternative_Plant")
        else:
            name = item
        name = str(name or "").strip()
        if not name:
            continue
        key = _canonical_plant_key(name)
        if key:
            out.setdefault(key, name)
    return out


def prescreen_candidate_universe(
    raw_df: pd.DataFrame,
    *,
    dosage_form: str = "",
    novel_candidate_plants: Iterable[Mapping[str, Any] | str] | None = None,
    mode: str | None = None,
    exploratory_budget: int | None = None,
    progress_callback=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(scoring_pool_df, prescreen_audit_df)``.

    ``scoring_pool_df`` is the subset of ``raw_df`` rows belonging to
    plants that should proceed to the expensive
    :func:`candidate_shortlisting.build_plant_candidate_shortlist` pass. It
    is always a subset of ``raw_df``'s own rows (never fabricated), so every
    downstream field build_plant_candidate_shortlist would otherwise have
    produced is computed from the exact same raw evidence.

    ``prescreen_audit_df`` has one row per PLANT in the full input universe
    (never per raw association row) with ``PreScreen_Status`` /
    ``PreScreen_Reason`` / ``Candidate_Source`` columns, so no catalogue
    plant is silently dropped without a traceable reason -- including the
    ones this function screens OUT.

    This function never calls any of the expensive per-plant scientific
    scoring helpers in candidate_shortlisting.py (evidence quality,
    scientific evidence components, compound quality, mechanism support,
    safety/regulatory, novelty/market). It only reuses the already-cheap
    per-row classification every raw row already goes through.
    """
    if not isinstance(raw_df, pd.DataFrame) or raw_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    if "Alternative_Plant" not in raw_df.columns:
        return raw_df.copy(), pd.DataFrame()

    _t0 = time.perf_counter()
    input_count = int(raw_df["Alternative_Plant"].nunique())
    _perf(f"stage5_prescreen start input_plants={input_count} input_rows={len(raw_df)}")

    novel_keys = _novel_candidate_keys(novel_candidate_plants)
    budget = resolve_exploratory_budget(
        mode or STAGE5_PRESCREEN_DEFAULT_MODE, override=exploratory_budget
    )

    # --- cheap per-row classification (reused, not re-derived) -----------
    _t = time.perf_counter()
    direct_flags: list[bool] = []
    target_flags: list[bool] = []
    hard_stop_flags: list[bool] = []
    row_statuses: list[str] = []
    for _, row in raw_df.iterrows():
        status, _reasons, flags = _row_classification(row, dosage_form)
        row_statuses.append(status)
        direct_flags.append(bool(flags["direct"]))
        target_flags.append(bool(flags["target"]))
        hard_stop_flags.append(bool(flags["hard_stop"]))
    _perf(
        f"stage5_prescreen row_classification done rows={len(raw_df)} "
        f"elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})"
    )

    scratch = raw_df.assign(
        _prescreen_direct=direct_flags,
        _prescreen_target=target_flags,
        _prescreen_hard_stop=hard_stop_flags,
        _prescreen_row_status=row_statuses,
    )
    source_id_col = "Source_Record_IDs" if "Source_Record_IDs" in scratch.columns else None

    # --- cheap per-plant aggregation (booleans/counts only) ---------------
    _t = time.perf_counter()
    plant_rows: list[dict[str, Any]] = []
    grouped = scratch.groupby("Alternative_Plant", sort=False, dropna=False)
    total_plants = grouped.ngroups
    processed = 0
    _PROGRESS_EVERY = 200
    _progress(progress_callback, 0, total_plants, "Pre-screening catalogue plants…")

    for plant, group in grouped:
        plant_name = str(plant or "").strip()
        if not plant_name or plant_name.lower() == "nan":
            continue
        processed += 1
        canonical_key = _canonical_plant_key(plant_name)
        has_direct = bool(group["_prescreen_direct"].any())
        has_target = bool(group["_prescreen_target"].any())
        has_hard_stop = bool(group["_prescreen_hard_stop"].any())
        shortlist_row_count = int((group["_prescreen_row_status"] == "Shortlist").sum())
        exploratory_row_count = int((group["_prescreen_row_status"] == "Exploratory").sum())
        if source_id_col:
            source_count = int(
                group[source_id_col].map(lambda v: not _is_missing(v)).sum()
            )
        else:
            source_count = 0
        is_stage2_novel = canonical_key in novel_keys

        plant_rows.append({
            "Alternative_Plant": plant_name,
            "_canonical_key": canonical_key,
            "has_direct": has_direct,
            "has_target": has_target,
            "has_hard_stop": has_hard_stop,
            "shortlist_row_count": shortlist_row_count,
            "exploratory_row_count": exploratory_row_count,
            "source_count": source_count,
            "is_stage2_novel": is_stage2_novel,
        })

        if processed % _PROGRESS_EVERY == 0:
            _progress(
                progress_callback, processed, total_plants,
                f"Pre-screening {processed} / {total_plants} catalogue plants…",
            )
    _perf(
        f"stage5_prescreen plant aggregation done plants={processed} "
        f"elapsed={time.perf_counter() - _t:.3f} (cumulative={time.perf_counter() - _t0:.3f})"
    )

    # --- classify: MANDATORY / EXPLORATORY / DROP --------------------------
    mandatory: list[dict[str, Any]] = []
    exploratory: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for entry in plant_rows:
        if entry["has_direct"] or entry["has_hard_stop"] or entry["is_stage2_novel"]:
            mandatory.append(entry)
        elif entry["has_target"] or entry["exploratory_row_count"] > 0:
            exploratory.append(entry)
        else:
            dropped.append(entry)

    # Rank exploratory candidates by a cheap, generic relevance proxy --
    # never a scientific score. No indication/plant-specific logic.
    exploratory.sort(
        key=lambda e: (e["shortlist_row_count"], e["source_count"], e["exploratory_row_count"]),
        reverse=True,
    )
    kept_exploratory = exploratory[:budget]
    dropped_exploratory = exploratory[budget:]

    mandatory_keys = {e["_canonical_key"] for e in mandatory}
    retained_keys = mandatory_keys | {e["_canonical_key"] for e in kept_exploratory}

    # --- Stage 2 novel candidates always survive, even with sparse/no
    # Supabase catalogue history (may not appear in raw_df at all yet). ----
    catalogue_keys = {e["_canonical_key"] for e in plant_rows}
    stage2_only_keys = set(novel_keys) - catalogue_keys

    # --- build the audit trail for every catalogue plant -------------------
    audit_rows: list[dict[str, Any]] = []
    for entry in mandatory:
        reason = (
            PRESCREEN_REASON_STAGE2_NOVEL if entry["is_stage2_novel"] and not entry["has_direct"]
            and not entry["has_hard_stop"] else
            PRESCREEN_REASON_HARD_STOP if entry["has_hard_stop"] and not entry["has_direct"] else
            PRESCREEN_REASON_DIRECT_EVIDENCE
        )
        source = _CANDIDATE_SOURCE_BOTH if entry["is_stage2_novel"] else _CANDIDATE_SOURCE_CATALOGUE
        audit_rows.append({
            "Alternative_Plant": entry["Alternative_Plant"],
            "PreScreen_Status": PRESCREEN_STATUS_SENT,
            "PreScreen_Reason": reason,
            "Candidate_Source": source,
        })
    for entry in kept_exploratory:
        source = _CANDIDATE_SOURCE_BOTH if entry["is_stage2_novel"] else _CANDIDATE_SOURCE_CATALOGUE
        audit_rows.append({
            "Alternative_Plant": entry["Alternative_Plant"],
            "PreScreen_Status": PRESCREEN_STATUS_SENT,
            "PreScreen_Reason": PRESCREEN_REASON_EXPLORATORY_KEPT,
            "Candidate_Source": source,
        })
    for entry in dropped_exploratory:
        audit_rows.append({
            "Alternative_Plant": entry["Alternative_Plant"],
            "PreScreen_Status": PRESCREEN_STATUS_EXCLUDED,
            "PreScreen_Reason": PRESCREEN_REASON_EXPLORATORY_BUDGET,
            "Candidate_Source": _CANDIDATE_SOURCE_CATALOGUE,
        })
    for entry in dropped:
        audit_rows.append({
            "Alternative_Plant": entry["Alternative_Plant"],
            "PreScreen_Status": PRESCREEN_STATUS_EXCLUDED,
            "PreScreen_Reason": PRESCREEN_REASON_NO_SIGNAL,
            "Candidate_Source": _CANDIDATE_SOURCE_CATALOGUE,
        })
    for key in stage2_only_keys:
        audit_rows.append({
            "Alternative_Plant": novel_keys[key],
            "PreScreen_Status": PRESCREEN_STATUS_SENT,
            "PreScreen_Reason": PRESCREEN_REASON_STAGE2_NOVEL,
            "Candidate_Source": _CANDIDATE_SOURCE_STAGE2,
        })

    prescreen_audit_df = pd.DataFrame(audit_rows)

    # --- bounded scoring pool: raw rows only, never fabricated -------------
    if retained_keys:
        key_series = scratch["Alternative_Plant"].map(_canonical_plant_key)
        scoring_pool_df = raw_df[key_series.isin(retained_keys)].copy()
    else:
        scoring_pool_df = raw_df.iloc[0:0].copy()

    retained_plant_count = len(retained_keys) + len(stage2_only_keys)
    _perf(
        f"stage5_prescreen done input_plants={input_count} "
        f"mandatory={len(mandatory)} exploratory_kept={len(kept_exploratory)} "
        f"exploratory_dropped={len(dropped_exploratory)} no_signal_dropped={len(dropped)} "
        f"stage2_novel_not_in_catalogue={len(stage2_only_keys)} "
        f"retained_plants={retained_plant_count} budget={budget} "
        f"total_elapsed={time.perf_counter() - _t0:.3f}"
    )
    _progress(
        progress_callback, total_plants, total_plants,
        f"Pre-screen selected {retained_plant_count} of {input_count} plants for full evaluation",
    )

    return scoring_pool_df, prescreen_audit_df
