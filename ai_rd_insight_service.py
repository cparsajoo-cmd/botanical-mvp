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
from evidence_adjudication_engine import build_adjudication_evidence_items

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
    """Use the exact curated evidence bundle used by scientific adjudication.

    This removes a previous split-brain condition where explanatory AI could see
    a different (and storage-order dependent) set of records from adjudication.
    The adapter only renames fields to the compact service contract.
    """
    try:
        raw_items = build_adjudication_evidence_items(
            evidence_df, plant_name, indication, max_items=MAX_EVIDENCE_ROWS_PER_CANDIDATE
        )
    except Exception:
        return []
    items: List[dict] = []
    for item in raw_items:
        items.append({
            "evidence_id": item.get("evidence_id"),
            "plant": plant_name,
            "compound": item.get("compound") or "",
            "target": item.get("target") or "",
            "mechanism_text": item.get("mechanism") or "",
            "result_direction": item.get("result_direction") or "",
            "study_model": item.get("study_model") or item.get("study_type_design") or "",
            "text_snippet": (item.get("evidence_text_snippet") or "")[:_MAX_NOTE_CHARS],
            "human_animal_in_vitro": item.get("human_animal_in_vitro"),
            "indication_match_strength": item.get("indication_match_strength"),
            "preparation": item.get("preparation"),
            "route_of_administration": item.get("route_of_administration"),
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
