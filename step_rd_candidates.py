import time
import threading
import json

import pandas as pd
import streamlit as st

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from market_intelligence_engine import MarketIntelligenceEngine
from pharma_report_generator import generate_pharma_report
from product_development_concept import add_development_concept_column
from candidate_output_adapter import validate_result_df
from candidate_shortlisting import (
    build_plant_candidate_shortlist,
    merge_authoritative_scores,
    rescore_commercial_component,
)
from sensitivity_display_adapter import prepare_sensitivity_payload
from decision_record_persistence import persist_decision_record
from decision_metadata import build_decision_metadata
from decision_explainability import attach_decision_explanations
from ai_rd_insight_service import generate_candidate_insights
from evidence_adjudication_engine import (
    adjudicate_candidate,
    apply_negative_evidence_cap,
    compute_deterministic_adjustments,
    sync_final_decision_status,
    build_final_rationale,
)
from standard_evidence_builder import (
    build_scientific_evidence_presentation_payload,
    get_scientific_evidence_by_ids,
    build_transferability_target_context,
)
from ai_usage_telemetry import start_new_ai_run, get_ai_run_tracker


# TEMPORARY DIAGNOSTIC INSTRUMENTATION (performance audit — runtime hang
# in indication-centric Candidate Discovery). Prints only; no behavior
# change. See the "Run Candidate Discovery" button handler below.
def _perf(msg):
    print(f"[PERF] {msg}", flush=True)


def _reconcile_final_decision_status(row) -> str:
    """Produce one populated scientific decision from deterministic + AI facts.

    The AI may only make the result more conservative.  Hard safety/regulatory
    statuses are never weakened.  Missing or contradictory AI evidence cannot
    coexist with an unqualified green recommendation.
    """
    def clean(key):
        value = row.get(key, "") if hasattr(row, "get") else ""
        text = str(value or "").strip()
        return "" if text.lower() in {"nan", "none", "null"} else text

    current = clean("Final_Decision_Status")
    if current in {"NO GO SAFETY", "NO GO REGULATORY"}:
        return current

    decision_class = clean("Decision_Class_AH")
    gate = clean("Relevance_Gate_Result")
    prep = clean("Preparation_Applicability_Class")
    adjudication = clean("Evidence_Adjudication_Status")
    direction = clean("Indication_Evidence_Direction").upper()
    human = clean("Human_Evidence_Strength").upper()
    conflict = clean("Evidence_Conflict_Level").upper()
    confidence = clean("Scientific_Evidence_Confidence").upper()
    indication_mode = clean("Indication_Evidence_Mode")
    safety_text = clean("Safety_Flags").lower()
    direct_count_text = clean("Direct_Indication_Evidence_Count")
    adjudication_count_text = clean("Evidence_Adjudication_Evidence_Count")
    try:
        direct_count = int(float(direct_count_text or 0))
    except (TypeError, ValueError):
        direct_count = 0
    try:
        adjudication_count = int(float(adjudication_count_text or 0))
    except (TypeError, ValueError):
        adjudication_count = 0

    if decision_class.startswith("H"):
        return "NO GO SAFETY"
    if decision_class.startswith("G") or gate.startswith("failed"):
        return "INSUFFICIENT EVIDENCE"
    # A serious but non-hard-stop safety signal may remain a viable research
    # question, but it must not be rendered as GO/GO WITH CAUTION.  Hard stops
    # are handled above; these signals require explicit expert safety review.
    severe_safety_terms = (
        "hepatotoxic", "liver injury", "nephrotoxic", "kidney injury",
        "teratogenic", "fatal", "seizure", "major bleeding", "anaphylaxis",
    )
    if any(term in safety_text for term in severe_safety_terms):
        return "EXPERT REVIEW REQUIRED"
    if prep == "incompatible":
        return "EXPERT REVIEW REQUIRED"
    if decision_class.startswith(("D", "F")) or gate == "passed_indirect_exploratory_only":
        return "EXPERT REVIEW REQUIRED"

    # A genuine AI no-evidence result means the candidate cannot be called GO,
    # even if a broad deterministic relevance count was positive.  NOT_RUN also
    # cannot masquerade as AI-reviewed.
    if adjudication in {"AI_ADJUDICATION_NO_EVIDENCE", "AI_ADJUDICATION_NOT_RUN"}:
        return "EXPERT REVIEW REQUIRED"

    if adjudication == "AI_ADJUDICATION_OK":
        # Cross-layer coherence gate.  A deterministic row cannot claim
        # direct HUMAN evidence while the structured review of the very same
        # Stage-5 evidence records finds no classifiable human evidence.
        # Likewise a positive direct-evidence count with an empty adjudication
        # bundle is an internal evidence-lineage contradiction.  In either
        # case the safe scientific state is expert review, not a green call.
        if indication_mode.startswith("Direct human/clinical") and human in {"NONE", "UNKNOWN", ""}:
            return "EXPERT REVIEW REQUIRED"
        # A topical/direct relevance label is not enough to support a green
        # human-efficacy call when none of the primary records actually reports
        # an indication-specific outcome.  This generic outcome-specificity
        # guard prevents adjacent outcomes (fatigue, stress, cognition, etc.)
        # from being promoted as direct efficacy for whatever indication was
        # requested.
        if indication_mode.startswith("Direct human/clinical") and direct_count <= 0:
            return "EXPERT REVIEW REQUIRED"
        if direct_count > 0 and adjudication_count <= 0:
            return "EXPERT REVIEW REQUIRED"
        if direction in {"MOSTLY_NEGATIVE", "CONSISTENT_NEGATIVE"} and human in {"MODERATE", "STRONG"}:
            return "INSUFFICIENT EVIDENCE"
        if (
            direction in {"INSUFFICIENT", "UNKNOWN", "NULL", ""}
            and human in {"NONE", "UNKNOWN", ""}
        ) or confidence == "VERY_LOW":
            return "EXPERT REVIEW REQUIRED"
        if confidence == "LOW" or conflict in {"MODERATE", "HIGH"} or human == "WEAK" or direction == "MIXED":
            return "GO WITH CAUTION"

    # If the provider fell back, deterministic evidence remains usable but the
    # absence of AI review is reflected conservatively.
    if adjudication in {
        "AI_ADJUDICATION_FALLBACK", "AI_ADJUDICATION_UNAVAILABLE",
        "AI_ADJUDICATION_INVALID", "AI_ADJUDICATION_DISABLED",
    }:
        if decision_class.startswith(("B", "C")) and gate == "passed_direct":
            return "GO WITH CAUTION"
        return "EXPERT REVIEW REQUIRED"

    if decision_class.startswith(("A", "B")) and gate in {"passed_direct", "not_applicable"}:
        return "GO"
    if decision_class.startswith(("C", "E")) and gate == "passed_direct":
        return "GO WITH CAUTION"
    return current or "EXPERT REVIEW REQUIRED"


def _evidence_coherence_status(row) -> str:
    """Deterministic cross-layer consistency diagnostic for the final report.

    This does not change scores. It exposes whether the deterministic evidence
    classification and structured adjudication describe the same evidence base.
    The vocabulary is disease- and product-form-agnostic.
    """
    def clean(key):
        value = row.get(key, "") if hasattr(row, "get") else ""
        text = str(value or "").strip()
        return "" if text.lower() in {"nan", "none", "null"} else text

    status = clean("Evidence_Adjudication_Status")
    if status == "AI_ADJUDICATION_NOT_RUN":
        return "NOT_REVIEWED"
    if status in {"AI_ADJUDICATION_FALLBACK", "AI_ADJUDICATION_UNAVAILABLE", "AI_ADJUDICATION_INVALID", "AI_ADJUDICATION_DISABLED"}:
        return "AI_FALLBACK"
    if status == "AI_ADJUDICATION_NO_EVIDENCE":
        try:
            direct_count = int(float(clean("Direct_Indication_Evidence_Count") or 0))
        except (TypeError, ValueError):
            direct_count = 0
        return "CONTRADICTION_NO_REVIEW_EVIDENCE" if direct_count > 0 else "COHERENT_NO_DIRECT_EVIDENCE"
    if status != "AI_ADJUDICATION_OK":
        return "UNKNOWN"

    indication_mode = clean("Indication_Evidence_Mode")
    human = clean("Human_Evidence_Strength").upper()
    try:
        direct_count = int(float(clean("Direct_Indication_Evidence_Count") or 0))
    except (TypeError, ValueError):
        direct_count = 0
    try:
        reviewed_count = int(float(clean("Evidence_Adjudication_Evidence_Count") or 0))
    except (TypeError, ValueError):
        reviewed_count = 0

    if direct_count > 0 and reviewed_count <= 0:
        return "CONTRADICTION_EMPTY_REVIEW_BUNDLE"
    if indication_mode.startswith("Direct human/clinical") and direct_count <= 0:
        return "CONTRADICTION_NO_OUTCOME_SPECIFIC_DIRECT_EVIDENCE"
    if indication_mode.startswith("Direct human/clinical") and human in {"NONE", "UNKNOWN", ""}:
        return "CONTRADICTION_HUMAN_CLASSIFICATION"
    return "COHERENT"


def _merge_and_sync_final_decision_status(result_df, plant_summary_df):
    """merge_authoritative_scores() + Part 4 fix: the merged report-ready
    frame's Final_Decision_Status comes from the raw engine row (set once,
    at engine.run() time, before adjudication ever ran) while
    Decision_Class_AH is the POST-adjudication authoritative value (see
    merge_authoritative_scores' authoritative_fields). Without this step
    the two can contradict each other -- e.g. Decision_Class_AH downgraded
    to "G — Hold / insufficient evidence" by apply_negative_evidence_cap()
    while Final_Decision_Status still reads "GO". This is the single
    synchronization point: it never runs the cap logic itself (that
    already happened in _run_evidence_adjudication), it only re-aligns
    Final_Decision_Status with whatever Decision_Class_AH the merge
    produced, downgrade-only (see
    evidence_adjudication_engine.sync_final_decision_status).
    """
    merged = merge_authoritative_scores(result_df, plant_summary_df)
    if isinstance(merged, pd.DataFrame) and not merged.empty:
        if "Final_Decision_Status" not in merged.columns:
            merged["Final_Decision_Status"] = ""
        if "Decision_Class_AH" in merged.columns:
            merged["Final_Decision_Status"] = [
                sync_final_decision_status(status, decision_class_ah)
                for status, decision_class_ah in zip(
                    merged["Final_Decision_Status"], merged["Decision_Class_AH"]
                )
            ]
        # Populate blanks and reconcile structured AI evidence with the
        # deterministic decision.  This is the final decision authority used by
        # Stage 6; it is conservative and never relaxes hard safety/regulatory
        # outcomes.
        merged["Final_Decision_Status"] = [
            _reconcile_final_decision_status(row) for _, row in merged.iterrows()
        ]
        merged["Evidence_Coherence_Status"] = [
            _evidence_coherence_status(row) for _, row in merged.iterrows()
        ]
    # Part 10 (this session) -- ONE deterministic final rationale, built
    # from the structured facts now finalized above (adjudication, safety,
    # commercial, synced final decision). Additive column
    # ("Final_Rationale") -- the existing generic "Rationale" column is
    # left untouched for backward compatibility; this is the strictly
    # more complete, structured-facts field going forward.
    if isinstance(merged, pd.DataFrame) and not merged.empty:
        merged["Final_Rationale"] = [
            build_final_rationale(row) for _, row in merged.iterrows()
        ]
    return merged


def _resolve_report_plant_column(df):
    """Part 6 (this session) -- canonical plant-identity column resolver
    for the report-ready frame. merge_authoritative_scores() (candidate_
    shortlisting.py) keys the report-ready frame on "Alternative_Plant" --
    NOT "Scientific_Name" -- so a caller that only checked for
    "Scientific_Name" (as the Stage 5 AI-insight block previously did)
    could silently see an empty candidate list and generate no insights
    at all. Checked in the project's existing priority order (see
    evidence_adjudication_engine._PLANT_NAME_COLUMNS for the same
    convention used elsewhere) with "Alternative_Plant" first, since that
    is this specific frame's actual canonical key. Returns None if the
    frame has neither -- callers must treat that as "no plant column
    available", never guess a default.
    """
    if not isinstance(df, pd.DataFrame):
        return None
    for candidate_col in ("Alternative_Plant", "Scientific_Name", "plant_species", "Plant_Scientific_Name"):
        if candidate_col in df.columns:
            return candidate_col
    return None




def _attach_ai_insights_to_report_df(report_df, ai_insights):
    """Attach bounded AI insight outputs to the authoritative Step 5/6 frame.

    Free-form AI never rewrites deterministic scores, safety/regulatory gates,
    or Final_Decision_Status here.  Structured evidence adjudication remains
    the only AI path allowed to cap a decision.  This adapter makes the AI
    mechanism/synthesis/hypothesis work visible in Step 6 and exports, and
    makes unavailable AI explicit instead of silently looking identical to a
    non-AI run.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df
    out = report_df.copy()
    plant_col = _resolve_report_plant_column(out)
    if plant_col is None:
        return out
    insights = ai_insights if isinstance(ai_insights, dict) else {}

    def _one(plant_name):
        insight = insights.get(str(plant_name), {}) or {}
        synthesis = insight.get("evidence_synthesis") or {}
        hypotheses = insight.get("hypotheses") or []
        edges = insight.get("mechanistic_edges") or []
        has_ai_content = bool(edges or synthesis or hypotheses)
        return {
            "AI_Insight_Status": "AI_REVIEW_AVAILABLE" if has_ai_content else "AI_REVIEW_UNAVAILABLE",
            "AI_Evidence_Items_Reviewed": int(insight.get("evidence_items_count") or 0),
            "AI_Mechanistic_Edge_Count": len(edges),
            "AI_Evidence_Consistency": synthesis.get("overall_consistency") if isinstance(synthesis, dict) else None,
            "AI_Evidence_Synthesis": synthesis.get("summary") if isinstance(synthesis, dict) else None,
            "AI_Hypothesis_Count": len(hypotheses),
            "AI_Top_Hypothesis": (hypotheses[0].get("hypothesis") if hypotheses and isinstance(hypotheses[0], dict) else None),
            "AI_Research_Next_Step": (hypotheses[0].get("research_next_step") if hypotheses and isinstance(hypotheses[0], dict) else None),
        }

    payloads = [_one(v) for v in out[plant_col].fillna("").astype(str)]
    for col in (
        "AI_Insight_Status", "AI_Evidence_Items_Reviewed", "AI_Mechanistic_Edge_Count",
        "AI_Evidence_Consistency", "AI_Evidence_Synthesis", "AI_Hypothesis_Count",
        "AI_Top_Hypothesis", "AI_Research_Next_Step",
    ):
        out[col] = [x[col] for x in payloads]
    return out

def _run_evidence_adjudication(plant_summary_df, evidence_df, indication, target_context):
    """Controlled AI evidence-adjudication post-processing pass (part 3C/14/15
    of the adjudication architecture) -- see evidence_adjudication_engine.py's
    module docstring for why this runs HERE (after
    build_plant_candidate_shortlist() returns, before merge_authoritative_scores())
    rather than inside the deterministic engine itself.

    Mutates and returns plant_summary_df with the new adjudication columns
    (listed in candidate_shortlisting.merge_authoritative_scores'
    authoritative_fields) added, and with Decision_Class_AH /
    Go_Investicate_Hold_NoGo downgraded (never upgraded) where
    apply_negative_evidence_cap() finds a material negative-human-evidence
    cap applies. Only Shortlist/Exploratory rows within
    _ADJUDICATION_MAX_CANDIDATES are adjudicated (cost control, part 17/19);
    every other row gets neutral/UNKNOWN placeholder columns so the
    dataframe shape never depends on how many rows were actually
    adjudicated. Never raises -- any per-candidate failure falls back to
    adjudicate_candidate()'s own fail-open status fields (part 16); this
    function has no additional try/except of its own around that call
    because adjudicate_candidate() already guarantees it never raises.
    """
    if not isinstance(plant_summary_df, pd.DataFrame) or plant_summary_df.empty:
        return plant_summary_df
    if "Alternative_Plant" not in plant_summary_df.columns:
        return plant_summary_df

    eligible_mask = plant_summary_df.get(
        "Scientific_Triage_Status", pd.Series(["Excluded"] * len(plant_summary_df))
    ).isin(["Shortlist", "Exploratory"])
    eligible_frame = plant_summary_df.loc[eligible_mask].copy()
    if "Overall_Score" in eligible_frame.columns:
        eligible_frame["_adjudication_rank_score"] = pd.to_numeric(
            eligible_frame["Overall_Score"], errors="coerce"
        ).fillna(float("-inf"))
        eligible_frame = eligible_frame.sort_values(
            "_adjudication_rank_score", ascending=False, kind="stable"
        )
    eligible_plants = (
        eligible_frame["Alternative_Plant"]
        .dropna().astype(str).drop_duplicates().tolist()[:_ADJUDICATION_MAX_CANDIDATES]
    )
    eligible_set = set(eligible_plants)

    # part B12 -- explicit UNKNOWN/neutral defaults for rows that are never
    # adjudicated, instead of leaving every column as None. The categorical
    # fields already use "UNKNOWN" as their controlled-vocabulary
    # not-applicable value everywhere else in this module (see
    # evidence_adjudication_engine.py's *_VALUES tuples), so reusing it here
    # keeps the schema's meaning stable across "adjudicated" and
    # "not adjudicated" rows rather than conflating "unknown" with "missing".
    _CATEGORICAL_UNKNOWN_DEFAULTS = {
        "Indication_Evidence_Direction": "UNKNOWN", "Human_Evidence_Strength": "UNKNOWN",
        "Evidence_Conflict_Level": "UNKNOWN", "Negative_Evidence_Severity": "UNKNOWN",
        "Preparation_Compatibility": "UNKNOWN", "Plant_Part_Compatibility": "UNKNOWN",
        "Route_Compatibility": "UNKNOWN", "Scientific_Evidence_Confidence": "UNKNOWN",
        "Positive_Evidence_IDs": (), "Negative_Evidence_IDs": (),
        "Key_Human_Evidence_IDs": (), "Preparation_Mismatch_Evidence_IDs": (),
        "Evidence_Adjudication_Evidence_Count": 0,
        "Evidence_Adjudication_Rationale": None,
        "Evidence_Adjudication_Fallback_Reason": None,
        "Evidence_Adjudication_Adjustment": 0.0, "Negative_Human_Evidence_Adjustment": 0.0,
        "Preparation_Adjustment": 0.0, "Plant_Part_Adjustment": 0.0,
        "Decision_Cap_Reason": None,
    }
    new_columns = {
        col: [
            (list(default) if isinstance(default, tuple) else default)
            for _ in range(len(plant_summary_df))
        ]
        for col, default in _CATEGORICAL_UNKNOWN_DEFAULTS.items()
    }
    new_columns["Evidence_Adjudication_Status"] = [None] * len(plant_summary_df)
    new_columns["Base_R&D_Opportunity_Score"] = [None] * len(plant_summary_df)
    new_columns["Final_R&D_Opportunity_Score"] = [None] * len(plant_summary_df)

    for idx, row in plant_summary_df.iterrows():
        plant = str(row.get("Alternative_Plant") or "")
        base_score = row.get("Overall_Score", 0.0)
        if plant not in eligible_set:
            new_columns["Evidence_Adjudication_Status"][idx] = "AI_ADJUDICATION_NOT_RUN"
            new_columns["Base_R&D_Opportunity_Score"][idx] = base_score
            new_columns["Final_R&D_Opportunity_Score"][idx] = base_score
            continue

        adjudication = adjudicate_candidate(
            plant, indication, evidence_df,
            dimension_status=row.get("Dimension_Status"),
            target_context=target_context,
            commercial_status=row.get("Commercial_Novelty_Status"),
        )
        adjustments = compute_deterministic_adjustments(adjudication, base_score)

        new_decision_class, new_go_call, cap_reason = apply_negative_evidence_cap(
            row.get("Decision_Class_AH", ""), row.get("Go_Investigate_Hold_NoGo", ""), adjudication,
        )
        if cap_reason:
            plant_summary_df.at[idx, "Decision_Class_AH"] = new_decision_class
            plant_summary_df.at[idx, "Go_Investigate_Hold_NoGo"] = new_go_call

        for key in (
            "Indication_Evidence_Direction", "Human_Evidence_Strength", "Evidence_Conflict_Level",
            "Negative_Evidence_Severity", "Preparation_Compatibility", "Plant_Part_Compatibility",
            "Route_Compatibility", "Scientific_Evidence_Confidence", "Positive_Evidence_IDs",
            "Negative_Evidence_IDs", "Key_Human_Evidence_IDs", "Preparation_Mismatch_Evidence_IDs",
            "Evidence_Adjudication_Status", "Evidence_Adjudication_Evidence_Count",
            "Evidence_Adjudication_Rationale", "Evidence_Adjudication_Fallback_Reason",
        ):
            new_columns[key][idx] = adjudication.get(key)
        for key in (
            "Evidence_Adjudication_Adjustment", "Negative_Human_Evidence_Adjustment",
            "Preparation_Adjustment", "Plant_Part_Adjustment",
            "Base_R&D_Opportunity_Score", "Final_R&D_Opportunity_Score",
        ):
            new_columns[key][idx] = adjustments.get(key)
        new_columns["Decision_Cap_Reason"][idx] = cap_reason

    for col, values in new_columns.items():
        plant_summary_df[col] = values

    # part B2 (ghost-score fix) -- Overall_Score becomes THIS module's
    # single authoritative post-adjudication score, in place, for every
    # adjudicated row. This is what makes Overall_Score, the
    # R&D_Opportunity_Score alias (candidate_shortlisting.merge_
    # authoritative_scores), ranking, the Streamlit shortlist/exploratory
    # tables (which read plant_summary_df directly -- see
    # _prepare_plant_triage_display below), and the final decision CSV all
    # agree, without adding a second competing scoring pass: it is simply
    # base_score + the already-computed, already-bounded adjudication
    # adjustment. Non-adjudicated rows are a no-op here (Final ==
    # Base == the original Overall_Score, set above).
    plant_summary_df["Overall_Score"] = new_columns["Final_R&D_Opportunity_Score"]
    return plant_summary_df


# Step 5 performance guardrails.  Commercial evidence can contribute at most
# five points to the authoritative plant-level score, so candidates more than
# this margin below the current top-50 boundary cannot enter the final top 50
# solely because of market enrichment.  We still keep a generous hard cap for
# pathological tie-heavy datasets.
_STEP5_FINAL_MAX_CANDIDATES = 50
_STEP5_COMMERCIAL_SCORE_MARGIN = 5.0
_STEP5_COMMERCIAL_MAX_PLANTS = 120

# AI R&D insight layer (mechanistic reasoning / evidence synthesis /
# hypotheses) cost control -- bounds how many shortlisted candidates get
# AI insight generation per run, independent of _STEP5_FINAL_MAX_CANDIDATES.
_AI_RD_INSIGHTS_MAX_CANDIDATES = 10
# Same cost-control rationale as _AI_RD_INSIGHTS_MAX_CANDIDATES -- part 19
# of the adjudication request (minimal, bounded change). Applied to
# plant_summary_df's Shortlist/Exploratory rows only (see
# _run_evidence_adjudication below), so Excluded candidates -- who most
# need no further AI spend -- are never adjudicated.
_ADJUDICATION_MAX_CANDIDATES = 15


def _configure_ai_run_budgets() -> None:
    """Part 5/6/13 (OpenAI-usage audit, this session) -- start a fresh
    per-run AI usage tracker and register a per-task call budget for
    every AI task this Stage 5 run can invoke, so a bug in any ONE call
    site cannot by itself generate an unbounded number of OpenAI
    requests. Called once, at the top of the "Run Candidate Discovery"
    button handler below -- never on an unrelated Streamlit rerender.

    Limits mirror the existing loop-level caps already enforced at each
    call site (kept as the single source of truth for those numbers,
    referenced here rather than re-hardcoded) plus the new grounding
    caps added this session (mechanistic_reasoning_service.py,
    hypothesis_generation_service.py) -- each candidate can trigger at
    most one mechanistic-reasoning call, one evidence-synthesis call,
    one hypothesis-generation call, and up to MAX_EDGES_FOR_GROUNDING /
    MAX_HYPOTHESES_FOR_GROUNDING verification calls.
    """
    from mechanistic_reasoning_service import MAX_EDGES_FOR_GROUNDING
    from hypothesis_generation_service import MAX_HYPOTHESES_FOR_GROUNDING

    tracker = start_new_ai_run()
    tracker.set_limit("embedding_query", 1)
    # Stage 5 should not normally standardize new evidence, but keep legacy
    # extractor paths bounded if a connector/custom path does so.
    tracker.set_limit("evidence_extraction", 8)
    tracker.set_limit("semantic_gate_extraction", 8)
    tracker.set_limit("scientific_intent", 2)
    tracker.set_limit("evidence_adjudication", _ADJUDICATION_MAX_CANDIDATES)
    tracker.set_limit("mechanistic_reasoning", _AI_RD_INSIGHTS_MAX_CANDIDATES)
    tracker.set_limit(
        "mechanistic_grounding_verification",
        _AI_RD_INSIGHTS_MAX_CANDIDATES * MAX_EDGES_FOR_GROUNDING,
    )
    tracker.set_limit("evidence_synthesis", _AI_RD_INSIGHTS_MAX_CANDIDATES)
    tracker.set_limit("hypothesis_generation", _AI_RD_INSIGHTS_MAX_CANDIDATES)
    tracker.set_limit(
        "hypothesis_grounding_verification",
        _AI_RD_INSIGHTS_MAX_CANDIDATES * MAX_HYPOTHESES_FOR_GROUNDING,
    )


def _render_ai_rd_insights():
    """Render the additive AI R&D insight layer, if any was computed --
    always clearly separated from the deterministic score/evidence/
    safety/regulatory/commercial sections rendered elsewhere, per the
    architecture's requirement that AI narrative never replaces or is
    mixed into the auditable deterministic output. Renders nothing (not
    even an empty section) when no insights are available -- e.g. AI
    was unavailable for this run, or Stage 5 has not produced a report
    yet -- so this is always safe to call unconditionally.
    """
    insights = st.session_state.get("rd_ai_insights")
    if not insights:
        return

    with st.expander("🧬 AI R&D Insights (mechanistic reasoning, evidence synthesis & hypotheses)", expanded=False):
        st.caption(
            "AI-assisted scientific reasoning over the SAME evidence shown above. "
            "This section never changes the deterministic score, safety gates, or "
            "regulatory status shown elsewhere -- it is a separate, clearly-labeled "
            "analytical layer. Hypotheses are explicitly hypotheses, not established evidence."
        )
        for plant_name, insight in insights.items():
            has_content = (
                insight.get("mechanistic_edges")
                or insight.get("evidence_synthesis")
                or insight.get("hypotheses")
            )
            if not has_content:
                continue
            st.markdown(f"**{plant_name}**")

            edges = insight.get("mechanistic_edges") or []
            if edges:
                st.caption("Mechanistic reasoning (evidence-grounded):")
                for edge in edges:
                    tag = "direct" if edge.get("relationship_type") == "direct" else "inferred"
                    st.write(
                        f"- [{tag}] {edge.get('compound') or '—'} → "
                        f"{edge.get('target_or_pathway') or '—'} → "
                        f"{edge.get('mechanism') or '—'} "
                        f"(evidence: {', '.join(edge.get('supporting_evidence_ids') or [])})"
                    )

            synthesis = insight.get("evidence_synthesis")
            if synthesis:
                st.caption("Cross-study evidence synthesis:")
                st.write(
                    f"- Consistency: **{synthesis.get('overall_consistency')}** — "
                    f"{synthesis.get('summary') or ''}"
                )
                if synthesis.get("heterogeneity_reason") not in (None, "not_applicable"):
                    st.write(f"- Heterogeneity: {synthesis.get('heterogeneity_reason')}")

            hypotheses = insight.get("hypotheses") or []
            if hypotheses:
                st.caption("R&D hypotheses (NOT established evidence):")
                for hyp in hypotheses:
                    st.write(
                        f"- 🧪 *{hyp.get('hypothesis_type')}*: {hyp.get('hypothesis')} "
                        f"— next step: {hyp.get('research_next_step') or '—'}"
                    )
            st.markdown("---")


_AI_STATUS_TASK_LABELS = (
    ("embedding_query", "Semantic embedding"),
    ("evidence_extraction", "Evidence structured extraction"),
    ("semantic_gate_extraction", "Semantic safety/regulatory extraction"),
    ("evidence_adjudication", "Evidence adjudication"),
    ("mechanistic_reasoning", "AI R&D insights — mechanistic reasoning"),
    ("evidence_synthesis", "AI R&D insights — evidence synthesis"),
    ("hypothesis_generation", "AI R&D insights — hypothesis generation"),
)

_AI_STATUS_ICON = {"OK": "✅", "FALLBACK": "⚠️", "UNAVAILABLE": "❌", "NOT_RUN": "⬜"}


def ai_status_lines(summary: dict) -> list[str]:
    """Part 11 (OpenAI-usage audit) -- turn a tracker summary (see
    ai_usage_telemetry.AIRunTracker.summary()/task_status_label()) into
    the compact per-task status lines the architecture spec asks for,
    e.g. "Evidence adjudication: UNAVAILABLE — insufficient_quota".
    Pure function (no Streamlit dependency) so it is directly testable.
    Never raises on a malformed/partial summary -- returns an empty list.
    """
    if not isinstance(summary, dict):
        return []
    tasks = summary.get("tasks") or {}
    breaker_open = bool(summary.get("provider_circuit_open"))
    breaker_reason = summary.get("provider_circuit_category") or summary.get("provider_circuit_reason") or ""
    lines = []
    for task_key, label in _AI_STATUS_TASK_LABELS:
        stats = tasks.get(task_key)
        if stats is None:
            status = "NOT_RUN"
        else:
            successes = stats.get("calls", 0) - stats.get("failures", 0)
            if successes > 0:
                status = "OK" if stats.get("failures", 0) == 0 else "FALLBACK"
            elif stats.get("cached_hits", 0) > 0:
                status = "OK"
            elif stats.get("skipped_breaker", 0) > 0 or breaker_open:
                status = "UNAVAILABLE"
            elif stats.get("skipped_budget", 0) > 0:
                status = "UNAVAILABLE"
            elif stats.get("failures", 0) > 0:
                status = "UNAVAILABLE"
            else:
                status = "NOT_RUN"
        detail = ""
        if status == "UNAVAILABLE" and breaker_open and breaker_reason:
            detail = f" — {breaker_reason}"
        elif status == "FALLBACK":
            errors = stats.get("errors_by_category") or {}
            if errors:
                detail = " — " + ", ".join(sorted(errors))
        lines.append(f"{_AI_STATUS_ICON.get(status, '')} {label}: {status}{detail}")
    # OpenAI availability never determines deterministic-engine health.
    lines.append("✅ Deterministic engine: OK")
    return lines


def _render_ai_status_summary():
    """Part 11 -- shows, in one compact place, which parts of the last
    run used real AI output vs. a deterministic fallback vs. never ran
    at all, so the deterministic result can never be mistaken for one
    that AI validated when AI actually failed (the exact production
    incident this session's audit was triggered by). Renders nothing if
    no run has completed yet."""
    summary = st.session_state.get("rd_ai_status_summary")
    if not summary:
        return
    lines = ai_status_lines(summary)
    if not lines:
        return
    with st.expander("🤖 AI status for this run", expanded=False):
        for line in lines:
            st.write(line)
        totals = (
            f"Logical AI calls: {summary.get('total_logical_calls', summary.get('total_api_calls', 0))} · "
            f"Provider attempts: {summary.get('total_provider_attempts', 0)} · "
            f"Cached (avoided): {summary.get('total_cached_hits', 0)} · "
            f"Skipped (budget): {summary.get('total_skipped_budget', 0)} · "
            f"Skipped (provider unavailable): {summary.get('total_skipped_breaker', 0)}"
        )
        st.caption(totals)

        total_input = int(summary.get("total_input_tokens", 0) or 0)
        total_cached_input = int(summary.get("total_cached_input_tokens", 0) or 0)
        total_output = int(summary.get("total_output_tokens", 0) or 0)
        estimated_cost = summary.get("estimated_cost_usd")
        priced_cost = float(summary.get("priced_cost_usd", 0.0) or 0.0)
        unpriced_models = summary.get("unpriced_models") or []
        st.caption(
            f"Provider-billed tokens — input: {total_input:,} "
            f"(cached input: {total_cached_input:,}) · output: {total_output:,}"
        )
        if estimated_cost is not None:
            st.success(f"Estimated OpenAI API cost for this run: ${float(estimated_cost):.4f}")
        elif unpriced_models:
            st.warning(
                f"Partial priced cost: ${priced_cost:.4f}. Cost for model override(s) "
                f"{', '.join(map(str, unpriced_models))} is not guessed; check the OpenAI pricing page."
            )
        else:
            st.info("Estimated OpenAI API cost for this run: $0.0000 (no provider-billed tokens recorded).")

        task_cost_lines = []
        for task_key, label in _AI_STATUS_TASK_LABELS:
            stats = (summary.get("tasks") or {}).get(task_key) or {}
            task_input = int(stats.get("input_tokens", 0) or 0)
            task_output = int(stats.get("output_tokens", 0) or 0)
            task_cost = stats.get("estimated_cost_usd")
            task_priced = float(stats.get("priced_cost_usd", 0.0) or 0.0)
            if not (task_input or task_output or stats.get("provider_attempts", 0)):
                continue
            cost_text = (
                f"${float(task_cost):.4f}" if task_cost is not None
                else f"at least ${task_priced:.4f} (unpriced model override)"
            )
            task_cost_lines.append(
                f"• {label}: {task_input:,} input / {task_output:,} output tokens — {cost_text}"
            )
        if task_cost_lines:
            st.markdown("**OpenAI usage by task**")
            for line in task_cost_lines:
                st.write(line)
        st.caption(
            "Cost is calculated from provider-reported token usage and the configured model. "
            "It is an estimate and does not include taxes, prepaid-credit adjustments, or other account-level charges."
        )

        st.download_button(
            "Download AI run metadata (JSON)",
            data=json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"),
            file_name="ai_run_metadata.json",
            mime="application/json",
            key="download_ai_run_metadata_json",
        )


def _unique_nonempty(values):
    seen = set()
    out = []
    for value in values:
        text = str(value or "").strip()
        if not text or text.lower() == "nan":
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _join_unique(values, limit=8):
    """Compact, deterministic aggregation for Step 4 plant summaries."""
    items = _unique_nonempty(values)
    if not items:
        return ""
    shown = items[:limit]
    suffix = f" (+{len(items) - limit} more)" if len(items) > limit else ""
    return "; ".join(shown) + suffix


def _build_scientific_plant_summary(inventory_df, regulatory_df=None):
    """Create one truthful summary row per plant without discarding detail.

    The detailed plant-compound table remains available separately and is the
    source for the full CSV export.  This summary only aggregates values that
    are already present in the inventory; it does not infer efficacy.
    """
    if not isinstance(inventory_df, pd.DataFrame) or inventory_df.empty:
        return pd.DataFrame()

    rows = []
    for plant, group in inventory_df.groupby("Known_Plant", sort=False):
        compound_values = _unique_nonempty(group.get("Known_Compound", []))
        target_values = _unique_nonempty(group.get("Known_Target", []))
        mechanism_values = _unique_nonempty(group.get("Known_Mechanism", []))
        reference_values = _unique_nonempty(group.get("Reference_URL", []))
        rows.append({
            "Plant": plant,
            "Compound_Count": len(compound_values),
            "Known_Compounds": _join_unique(compound_values, 6),
            "Target_Count": len(target_values),
            "Known_Targets": _join_unique(target_values, 6),
            "Known_Mechanisms": _join_unique(mechanism_values, 6),
            "Evidence_Levels": _join_unique(group.get("Evidence_Level", []), 5),
            "Plant_Parts": _join_unique(group.get("Known_Plant_Part", []), 5),
            "Extraction_Methods": _join_unique(group.get("Typical_Extraction", []), 5),
            "Dosage_Forms": _join_unique(group.get("Dosage_Form", []), 5),
            "Safety_Notes": _join_unique(group.get("Safety_Note", []), 4),
            "Toxicity_Notes": _join_unique(group.get("Toxicity", []), 4),
            "Reference_Count": len(reference_values),
        })

    summary_df = pd.DataFrame(rows)

    if isinstance(regulatory_df, pd.DataFrame) and not regulatory_df.empty and "Plant" in regulatory_df.columns:
        regulatory_cols = [
            c for c in [
                "Plant", "EMA_HMPC_Status", "WHO_Status", "ESCOP_Status",
                "US_Status", "UK_Status"
            ] if c in regulatory_df.columns
        ]
        if len(regulatory_cols) > 1:
            reg = regulatory_df[regulatory_cols].drop_duplicates(subset=["Plant"])
            summary_df = summary_df.merge(reg, on="Plant", how="left")

    return summary_df


def _get_evidence_df():
    evidence_df = st.session_state.get("evidence_df")
    if isinstance(evidence_df, pd.DataFrame):
        return evidence_df
    return None


def _attach_commercial_market_intelligence(
    result_df, *, evidence_df, indication, dosage_form, market, candidate_plants=None
):
    """Attach one indication-aware commercial snapshot per candidate plant.

    This is a local post-processing layer over the already-loaded structured
    market evidence.  It performs no network calls, does not alter scientific
    evidence, and never treats missing market data as white space.  The legacy
    ``Market_Status``/``Novelty_Status`` columns remain untouched for backward
    compatibility; new ``Commercial_*`` and ``Chemical_Differentiation_Status``
    columns make the two concepts explicit.
    """
    if not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return result_df

    out = result_df.copy()
    if "Chemical_Differentiation_Status" not in out.columns and "Novelty_Status" in out.columns:
        out["Chemical_Differentiation_Status"] = out["Novelty_Status"]

    if "Alternative_Plant" not in out.columns:
        return out

    engine = MarketIntelligenceEngine(evidence_df)

    # IMPORTANT PERFORMANCE RULE: Step 5 passes a bounded pre-shortlist here.
    # Never silently expand that back to every raw candidate plant.
    if candidate_plants is None:
        plants = [
            str(v).strip() for v in out["Alternative_Plant"].dropna().unique().tolist()
            if str(v).strip()
        ]
    else:
        allowed = {str(v).strip().lower() for v in candidate_plants if str(v).strip()}
        plants = [
            str(v).strip() for v in out["Alternative_Plant"].dropna().unique().tolist()
            if str(v).strip() and str(v).strip().lower() in allowed
        ]
    if not plants:
        return out

    # If there is no structured market evidence at all, do not call evaluate()
    # once per candidate just to rediscover the same SEARCH_NOT_PERFORMED state.
    # Populate the honest neutral fields in one vectorized assignment instead.
    if getattr(engine, "_market_rows", pd.DataFrame()).empty:
        indication_status = "UNKNOWN" if str(indication or "").strip() else "NOT_REQUESTED"
        defaults = {
            "Commercial_Market_Status": "Search not performed",
            "Commercial_Search_Status": "SEARCH_NOT_PERFORMED",
            "Commercial_Market_Data_Usable": False,
            "Commercial_Market_Score": None,
            "Commercial_Market_Saturation": "UNKNOWN",
            "Commercial_Status_Overall": "UNKNOWN",
            "Commercial_Status_For_Indication": indication_status,
            "Commercial_Novelty_Status": "Commercial novelty not assessed",
            "Commercial_Positioning": "Market data incomplete — do not classify as new commercial R&D",
            # part C fix -- SEARCH_NOT_PERFORMED means no real search ran,
            # so these are UNKNOWN/nullable, never a numeric 0 (a 0 would
            # falsely read as "search ran, found zero competitors").
            "Overall_Product_Hits": None,
            "Indication_Product_Hits": None,
            "Indication_Brand_Count": None,
            "Indication_Market_Saturation": "UNKNOWN",
            "Indication_Market_Search_Status": "SEARCH_NOT_PERFORMED" if str(indication or "").strip() else "NOT_REQUESTED",
            "Indication_Market_Data_Usable": False,
            "Indication_Market_Score": None,
            "Indication_Matched_Terms": None,
            "Indication_Unclear_Product_Count": None,
            "Indication_Explicit_Nonmatch_Product_Count": None,
        }
        plant_mask = out["Alternative_Plant"].fillna("").astype(str).str.strip().str.lower().isin(
            {p.lower() for p in plants}
        )
        for column, value in defaults.items():
            if column not in out.columns:
                out[column] = None
            if isinstance(value, (list, dict, set)):
                out.loc[plant_mask, column] = [value] * int(plant_mask.sum())
            else:
                out.loc[plant_mask, column] = value
        return out

    rename = {
        "Market_Status": "Commercial_Market_Status",
        "Search_Status": "Commercial_Search_Status",
        "Market_Data_Usable": "Commercial_Market_Data_Usable",
        "Market_Score": "Commercial_Market_Score",
        "Market_Saturation": "Commercial_Market_Saturation",
        "Market_Evidence_Source_IDs": "Commercial_Market_Source_IDs",
        "Market_Retrieval_Timestamp": "Commercial_Market_Retrieval_Timestamp",
    }
    keep = {
        "Commercial_Market_Status", "Commercial_Search_Status",
        "Commercial_Market_Data_Usable", "Commercial_Market_Score",
        "Commercial_Market_Saturation", "Commercial_Market_Source_IDs",
        "Commercial_Market_Retrieval_Timestamp",
        "Commercial_Status_Overall", "Commercial_Status_For_Indication",
        "Commercial_Novelty_Status", "Commercial_Positioning",
        "Overall_Product_Hits", "Indication_Product_Hits",
        "Indication_Brand_Count", "Indication_Market_Saturation",
        "Indication_Market_Search_Status", "Indication_Market_Data_Usable",
        "Indication_Market_Score", "Indication_Matched_Terms",
        "Indication_Unclear_Product_Count",
        "Indication_Explicit_Nonmatch_Product_Count",
    }

    rows = []
    for plant in plants:
        snapshot = engine.evaluate(
            {"Scientific_Name": plant},
            indication=indication,
            dosage_form=dosage_form,
            market=market,
        )
        normalized = {rename.get(k, k): v for k, v in snapshot.items()}
        row = {"Alternative_Plant": plant}
        row.update({k: v for k, v in normalized.items() if k in keep})
        rows.append(row)

    market_df = pd.DataFrame(rows)
    if market_df.empty:
        return out

    # Drop only fields this function owns, allowing safe reuse on a DataFrame
    # that was already enriched during the same Streamlit session.
    owned = [c for c in market_df.columns if c != "Alternative_Plant" and c in out.columns]
    if owned:
        out = out.drop(columns=owned)
    return out.merge(market_df, on="Alternative_Plant", how="left")


def _step5_commercial_enrichment_plants(pre_summary_df):
    """Choose the only plants that need commercial enrichment in Step 5.

    The scientific/eligibility shortlist is built first.  Market opportunity
    can add at most five points, so only non-excluded plants within five points
    of the current final-top-50 boundary can plausibly enter that top 50 because
    of commercial evidence.  The hard cap protects tie-heavy datasets.
    """
    if not isinstance(pre_summary_df, pd.DataFrame) or pre_summary_df.empty:
        return []
    if "Alternative_Plant" not in pre_summary_df.columns:
        return []

    eligible = pre_summary_df.copy()
    if "Scientific_Triage_Status" in eligible.columns:
        eligible = eligible[eligible["Scientific_Triage_Status"] != "Excluded"]
    if eligible.empty:
        return []

    scores = pd.to_numeric(eligible.get("Overall_Score"), errors="coerce").fillna(0.0)
    eligible = eligible.assign(_step5_pre_score=scores).sort_values(
        "_step5_pre_score", ascending=False
    )
    if len(eligible) > _STEP5_FINAL_MAX_CANDIDATES:
        cutoff = float(eligible.iloc[_STEP5_FINAL_MAX_CANDIDATES - 1]["_step5_pre_score"])
        eligible = eligible[
            eligible["_step5_pre_score"] >= cutoff - _STEP5_COMMERCIAL_SCORE_MARGIN
        ]

    eligible = eligible.head(_STEP5_COMMERCIAL_MAX_PLANTS)
    return [
        str(v).strip() for v in eligible["Alternative_Plant"].tolist()
        if str(v).strip()
    ]


def _combine_step5_final_summary(pre_summary_df, enriched_summary_df):
    """Keep the re-scored enriched top candidates plus all excluded audit rows."""
    if not isinstance(enriched_summary_df, pd.DataFrame) or enriched_summary_df.empty:
        if not isinstance(pre_summary_df, pd.DataFrame):
            return pd.DataFrame()
        primary = pre_summary_df
        if "Scientific_Triage_Status" in primary.columns:
            keep = primary[primary["Scientific_Triage_Status"] != "Excluded"].head(
                _STEP5_FINAL_MAX_CANDIDATES
            )
            excluded = primary[primary["Scientific_Triage_Status"] == "Excluded"]
            return pd.concat([keep, excluded], ignore_index=True)
        return primary.head(_STEP5_FINAL_MAX_CANDIDATES).reset_index(drop=True)

    enriched_primary = enriched_summary_df
    if "Scientific_Triage_Status" in enriched_primary.columns:
        enriched_primary = enriched_primary[
            enriched_primary["Scientific_Triage_Status"] != "Excluded"
        ].head(_STEP5_FINAL_MAX_CANDIDATES)

    if isinstance(pre_summary_df, pd.DataFrame) and "Scientific_Triage_Status" in pre_summary_df.columns:
        excluded = pre_summary_df[pre_summary_df["Scientific_Triage_Status"] == "Excluded"]
    else:
        excluded = pd.DataFrame()
    return pd.concat([enriched_primary, excluded], ignore_index=True)


def _finalize_step5_summary(plant_summary_df: pd.DataFrame) -> pd.DataFrame:
    """Re-sort and cap the single authoritative Step 5 summary.

    Stage 5 candidate-funnel performance fix: replaces the old two-pass
    ``_combine_step5_final_summary(pre_summary_df, enriched_summary_df)``
    merge, which existed only because commercial enrichment used to require
    a second, separately-sorted ``build_plant_candidate_shortlist()`` call.
    With commercial enrichment now folded in via
    ``rescore_commercial_component()`` (in place, on the one summary that
    already exists), the enriched Novelty & Market component can change a
    plant's Overall_Score and therefore its rank -- so this re-sorts using
    the exact same key build_plant_candidate_shortlist() itself sorts by,
    then applies the same "keep all Excluded rows for audit, cap only the
    non-excluded primary table" rule as before.
    """
    if not isinstance(plant_summary_df, pd.DataFrame) or plant_summary_df.empty:
        return plant_summary_df
    if "Scientific_Triage_Status" not in plant_summary_df.columns:
        return plant_summary_df.head(_STEP5_FINAL_MAX_CANDIDATES).reset_index(drop=True)

    status_order = pd.Categorical(
        plant_summary_df["Scientific_Triage_Status"],
        categories=["Shortlist", "Exploratory", "Excluded"],
        ordered=True,
    )
    sort_cols = ["Overall_Score", "Traceable_Source_Count", "Distinctive_Compound_Count"]
    sort_cols = [c for c in sort_cols if c in plant_summary_df.columns]
    sorted_df = plant_summary_df.assign(_status_order=status_order).sort_values(
        ["_status_order", *sort_cols],
        ascending=[True] + [False] * len(sort_cols),
    ).drop(columns=["_status_order"]).reset_index(drop=True)

    keep = sorted_df[sorted_df["Scientific_Triage_Status"] != "Excluded"].head(
        _STEP5_FINAL_MAX_CANDIDATES
    )
    excluded = sorted_df[sorted_df["Scientific_Triage_Status"] == "Excluded"]
    return pd.concat([keep, excluded], ignore_index=True)



def _norm_run_context(value):
    return " ".join(str(value or "").strip().lower().split())


def _get_step2_retrieval_coverage(*, indication, market):
    """Return the run-scoped per-plant coverage map for these exact inputs.

    An explicit empty mapping means coverage is NOT ASSESSABLE for the current
    decision run.  Historical Supabase rows are never used to manufacture a
    completeness claim.
    """
    research_output = st.session_state.get("research_output")
    if not isinstance(research_output, dict):
        return {}
    if _norm_run_context(research_output.get("retrieval_coverage_market")) != _norm_run_context(market):
        return {}
    if _norm_run_context(research_output.get("retrieval_coverage_indication")) != _norm_run_context(indication):
        return {}
    coverage = research_output.get("retrieval_coverage_by_plant")
    return coverage if isinstance(coverage, dict) else {}


def _get_step2_candidate_shortlist():
    """Return the final candidate shortlist produced by Step 2.

    Step 3 must analyse the same candidates that were actually sent through
    the Step 2 evidence-collection loop.  Older code rebuilt a fresh, broad
    indication inventory here, which could replace an 8-plant shortlist with
    dozens of unrelated catalogue plants.

    The research output is the authoritative source.  The evidence dataframe
    is only a compatibility fallback for sessions created by older versions.
    """
    research_output = st.session_state.get("research_output")
    if isinstance(research_output, dict):
        candidates = _unique_nonempty(research_output.get("candidate_plants", []))
        if candidates:
            return candidates, "Step 2 final shortlist"

        diagnostics = research_output.get("candidate_discovery_diagnostics") or {}
        if isinstance(diagnostics, dict):
            candidates = _unique_nonempty(diagnostics.get("final_candidate_plants", []))
            if candidates:
                return candidates, "Step 2 diagnostic shortlist"

    evidence_df = _get_evidence_df()
    if isinstance(evidence_df, pd.DataFrame) and not evidence_df.empty:
        for column in ("plant", "Plant", "scientific_name", "Scientific_Name"):
            if column in evidence_df.columns:
                candidates = _unique_nonempty(evidence_df[column].tolist())
                if candidates:
                    return candidates, "Step 2 evidence records"

    return [], "unavailable"


def _get_step2_novel_discovered_candidates(*, indication, market):
    """Return the validated novel (not-yet-in-Supabase) candidates Stage 2
    discovered for THESE exact indication/market inputs, in the shape
    BotanicalRDCandidateEngine.__init__'s ``discovered_candidates``
    parameter expects.

    Scoped to the same indication/market the research run was for -- a
    novel candidate discovered while researching "sleep" must not silently
    leak into an unrelated "diabetes" Step 5 run. Returns [] (never raises)
    when no research run has been made for these inputs yet, mirroring
    _get_step2_retrieval_coverage()'s own fail-safe pattern.
    """
    research_output = st.session_state.get("research_output")
    if not isinstance(research_output, dict):
        return []
    if _norm_run_context(research_output.get("retrieval_coverage_market")) != _norm_run_context(market):
        return []
    if _norm_run_context(research_output.get("retrieval_coverage_indication")) != _norm_run_context(indication):
        return []
    candidates = research_output.get("novel_discovered_candidates")
    return candidates if isinstance(candidates, list) else []


def _collect_evidence_record_ids(result_df):
    """Task 13.2C — the union of every candidate row's own
    Applicability_Summary.evidence_record_ids (Task 10.2), deduplicated,
    order-preserving. Read-only over `result_df` — never touches the
    engine, evidence_df, or the database itself; this only decides
    WHICH ids to later ask standard_evidence_builder.
    get_scientific_evidence_by_ids() to resolve.

    A row with no "Applicability_Summary" column at all, a None value,
    or any non-dict value simply contributes nothing — never an error,
    matching the same degrade-safely discipline
    build_applicability_traceability() already established for reading
    this same field in pharma_report_generator.py.
    """
    ids = []
    seen = set()
    if not isinstance(result_df, pd.DataFrame) or "Applicability_Summary" not in result_df.columns:
        return ids
    for summary in result_df["Applicability_Summary"]:
        if not isinstance(summary, dict):
            continue
        for record_id in summary.get("evidence_record_ids") or []:
            if record_id is None or record_id in seen:
                continue
            seen.add(record_id)
            ids.append(record_id)
    return ids


# ---------------------------------------------------------------------- #
# Cache the raw Supabase table fetches. plant_compounds went from ~850
# rows to 50,000+ after the Dr. Duke's import — refetching that whole
# table over the network every single time a button is clicked (and this
# file previously built TWO separate engines per Step 3 click, so TWO
# full refetches) is what made Step 3 hang/stall. Caching it means the
# network fetch happens once per session (or until ttl expires), and every
# engine built afterwards reuses the same in-memory DataFrame — engine
# construction itself (grouping ~50k rows by scientific_name) is a fast,
# local pandas operation once the network fetch is out of the picture.
# ---------------------------------------------------------------------- #

@st.cache_data(ttl=3600, show_spinner=False)
def _cached_plant_compounds_df():
    """Returns (df, succeeded). succeeded=False means the load itself
    failed (network/auth/schema error) — NOT that the query legitimately
    returned zero rows. Previously this silently returned an empty
    DataFrame on ANY failure, indistinguishable from "no data exists" —
    flagged in external review as a fail-silent risk (no way to tell a
    real outage from real absence of data) feeding directly into a
    second risk: nothing downstream knew to be more cautious about a
    recommendation built on data that may not have actually loaded.
    See BotanicalRDCandidateEngine's data_source_reliable parameter and
    structured_rationale.go_investigate_hold_no_go's fallback_occurred
    parameter for what this now feeds into."""
    from supabase_data import load_plant_compounds_df
    try:
        return load_plant_compounds_df(), True
    except Exception:
        return pd.DataFrame(), False


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_compound_profiles_df():
    """See _cached_plant_compounds_df's docstring — same (df, succeeded) contract."""
    from supabase_data import load_compound_profiles_df
    try:
        return load_compound_profiles_df(), True
    except Exception:
        return pd.DataFrame(), False


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_scientific_evidence_df():
    """See _cached_plant_compounds_df's docstring — same (df, succeeded) contract."""
    from supabase_data import load_scientific_evidence_df
    try:
        return load_scientific_evidence_df(), True
    except Exception:
        return pd.DataFrame(), False


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_evidence_records_df():
    """Full paginated evidence_records read, cached for one hour.

    The engine historically loaded this structured table independently of the
    canonical ``evidence_df`` supplied by app.py. We preserve that scientific
    data path, but stop downloading the same 20k+ rows on every engine build.
    """
    from supabase_data import load_evidence_records_df
    try:
        return load_evidence_records_df(), True
    except Exception:
        return pd.DataFrame(), False


_CANDIDATE_DISCOVERY_PROCESS_LOCK = threading.Lock()


def _candidate_discovery_process_lock():
    """One process-wide lock preventing Streamlit cache stampedes.

    Streamlit can execute multiple script threads when a user double-clicks,
    refreshes during a long run, or opens the same app in several tabs. Before
    this guard, those threads could all miss the same cold cache at once and
    each download/build the 20k+ row evidence universe independently.
    """
    return _CANDIDATE_DISCOVERY_PROCESS_LOCK


# Building the engine itself is the expensive part now — with 50,000+
# plant_compounds rows, __init__ groups every row by scientific_name and
# builds a deduplicated dict per plant (~2,200 plants). That grouping work
# was happening from scratch on every single button click. Caching the
# constructed ENGINE (not just the raw table) means that grouping happens
# once per `use_live_search` value and is then reused.
#
# evidence_df (from live Step 2 searches, stored in session state) is kept
# out of the *hashed* argument (it's still underscore-prefixed, since
# Streamlit can't hash a DataFrame directly) but its CONTENT now feeds the
# cache key via `evidence_fingerprint` below. Previously evidence_df was
# excluded from the cache key entirely, so a fresh Step 2 run could sit
# unused in a stale cached engine for up to `ttl` seconds. Fingerprinting
# is deliberately cheap (row count + a vectorized content hash) rather
# than hashing the whole DataFrame structurally, since this data is
# usually small (a handful of live-search results per session).
def _evidence_fingerprint(evidence_df):
    if evidence_df is None or evidence_df.empty:
        return ("empty", 0)
    try:
        content_hash = int(pd.util.hash_pandas_object(evidence_df, index=True).sum())
    except Exception:
        # JSONB/list/dict cells are common in evidence_records and are not
        # always hashable by pandas directly. Falling back to row-count only
        # can keep a stale engine when a record is edited in place without a
        # row-count change, so use a deterministic string view before giving
        # up. This is cache invalidation only; the DataFrame itself is untouched.
        try:
            stable_view = evidence_df.astype(str)
            content_hash = int(pd.util.hash_pandas_object(stable_view, index=True).sum())
        except Exception:
            content_hash = hash((tuple(map(str, evidence_df.columns)), len(evidence_df)))
    return (len(evidence_df), content_hash)


ENGINE_CACHE_VERSION = "step5_runtime_egress_guard_v1"


def _discovered_candidates_fingerprint(discovered_candidates):
    """Hashable fingerprint for st.cache_resource's cache key. The actual
    list of dicts is passed separately as an underscore-prefixed argument
    (excluded from Streamlit's hashing, same convention already used for
    ``_evidence_df`` below) since a list of dicts is not itself hashable.
    """
    if not discovered_candidates:
        return ("none", 0)
    names = tuple(sorted(
        str(item.get("Scientific_Name") or "") for item in discovered_candidates
    ))
    return (names, len(names))


@st.cache_resource(ttl=3600, show_spinner=False)
def _cached_engine(
    use_live_search: bool,
    evidence_fingerprint,
    engine_cache_version: str,
    discovered_candidates_fingerprint=("none", 0),
    _evidence_df=None,
    _discovered_candidates=None,
):
    plant_compounds_df, plant_compounds_ok = _cached_plant_compounds_df()
    compound_profiles_df, compound_profiles_ok = _cached_compound_profiles_df()
    scientific_evidence_df, scientific_evidence_ok = _cached_scientific_evidence_df()
    evidence_records_df, evidence_records_ok = _cached_evidence_records_df()

    # Preserve the pre-fix scientific data path exactly: evidence_df remains the
    # canonical deduplicated read supplied by app.py, while evidence_records_df
    # remains the full structured table used by indication-centric discovery.
    # The optimization is transport-only: the latter is now fetched at most once
    # per cache TTL instead of once per engine construction / concurrent click.
    return BotanicalRDCandidateEngine(
        evidence_df=_evidence_df,
        use_live_search=use_live_search,
        plant_compounds_df=plant_compounds_df,
        compound_profiles_df=compound_profiles_df,
        scientific_evidence_df=scientific_evidence_df,
        evidence_records_df=evidence_records_df,
        # Review #17: if any core Supabase load actually FAILED (not
        # just legitimately returned few/no rows), the engine caps
        # every recommendation at "Investigate" — a Go call must never
        # be issued on data that may not have actually loaded.
        data_source_reliable=(
            plant_compounds_ok and compound_profiles_ok
            and scientific_evidence_ok and evidence_records_ok
        ),
        discovered_candidates=_discovered_candidates,
    )


def _build_engine(evidence_df, use_live_search, discovered_candidates=None):
    fingerprint = _evidence_fingerprint(evidence_df)
    return _cached_engine(
        use_live_search,
        fingerprint,
        ENGINE_CACHE_VERSION,
        discovered_candidates_fingerprint=_discovered_candidates_fingerprint(discovered_candidates),
        _evidence_df=evidence_df,
        _discovered_candidates=discovered_candidates,
    )


def _candidate_discovery_run_key(
    *, indication, dosage_form, market, reference_plant, reference_compound,
    discovery_mode, use_live_search, evidence_df,
):
    """Stable per-session key for exact-input result reuse.

    Re-clicking Run with unchanged inputs should display the already completed
    result, not execute another multi-minute scientific pipeline.
    """
    return (
        str(indication or "").strip().casefold(),
        str(dosage_form or "").strip().casefold(),
        str(market or "").strip().casefold(),
        str(reference_plant or "").strip().casefold(),
        str(reference_compound or "").strip().casefold(),
        str(discovery_mode or "").strip().casefold(),
        bool(use_live_search),
        _evidence_fingerprint(evidence_df),
        ENGINE_CACHE_VERSION,
    )


def _offline_engine():
    return _build_engine(_get_evidence_df(), use_live_search=False)


# Display/loop safety cap. With Dr. Duke's data, "known plants" for a
# broad indication can run into the hundreds or low thousands — rendering
# that as one long joined string, or running market_landscape_df across
# all of them, is what makes the page feel unresponsive. Showing/scoring
# the first N is enough to be useful; nothing below silently drops data,
# it only limits what's displayed/probed by these two exploratory steps.
_MAX_MARKET_CHECK_PLANTS = 30


def _detect_discovery_mode(result_df) -> str:
    """Single source of truth for "which discovery mode produced this
    result_df" — used by both the success-branch and the fallback-rebuild
    branch below so decision_metadata.build_decision_metadata() and the
    UI's own indication-mode banner never disagree about which mode ran."""
    if not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return "unknown"
    is_indication_mode = (
        "Scoring_Config_Version" in result_df.columns
        and result_df["Scoring_Config_Version"].astype(str).str.startswith("2.").any()
    ) or (
        "Reference_Plant" in result_df.columns
        and result_df["Reference_Plant"].astype(str).eq("Indication-centric discovery").all()
    )
    return "indication" if is_indication_mode else "compound_substitution"




def _prepare_plant_triage_display(df):
    """Return a concise user-facing plant-level triage table.

    Phase 3 made ``Overall_Score`` / ``R&D_Opportunity_Score`` the
    authoritative plant-level score. ``Scientific_Triage_Score`` is retained
    in the downloadable audit CSV as a legacy diagnostic, but must not be
    presented as the primary score in the Streamlit table.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()

    view = df.copy()
    score_col = None
    for candidate in ("R&D_Opportunity_Score", "Overall_Score"):
        if candidate in view.columns:
            score_col = candidate
            break

    columns = ["Alternative_Plant"]
    if score_col:
        columns.append(score_col)
    columns.extend([
        "Evidence_Confidence",
        "Scientific_Triage_Status",
        "Go_Investigate_Hold_NoGo",
        "Commercial_Positioning",
        "Commercial_Novelty_Status",
        "Overall_Product_Hits",
        "Indication_Product_Hits",
        "Chemical_Differentiation_Status",
        "Indication_Relevance",
        "Evidence_Quality_Score",
        "Why_Selected_or_Rejected",
    ])
    columns = [column for column in columns if column in view.columns]
    view = view[columns].copy()

    if score_col:
        view[score_col] = pd.to_numeric(view[score_col], errors="coerce")
        view = view.sort_values(score_col, ascending=False, na_position="last")

    rename_map = {
        "Alternative_Plant": "Plant",
        "R&D_Opportunity_Score": "R&D Opportunity Score",
        "Overall_Score": "R&D Opportunity Score",
        "Evidence_Confidence": "Evidence Strength Index",
        "Scientific_Triage_Status": "Triage Status",
        "Go_Investigate_Hold_NoGo": "Decision",
        "Commercial_Positioning": "Commercial Positioning",
        "Commercial_Novelty_Status": "Commercial Novelty",
        "Overall_Product_Hits": "Overall Product Hits",
        "Indication_Product_Hits": "Indication Product Hits",
        "Chemical_Differentiation_Status": "Chemical Differentiation",
        "Indication_Relevance": "Indication Relevance",
        "Evidence_Quality_Score": "Evidence Quality Score",
        "Why_Selected_or_Rejected": "Why selected / rejected",
    }
    return view.rename(columns=rename_map).reset_index(drop=True)


def _eligible_mask(df: pd.DataFrame) -> pd.Series:
    """Phase 4 — Eligibility Gate. True only for rows explicitly marked
    ELIGIBLE / ELIGIBLE_WITH_RESTRICTIONS (Eligible_For_Normal_Ranking
    == True) — used as a final safety-net filter in BOTH the modern
    (report_ready_df) and legacy (result_df) branches of
    _recommendation_block(), so neither branch's own fallback logic can
    surface a hard no-go/incomplete/expert-review row, no matter how it
    got there. A row with neither column at all (pre-Phase-4 data) is
    treated as NOT eligible for normal ranking — see the Phase 4 design
    review: "رکورد قدیمی بدون eligibility data باید INCOMPLETE تلقی
    شود، نه ELIGIBLE."
    """
    if "Eligible_For_Normal_Ranking" in df.columns:
        return df["Eligible_For_Normal_Ranking"].fillna(False).astype(bool)
    if "Eligibility_Status" in df.columns:
        return df["Eligibility_Status"].astype(str).isin(
            ("eligible", "eligible_with_restrictions")
        )
    return pd.Series(False, index=df.index)


def _no_go_mask(df: pd.DataFrame) -> pd.Series:
    if "Eligibility_Status" in df.columns:
        return df["Eligibility_Status"].astype(str).isin(("no_go_safety", "no_go_regulatory"))
    return pd.Series(False, index=df.index)


def _recommendation_block(result_df, report_ready_df=None):
    # Phase 3 (IMPLEMENTATION_PLAN.md) — prefer the authoritative,
    # one-row-per-plant frame (merge_authoritative_scores()'s output) so
    # this block's picks can never disagree with the Step 5 shortlist or
    # the downloaded report about which plant is recommended. Falls back
    # to the pre-Phase-3 raw-row behavior only if no report-ready frame is
    # available yet (e.g. a session that ran Step 5 before this change).
    if isinstance(report_ready_df, pd.DataFrame) and not report_ready_df.empty:
        df = report_ready_df.copy()
        call_col = "Go_Investigate_Hold_NoGo" if "Go_Investigate_Hold_NoGo" in df.columns else None

        best_rows = df  # already one row per plant, already sorted by Overall_Score

        # Post-Phase-3-review fix (Issue 1): classify by normalized PREFIX,
        # not exact match. Exploratory candidates carry the value
        # "Investigate — verify before proceeding" (see
        # candidate_shortlisting._derive_go_call), which starts with
        # "Investigate" but is not equal to the bare string "Investigate" —
        # an exact-match .isin(["Go", "Investigate"]) silently dropped
        # every exploratory candidate from both sections entirely.
        recommended = best_rows
        weak = best_rows.iloc[0:0]
        if call_col:
            call_series = best_rows[call_col].fillna("").astype(str).str.strip()
            recommended = best_rows[
                call_series.str.startswith("Go") | call_series.str.startswith("Investigate")
            ]
            weak = best_rows[
                call_series.str.startswith("Hold") | call_series.str.startswith("No-Go")
            ]
            if recommended.empty:
                # Never fall back into rows already classified as weak —
                # an all-Hold/No-Go result set must not be relabeled
                # "recommended" just because nothing matched Go/Investigate.
                recommended = best_rows.drop(weak.index).head(5)

        # Phase 4 — Eligibility Gate safety net. Go_Investigate_Hold_
        # NoGo is already derived from Decision_Class_AH, which is now
        # itself eligibility-driven (see decision_class_ah.py), so this
        # should already be a no-op for correctly-labelled rows — kept
        # as an explicit, structural final filter (not relying solely
        # on string-prefix matching of call_col) so "recommended" can
        # never contain a row Eligible_For_Normal_Ranking says is not.
        recommended = recommended[_eligible_mask(recommended)]

        # Phase 7 — ranking score/order must never overrule the validated
        # scientific final-decision layer. Crucially, an unresolved candidate
        # is NOT the same thing as a scientifically weak/rejected candidate.
        # Keep three semantic states distinct in the modern Stage-6 view:
        #   1) GO / GO WITH CAUTION -> actionable validation priority,
        #   2) EXPERT REVIEW REQUIRED -> unresolved / needs human adjudication,
        #   3) INSUFFICIENT EVIDENCE / NO-GO -> weak or not recommended.
        # This is presentation-only: no score, gate, rank, or final decision is
        # modified here.
        expert_review = best_rows.iloc[0:0]
        if "Final_Decision_Status" in best_rows.columns:
            final_status = best_rows["Final_Decision_Status"].fillna("").astype(str).str.strip()
            has_final_status = final_status.ne("")
            actionable_status = final_status.isin(("GO", "GO WITH CAUTION"))
            expert_review_status = final_status.eq("EXPERT REVIEW REQUIRED")
            weak_final_status = final_status.isin((
                "INSUFFICIENT EVIDENCE",
                "NO GO SAFETY",
                "NO GO REGULATORY",
                "NO-GO SAFETY",
                "NO-GO REGULATORY",
            ))
            # Any future explicit final status that is neither actionable nor
            # expert-review is conservatively treated as a non-recommendation.
            other_non_actionable = (
                has_final_status
                & ~actionable_status
                & ~expert_review_status
                & ~weak_final_status
            )

            if expert_review_status.any():
                expert_review = best_rows.loc[expert_review_status].copy()
                # Remove unresolved rows from both green and red buckets. They
                # receive their own amber section below, so an AI/data-coherence
                # uncertainty can never be miscommunicated as "not recommended".
                recommended = recommended.loc[
                    ~recommended.index.isin(expert_review.index)
                ]
                weak = weak.loc[~weak.index.isin(expert_review.index)]

            authoritative_weak = weak_final_status | other_non_actionable
            if authoritative_weak.any():
                _scientific_weak = best_rows.loc[authoritative_weak]
                recommended = recommended.loc[
                    ~recommended.index.isin(_scientific_weak.index)
                ]
                weak = pd.concat([weak, _scientific_weak]).loc[
                    lambda x: ~x.index.duplicated(keep="first")
                ]

        # Stage 6 is a presentation/decision boundary, not another scorer.
        # Keep the authoritative Step 5 ordering, but do not label a
        # mechanism-only / low-relevance hypothesis as "Recommended".
        # The underlying rows remain visible in a separate exploratory
        # bucket; nothing is deleted and no upstream score is rewritten.
        if "Relevance_Gate_Result" in best_rows.columns:
            _gate = best_rows["Relevance_Gate_Result"].fillna("").astype(str).str.strip()
            _direct_idx = best_rows.index[_gate.eq("passed_direct")]
            _exploratory_idx = best_rows.index[_gate.eq("passed_indirect_exploratory_only")]

            # Direct relevance is mandatory for the primary recommendation.
            # This closes the previous leak where every "Investigate" row,
            # including low-relevance mechanistic hypotheses, appeared in
            # the green Recommended table.
            non_direct_recommended = recommended.index.difference(_direct_idx)
            recommended = recommended.loc[recommended.index.intersection(_direct_idx)]

            exploratory = best_rows.loc[best_rows.index.intersection(_exploratory_idx)]
            # Preserve any other non-direct Investigate rows as exploratory
            # rather than silently dropping them.
            if len(non_direct_recommended):
                exploratory = pd.concat([
                    exploratory, best_rows.loc[best_rows.index.intersection(non_direct_recommended)]
                ]).loc[lambda x: ~x.index.duplicated(keep="first")]
            # If an authoritative final decision says EXPERT REVIEW REQUIRED,
            # the amber review bucket is the single presentation authority.
            # Do not duplicate the same unresolved candidate in exploratory.
            if not expert_review.empty:
                exploratory = exploratory.loc[
                    ~exploratory.index.isin(expert_review.index)
                ]
        else:
            # Backward compatibility for old session-state frames created
            # before Relevance_Gate_Result was passed through the merge.
            exploratory = best_rows.iloc[0:0]

        display_cols = [
            col for col in [
                "Alternative_Plant",
                "Supported_Targets_or_Mechanisms",
                "Indication_Relevance",
                "Indication_Evidence_Mode",
                "Direct_Indication_Evidence_Count",
                "Preparation_Applicability_Class",
                "Relevance_Gate_Result",
                "R&D_Opportunity_Score",
                "Final_Decision_Status",
                "Decision_Class_AH",
                "Go_Investigate_Hold_NoGo",
                "Evidence_Adjudication_Status",
                "Evidence_Adjudication_Evidence_Count",
                "Evidence_Coherence_Status",
                "Evidence_Adjudication_Fallback_Reason",
                "Indication_Evidence_Direction",
                "Human_Evidence_Strength",
                "Evidence_Conflict_Level",
                "Scientific_Evidence_Confidence",
                "AI_Insight_Status",
                "AI_Evidence_Items_Reviewed",
                "AI_Evidence_Consistency",
                "AI_Evidence_Synthesis",
                "AI_Top_Hypothesis",
                "AI_Research_Next_Step",
                "Safety_Flags",
                "Commercial_Positioning",
                "Commercial_Novelty_Status",
                "Overall_Product_Hits",
                "Indication_Product_Hits",
                "Commercial_Market_Status",
                "Commercial_Status_For_Indication",
                "Indication_Market_Search_Status",
                "Chemical_Differentiation_Status",
                "Final_Rationale",
                "Rationale",
            ] if col in recommended.columns
        ]
        weak_display_cols = [
            col for col in display_cols + ["Why_Selected_or_Rejected"]
            if col in weak.columns
        ]

        st.markdown("### ✅ Priority candidates / worth validating")
        if "Evidence_Adjudication_Status" in recommended.columns:
            _displayed = recommended.head(10)
            _adj = _displayed["Evidence_Adjudication_Status"].fillna("").astype(str)
            _ai_ok = _adj.eq("AI_ADJUDICATION_OK")
            if _ai_ok.any():
                st.success(
                    f"AI scientific adjudication completed for {int(_ai_ok.sum())} of "
                    f"{len(_displayed)} displayed candidate(s). Structured AI fields below can "
                    "downgrade/cap a decision, but cannot override hard safety/regulatory gates."
                )
            else:
                st.warning(
                    "AI scientific adjudication was unavailable or fell back for this run. "
                    "The recommendation is therefore deterministic for these displayed candidates; "
                    "the table shows the fallback status explicitly."
                )
        st.caption(
            "\"Recommended\" means worth a human researcher's time to validate. "
            "Scientific evidence, chemical/source differentiation, and commercial "
            "novelty are separate signals. A candidate is never labelled commercial "
            "white-space merely because market search was missing or because it has "
            "an alternative chemical source. `Final_Decision_Status` remains the "
            "scientific decision authority."
        )
        # Preserve the historical Stage-6 contract: both direct recommendations
        # and exploratory Investigate candidates appear in the first
        # "worth validating" table.  The scientific distinction is explicit in
        # Stage_6_Section instead of being encoded by silently moving exploratory
        # rows to a different dataframe (which breaks downstream/test consumers).
        _recommended_display = recommended.copy()
        _recommended_display["Stage_6_Section"] = (
            "Priority validation — direct indication evidence"
        )
        if not exploratory.empty:
            _exploratory_display = exploratory.copy()
            _exploratory_display["Stage_6_Section"] = (
                "Exploratory — indirect/mechanistic evidence; direct validation needed"
            )
            _recommended_display = pd.concat(
                [_recommended_display, _exploratory_display], axis=0
            )
            _recommended_display = _recommended_display.loc[
                ~_recommended_display.index.duplicated(keep="first")
            ]

        _primary_cols = [
            c for c in ["Stage_6_Section"] + display_cols
            if c in _recommended_display.columns
        ]
        st.dataframe(_recommended_display[_primary_cols].head(10), width="stretch")

        # Unresolved candidates get their own amber section.  They are not
        # labelled weak/rejected because EXPERT REVIEW REQUIRED means the
        # evidence or pipeline state is unresolved, not that the scientific
        # evidence is necessarily poor.  Direct candidates with coherence,
        # preparation, safety-review, or AI-adjudication uncertainty therefore
        # remain visible without a false negative label.
        if not expert_review.empty:
            _review_display = expert_review.copy()
            _review_display["Stage_6_Section"] = (
                "Requires expert review — unresolved scientific decision"
            )
            st.markdown("### 🟠 Requires expert review / unresolved")
            st.caption(
                "These candidates are not classified as weak or rejected. "
                "They require human review because the final scientific decision "
                "is unresolved (for example evidence-coherence, preparation, "
                "safety/regulatory review, or incomplete adjudication)."
            )
            _review_cols = [
                c for c in ["Stage_6_Section"] + display_cols +
                ["Why_Selected_or_Rejected", "Triage_Gate_Reasons"]
                if c in _review_display.columns
            ]
            st.dataframe(_review_display[_review_cols].head(20), width="stretch")

        # The red section is reserved for genuinely non-actionable scientific
        # outcomes (insufficient evidence / Hold / hard No-Go / excluded), not
        # for unresolved expert-review cases.
        if not weak.empty:
            _weak_display = weak.copy()
            _weak_display["Stage_6_Section"] = "Weak / not recommended"
            st.markdown("### 🔴 Weak / not recommended")
            st.caption(
                "Insufficient-evidence, Hold, No-Go and excluded candidates remain "
                "visible with the authoritative rejection reason."
            )
            _weak_cols = [
                c for c in ["Stage_6_Section"] + display_cols +
                ["Why_Selected_or_Rejected", "Triage_Gate_Reasons"]
                if c in _weak_display.columns
            ]
            st.dataframe(_weak_display[_weak_cols].head(20), width="stretch")
        return

    if result_df is None or not isinstance(result_df, pd.DataFrame) or result_df.empty:
        st.warning("Run Step 5 first, then generate the final recommendation.")
        return

    df = result_df.copy()

    if "R&D_Opportunity_Score" in df.columns:
        df["R&D_Opportunity_Score"] = pd.to_numeric(
            df["R&D_Opportunity_Score"], errors="coerce"
        ).fillna(0)
        df = df.sort_values("R&D_Opportunity_Score", ascending=False)

    plant_col = "Alternative_Plant" if "Alternative_Plant" in df.columns else df.columns[0]
    decision_col = "Decision_Class" if "Decision_Class" in df.columns else None

    best_rows = df.drop_duplicates(subset=[plant_col], keep="first")

    recommended = best_rows
    if decision_col:
        recommended = best_rows[
            best_rows[decision_col].astype(str).str.contains(
                "strong|promising|recommend", case=False, na=False
            )
        ]
        if recommended.empty:
            # Phase 4 fix: the pre-Phase-4 version of this fallback was
            # `best_rows.head(5)` — unfiltered by anything — which the
            # audit proved could surface a hard no-go candidate (a
            # regulatory-prohibited or safety-concern row) at the top of
            # "Recommended" whenever nothing matched the positive regex
            # above. Excluding no-go rows before taking the top 5 closes
            # that gap without requiring every candidate set to have a
            # "strong/promising" row.
            recommended = best_rows[~_no_go_mask(best_rows)].head(5)

    # Phase 4 — Eligibility Gate safety net (legacy branch). Same
    # reasoning as the modern branch above: an explicit, structural
    # final filter so eligibility is authoritative even if decision_col
    # text was somehow inconsistent with it.
    recommended = recommended[_eligible_mask(recommended)]

    display_cols = [
        col for col in [
            "Alternative_Plant",
            "Shared_or_Similar_Compound",
            "Target_or_Mechanism",
            "R&D_Opportunity_Score",
            "Decision_Class",
            "Safety_Flags",
            "Commercial_Positioning",
            "Commercial_Novelty_Status",
            "Overall_Product_Hits",
            "Indication_Product_Hits",
            "Commercial_Market_Status",
            "Commercial_Status_For_Indication",
            "Indication_Market_Search_Status",
            "Chemical_Differentiation_Status",
            "Rationale",
        ] if col in recommended.columns
    ]

    st.markdown("### ✅ Priority candidates / worth validating")
    st.caption(
        "\"Recommended\" means worth validation, not proof of efficacy or novelty. "
        "Chemical/source differentiation is shown separately from commercial status; "
        "missing commercial evidence does not count as market white-space."
    )
    st.dataframe(recommended[display_cols].head(10), width="stretch")

    if decision_col:
        weak = best_rows[
            best_rows[decision_col].astype(str).str.contains(
                "weak|reject|not", case=False, na=False
            )
        ]
        if not weak.empty:
            st.markdown("### 🔴 Weak / not recommended")
            st.dataframe(weak[display_cols].head(10), width="stretch")


def render_rd_candidates_step(inputs):
    indication = inputs.get("indication", "")
    dosage_form = inputs.get("dosage_form", "")
    market = inputs.get("market", "")
    transferability_target_context = build_transferability_target_context(
        indication=indication,
        dosage_form=dosage_form,
        standardized_project=inputs.get("standardized_project"),
    )

    st.markdown("---")
    st.markdown("## Step 3 — Market & Competitive Landscape")

    st.caption(
        "Check what already exists in the market: existing botanical products, "
        "known plants, regulatory status, patent readiness, retail/brand search readiness, "
        "and market saturation signals."
    )

    live_market = st.checkbox(
        "Include live patent / retail search if API keys are configured",
        value=False,
        help="Keep this off unless external API keys are configured.",
        key="rd_market_live_checkbox",
    )

    if st.button("Run Market Analysis", type="primary", key="run_step1_market"):
        try:
            shortlist, shortlist_source = _get_step2_candidate_shortlist()

            # Keep the broad indication inventory only as secondary context.
            # It is useful for Step 4/5 and for showing the size of the wider
            # landscape, but it must not replace the Step 2 shortlist used for
            # the main market analysis.
            with st.spinner("Loading broader indication inventory..."):
                offline_engine = _offline_engine()
                inventory_df = offline_engine.known_inventory_df(indication)

            broader_plants = (
                _unique_nonempty(inventory_df.get("Known_Plant", []))
                if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty
                else []
            )

            st.session_state["rd_inventory_df_internal"] = inventory_df
            st.session_state["rd_broader_market_context_plants"] = broader_plants
            st.session_state["rd_broader_market_context_total"] = len(broader_plants)

            if shortlist:
                market_plants = shortlist[:_MAX_MARKET_CHECK_PLANTS]
                source_label = shortlist_source
            else:
                # Compatibility fallback for users who enter Step 3 without
                # running Step 2 in the current session.  It is explicit in the
                # UI so a broad inventory can never silently masquerade as the
                # Step 2 shortlist.
                market_plants = broader_plants[:_MAX_MARKET_CHECK_PLANTS]
                source_label = "broader indication inventory fallback"

            st.session_state["rd_known_plants"] = market_plants
            st.session_state["rd_known_plants_total"] = len(market_plants)
            st.session_state["rd_market_input_source"] = source_label

            if not market_plants:
                st.session_state["rd_market_landscape_df"] = pd.DataFrame()
                st.warning(
                    "No Step 2 candidate shortlist or broader indication inventory "
                    "was available. Run Step 2 first, then retry Market Analysis."
                )
            else:
                market_engine = _build_engine(
                    _get_evidence_df(), use_live_search=live_market
                )

                with st.spinner(
                    f"Checking market and competitive landscape for "
                    f"{len(market_plants)} shortlisted plant(s)..."
                ):
                    landscape_df = market_engine.market_landscape_df(market_plants)

                    # General commercial classification for the CURRENT indication.
                    # Keep it independent from the legacy regulatory/patent landscape:
                    # a plant can be commercially established overall but still be a
                    # repurposing candidate for this indication, or its indication
                    # positioning can simply be unverified.
                    commercial_df = _attach_commercial_market_intelligence(
                        pd.DataFrame({"Alternative_Plant": market_plants}),
                        evidence_df=_get_evidence_df(),
                        indication=indication,
                        dosage_form=dosage_form,
                        market=market,
                    )
                    if isinstance(commercial_df, pd.DataFrame) and not commercial_df.empty:
                        commercial_df = commercial_df.rename(columns={"Alternative_Plant": "Plant"})
                        commercial_cols = [
                            c for c in commercial_df.columns
                            if c == "Plant" or c.startswith("Commercial_")
                            or c.startswith("Indication_")
                            or c == "Overall_Product_Hits"
                        ]
                        landscape_df = landscape_df.merge(
                            commercial_df[commercial_cols].drop_duplicates(subset=["Plant"]),
                            on="Plant", how="left",
                        )

                st.session_state["rd_market_landscape_df"] = landscape_df
                st.success("✅ Market analysis completed.")

        except Exception as e:
            st.error(f"Market analysis failed: {e}")

    known_plants = st.session_state.get("rd_known_plants", [])
    known_plants_total = st.session_state.get("rd_known_plants_total", len(known_plants))
    market_input_source = st.session_state.get("rd_market_input_source", "")
    broader_plants = st.session_state.get("rd_broader_market_context_plants", [])
    broader_total = st.session_state.get(
        "rd_broader_market_context_total", len(broader_plants)
    )
    landscape_df = st.session_state.get("rd_market_landscape_df")

    if known_plants:
        if "fallback" in str(market_input_source).lower():
            st.warning(
                "Step 2 shortlist was unavailable, so this run used the broader "
                "indication inventory. Run Step 2 and rerun Market Analysis for "
                "shortlist-aligned results."
            )

        st.write(
            f"**Step 2 candidates used for primary market analysis** "
            f"({len(known_plants)} plant(s); source: {market_input_source}):"
        )
        st.write(", ".join(known_plants))

    if broader_plants:
        shortlist_keys = {str(x).strip().lower() for x in known_plants}
        context_only = [
            plant for plant in broader_plants
            if str(plant).strip().lower() not in shortlist_keys
        ]
        with st.expander(
            f"Broader market context — {broader_total} indication-linked plant(s)",
            expanded=False,
        ):
            st.caption(
                "Context only: these plants are not included in the primary market "
                "analysis unless they were also selected in Step 2."
            )
            if context_only:
                preview = context_only[:_MAX_MARKET_CHECK_PLANTS]
                st.write(", ".join(preview))
                if len(context_only) > len(preview):
                    st.caption(
                        f"+{len(context_only) - len(preview)} additional context plant(s)."
                    )
            else:
                st.write("All broader-context plants are already in the Step 2 shortlist.")

    if isinstance(landscape_df, pd.DataFrame) and not landscape_df.empty:
        compact_columns = [
            "Plant",
            "Region_of_Origin",
            "EMA_HMPC_Status",
            "WHO_Status",
            "ESCOP_Status",
            "US_Status",
            "UK_Status",
            "Patent_Search_Status",
            "Retail_Products_Status",
            "Commercial_Status_Overall",
            "Commercial_Status_For_Indication",
            "Commercial_Novelty_Status",
            "Overall_Product_Hits",
            "Indication_Product_Hits",
            "Indication_Market_Search_Status",
        ]
        compact_columns = [c for c in compact_columns if c in landscape_df.columns]
        st.caption(
            "Compact regulatory view. EMA/HMPC wording is summarized for readability; "
            "the source wording remains available below."
        )

        # Build the complete export before rendering the compact table.  This
        # places the explicit full-export button above the dataframe toolbar,
        # whose built-in CSV icon exports only the visible compact columns.
        preferred_export_columns = [
            "Plant",
            "Region_of_Origin",
            "EMA_HMPC_Status",
            "EMA_HMPC_Detail",
            "EMA_Source",
            "WHO_Status",
            "WHO_Source",
            "ESCOP_Status",
            "ESCOP_Source",
            "Regulatory_Source",
            "US_Status",
            "UK_Status",
            "Patent_Search_Status",
            "Patent_Detail",
            "Retail_Products_Status",
            "Retail_Products_Detail",
            "Commercial_Status_Overall",
            "Commercial_Status_For_Indication",
            "Commercial_Novelty_Status",
            "Commercial_Positioning",
            "Overall_Product_Hits",
            "Indication_Product_Hits",
            "Commercial_Market_Saturation",
            "Indication_Market_Saturation",
            "Indication_Market_Search_Status",
            "Commercial_Market_Source_IDs",
        ]
        export_columns = [
            column for column in preferred_export_columns
            if column in landscape_df.columns
        ]
        export_columns.extend(
            column for column in landscape_df.columns
            if column not in export_columns
        )
        market_export_df = landscape_df.loc[:, export_columns].copy()

        st.download_button(
            "⬇️ Download FULL market analysis (all columns)",
            data=market_export_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="step3_market_competitive_landscape_full.csv",
            mime="text/csv",
            key="rd_download_full_market_csv",
            help=(
                "Use this button for the complete export. The small download icon "
                "inside the table exports only the columns visible in the compact view."
            ),
            type="primary",
        )
        st.caption(
            "Use the red FULL export button above. The small download icon inside "
            "the table exports only the visible compact columns."
        )

        st.dataframe(landscape_df[compact_columns], width="stretch")

        detail_columns = [
            "Plant",
            "EMA_HMPC_Detail",
            "EMA_Source",
            "WHO_Status",
            "WHO_Source",
            "ESCOP_Status",
            "ESCOP_Source",
            "Regulatory_Source",
            "Patent_Detail",
            "Retail_Products_Detail",
        ]
        detail_columns = [c for c in detail_columns if c in landscape_df.columns]
        if detail_columns:
            with st.expander("Regulatory and market-source details", expanded=False):
                st.dataframe(landscape_df[detail_columns], width="stretch")



    st.markdown("---")
    st.markdown("## Step 4 — Existing Scientific Knowledge")

    st.caption(
        "Review the current scientific inventory for the Step 2 shortlist: "
        "plants, compounds, targets, mechanisms, evidence level, extraction, "
        "safety and source provenance. This is a knowledge map, not a claim of efficacy."
    )

    if st.button("Run Scientific Knowledge Analysis", type="primary", key="run_step2_science"):
        try:
            with st.spinner("Looking up known plants, compounds, mechanisms, safety and sources..."):
                offline_engine = _offline_engine()
                broad_inventory_df = offline_engine.known_inventory_df(indication)

            shortlist, shortlist_source = _get_step2_candidate_shortlist()
            if shortlist and isinstance(broad_inventory_df, pd.DataFrame):
                shortlist_keys = {str(x).strip().lower() for x in shortlist}
                primary_inventory_df = broad_inventory_df[
                    broad_inventory_df["Known_Plant"].fillna("").astype(str).str.strip().str.lower().isin(shortlist_keys)
                ].copy()
            else:
                primary_inventory_df = broad_inventory_df.copy()
                shortlist_source = "broader indication inventory fallback"

            st.session_state["rd_inventory_df"] = primary_inventory_df
            st.session_state["rd_inventory_df_broader"] = broad_inventory_df
            st.session_state["rd_science_input_source"] = shortlist_source

            if isinstance(primary_inventory_df, pd.DataFrame) and not primary_inventory_df.empty:
                st.success("✅ Scientific knowledge analysis completed.")
            else:
                st.warning(
                    "No scientific inventory rows were found for the selected Step 2 candidates. "
                    "The broader indication inventory is still available below for context."
                )

        except Exception as e:
            st.error(f"Scientific knowledge analysis failed: {e}")

    inventory_df = st.session_state.get("rd_inventory_df")
    broader_inventory_df = st.session_state.get("rd_inventory_df_broader")
    science_input_source = st.session_state.get("rd_science_input_source", "unavailable")

    if isinstance(inventory_df, pd.DataFrame) and not inventory_df.empty:
        n_known_plants = inventory_df["Known_Plant"].nunique() if "Known_Plant" in inventory_df.columns else 0
        n_known_compounds = inventory_df["Known_Compound"].nunique() if "Known_Compound" in inventory_df.columns else 0
        n_mechanisms = (
            inventory_df["Known_Mechanism"].replace("", pd.NA).dropna().nunique()
            if "Known_Mechanism" in inventory_df.columns else 0
        )
        n_sources = (
            inventory_df["Reference_URL"].replace("", pd.NA).dropna().nunique()
            if "Reference_URL" in inventory_df.columns else 0
        )

        st.caption(
            f"{n_known_plants} shortlisted plant(s), {n_known_compounds} known compound(s), "
            f"{n_mechanisms} mechanism statement(s), {n_sources} linked reference(s) "
            f"(source: {science_input_source})."
        )

        regulatory_df = st.session_state.get("rd_market_landscape_df")
        summary_df = _build_scientific_plant_summary(inventory_df, regulatory_df)

        st.markdown("### Plant-level scientific knowledge summary")
        st.dataframe(summary_df, width="stretch", hide_index=True)

        st.download_button(
            "⬇️ Download plant-level scientific summary (CSV)",
            data=summary_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="step4_scientific_knowledge_summary.csv",
            mime="text/csv",
            key="download_step4_summary_csv",
        )

        st.markdown("### Detailed plant–compound evidence inventory")
        st.caption(
            "Each row is one plant–compound record. Empty fields mean the source database "
            "does not currently contain that information; they are not filled by inference."
        )
        st.dataframe(inventory_df.head(500), width="stretch", hide_index=True)

        st.download_button(
            "⬇️ Download FULL scientific knowledge inventory (all columns)",
            data=inventory_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="step4_scientific_knowledge_full.csv",
            mime="text/csv",
            key="download_step4_full_csv",
        )

        if len(inventory_df) > 500:
            st.caption(
                f"Showing first 500 of {len(inventory_df)} detailed rows; "
                "the FULL CSV contains every row."
            )

    if isinstance(broader_inventory_df, pd.DataFrame) and not broader_inventory_df.empty:
        primary_plants = set(
            inventory_df["Known_Plant"].dropna().astype(str)
            if isinstance(inventory_df, pd.DataFrame) and "Known_Plant" in inventory_df.columns
            else []
        )
        broader_only = broader_inventory_df[
            ~broader_inventory_df["Known_Plant"].fillna("").astype(str).isin(primary_plants)
        ].copy()
        broader_count = broader_inventory_df["Known_Plant"].nunique()
        with st.expander(
            f"Broader scientific context — {broader_count} indication-linked plant(s)",
            expanded=False,
        ):
            st.caption(
                "Context only. These rows are not part of the primary Step 2 shortlist analysis."
            )
            st.dataframe(broader_only.head(300), width="stretch", hide_index=True)
            st.download_button(
                "Download broader scientific context (CSV)",
                data=broader_inventory_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="step4_broader_scientific_context.csv",
                mime="text/csv",
                key="download_step4_broader_csv",
            )

    st.markdown("---")
    st.markdown("## Step 5 — R&D Candidate Discovery & Decision Engine")

    st.caption(
        "Generate alternative botanical candidates and score them using evidence, "
        "mechanism plausibility, chemical differentiation, safety, regulatory feasibility, "
        "and independently verified market opportunity. Missing market data never counts as novelty."
    )

    col1, col2 = st.columns(2)

    discovery_mode_label = st.radio(
        "Discovery objective",
        options=[
            "Find botanicals for an indication",
            "Find alternative botanical sources of an active compound",
        ],
        index=0,
        help=(
            "Indication mode ranks plants from plant–indication evidence. "
            "Compound-source mode retains the legacy chemical-substitution workflow."
        ),
        key="rd_discovery_mode",
    )
    discovery_mode = (
        "indication" if discovery_mode_label.startswith("Find botanicals")
        else "compound_substitution"
    )

    with col1:
        reference_plant = st.text_input(
            "Reference plant (compound-source mode only)",
            value="",
            help="Leave empty to analyze every known plant for this indication.",
            key="rd_reference_plant",
        )

    with col2:
        reference_compound = st.text_input(
            "Reference compound (compound-source mode only)",
            value="",
            key="rd_reference_compound",
        )

    use_live_search = st.checkbox(
        "Include live Europe PMC evidence search",
        value=False,
        help="Keep this off unless needed. It may hit rate limits.",
        key="rd_live_evidence_checkbox",
    )

    evidence_df_for_run = _get_evidence_df()
    run_key = _candidate_discovery_run_key(
        indication=indication,
        dosage_form=dosage_form,
        market=market,
        reference_plant=reference_plant,
        reference_compound=reference_compound,
        discovery_mode=discovery_mode,
        use_live_search=use_live_search,
        evidence_df=evidence_df_for_run,
    )

    discovery_lock = _candidate_discovery_process_lock()
    discovery_busy = discovery_lock.locked()
    run_clicked = st.button(
        "Run Candidate Discovery",
        type="primary",
        key="run_step3_candidates",
        disabled=discovery_busy,
    )
    if discovery_busy:
        st.caption(
            "Candidate Discovery is already running in this app process. "
            "A second copy will not be started; wait for the active run to finish."
        )

    _rerun_after_discovery = False
    if run_clicked:
        _configure_ai_run_budgets()
        existing_result = st.session_state.get("rd_candidates_df")
        if (
            st.session_state.get("rd_candidate_run_key") == run_key
            and isinstance(existing_result, pd.DataFrame)
            and not existing_result.empty
        ):
            st.info("Same inputs detected — reusing the completed Step 5 result.")
            _rerun_after_discovery = True
        elif not discovery_lock.acquire(blocking=False):
            st.warning(
                "Another Candidate Discovery run started just before this click. "
                "No duplicate job was launched."
            )
        else:
            progress = st.progress(0.0, text="Preparing cached scientific data…")

            def _step5_progress(stage, current=0, total=0, message=""):
                # The indication engine reports real plant-level progress. The
                # stage offsets leave room for evidence-index construction and
                # plant-level shortlisting before/after the main scoring loop.
                if stage == "candidate_universe":
                    value = 0.05
                elif stage == "evidence_index":
                    value = 0.12
                elif stage == "profile":
                    value = 0.18
                elif stage == "catalogue_prescreen":
                    value = 0.20
                elif stage == "embedding":
                    value = 0.22
                elif stage == "scoring":
                    fraction = (float(current) / float(total)) if total else 0.0
                    value = 0.22 + 0.63 * max(0.0, min(1.0, fraction))
                elif stage == "discovery_done":
                    value = 0.86
                else:
                    value = 0.02
                progress.progress(
                    max(0.0, min(1.0, value)),
                    text=message or "Discovering and scoring R&D candidates…",
                )

            try:
                _perf_t0 = time.perf_counter()
                _perf(f"build_engine start discovery_mode={discovery_mode!r} indication={indication!r}")
                novel_discovered_candidates = _get_step2_novel_discovered_candidates(
                    indication=indication, market=market,
                )
                engine = _build_engine(
                    evidence_df_for_run,
                    use_live_search=use_live_search,
                    discovered_candidates=novel_discovered_candidates,
                )
                _perf(
                    f"build_engine done elapsed={time.perf_counter() - _perf_t0:.3f} "
                    f"novel_discovered_candidates={len(novel_discovered_candidates)}"
                )

                with st.spinner("Discovering and scoring R&D candidates..."):
                    _perf_t_run = time.perf_counter()
                    result_df = engine.run(
                        indication=indication,
                        dosage_form=dosage_form,
                        market=market,
                        reference_plant=reference_plant,
                        reference_compound=reference_compound,
                        discovery_mode=discovery_mode,
                        progress_callback=_step5_progress,
                        target_context=transferability_target_context,
                        retrieval_coverage_by_plant=_get_step2_retrieval_coverage(
                            indication=indication, market=market
                        ),
                        enable_stage5_prescreen=(discovery_mode == "indication"),
                    )
                    _perf(
                        f"engine.run() done rows={0 if result_df is None else len(result_df)} "
                        f"elapsed={time.perf_counter() - _perf_t_run:.3f} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )

                # The authoritative Stage-5 catalogue pre-screen now runs INSIDE
                # indication_candidate_discovery, before its expensive per-plant
                # loop.  Do not pre-screen the already-expanded result again here.
                if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                    scoring_pool_df = result_df
                    prescreen_audit_df = getattr(engine, "stage5_prescreen_audit_df", pd.DataFrame())
                    st.session_state["rd_candidate_prescreen_audit_df"] = prescreen_audit_df
                    _perf(
                        f"stage5 prescreen authoritative pool rows={len(scoring_pool_df)} "
                        f"plants={scoring_pool_df['Alternative_Plant'].nunique() if 'Alternative_Plant' in scoring_pool_df.columns else 0}"
                    )

                    progress.progress(0.87, text="Building scientific shortlist…")

                    def _shortlist_progress(current=0, total=0, message=""):
                        # UX fix (2026-08-26): build_plant_candidate_shortlist()
                        # previously took no progress_callback at all, so this
                        # entire stage (measured in production at several
                        # minutes -- see its own PERF "scoring" instrumentation)
                        # left the bar frozen at 0.87 with no visible movement,
                        # indistinguishable from a genuine hang. Mapped into the
                        # existing 0.87-0.90 band reserved for this stage; never
                        # touches scoring/filtering/ranking itself.
                        fraction = (float(current) / float(total)) if total else 0.0
                        value = 0.87 + 0.03 * max(0.0, min(1.0, fraction))
                        progress.progress(
                            max(0.0, min(1.0, value)),
                            text=message or "Building scientific shortlist…",
                        )

                    # ONE authoritative expensive scientific-scoring pass, over
                    # the bounded pool only.
                    _perf_t_shortlist = time.perf_counter()
                    plant_summary_df, triage_audit_df = build_plant_candidate_shortlist(
                        scoring_pool_df,
                        indication=indication,
                        dosage_form=dosage_form,
                        max_candidates=0,
                        target_context=transferability_target_context,
                        progress_callback=_shortlist_progress,
                    )
                    market_plants = _step5_commercial_enrichment_plants(plant_summary_df)
                    _perf(
                        f"shortlist done plants={len(plant_summary_df)} "
                        f"market_enrichment_plants={len(market_plants)} "
                        f"elapsed={time.perf_counter() - _perf_t_shortlist:.3f}"
                    )

                    progress.progress(0.90, text="Checking commercial status for shortlisted candidates…")
                    _perf_t_market = time.perf_counter()
                    result_df = _attach_commercial_market_intelligence(
                        result_df,
                        evidence_df=evidence_df_for_run,
                        indication=indication,
                        dosage_form=dosage_form,
                        market=market,
                        candidate_plants=market_plants,
                    )
                    _perf(
                        f"commercial enrichment done plants={len(market_plants)} "
                        f"elapsed={time.perf_counter() - _perf_t_market:.3f}"
                    )

                    # Fold commercial enrichment into the score by updating
                    # ONLY the Novelty & Market component of the plants that
                    # were enriched -- every other already-computed
                    # scientific component (indication relevance, scientific
                    # evidence, compound quality, mechanism support, safety/
                    # regulatory) is reused unchanged. This is the "zero
                    # duplicate full-scoring executions" requirement: no
                    # second build_plant_candidate_shortlist() call happens
                    # here regardless of how many plants were enriched.
                    progress.progress(0.95, text="Updating scores with commercial data…")
                    if market_plants:
                        _perf_t_rescore = time.perf_counter()
                        plant_summary_df = rescore_commercial_component(
                            plant_summary_df, result_df, market_plants,
                        )
                        _perf(
                            f"commercial rescore done plants={len(market_plants)} "
                            f"elapsed={time.perf_counter() - _perf_t_rescore:.3f}"
                        )
                    plant_summary_df = _finalize_step5_summary(plant_summary_df)
                else:
                    plant_summary_df, triage_audit_df = pd.DataFrame(), pd.DataFrame()

                st.session_state["rd_candidates_df"] = result_df
                # Any previously prepared CSV bytes belong to the former run.
                st.session_state.pop("rd_raw_candidate_csv_bytes", None)
                st.session_state.pop("rd_triage_audit_csv_bytes", None)

                if isinstance(result_df, pd.DataFrame) and not result_df.empty:
                    # Controlled AI evidence-adjudication layer (part 3C/14/15).
                    # Runs on plant_summary_df BEFORE merge_authoritative_scores()
                    # below, so the new structured columns and any negative-
                    # evidence decision cap are already present on every row
                    # merge_authoritative_scores() reads -- see that function's
                    # authoritative_fields and evidence_adjudication_engine.py's
                    # module docstring for the full rationale. Never blocks Step 5:
                    # adjudicate_candidate() itself is fail-open (part 16), and
                    # this call has no external try/except of its own for the
                    # same reason the AI R&D insight block below does not need
                    # one around generate_candidate_insights() per-plant.
                    _perf_t_adjudication = time.perf_counter()
                    # Use the processed Stage-5 evidence rows themselves as
                    # the adjudication evidence source.  They carry the same
                    # authoritative Indication_Match_Type/score, traceability,
                    # study-design and preparation decisions that created the
                    # shortlist.  Feeding the raw evidence store here used to
                    # make deterministic relevance and AI relevance disagree.
                    # This is generic for every indication and product form.
                    plant_summary_df = _run_evidence_adjudication(
                        plant_summary_df, result_df, indication,
                        transferability_target_context,
                    )
                    _perf(
                        f"evidence adjudication done "
                        f"elapsed={time.perf_counter() - _perf_t_adjudication:.3f} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )
                    _perf(
                        f"final plant shortlist ready plants={0 if plant_summary_df is None else len(plant_summary_df)} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )
                    st.session_state["rd_candidate_plant_summary_df"] = plant_summary_df
                    st.session_state["rd_candidate_triage_audit_df"] = triage_audit_df
                    # Phase 3 (IMPLEMENTATION_PLAN.md) — the single authoritative,
                    # report-ready frame. Both the recommendation block and the
                    # downloaded report are built from THIS, not from result_df
                    # directly, so they can never disagree with the shortlist
                    # above about which plant is the top candidate.
                    _perf_t_merge = time.perf_counter()
                    st.session_state["rd_report_ready_df"] = _merge_and_sync_final_decision_status(
                        result_df, plant_summary_df
                    )
                    _perf(
                        f"merge_authoritative_scores() done "
                        f"elapsed={time.perf_counter() - _perf_t_merge:.3f} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )
                    # Phase 4 (IMPLEMENTATION_PLAN.md) — computed ONCE per
                    # decision run, from the same report_ready_df just built.
                    # Both the downloaded report and the persisted decision
                    # record read this exact dict — see build_decision_metadata()'s
                    # own docstring.
                    _perf_t_decision = time.perf_counter()
                    st.session_state["rd_decision_metadata"] = build_decision_metadata(
                        st.session_state["rd_report_ready_df"],
                        indication=indication, dosage_form=dosage_form, market=market,
                        discovery_mode=_detect_discovery_mode(result_df),
                    )
                    _perf(
                        f"build_decision_metadata() done "
                        f"elapsed={time.perf_counter() - _perf_t_decision:.3f} "
                        f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                    )
                    # PHASE 6 — additive structured causal trace.  This reads the
                    # authoritative score/gate outputs and triage audit only; it never
                    # changes scoring, gating, ranking, connectors, or UI behaviour.
                    st.session_state["rd_report_ready_df"] = attach_decision_explanations(
                        st.session_state["rd_report_ready_df"],
                        triage_audit_df,
                        decision_metadata=st.session_state["rd_decision_metadata"],
                    )

                    counts = (
                        plant_summary_df["Scientific_Triage_Status"].value_counts()
                        if isinstance(plant_summary_df, pd.DataFrame) and not plant_summary_df.empty
                        else pd.Series(dtype=int)
                    )
                    shortlisted = int(counts.get("Shortlist", 0))
                    exploratory = int(counts.get("Exploratory", 0))
                    excluded = int(counts.get("Excluded", 0))
                    st.session_state["rd_candidate_run_key"] = run_key
                    # Additive AI R&D insight layer (hybrid AI-R&D architecture,
                    # mechanistic reasoning / evidence synthesis / R&D
                    # hypotheses): computed per shortlisted candidate from the
                    # same authoritative rd_report_ready_df everything above
                    # reads, stored SEPARATELY, and never written back into
                    # result_df / plant_summary_df / rd_report_ready_df --
                    # Deterministic_Score / R&D_Opportunity_Score are never
                    # touched by this block. Every AI stage inside
                    # generate_candidate_insights() fails open independently
                    # (see ai_rd_insight_service.py's own module docstring),
                    # so this can never block Stage 5 completing.
                    try:
                        _perf_t_ai_insights = time.perf_counter()
                        _report_df = st.session_state.get("rd_report_ready_df")
                        _insight_plant_col = _resolve_report_plant_column(_report_df)
                        _insight_plants = []
                        if _insight_plant_col is not None:
                            _insight_plants = (
                                _report_df[_insight_plant_col].dropna().astype(str)
                                .drop_duplicates().tolist()[:_AI_RD_INSIGHTS_MAX_CANDIDATES]
                            )
                        ai_insights = {}
                        for _plant_name in _insight_plants:
                            _score_summary = None
                            _plant_rows = _report_df[_report_df[_insight_plant_col] == _plant_name]
                            if not _plant_rows.empty:
                                _first_row = _plant_rows.iloc[0]
                                _score_summary = {
                                    "deterministic_score": _first_row.get("Overall_Score"),
                                    "evidence_status": _first_row.get("Evidence_Status", ""),
                                }
                            ai_insights[_plant_name] = generate_candidate_insights(
                                _plant_name, result_df, score_summary=_score_summary,
                                indication=indication,
                            )
                        st.session_state["rd_ai_insights"] = ai_insights
                        st.session_state["rd_report_ready_df"] = _attach_ai_insights_to_report_df(
                            st.session_state.get("rd_report_ready_df"), ai_insights
                        )
                        _perf(
                            f"AI R&D insights done candidates={len(ai_insights)} "
                            f"elapsed={time.perf_counter() - _perf_t_ai_insights:.3f} "
                            f"(cumulative={time.perf_counter() - _perf_t0:.3f})"
                        )
                    except Exception as _ai_insights_exc:
                        st.session_state["rd_ai_insights"] = {}
                        _perf(
                            f"AI R&D insights skipped ({type(_ai_insights_exc).__name__}: "
                            f"{_ai_insights_exc}) -- Stage 5 output is unaffected"
                        )

                    # Part 11 (OpenAI-usage audit, this session) -- snapshot the
                    # run's AI status NOW, at the end of the run, so the
                    # deterministic result and the AI status shown together
                    # never diverge: a later Streamlit rerender re-reads this
                    # snapshot (never live tracker state, which would reset on
                    # the next "Run Candidate Discovery" click) via
                    # _render_ai_status_summary() below.
                    st.session_state["rd_ai_status_summary"] = get_ai_run_tracker().summary()

                    progress.progress(1.0, text="Candidate Discovery complete.")
                    st.success(
                        f"✅ {len(result_df)} raw plant–compound associations generated; "
                        f"aggregated into {shortlisted + exploratory + excluded} plant candidates "
                        f"({shortlisted} shortlisted, {exploratory} exploratory, {excluded} excluded)."
                    )
                    # Render the result in a fresh, lightweight rerun only AFTER
                    # releasing the process lock in the finally block below.
                    _rerun_after_discovery = True
                else:
                    st.session_state.pop("rd_candidate_plant_summary_df", None)
                    st.session_state.pop("rd_candidate_triage_audit_df", None)
                    st.session_state.pop("rd_candidate_run_key", None)
                    progress.progress(1.0, text="Candidate Discovery finished — no candidates found.")
                    st.warning("No R&D candidates found.")

            except Exception as e:
                st.session_state.pop("rd_candidate_run_key", None)
                st.error(f"Candidate discovery failed: {e}")
            finally:
                discovery_lock.release()

    if _rerun_after_discovery:
        _perf("Step 5 result ready; rerunning UI after releasing discovery lock")
        st.rerun()

    result_df = st.session_state.get("rd_candidates_df")

    # Do not enrich all raw rows automatically. At several thousand rows,
    # row-wise development-concept formatting is not cheap on Streamlit Cloud
    # and was the main reason the page kept showing "Stop" after discovery had
    # already completed. It is prepared lazily only when the user requests the
    # full raw audit export below.

    if isinstance(result_df, pd.DataFrame) and not result_df.empty:
        is_indication_mode = _detect_discovery_mode(result_df) == "indication"
        if is_indication_mode:
            st.info(
                "🔎 **Indication-centric discovery:** candidates enter through "
                "plant-specific indication or mechanism evidence. Shared chemistry "
                "is supporting metadata only and is not used as an entry gate."
            )
        elif "Reference_Plant" in result_df.columns:
            n_ref_plants = result_df["Reference_Plant"].nunique()
            if n_ref_plants <= 3:
                ref_names = ", ".join(result_df["Reference_Plant"].dropna().unique()[:3])
                st.warning(
                    f"⚠️ **Every candidate below traces back to just {n_ref_plants} "
                    f"reference plant(s)** ({ref_names}). Broaden the reference base "
                    "before treating compound-source results as comprehensive."
                )
        plant_summary_df = st.session_state.get("rd_candidate_plant_summary_df")
        triage_audit_df = st.session_state.get("rd_candidate_triage_audit_df")
        if not isinstance(plant_summary_df, pd.DataFrame) or plant_summary_df.empty:
            _perf_t0_fallback = time.perf_counter()
            _fallback_df = result_df
            _prescreen_audit = st.session_state.get("rd_candidate_prescreen_audit_df")
            if isinstance(_prescreen_audit, pd.DataFrame) and not _prescreen_audit.empty and "PreScreen_Status" in _prescreen_audit.columns:
                _kept = set(
                    _prescreen_audit.loc[
                        _prescreen_audit["PreScreen_Status"].astype(str).eq("SENT_TO_FULL_SCORING"),
                        "Alternative_Plant",
                    ].dropna().astype(str)
                )
                if _kept and "Alternative_Plant" in result_df.columns:
                    _fallback_df = result_df[result_df["Alternative_Plant"].astype(str).isin(_kept)].copy()
            _perf(
                "fallback-path build_plant_candidate_shortlist() start "
                f"plants={_fallback_df['Alternative_Plant'].nunique() if 'Alternative_Plant' in _fallback_df.columns else 0}"
            )
            plant_summary_df, triage_audit_df = build_plant_candidate_shortlist(
                _fallback_df,
                indication=indication,
                dosage_form=dosage_form,
                max_candidates=50,
                target_context=transferability_target_context,
            )
            _perf(f"fallback-path build_plant_candidate_shortlist() done elapsed={time.perf_counter() - _perf_t0_fallback:.3f}")
            st.session_state["rd_candidate_plant_summary_df"] = plant_summary_df
            st.session_state["rd_candidate_triage_audit_df"] = triage_audit_df
            _perf_t_merge_fallback = time.perf_counter()
            st.session_state["rd_report_ready_df"] = _merge_and_sync_final_decision_status(
                result_df, plant_summary_df
            )
            _perf(f"fallback-path merge_authoritative_scores() done elapsed={time.perf_counter() - _perf_t_merge_fallback:.3f}")
            _perf_t_decision_fallback = time.perf_counter()
            st.session_state["rd_decision_metadata"] = build_decision_metadata(
                st.session_state["rd_report_ready_df"],
                indication=indication, dosage_form=dosage_form, market=market,
                discovery_mode=_detect_discovery_mode(result_df),
            )
            _perf(f"fallback-path build_decision_metadata() done elapsed={time.perf_counter() - _perf_t_decision_fallback:.3f}")
        report_ready_df = st.session_state.get("rd_report_ready_df")
        if not isinstance(report_ready_df, pd.DataFrame):
            report_ready_df = _merge_and_sync_final_decision_status(result_df, plant_summary_df)
            st.session_state["rd_report_ready_df"] = report_ready_df
        decision_metadata = st.session_state.get("rd_decision_metadata")
        if not decision_metadata:
            decision_metadata = build_decision_metadata(
                report_ready_df, indication=indication, dosage_form=dosage_form,
                market=market, discovery_mode=_detect_discovery_mode(result_df),
            )
            st.session_state["rd_decision_metadata"] = decision_metadata

        # Additive AI R&D insight layer -- rendered here, clearly separated
        # from the deterministic score/evidence/safety/regulatory/commercial
        # sections below. Renders nothing if no insights were computed for
        # this run (e.g. AI was unavailable) -- see _render_ai_rd_insights().
        _render_ai_rd_insights()

        st.info(
            "📊 **Scientific triage:** the main view shows only plant-level results. "
            "Raw plant–compound associations and excluded rows remain available as CSV audit files. "
            "The triage score prioritizes review; it is not an efficacy claim."
        )

        if isinstance(plant_summary_df, pd.DataFrame) and not plant_summary_df.empty:
            shortlist_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"] == "Shortlist"
            ].copy()
            exploratory_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"] == "Exploratory"
            ].copy()
            excluded_df = plant_summary_df[
                plant_summary_df["Scientific_Triage_Status"] == "Excluded"
            ].copy()

            st.markdown(f"### Scientific shortlist — {len(shortlist_df)} plant(s)")
            if shortlist_df.empty:
                st.warning(
                    "No plant passed all scientific gates. Raw chemical matches are not shown as candidates."
                )
            else:
                shortlist_display_df = _prepare_plant_triage_display(shortlist_df)
                st.dataframe(
                    shortlist_display_df,
                    width="stretch",
                    hide_index=True,
                    height=min(420, 86 + 44 * len(shortlist_display_df)),
                )

            with st.expander(
                f"Exploratory candidates — showing top {min(20, len(exploratory_df))} of {len(exploratory_df)}",
                expanded=False,
            ):
                st.caption(
                    "Plausible hypotheses with incomplete evidence. The complete list is included in the CSV export."
                )
                if not exploratory_df.empty:
                    exploratory_display_df = _prepare_plant_triage_display(
                        exploratory_df.head(20)
                    )
                    st.dataframe(
                        exploratory_display_df,
                        width="stretch",
                        hide_index=True,
                        height=min(520, 86 + 44 * len(exploratory_display_df)),
                    )

            # Additive AI R&D insight layer -- clearly separated from the
            # deterministic shortlist above (see _render_ai_rd_insights()'s
            # own docstring). Renders nothing if unavailable.
            _render_ai_rd_insights()

            st.download_button(
                "⬇️ Download complete plant-level triage (CSV)",
                data=plant_summary_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="step5_plant_centric_scientific_shortlist.csv",
                mime="text/csv",
                key="rd_download_plant_shortlist_csv",
                type="primary",
                help="Contains all shortlisted, exploratory and excluded plant candidates with reasons.",
            )

            # Additive AI R&D insight layer -- see _render_ai_rd_insights()'s
            # own docstring. Renders nothing when no insights were computed
            # for this run (e.g. AI was unavailable) -- always safe to call.
            _render_ai_rd_insights()

            st.caption(
                f"{len(excluded_df)} excluded plant(s) are not rendered on screen to keep the mobile page responsive; "
                "their gate failures and rejection reasons are preserved in the complete CSV."
            )

        st.markdown("#### Audit downloads")
        st.caption(
            "Large audit files are prepared only on request, so normal Step 5 viewing stays responsive on mobile."
        )

        raw_csv_bytes = st.session_state.get("rd_raw_candidate_csv_bytes")
        audit_csv_bytes = st.session_state.get("rd_triage_audit_csv_bytes")

        if raw_csv_bytes is None or (
            isinstance(triage_audit_df, pd.DataFrame)
            and not triage_audit_df.empty
            and audit_csv_bytes is None
        ):
            if st.button(
                "Prepare full audit CSV files",
                key="rd_prepare_audit_csv_btn",
                help="Formats the large raw network only when you actually need to download it.",
            ):
                with st.spinner("Preparing large audit files..."):
                    export_df = add_development_concept_column(
                        result_df, inputs.get("standardized_project")
                    )
                    st.session_state["rd_raw_candidate_csv_bytes"] = (
                        export_df.to_csv(index=False).encode("utf-8-sig")
                    )
                    if isinstance(triage_audit_df, pd.DataFrame) and not triage_audit_df.empty:
                        st.session_state["rd_triage_audit_csv_bytes"] = (
                            triage_audit_df.to_csv(index=False).encode("utf-8-sig")
                        )
                st.rerun()
        else:
            st.download_button(
                "Download raw plant–compound network (CSV)",
                data=raw_csv_bytes,
                file_name="step5_raw_candidate_association_network.csv",
                mime="text/csv",
                key="rd_download_raw_candidate_network_csv",
            )
            if audit_csv_bytes is not None:
                st.download_button(
                    "Download full scientific gate audit (CSV)",
                    data=audit_csv_bytes,
                    file_name="step5_scientific_gate_audit.csv",
                    mime="text/csv",
                    key="rd_download_triage_audit_csv",
                )

        with st.expander("🌍 Enrich with market/patent landscape (optional, per-candidate)"):
            st.caption(
                "Merges each candidate's real regulatory (EMA/WHO/ESCOP), patent, "
                "and retail search status into the table above — kept separate "
                "from the default run because patent search makes a real network "
                "call when EPO_OPS_KEY/EPO_OPS_SECRET are configured. Retail "
                "search has no free data source and will honestly show "
                "\"Not configured\"/\"Not implemented\" until a paid search API "
                "is wired in (see _search_retail_products())."
            )
            unique_plant_count = result_df["Alternative_Plant"].nunique() if "Alternative_Plant" in result_df.columns else 0
            max_plants = st.slider(
                "Max unique plants to check", 5, 100, min(30, max(unique_plant_count, 5)),
                key="rd_market_landscape_max_plants",
                help=f"This result has {unique_plant_count} unique alternative plants.",
            )
            if st.button("Run market/patent landscape check", key="rd_enrich_market_btn"):
                with st.spinner("Checking regulatory/patent/retail status per plant..."):
                    enrich_engine = _build_engine(_get_evidence_df(), use_live_search=use_live_search)
                    enriched_df = enrich_engine.enrich_candidates_with_market_landscape(
                        result_df, max_plants=max_plants,
                    )
                st.session_state["rd_candidates_df_enriched"] = enriched_df

            enriched_df = st.session_state.get("rd_candidates_df_enriched")
            if isinstance(enriched_df, pd.DataFrame) and not enriched_df.empty:
                note = enriched_df["Market_Landscape_Note"].iloc[0] if "Market_Landscape_Note" in enriched_df.columns else ""
                if note:
                    st.warning(note)
                display_cols = [c for c in enriched_df.columns if c.startswith("Market_Landscape_") or c in ("Alternative_Plant", "Reference_Plant")]
                st.dataframe(enriched_df[display_cols].drop_duplicates(subset=["Alternative_Plant"]).head(200), width="stretch")
                st.download_button(
                    "Download enriched table (CSV)",
                    data=enriched_df.to_csv(index=False).encode("utf-8"),
                    file_name="botanical_rd_candidates_market_enriched.csv",
                    mime="text/csv",
                    key="rd_download_enriched_csv",
                )

        with st.expander("📐 Validate output contract (Data Contracts adapter)"):
            st.caption(
                "Checks every row against data_contracts.CandidateAssessment — "
                "the named schema this output is supposed to have. A clean "
                "result means the real columns and the documented contract "
                "still agree; any errors here mean something drifted (a "
                "renamed column, an unexpected type) and point to exactly "
                "which row and field."
            )
            if st.button("Run contract validation", key="rd_validate_contract_btn"):
                records, errors_df = validate_result_df(
                    result_df, indication=indication, project_id=f"{indication}-{market}",
                )
                if errors_df.empty:
                    st.success(
                        f"✅ All {len(records)} rows validated cleanly against "
                        f"the CandidateAssessment contract."
                    )
                else:
                    st.error(
                        f"⚠️ {len(errors_df)} contract issue(s) found across "
                        f"{errors_df['row_index'].nunique()} row(s) — "
                        f"{len(records)} of {len(result_df)} rows still "
                        f"validated cleanly."
                    )
                    st.dataframe(errors_df, width="stretch")

                # Task 4 — best-effort persistence of the just-validated
                # records as ONE locked, versioned decision record. A
                # decision record must represent a FULLY validated
                # analysis, never a partial one — so this only runs when
                # errors_df is empty (every row validated cleanly), not
                # merely when records is non-empty. Never blocks or
                # interrupts this page; only a minimal status message is
                # shown, per the same UI constraint already used for
                # Sprint 6A.2's telemetry persistence (no database/SQL
                # details exposed here). Append-only — see
                # decision_record_persistence.py's LOCK SEMANTICS.
                if errors_df.empty and records:
                    decision_record_summary = persist_decision_record(
                        records, indication=indication, project_id=f"{indication}-{market}",
                        decision_metadata=st.session_state.get("rd_decision_metadata"),
                        # PHASE 2 (review round, issue 2) — the same
                        # evidence_df already loaded for this page,
                        # passed through so persist_decision_record()'s
                        # score_contributions can compute article-level
                        # evidence identity (not just raw database ids)
                        # for duplicate-score-contribution detection.
                        evidence_df=_get_evidence_df(),
                        # PHASE 6 — authoritative plant-level causal traces are
                        # persisted verbatim with the existing decision snapshot.
                        decision_explanations={
                            str(r.get("Alternative_Plant", "")): r.get("Decision_Explanation")
                            for _, r in st.session_state.get("rd_report_ready_df", pd.DataFrame()).iterrows()
                            if r.get("Decision_Explanation") is not None
                        },
                    )
                    if decision_record_summary["status"] == "persisted":
                        st.session_state["rd_last_decision_record_id"] = decision_record_summary["analysis_id"]
                        st.caption(
                            f"✅ Decision record persisted "
                            f"(analysis_id: {decision_record_summary['analysis_id']})"
                        )
                    else:
                        st.caption("ℹ️ Decision-record persistence unavailable")
                elif records:
                    st.caption(
                        "ℹ️ Decision record not persisted — contract validation "
                        "found issues, so this analysis is not yet complete."
                    )

        # Task 2 — Scoring sensitivity / ranking robustness. Purely
        # additive: prepare_sensitivity_payload() only calls the
        # existing fragility_report()/build_robustness_analysis()
        # entry points in scoring_sensitivity_report.py on the SAME
        # result_df already produced above — no re-run of engine.run(),
        # no new scoring logic, no change to result_df itself.
        with st.expander("Scoring sensitivity and ranking robustness", expanded=False):
            payload = prepare_sensitivity_payload(result_df)

            if payload["status"] == "insufficient_data":
                st.info(payload["message"])
            else:
                fragility = payload["fragility"]
                if fragility:
                    st.caption(fragility["summary"])

                counts = payload["rank_stability_counts"] or {}
                if counts:
                    st.caption("Leave-one-section-out rank stability")
                    ordered_levels = [
                        lvl for lvl in ("Stable", "Moderately stable", "Fragile", "Tied", "Insufficient")
                        if lvl in counts
                    ]
                    cols = st.columns(len(ordered_levels)) if ordered_levels else []
                    for col, level in zip(cols, ordered_levels):
                        col.metric(level, counts[level])

                perturb_counts = payload.get("weight_perturbation_stability_counts") or {}
                if perturb_counts:
                    st.caption("Actual ±10% section-weight perturbation")
                    ordered = [
                        lvl for lvl in ("Robust", "Moderately robust", "Sensitive")
                        if lvl in perturb_counts
                    ]
                    cols = st.columns(len(ordered)) if ordered else []
                    for col, level in zip(cols, ordered):
                        col.metric(level, perturb_counts[level])

                st.caption(
                    f"Ranking calibration status: {payload.get('ranking_calibration_status', 'unknown')} — "
                    f"{payload.get('ranking_calibration_notice', '')}"
                )

            st.divider()
            st.markdown(f"**{payload['boundary_statement']}**")
            st.caption(payload["boundary_explanation"])

        # part B6 fix -- this is the PRIMARY final decision-table download,
        # so it must be the authoritative, adjudicated, plant-level
        # report_ready_df (Base/Final_R&D_Opportunity_Score, the
        # Evidence_Adjudication_* fields, final decision fields, safety and
        # commercial status all live there — see candidate_shortlisting.
        # merge_authoritative_scores' authoritative_fields). result_df is
        # the raw, pre-aggregation per-compound association network; it is
        # still available separately above under "Download raw
        # plant–compound network (CSV)" for audit purposes, so nothing is
        # lost by no longer exporting it here.
        _decision_table_source_df = st.session_state.get("rd_report_ready_df")
        if not isinstance(_decision_table_source_df, pd.DataFrame) or _decision_table_source_df.empty:
            _decision_table_source_df = result_df
        st.download_button(
            "Download decision table (CSV)",
            data=_decision_table_source_df.to_csv(index=False).encode("utf-8"),
            file_name="botanical_rd_candidates.csv",
            mime="text/csv",
        )

        # Task 13.2C — per-item scientific evidence detail. Built ONCE
        # here, outside pharma_report_generator.py entirely: collect
        # this analysis's evidence_record_ids (already on every
        # candidate row via Task 10.2's Applicability_Summary), resolve
        # them against the same evidence_df already loaded for this
        # session, then convert to a presentation-safe payload before
        # it ever reaches the report layer. generate_pharma_report()
        # only ever receives the final plain-dict payload below — it
        # never imports standard_evidence_builder, never sees a
        # ScientificEvidence object, and never touches evidence_df or
        # the engine itself.
        scientific_evidence_by_id = get_scientific_evidence_by_ids(
            _collect_evidence_record_ids(result_df), _get_evidence_df()
        )
        scientific_evidence_payload = build_scientific_evidence_presentation_payload(
            scientific_evidence_by_id
        )

        report_ready_df = st.session_state.get("rd_report_ready_df")
        report_source_df = (
            report_ready_df
            if isinstance(report_ready_df, pd.DataFrame) and not report_ready_df.empty
            else result_df
        )
        report_markdown = generate_pharma_report(
            report_source_df, indication=indication, dosage_form=dosage_form, market=market,
            standardized_project=inputs.get("standardized_project"),
            decision_record_id=st.session_state.get("rd_last_decision_record_id"),
            scientific_evidence_payload=scientific_evidence_payload,
            decision_metadata=st.session_state.get("rd_decision_metadata"),
        )
        st.download_button(
            "Download R&D report (Markdown)",
            data=report_markdown.encode("utf-8"),
            file_name="botanical_rd_report.md",
            mime="text/markdown",
            help="A structured, per-candidate write-up (scientific/commercial/regulatory "
                 "rationale, evidence strengths & weaknesses, next-experiment suggestion, "
                 "sources) for the top-scoring candidates, plus a summary table for the rest.",
        )

        with st.expander("Preview R&D report"):
            st.markdown(report_markdown)

    st.markdown("---")
    st.markdown("## Step 6 — Final Recommendation")

    st.caption(
        "Generate a concise R&D recommendation based on the decision table produced in Step 5."
    )

    if st.button("Generate Final Recommendation", type="primary", key="run_step4_recommendation"):
        st.session_state["show_final_recommendation"] = True

    if st.session_state.get("show_final_recommendation"):
        _recommendation_block(result_df, st.session_state.get("rd_report_ready_df"))

    _render_ai_rd_insights()
    _render_ai_status_summary()
