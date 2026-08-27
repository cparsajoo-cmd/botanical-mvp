"""AI R&D insight orchestrator -- the Stage 5 integration point for
mechanistic_reasoning_service.py, evidence_synthesis_service.py, and
hypothesis_generation_service.py.

INTEGRATION POINT
step_rd_candidates.py calls generate_candidate_insights() once per
ranked candidate AFTER the deterministic engine.run() result_df already
exists (see step_rd_candidates.py). This function's output is stored
and rendered SEPARATELY from the deterministic score/columns -- it never
modifies result_df, never touches Deterministic_Score /
R&D_Opportunity_Score, and is entirely optional: Stage 5's existing
output is complete and correct with or without this function ever being
called (Part 15/17/18 of the architecture spec).

WHY A THIN, GENERIC EVIDENCE ADAPTER
botanical_rd_candidate_engine.py's internal evidence indexing
(_collect_raw_evidence, contributing_records, authority_index, ...) is
deep, pooled-text-oriented machinery built for the deterministic scoring
path. Reusing it here would mean either modifying that machinery (out of
scope -- Part 15/17 require the deterministic scoring path to remain
untouched) or duplicating a large amount of internal state. Instead,
_evidence_items_from_df() below reads the SAME raw evidence_records_df
columns (see standard_evidence_schema.py's canonical column names:
Evidence_Record_ID/PMID, Scientific_Name, Result_Direction, Study_Model,
Notes) directly and independently, producing the small, generic
``evidence_items`` list the three AI services already expect. This is a
read-only, additive adapter -- it has no effect on how the deterministic
engine computes anything.

FAIL-OPEN, INDEPENDENTLY PER STAGE
Each of the three AI stages (mechanism, synthesis, hypotheses) is
wrapped in its own try/except here, on top of the fail-open behavior
each service already implements internally. A failure in one stage
(e.g. mechanistic reasoning) does not prevent the others from running
(e.g. evidence synthesis can still run on the same evidence_items even
if mechanism reasoning failed) -- matching Part 18's requirement that
each AI capability degrades independently.
"""
from __future__ import annotations

from typing import List, Optional

from mechanistic_reasoning_service import reason_about_mechanisms
from evidence_synthesis_service import synthesize_evidence
from hypothesis_generation_service import generate_hypotheses
from evidence_adjudication_engine import is_indication_relevant_row

# Cost control -- bound how many raw evidence rows are turned into
# evidence_items for one candidate, regardless of how many the
# underlying table has (Part 19).
MAX_EVIDENCE_ROWS_PER_CANDIDATE = 30
_MAX_NOTE_CHARS = 500


def _row_get(row, *keys):
    for key in keys:
        try:
            value = row.get(key)
        except AttributeError:
            value = row[key] if key in row else None
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _evidence_items_from_df(evidence_df, plant_name: str, indication: str = "") -> List[dict]:
    """Read-only adapter: raw evidence_records_df rows for one plant ->
    the generic evidence_items contract the AI services expect. Returns
    [] for any missing/empty dataframe or plant with no matching rows --
    never raises.

    Part 7 (this session) -- filtered to INDICATION-RELEVANT rows only,
    reusing evidence_adjudication_engine.is_indication_relevant_row (the
    exact same predicate the adjudication layer applies), so this
    explanatory AI stage sees the same evidence scope adjudication saw
    rather than the plant's whole, indication-agnostic evidence history.
    When indication is empty, every matched row is kept (nothing to
    filter on -- matches is_indication_relevant_row's own behavior).
    """
    if evidence_df is None:
        return []
    try:
        if evidence_df.empty:
            return []
    except AttributeError:
        return []

    plant_key = str(plant_name or "").strip().lower()
    if not plant_key:
        return []

    try:
        name_col = None
        for candidate_col in ("Scientific_Name", "plant_species", "Plant_Scientific_Name"):
            if candidate_col in evidence_df.columns:
                name_col = candidate_col
                break
        if name_col is None:
            return []
        matched = evidence_df[
            evidence_df[name_col].astype(str).str.strip().str.lower() == plant_key
        ]
    except Exception:
        return []

    indication_tokens = [t for t in str(indication or "").strip().lower().split() if len(t) > 2]

    items = []
    for _, row in matched.iterrows():
        if len(items) >= MAX_EVIDENCE_ROWS_PER_CANDIDATE:
            break
        try:
            if not is_indication_relevant_row(row, indication_tokens):
                continue
        except Exception:
            pass  # never let the relevance check itself block this fail-open adapter
        evidence_id = _row_get(row, "Evidence_Record_ID", "evidence_record_id", "PMID", "pmid", "Record_ID")
        if not evidence_id:
            continue
        note = _row_get(row, "Notes", "supporting_sentence", "Raw_Text")
        items.append({
            "evidence_id": evidence_id,
            "plant": plant_name,
            "compound": _row_get(row, "Compound", "compound_name"),
            "target": _row_get(row, "Target", "target"),
            "mechanism_text": _row_get(row, "Mechanism", "mechanism"),
            "result_direction": _row_get(row, "Result_Direction", "evidence_direction"),
            "study_model": _row_get(row, "Study_Model", "study_model"),
            "text_snippet": note[:_MAX_NOTE_CHARS],
        })
    return items


def generate_candidate_insights(
    plant_name: str,
    evidence_df,
    score_summary: Optional[dict] = None,
    indication: str = "",
) -> dict:
    """Return {"evidence_items_count", "mechanistic_edges",
    "evidence_synthesis", "hypotheses"} for one candidate. Every AI
    stage fails open independently -- an empty/None result for a stage
    means that stage produced nothing usable, never an exception
    propagating to the caller. Always returns a dict (never raises), so
    Stage 5 rendering can call this unconditionally and just check
    whether each section is non-empty before displaying it.

    ``indication`` (Part 7, this session) narrows the evidence bundle to
    indication-relevant rows only -- see _evidence_items_from_df.
    """
    evidence_items = _evidence_items_from_df(evidence_df, plant_name, indication)

    mechanistic_edges: List[dict] = []
    try:
        mechanistic_edges = reason_about_mechanisms(evidence_items)
    except Exception:
        mechanistic_edges = []

    synthesis = None
    try:
        synthesis = synthesize_evidence(evidence_items)
    except Exception:
        synthesis = None

    hypotheses: List[dict] = []
    try:
        evidence_ids = [item["evidence_id"] for item in evidence_items]
        hypotheses = generate_hypotheses(
            mechanistic_edges, synthesis, score_summary=score_summary,
            evidence_ids=evidence_ids, evidence_items=evidence_items,
        )
    except Exception:
        hypotheses = []

    return {
        "evidence_items_count": len(evidence_items),
        "mechanistic_edges": mechanistic_edges,
        "evidence_synthesis": synthesis,
        "hypotheses": hypotheses,
    }
