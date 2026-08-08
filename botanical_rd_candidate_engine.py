import os
import re
import base64
import json
from datetime import datetime, timezone
import requests
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd
import botanical_taxonomy as _botanical_taxonomy

from concentration_normalizer import parse_concentration, format_concentration_info
from evidence_hierarchy_classifier import classify_evidence_hierarchy
from scientific_phrase_matcher import has_phrase_match
from negative_evidence_classifier import classify_negative_evidence
from evidence_interpretation import interpret_evidence
from evidence_authority import classify_source_authority_from_row
from evidence_confidence import compute_evidence_confidence, confidence_adjusted_framing_note
from grade_certainty_classifier import classify_grade_certainty
from decision_class_ah import classify_decision_ah
from white_space_classifier import classify_white_space
from structured_rationale import (
    go_investigate_hold_no_go,
    scientific_rationale,
    commercial_regulatory_rationale,
    evidence_strengths,
    evidence_weaknesses,
    next_experiment_suggestion,
    evidence_conflict_reasoning,
    recommendation_confidence_statement,
    competitive_positioning_statement,
    regulatory_rationale,
    commercial_rationale,
    safety_rationale,
    clinical_rationale,
    build_evidence_conflict_structured,
)
from comparative_rationale import build_comparative_rationale, build_comparative_rationale_structured
from regulatory_barrier_classifier import classify_regulatory_barriers
from final_decision_policy import (
    resolve_scientific_evidence, decide_final, FinalDecisionStatus,
    final_status_from_engine_row, assessment_domain_from_indication,
)
from data_contracts import GateStatus, EvidenceApplicability, APPLICABILITY_STRENGTH_ORDER
# Phase 4 — Eligibility Gate. See eligibility_gate.py's module docstring
# for why this is a separate, self-contained module rather than more
# entries in data_contracts.py. _decision_class() is now DERIVED from
# evaluate_eligibility()'s outcome instead of the pre-Phase-4 inline
# same_plant bypass — see _decision_class()'s own docstring below.
from eligibility_gate import (
    EligibilityStatus as _EligibilityStatus,
    ScoreValidity as _ScoreValidity,
    RankingPartition as _RankingPartition,
    RANKING_PARTITION_SORT_ORDER as _RANKING_PARTITION_SORT_ORDER,
    classify_safety_finding as _classify_safety_finding,
    classify_regulatory_finding as _classify_regulatory_finding,
    evaluate_eligibility as _evaluate_eligibility,
)
# Critical Safety False-Negative remediation (Case 006 / Hypericum
# perforatum) — a third, independent structured channel alongside
# free-text SAFETY_TERMS and structured DB_ACTIVITY_SAFETY_TERMS. See
# interaction_severity_classifier.py's module docstring for the full
# rationale and why this does not violate the existing SAFETY_TERMS /
# HARD_SAFETY_TERMS capability boundary documented in
# engine_evidence_input.py / test_gold_case_execution.py.
from interaction_severity_classifier import (
    classify_interaction_assertion as _classify_interaction_assertion,
    hard_hit_terms_for as _interaction_hard_hit_terms_for,
    informational_terms_for as _interaction_informational_terms_for,
    HARD_GATE_SIGNAL_TERM as _INTERACTION_HARD_GATE_SIGNAL_TERM,
    InteractionSeverityTier as _InteractionSeverityTier,
)
from safety_assertion_engine import (
    classify_safety_assertions as _classify_safety_assertions,
    summarize_safety_assertions as _summarize_safety_assertions,
    SafetyAssertionType as _SafetyAssertionType,
    AssertionPolarity as _SafetyAssertionPolarity,
    safety_assertion_from_dict as _safety_assertion_from_dict,
)


def sort_by_ranking_partition_then_score(df):
    """Correction round (2nd pass) — the single, shared, directly
    testable implementation of run()'s final row order: sort by
    Ranking_Partition FIRST (NORMAL, then PRELIMINARY_OR_EXPERT_REVIEW,
    then EXCLUDED_NO_GO — see eligibility_gate.RANKING_PARTITION_SORT_ORDER),
    R&D_Opportunity_Score DESCENDING second. A hard no-go row's raw
    score, however high, can never place it ahead of a genuinely
    NORMAL-partition row.

    This does NOT drop or filter any row — the input's full row count
    is preserved, only the order changes, so run()'s own output stays
    audit-complete (every candidate the engine produced is still
    present) while no longer being "sorted by score alone" the way the
    audit-completeness requirement had previously left it. A row
    missing the Ranking_Partition column entirely (should not happen
    for any row produced by the current run() — kept only as a safe
    fallback) sorts LAST, never accidentally first.

    Takes and returns a plain pandas DataFrame so it can be unit-tested
    with a small synthetic frame, independent of a full engine run.
    """
    if df.empty or "Ranking_Partition" not in df.columns:
        return df

    partition_sort_key = {
        partition.value: order
        for partition, order in _RANKING_PARTITION_SORT_ORDER.items()
    }
    sortable = df.copy()
    sortable["_Ranking_Partition_Sort_Key"] = sortable["Ranking_Partition"].map(
        partition_sort_key
    ).fillna(len(partition_sort_key))
    sortable = sortable.sort_values(
        by=["_Ranking_Partition_Sort_Key", "R&D_Opportunity_Score"],
        ascending=[True, False],
    ).drop(columns=["_Ranking_Partition_Sort_Key"]).reset_index(drop=True)
    return sortable

from standard_evidence_builder import (
    build_scientific_evidence,
    normalize_missing_value,
    classify_ema_hmpc_signal,
)
from phase5_scoring_config import (
    SCORING_MODEL_VERSION,
    MARKET_STATUS_POINTS,
)
from occurrence_seed import build_occurrence_lookup
from industrial_feasibility import classify_industrial_feasibility
from evidence_coverage import classify_candidate_evidence_strength

try:
    from evidence_database import load_evidence_database
except Exception:
    def load_evidence_database():
        return []

try:
    from global_candidate_ranking_engine import rank_global_candidates
except Exception:
    def rank_global_candidates(*args, **kwargs):
        return pd.DataFrame()

from global_plant_candidate_database import GLOBAL_PLANT_CANDIDATES
from compound_occurrence_map import get_region

try:
    from supabase_data import (
        load_plant_compounds_df,
        load_compound_profiles_df,
        load_scientific_evidence_df,
        load_evidence_records_df,
    )
except Exception:
    def load_plant_compounds_df():
        return pd.DataFrame()

    def load_compound_profiles_df():
        return pd.DataFrame()

    def load_scientific_evidence_df():
        return pd.DataFrame()

    def load_evidence_records_df():
        return pd.DataFrame()

try:
    from regulatory_frameworks import get_us_uk_status
except Exception:
    def get_us_uk_status(plant):
        return {}
from seed_data import (
    PLANT_COMPOUNDS,
    COMPOUND_TARGETS,
    TARGET_DISEASES,
    SLEEP_TEA_EVIDENCE,
)


OUTPUT_COLUMNS = [
    "Reference_Plant",
    "Reference_Plant_Part",
    "Reference_Compound",
    "Alternative_Plant",
    "Alternative_Plant_Part",
    "Shared_or_Similar_Compound",
    "Target_or_Mechanism",
    "Target_Provenance",
    "Concentration_Info",
    "Extraction_Method",
    "Industrial_Feasibility",
    "Co_Compounds",
    "Safety_Flags",
    "Interaction_Flags",
    "Evidence_Source",
    "Source_Record_IDs",
    "Occurrence_Corroboration",
    "Candidate_Evidence_Strength_Tier",
    "Evidence_Level",
    "Evidence_Hierarchy_Detail",
    "Study_Design",
    "Evidence_Direction",
    "Evidence_Quality",
    "Evidence_Applicability",
    "Has_Negative_Evidence",
    "Negative_Evidence_Types",
    "Market_Status",
    "Regulatory_Recognition_Status",
    "Regulatory_Barriers",
    "Novelty_Status",
    "R&D_Opportunity_Score",
    "Score_Breakdown",
    "Evidence_Confidence",
    "Decision_Class",
    "Decision_Class_AH",
    "White_Space_Type",
    "Confidence_Note",
    "Go_Investigate_Hold_NoGo",
    "Scientific_Rationale",
    "Commercial_Regulatory_Rationale",
    "Evidence_Strengths",
    "Evidence_Weaknesses",
    "Next_Experiment_Suggestion",
    "Evidence_Conflict_Reasoning",
    "Evidence_Conflict_Structured",
    "Recommendation_Confidence_Statement",
    "Competitive_Positioning",
    "Regulatory_Rationale",
    "Commercial_Rationale",
    "Safety_Rationale",
    "Clinical_Rationale",
    "Comparative_Rationale",
    "Comparative_Rationale_Structured",
    "Rationale",
    # Task 1 — Formal Gate Layer. Additive only: see _evaluate_gates()
    # and CandidateAssessment.gate_results. Never read by _decision_class()
    # or _score_candidate() — carrying no influence on Decision_Class,
    # R&D_Opportunity_Score, or ranking, except that its "safety" and
    # (as of Task 4) "regulatory" entries report (rather than change)
    # the same hard, non-compensatory exclusions _decision_class()
    # already enforces via _hard_safety_gate()/_hard_regulatory_gate().
    "Gate_Results",
    # Task 3 — externalized, versioned scoring weights. Records WHICH
    # ScoringConfig this row's R&D_Opportunity_Score was computed with
    # (see ScoringConfig/DEFAULT_SCORING_CONFIG above and
    # self.scoring_config in __init__). Purely descriptive metadata —
    # never read back into scoring itself.
    "Scoring_Config_Version",
    # Task 10.2 — Evidence-level Preparation Applicability, candidate-
    # level summary. Additive only: see _summarize_applicability() and
    # CandidateAssessment.applicability_summary. Never read by
    # _decision_class(), _score_candidate(), _evaluate_gates(), or
    # go_investigate_hold_no_go() — carries no influence on
    # Decision_Class, Decision_Class_AH, R&D_Opportunity_Score, gate
    # outcomes, or ranking.
    "Applicability_Summary",
    # Task 2 — GRADE-style clinical-evidence certainty grading.
    # Additive only: see grade_certainty_classifier.py and
    # classify_grade_certainty(). Never read by _decision_class(),
    # _score_candidate(), _evaluate_gates(), or
    # go_investigate_hold_no_go() — carries no influence on
    # Decision_Class, Decision_Class_AH, R&D_Opportunity_Score, gate
    # outcomes, Evidence_Confidence, or ranking.
    "GRADE_Certainty",
    "GRADE_Certainty_Rationale",
    # NOTE (post-Task-5 rollback): an earlier version of this file also
    # computed Robustness_Analysis/Boundary_Fragility here, duplicating
    # sensitivity_display_adapter.py's existing, UI-facing
    # fragility_report()/build_robustness_analysis() calls (same
    # functions, same result_df, called a second time for no
    # additional consumer — neither column was ever read by anything
    # downstream of run()). Removed; sensitivity_display_adapter.py
    # (called from step_rd_candidates.py after run() returns) remains
    # the single source of truth for sensitivity/robustness analysis.
    # Do not re-add a second computation path here.
    # Phase 4 — Eligibility Gate. Structured, machine-readable fields so
    # downstream consumers (candidate_shortlisting.py, step_rd_candidates.py,
    # pharma_report_generator.py, candidate_output_adapter.py) never have
    # to regex Decision_Class text to know whether a row is a hard no-go,
    # incomplete, or needs expert review. See eligibility_gate.py.
    # Inserted before Decision_Engine_Version (not after it) so
    # test_task15_decision_engine_version_tracking.py's
    # `OUTPUT_COLUMNS[-1] == "Decision_Engine_Version"` invariant holds.
    "Eligibility_Status",
    "Hard_No_Go",
    "Eligible_For_Normal_Ranking",
    "Ranking_Partition",
    "Score_Validity",
    "Gate_Type",
    "Gate_Reason",
    "Gate_Evidence_IDs",
    # Structured six-class scientific decision. This is the authoritative
    # decision state for validation/consumers; legacy Decision_Class remains
    # for backward-compatible score-tier presentation.
    "Final_Decision_Status",
    # Correction round — finding-specific evidence traceability (not
    # just the row-level union above). See eligibility_gate.py's
    # SafetyFinding.evidence_ids / RegulatoryFinding.evidence_ids and
    # botanical_rd_candidate_engine.py's row-loop construction of
    # _safety_gate_evidence_ids / _regulatory_gate_evidence_ids.
    "Safety_Gate_Evidence_IDs",
    "Regulatory_Gate_Evidence_IDs",
    "Safety_Assertions",
    "Safety_Decision_Confidence",
    "Safety_Evidence_Conflict",
    "Safety_Severity_Rule",
    "Safety_Severity",
    "Safety_Scope",
    "Safety_Context_Relevance",
    "Regulatory_Status",
    "Regulatory_Scope",
    "Regulatory_Context_Relevance",
    "Data_Completeness",
    "Requires_Expert_Review",
    # Task 15 — reproducibility metadata only, appended last (not
    # inserted between existing analytical columns) so no historical
    # column ORDER assumption breaks. See DECISION_ENGINE_VERSION below
    # for what this value means and when it must change.
    "Decision_Engine_Version",
]


# ======================================================================
# Task 15 — Decision Engine Version Tracking.
#
# DECISION_ENGINE_VERSION identifies which version of THIS FILE's
# end-to-end decision logic (candidate assessment, evidence
# interpretation, applicability handling, hierarchy/confidence logic,
# gates, decision classification, and any other ranking-relevant
# engine behavior) produced a given candidate row / persisted decision
# record. It is reproducibility metadata ONLY — never read by
# _score_candidate(), _decision_class(), _evaluate_gates(),
# go_investigate_hold_no_go(), sorting, or filtering anywhere in this
# file. Setting or reading it has no effect on any candidate's score,
# rank, gate outcome, confidence, applicability, or decision class.
#
# THIS IS A SEPARATE CONCEPT FROM Scoring_Config_Version (Task 3).
# Scoring_Config_Version identifies which ScoringConfig (weights) was
# used; DECISION_ENGINE_VERSION identifies which version of the LOGIC
# itself (this file's code) was used. A single ScoringConfig can be
# run against multiple engine-logic versions over time, and a single
# engine-logic version can be run with multiple ScoringConfigs — they
# vary independently and must never be merged into one value or
# derived from one another.
#
# WHEN TO INCREMENT: any change that can alter a candidate's
# R&D_Opportunity_Score, Decision_Class, Decision_Class_AH, gate
# outcome (PASSED/FAILED/NOT_EVALUABLE for any gate), Evidence_Confidence,
# Applicability_Classification/Applicability_Summary content, or
# candidate ranking/ordering. Formatting-only, documentation-only, or
# report/presentation-only changes (e.g. Task 13.1-13.2C's report
# wiring, or this comment itself) do NOT require an increment — nothing
# about what a candidate IS changes when only how it's DISPLAYED
# changes.
#
# WHY A HARDCODED STRING, NOT DERIVED FROM GIT/TIMESTAMPS/PACKAGE
# METADATA: a persisted decision record must remain interpretable by
# someone reading it years later, outside any Git checkout, with no
# access to this repository's commit history or install environment.
# A hardcoded, manually-incremented string is the only thing that
# survives that — the same reasoning Task 3's Scoring_Config_Version
# already established for scoring weights.
# 1.0.1 — Phase 2A (regulatory-normalization audit): _market_status()
# no longer maps mere EMA/HMPC inventory presence to "Regulatory
# monograph exists". Inventory-only records now return "Listed in EMA
# HMPC inventory — monograph not established" instead, which falls
# through to the market-signal neutral-default component in
# _score_candidate() (+3) rather than the regulatory-monograph
# component (+2) — a real, small R&D_Opportunity_Score change for any
# inventory-listed-only candidate. Genuine monograph/traditional-use
# text is unaffected and still reaches the same scores as before.
# 1.0.2 — Phase 2D-A (canonical EMA connector wiring): _market_status()
# now consumes a per-run cached canonical EMA/HMPC connector result
# (self._canonical_regulatory_by_plant) instead of always seeing an
# empty EMA_Status. Concretely, for real data today, only two of the
# canonical categories are actually reachable through the live
# connector (verified_synonym/pharmacopoeial tables are still empty):
#   - exact_species_match -> Market_Status = "Listed in EMA HMPC
#     inventory — monograph not established" (was: "Search not
#     performed"/"Search incomplete")
#   - parsing_failed/source_unavailable -> Market_Status = "Source
#     unavailable" (new, distinct value; was collapsing into "Search
#     not performed")
# _score_candidate()'s market-signal component is UNCHANGED in value
# for both (neither string matches the "regulatory monograph"/
# "traditional-use" substring check, so both still fall to the same
# market_neutral_default as before) — so R&D_Opportunity_Score itself
# does not change for real data today. However, Market_Status the
# STRING does change, which has one confirmed real downstream effect:
# white_space_classifier.NO_SEARCH_MARKET_STATES does not include
# "Listed in EMA HMPC inventory — monograph not established", so a
# plant that used to read as "no market search happened" (blocking
# Regulatory White Space) can now read as "a search happened, and
# didn't confirm a monograph" (making Regulatory White Space reachable
# for that plant where it wasn't before). White_Space_Type itself was
# NOT modified — this is a real behavior change caused only by
# white_space_classifier.py now receiving a more informative input.
# 1.0.3 — Phase 2D-B (performance rollback/refinement of 1.0.2): 1.0.2's
# unbounded per-run canonical-EMA-cache build (self.
# _canonical_regulatory_by_plant populated for every unique alt-plant,
# potentially 1,000-2,000+) caused a confirmed Streamlit CPU-throttling
# regression in default Candidate Discovery — see the Phase 2D
# performance audit. That automatic build was removed; default
# Candidate Discovery no longer performs ANY canonical EMA/HMPC
# lookups (0, not "up to 30" — Option B, opt-in only, was chosen; see
# run()'s Phase 2D-B comment for why the bounded-final-set Option A
# was rejected: it would make Market_Status inconsistent with the
# Market_Status _score_candidate() actually scored). Market_Status
# reverts to exactly its pre-1.0.2 behavior (the canonical branches in
# _market_status() are unreachable again by default, not removed).
# Canonical EMA/HMPC data remains available exactly as it was before
# 1.0.2: through the separate, explicitly-capped (max_plants=30)
# enrich_candidates_with_market_landscape() action, in the
# Market_Landscape_EMA_HMPC_* columns — never in Market_Status itself
# unless a caller explicitly populates
# self._canonical_regulatory_by_plant before calling run().
DECISION_ENGINE_VERSION = "1.3.0"


# Task 10.2 — explicit allowlist for _build_evidence_text_index()'s
# self.evidence_df pass. Replaces the previous unconditional
# `str(value) for value in row.values` (every column, unfiltered).
#
# WHY: that unfiltered join meant any column added to evidence_df in
# the future automatically became part of the free text that
# classify_evidence_hierarchy()/classify_negative_evidence() pattern-
# match against for Evidence_Hierarchy_Detail/Has_Negative_Evidence.
# Task 10.2 adds several PLATFORM-GENERATED interpretation columns
# (Applicability_Classification/_Rationale/_Evaluated_Dimensions/
# _Missing_Dimensions/_Detected_Mismatches) to that same DataFrame —
# feeding platform-generated interpretation back into the classifiers
# that interpretation was itself derived from is a feedback loop, not
# scientific source evidence, and must not happen.
#
# This list was built by auditing database.load_evidence_records()'s
# actual row-dict keys (the only place self.evidence_df's columns are
# defined) — no column name here is invented, and none of the excluded
# columns are removed from evidence_df itself, only from this text
# concatenation.
#
# Excluded, deliberately:
#   - Applicability_Classification / _Rationale / _Evaluated_Dimensions
#     / _Missing_Dimensions / _Detected_Mismatches (Task 10.2, this
#     task's own generated output)
#   - Direct_For_Selected_Product / Directness_Reason ("directness
#     interpretation" — pre-existing platform-generated interpretation,
#     was already leaking into this index before this task; corrected
#     here per the same principle)
#   - Plant_ID / Evidence_Record_ID (identifiers, not scientific text)
EVIDENCE_TEXT_INDEX_ALLOWLIST = (
    "Scientific_Name", "Common_Name", "Plant",
    "Product_Type", "Dosage_Form", "Target_Indication", "Target_Market",
    "EMA_Status", "WHO_Status", "ESCOP_Status",
    "Clinical_Level", "Clinical_RCT_Count", "Meta_Level", "Meta_Count",
    "Dosage_Form_Evidence", "Infusion_Evidence",
    "Safety_Level", "Drug_Interaction_Level", "Commercial_Level",
    "Regulatory_Status", "Novel_Food_Status", "Notes",
    "Evidence_Type", "Evidence_Level", "Dosage_Form_Relevance", "Study_Model",
    "Detected_Dosage_Forms", "Detected_Indications", "Regulatory_Evidence",
    "Evidence_Score",
    "Study_Type", "Dosage_Form_Detected", "Target_Indication_Detected",
    "Population", "Sample_Size", "Comparator", "Primary_Outcome",
    "Result_Direction", "Safety_Signal",
    "Reference_Count", "Source_Type", "Source_Title",
    "Source_Organization", "Source_Year", "Source_URL",
)

# TECHNICAL DEBT NOTE (post-Task-10.2 correction — scope explicitly NOT
# widened here; recorded for the future ScientificEvidence/source-
# assertion separation task).
#
# This allowlist was built by excluding only the fields Task 10.2 itself
# identified as platform-generated interpretation (the 5 new
# Applicability_* fields, plus Direct_For_Selected_Product/
# Directness_Reason). It was NOT audited for whether OTHER pre-existing
# columns above are themselves already partially interpreted rather
# than raw source text — several are plausible candidates for that
# same concern and deserve review under that future task, not this
# correction:
#   - Evidence_Type / Evidence_Level: can be set either from a
#     connector's own reported value OR from the optional LLM
#     extractor (llm_extractor.py) — an LLM-classified value re-entering
#     the same text index that other classifiers read is the same
#     shape of concern this task corrected for Applicability_*, just
#     pre-existing and out of THIS correction's scope.
#   - Dosage_Form_Relevance / Detected_Dosage_Forms / Detected_Indications:
#     also LLM-derived when the optional LLM path runs, not always raw
#     source text.
#   - EMA_Status / WHO_Status / ESCOP_Status: can carry either a real
#     connector's descriptive output or (historically) the disabled
#     legacy stub's literal "Yes" (see ARCHITECTURE.md Sprint 5) —
#     interpretation-shaped either way.
# None of these are touched by this correction — narrowing this
# allowlist further is a decision for the ScientificEvidence activation/
# source-assertion separation task, where the distinction between "raw
# source assertion" and "platform-derived interpretation" is the task's
# actual subject, not a side effect of a merge-counting bugfix.



SIMILAR_COMPOUND_GROUPS = {
    "flavonoid": [
        "apigenin", "luteolin", "quercetin", "kaempferol", "rutin",
        "vitexin", "isovitexin", "orientin", "chrysin",
        "baicalin", "baicalein", "wogonin", "spinosin", "tiliroside",
    ],
    "phenolic acid": [
        "rosmarinic acid", "caffeic acid", "chlorogenic acid",
        "gallic acid", "ellagic acid",
    ],
    "terpene_or_volatile": [
        "linalool", "linalyl acetate", "citral", "bisabolol",
        "chamazulene", "thymol", "carvacrol", "menthol",
        "eugenol", "bornyl acetate", "terpinen-4-ol",
    ],
    "saponin": [
        "gypenosides", "saponins", "jujubosides", "sitoindosides",
    ],
    "lactone": [
        "kavalactones", "kavain", "yangonin",
        "valerenic acid", "valepotriates",
    ],
    "withanolide": [
        "withanolides", "withaferin a",
    ],
}


SAFETY_TERMS = [
    "toxicity", "toxic", "hepatotoxic", "cytotoxic", "adverse",
    "contraindication", "contraindicated", "pregnancy",
    "breastfeeding", "allergy", "warning", "caution",
]


# Dr. Duke's own Known_Target/activity vocabulary already documents some
# compounds as having concerning properties (e.g. "Lithogenic" = promotes
# kidney stone formation, "Emetic" = induces vomiting) — this is
# structured data already present in every row, not something that needs
# a literature search to discover. Previously, safety flagging only
# scanned free-text evidence collected from PubMed/EMA/etc, so a
# compound could be labelled "Lithogenic; Inflammatory" in its own
# Target_or_Mechanism column and still be presented as an unflagged
# "Recommended" candidate. These terms are checked against the
# mechanism/target text directly, in addition to SAFETY_TERMS being
# checked against free-text evidence — for any compound, any plant, any
# indication.
DB_ACTIVITY_SAFETY_TERMS = [
    "lithogenic", "emetic", "hepatotoxic", "nephrotoxic", "neurotoxic",
    "carcinogenic", "mutagenic", "teratogenic", "abortifacient",
    "convulsant", "narcotic", "poison", "vesicant", "hemolytic",
    "nephrotoxin", "hepatotoxin", "genotoxic", "embryotoxic",
    "cardiotoxic", "irritant",
]

# Two tiers, because these are not equally trustworthy signals:
#
# HARD_SAFETY_TERMS — a clear, direct physiological/mechanical/
# reproductive mechanism with no common "protective against" research
# framing to confuse it with (kidney stones, induced abortion,
# convulsions, blistering, poisoning, blood-cell destruction). A
# candidate carrying one of these must never appear under "Recommended",
# regardless of score.
#
# CONTROVERSIAL_SAFETY_TERMS — two distinct families that share the same
# underlying problem: Dr. Duke's activity tags are extracted from
# publication text without distinguishing "compound X CAUSES this" from
# "compound X PROTECTS AGAINST this caused by something else".
#   1. The genotoxicity-assay family (carcinogenic/mutagenic/genotoxic)
#      — typically from decades-old in-vitro/bacterial (Ames-test-style)
#      or high-dose animal studies, without real-world dose/exposure
#      context.
#   2. The organ-toxicity family (hepatotoxic/nephrotoxic/cardiotoxic/
#      neurotoxic) — verified this is a real, systematic mislabeling
#      risk, not a one-off: "flavonoid protects against
#      doxorubicin-induced cardiotoxicity", "...cisplatin-induced
#      nephrotoxicity", "...against drug-induced hepatotoxicity" are
#      each themselves extremely common, standard study designs across
#      hundreds of published papers on plant compounds — a naive
#      extraction pass over that literature will tag the PROTECTIVE
#      compound with the organ-toxicity word just as readily as it would
#      tag an actual causative agent. Quercetin is the clearest confirmed
#      case (LiverTox/NIH: "well tolerated... not linked to serum enzyme
#      elevations or clinically apparent liver injury... likelihood
#      score E [unlikely cause]", while numerous studies show it
#      protecting against hepatotoxicity induced by other agents) — but
#      the same "protects against X-induced Y-toxicity" paradigm is
#      equally standard for nephro-, cardio-, and neuro-toxicity, so the
#      same risk applies to all four, for any compound, not just this
#      one.
# These stay flagged and visible (Safety_Flags, Rationale, and a capped
# score — never "Strong") but do NOT auto-exclude a candidate from
# "Recommended" the way HARD_SAFETY_TERMS does — a human reviewer needs
# to read the actual finding and weigh dose/context/causal direction,
# not have it decided for them by a keyword co-occurrence. "Emetic" and
# "Irritant" are milder still and are excluded from both hard tiers for
# the same reason.
HARD_SAFETY_TERMS = (set(DB_ACTIVITY_SAFETY_TERMS) - {
    "emetic", "irritant",
    "carcinogenic", "mutagenic", "genotoxic",
    "hepatotoxic", "hepatotoxin", "nephrotoxic", "nephrotoxin",
    "cardiotoxic", "neurotoxic",
}) | {
    # Critical Safety False-Negative remediation (Case 006) — the
    # ONE additional term the structured interaction/contraindication
    # classifier (interaction_severity_classifier.py) can contribute.
    # This is the single, narrow, documented exception to "free text
    # cannot reach HARD_SAFETY_TERMS" (see that module's docstring):
    # it is reachable ONLY via classify_interaction_assertion()
    # resolving to a SERIOUS_* tier (explicit contraindication/
    # interaction assertion language AND a recognized high-risk
    # interacting drug class), never via a bare hazard word or
    # substring match against this string directly. Still disjoint
    # from SAFETY_TERMS (the softer free-text vocabulary) — see
    # test_hard_safety_terms_and_safety_terms_still_disjoint_except_for_structured_interaction_signal
    # in test_structured_serious_interaction_gate_fix.py.
    _INTERACTION_HARD_GATE_SIGNAL_TERM,
}
CONTROVERSIAL_SAFETY_TERMS = {
    "carcinogenic", "mutagenic", "genotoxic",
    "hepatotoxic", "hepatotoxin", "nephrotoxic", "nephrotoxin",
    "cardiotoxic", "neurotoxic",
}

# Task 4 — activating the regulatory gate as a second, non-compensatory
# hard stop on Decision_Class, alongside the existing hard-safety
# exclusion. A documented explicit "Prohibited / banned" regulatory
# finding is exactly as decisive a reason to stop as a documented hard
# safety term: no score, market signal, or mechanistic plausibility
# should be able to compensate for either. See _hard_regulatory_gate()
# and _decision_class()'s early-return for where this is enforced, and
# HARD_STOP_DECISION_CLASSES below for where the two hard-stop strings
# are treated as equally "worst" during multi-compound merging.
REGULATORY_PROHIBITION_DECISION_CLASS = (
    "Regulatory prohibition — not suitable without regulatory review"
)
HARD_STOP_DECISION_CLASSES = {
    "Safety concern — not suitable without expert review",
    REGULATORY_PROHIBITION_DECISION_CLASS,
}


INTERACTION_TERMS = [
    "drug interaction", "interaction", "cyp", "cytochrome",
    "warfarin", "anticoagulant", "antiplatelet", "ssri", "maoi",
    "benzodiazepine", "sedative", "hypoglycemic",
    "antidiabetic", "antihypertensive",
]


EXTRACTION_KEYWORDS = {
    "aqueous / infusion": [
        "aqueous", "water", "infusion", "decoction", "tea",
    ],
    "hydroalcoholic": [
        "hydroalcoholic", "hydroethanolic", "ethanol-water",
    ],
    "ethanolic": [
        "ethanol", "ethanolic",
    ],
    "essential oil / distillation": [
        "essential oil", "volatile oil", "steam distillation", "distillation",
    ],
    "co2 extract": [
        "co2", "supercritical",
    ],
}


# Generic/connector words that appear across many different indication
# names (e.g. "Joint & muscle comfort" and "Metabolic & blood sugar
# support" both contain "&" and "support"). These must be excluded from
# any token-overlap fallback matching, otherwise unrelated indications
# get falsely linked just because they share a filler word.
INDICATION_STOPWORDS = {
    "&", "/", "-", "and", "or", "of", "for", "in", "on", "the", "a", "to",
    "support", "health", "comfort", "care", "wellness", "relief",
}

# Precomputed once at import time so _curated_evidence_for() is an O(1)
# dict lookup instead of a linear scan (with a _norm() call per item)
# repeated on every single output row.
_SLEEP_TEA_EVIDENCE_NORM_MAP = {
    re.sub(r"\s+", " ", name.strip().lower()): evidence
    for name, evidence in SLEEP_TEA_EVIDENCE.items()
}


# =====================================================================
# Task 3 — Externalized, versioned scoring weights.
#
# WHAT THIS IS
# _score_candidate()'s section-level weights (the ones already named
# and documented in that method's own "COMPLETE WEIGHTS TABLE"
# docstring) are collected here as a single, named, versioned object
# instead of being bare inline literals. DEFAULT_SCORING_CONFIG's
# values are IDENTICAL to what _score_candidate() computed before this
# task existed — verified by a byte-identical regression test
# (test_default_scoring_config_reproduces_identical_scores_to_pre_task_hardcoded_values
# in test_scoring_config.py). This is a governance/visibility change,
# not a scoring change.
#
# WHAT THIS IS NOT
# This does not externalize every numeric literal in the engine.
# _extraction_fit_score()'s internal keyword-matching weights (its own
# separate, smaller "up to 26, capped at 18 when folded into Product-
# development fit" sub-scores) are deliberately left as an internal
# implementation detail of that one helper, not promoted into
# ScoringConfig — they already feed into Product-development fit as a
# single already-capped number, and pulling them out too would balloon
# this change far past "the smallest possible extension" without a
# proportionate governance benefit. If per-keyword extraction weights
# ever need to be independently configurable, that is a deliberately
# separate, later, smaller change — not part of Task 3.
#
# HOW THIS IS USED
# BotanicalRDCandidateEngine.__init__ accepts an optional
# scoring_config: ScoringConfig, defaulting to DEFAULT_SCORING_CONFIG,
# stored as self.scoring_config. _score_candidate() reads
# self.scoring_config.<field> in place of each of these values' former
# bare literals — nothing else about _score_candidate()'s control flow,
# rounding, clamping, or section structure changes.
# =====================================================================

@dataclass(frozen=True)
class ScoringConfig:
    """Named, versioned scoring weights for _score_candidate(). See the
    Task 3 block comment above this class for what is and is not
    covered. Every default below is copied verbatim from
    _score_candidate()'s pre-Task-3 inline literals — see that
    method's own "COMPLETE WEIGHTS TABLE" docstring, which this
    dataclass's field values must always match."""

    version: str = "1.0-default"

    # 1) Chemical/mechanistic link (base points, before the
    # target-specificity and commonality modifiers, which stay as
    # multiplicative logic in _score_candidate() rather than becoming
    # separate config fields — they're formulas, not weights).
    chem_link_exact: float = 22
    chem_link_target_verified: float = 15
    chem_link_class_only: float = 5

    # 2) Evidence quality, by Evidence_Level.
    evidence_clinical: float = 24
    evidence_regulatory: float = 20
    evidence_preclinical: float = 12
    evidence_general_literature: float = 7
    evidence_none: float = 0

    # 3) Product-development fit.
    product_fit_concentration_reported: float = 10
    product_fit_concentration_missing: float = 2
    product_fit_extraction_cap: float = 18
    product_fit_co_compound_per_item: float = 2
    product_fit_co_compound_cap: float = 8
    product_fit_target_identified: float = 8
    product_fit_target_missing: float = 1

    # 4) Novelty (only awarded when evidence_level != "No direct evidence").
    novelty_common: float = 0
    novelty_alternative: float = 10
    novelty_other: float = 2

    # 5) Market signal. Sourced from phase5_scoring_config.MARKET_STATUS_POINTS
    # (single central place, Phase 5 §1/§10) -- not copied literals.
    market_verified_marketed_product: float = MARKET_STATUS_POINTS["Verified marketed product"]
    market_regulatory_monograph_or_traditional_use: float = MARKET_STATUS_POINTS["Regulatory monograph exists"]
    market_commercial_evidence_reported: float = MARKET_STATUS_POINTS["Commercial evidence reported"]
    market_no_verified_product_found: float = MARKET_STATUS_POINTS["No verified product found"]
    market_conflicting_evidence: float = MARKET_STATUS_POINTS["Conflicting evidence"]
    market_search_incomplete: float = MARKET_STATUS_POINTS["Search incomplete"]
    # "Search not performed" / "Source unavailable" / "Unknown" — the
    # neutral default when no real search signal exists either way.
    # PHASE 5 FIX (addendum §10, main audit §3.1): this used to be +3,
    # which scored ABOVE a verified positive market finding (+1) —
    # confirmed defect. Now neutral 0.0, sourced from the central config.
    market_neutral_default: float = MARKET_STATUS_POINTS["Unknown"]

    # 6) Safety/interaction/self-row penalties.
    safety_flag_penalty: float = -14
    interaction_flag_penalty: float = -10
    same_plant_penalty: float = -15


# The single default instance every engine uses unless a caller
# explicitly overrides it — this is what makes DEFAULT_SCORING_CONFIG
# the "1.0-default" version referenced anywhere scoring_config_version
# appears in output (see CandidateAssessment.scoring_config_version).
DEFAULT_SCORING_CONFIG = ScoringConfig()


# Task 7 — precomputed once at import time, same reasoning as
# _SLEEP_TEA_EVIDENCE_NORM_MAP just above: an O(1) dict lookup instead
# of scanning seed_data.PLANT_COMPOUNDS per row. See occurrence_seed.py
# for what this is derived from (entirely seed_data.py's own existing
# data — no new botanical claims).
_OCCURRENCE_LOOKUP = build_occurrence_lookup()


class BotanicalRDCandidateEngine:
    """
    Central engine for botanical R&D candidate discovery.

    It starts from a product/problem and produces a decision table for
    alternative or better botanical R&D candidates.

    This engine replaces scattered logic from:
    ranking, market, white-space, knowledge extraction, target discovery,
    mechanism discovery, target-compound-plant discovery, graph, and
    botanical substitution.
    """

    def __init__(
        self,
        evidence_df=None,
        candidate_data=None,
        use_live_search=True,
        plant_compounds_df=None,
        compound_profiles_df=None,
        scientific_evidence_df=None,
        evidence_records_df=None,
        data_source_reliable=True,
        scoring_config=None,
    ):
        # Task 3 — externalized, versioned scoring weights. Defaults to
        # DEFAULT_SCORING_CONFIG (byte-identical to the pre-Task-3
        # hardcoded values) unless a caller explicitly overrides it.
        self.scoring_config = scoring_config if scoring_config is not None else DEFAULT_SCORING_CONFIG

        self.evidence_df = self._to_dataframe(evidence_df)
        self.use_live_search = use_live_search

        # Task 11.1 — default before run() has built the real index
        # (see run()'s own call to _build_scientific_evidence_index()).
        # Empty, never None, so a caller that reads this before calling
        # run() gets a valid empty dict rather than an AttributeError.
        self.scientific_evidence_index = {}

        # Phase 2D-A / 2D-B — default, and (as of 2D-B's performance
        # correction) the value default Candidate Discovery keeps
        # throughout run() — see run()'s Phase 2D-B comment for why
        # the unbounded per-run rebuild Phase 2D-A added was removed.
        # Empty, never None/missing, so _market_status() (via a
        # defensive getattr(self, "_canonical_regulatory_by_plant", {}))
        # and any test/caller constructing an engine via __new__()
        # without __init__() stay safe rather than hitting an
        # AttributeError. Keyed by exact Scientific_Name string;
        # each value is _eu_regulatory_status()'s own full structured
        # result dict (EMA_HMPC_Match_Category, EMA_HMPC_Status,
        # EMA_HMPC_Detail, EMA_Source, ...) — never reduced to just the
        # compact display string, so _market_status() never has to
        # re-derive the match category from text. A caller that wants
        # canonical EMA data in Market_Status (rather than only in the
        # separate Market_Landscape_EMA_HMPC_* columns from
        # enrich_candidates_with_market_landscape()) may still populate
        # this dict explicitly before calling run() — the consuming
        # logic in _market_status() is intentionally still fully wired.
        self._canonical_regulatory_by_plant = {}

        # Real Supabase tables (806 / 310 / 47 records as of the last known
        # snapshot) are the primary data source. Any of them can be passed
        # in explicitly (e.g. for tests); otherwise they're fetched live.
        # If Supabase is unreachable, these come back empty and the engine
        # falls back to the small local seed dataset further below.
        self.plant_compounds_df, pc_ok = self._load_supabase_df(
            plant_compounds_df, load_plant_compounds_df
        )
        self.compound_profiles_df, cp_ok = self._load_supabase_df(
            compound_profiles_df, load_compound_profiles_df
        )
        self.scientific_evidence_df, se_ok = self._load_supabase_df(
            scientific_evidence_df, load_scientific_evidence_df
        )
        self.evidence_records_df, er_ok = self._load_supabase_df(
            evidence_records_df, load_evidence_records_df
        )

        # External review #17/#19: a "Go" recommendation must never
        # rest on data that may not have actually loaded. data_source_reliable
        # (constructor param) carries whatever the CALLER already knows
        # (e.g. step_rd_candidates.py's _cached_engine, which tracks
        # each Supabase load's real success/failure before this
        # constructor ever runs) — ANDed here with whatever THIS
        # constructor detects on its own, for any DataFrame it had to
        # load itself (e.g. a caller that didn't pre-load, or a test
        # that omits data_source_reliable entirely). See
        # structured_rationale.go_investigate_hold_no_go's
        # fallback_occurred parameter for where this is actually used.
        self.data_source_reliable = (
            bool(data_source_reliable) and pc_ok and cp_ok and se_ok and er_ok
        )

        if candidate_data is not None:
            self.candidate_data = candidate_data
            self.candidate_source = "override"
        elif not self.plant_compounds_df.empty:
            self.candidate_data = self._candidates_from_plant_compounds()
            self.candidate_source = "supabase"
        else:
            # GLOBAL_PLANT_CANDIDATES alone (35 plants, each hand-tagged
            # with Indications) is used for REFERENCE-plant selection.
            # But it's noticeably smaller than seed_data.PLANT_COMPOUNDS
            # (48+ plants) — so alternative-plant matching was silently
            # blind to any plant only present in PLANT_COMPOUNDS (e.g.
            # Eschscholzia californica never got considered as an
            # isoquinoline-alkaloid alternative to Berberis vulgaris).
            # Merge in every seed_data plant not already covered, with no
            # Indications tag (so it still can't be picked as a
            # reference plant via indication text-matching — only as an
            # alternative-plant match target), to make alt-plant search
            # cover the full local dataset.
            self.candidate_data = (
                GLOBAL_PLANT_CANDIDATES + self._seed_data_only_candidates()
            )
            self.candidate_source = "local_fallback"

        self.compound_to_class, self.compound_to_targets, self.compound_to_target_sources = (
            self._build_compound_indexes()
        )

        self.target_compound_count, self.target_genericity_threshold = (
            self._build_target_frequency_index(self.compound_to_targets)
        )

        # Compound "commonality" index: for every compound, how many
        # DISTINCT plants (across the whole database, regardless of
        # indication) contain it. This is deliberately generic — it is
        # not tied to any specific plant, compound, or indication, so it
        # applies the same way whether the query is about sleep, cough,
        # skin, metabolic health, or anything else added later.
        #
        # The problem this fixes: a compound like an abundant, widely
        # distributed flavonoid can appear in hundreds/thousands of
        # unrelated plants. Before this, an "exact" name match on such a
        # compound scored identically to an exact match on a genuinely
        # rare, differentiating compound — so ubiquitous compounds
        # silently dominated Step 5/6 results for ANY indication, not
        # just one. The threshold below is derived from the actual
        # distribution of compound frequencies in whatever database is
        # loaded (90th percentile), so it self-adjusts as the database
        # grows or shrinks instead of being a hardcoded number tuned to
        # today's data.
        self.compound_plant_count, self.compound_commonality_threshold = (
            self._build_compound_frequency_index()
        )

        # A compound-specific (NOT plant-pooled) target/activity index,
        # built directly from Dr. Duke's raw data: compound -> the set of
        # activities recorded for THAT compound specifically, across
        # every plant it appears in. This is deliberately separate from
        # self.compound_to_targets (the small hand-curated
        # COMPOUND_TARGETS/compound_profiles set used for class-based
        # "target_verified" matching) — that dict doesn't cover most of
        # Dr. Duke's ~2,000+ plant database, so using it for safety
        # flagging would silently miss real DB-documented hazards like
        # Calcium Oxalate's "Lithogenic" tag. This index is used ONLY for
        # safety-flag lookups, scoped to the one compound actually
        # matched in each row — not the alternative plant's entire pooled
        # activity profile across all of its other, unrelated compounds.
        self.compound_own_targets = self._build_compound_target_index()

    def _build_compound_target_index(self):
        df = self.plant_compounds_df

        if (
            df is None or df.empty
            or "compound_name" not in df.columns
            or "target" not in df.columns
        ):
            return {}

        index = defaultdict(set)
        grouped = df.groupby(
            df["compound_name"].fillna("").map(self._norm)
        )["target"]

        for compound_norm, values in grouped:
            if not compound_norm:
                continue
            index[compound_norm].update(self._split_series_terms(values))

        return dict(index)

    def _build_compound_frequency_index(self):
        df = self.plant_compounds_df

        if (
            df is None or df.empty
            or "scientific_name" not in df.columns
            or "compound_name" not in df.columns
        ):
            return {}, None

        work = df[["scientific_name", "compound_name"]].copy()
        work["scientific_name"] = work["scientific_name"].fillna("").astype(str).str.strip()
        work["compound_norm"] = work["compound_name"].fillna("").map(self._norm)
        work = work[(work["scientific_name"] != "") & (work["compound_norm"] != "")]

        if work.empty:
            return {}, None

        counts = (
            work.drop_duplicates(["scientific_name", "compound_norm"])
            .groupby("compound_norm")["scientific_name"]
            .nunique()
        )

        plant_count_map = counts.to_dict()

        # 90th percentile of how many distinct plants each compound
        # appears in = "this compound is in the top 10% most common
        # compounds in our own database". A small floor keeps this
        # meaningful even on a tiny/sparse database (avoids flagging
        # compounds as "common" just because everything is rare so far).
        if len(counts) >= 5:
            threshold = max(float(counts.quantile(0.90)), 8.0)
        else:
            threshold = max(float(counts.max()) + 1, 8.0)

        return plant_count_map, threshold

    def _compound_commonality(self, compound_label):
        """Returns (plant_count, is_common) for a compound label that may
        include the '[similar: ...]' suffix added by _match_compounds."""
        if not compound_label:
            return 0, False

        clean = compound_label.split("[")[0].strip()
        count = self.compound_plant_count.get(self._norm(clean), 0)

        is_common = (
            self.compound_commonality_threshold is not None
            and count >= self.compound_commonality_threshold
        )

        return count, is_common

    def run(
        self,
        indication,
        dosage_form="",
        market="",
        reference_plant="",
        reference_compound="",
        product_type=None,
        max_reference_plants=12,
        discovery_mode="compound_substitution",
        progress_callback=None,
    ):
        if discovery_mode == "indication":
            from indication_candidate_discovery import discover_indication_candidates
            return discover_indication_candidates(
                self, indication=indication, dosage_form=dosage_form, market=market,
                product_type=product_type or (dosage_form or "botanical product"),
                progress_callback=progress_callback,
            )
        if discovery_mode not in {"compound_substitution", "legacy"}:
            raise ValueError("discovery_mode must be indication or compound_substitution")

        problem = indication
        product_type = product_type or (dosage_form or "botanical product")

        all_candidates = self._candidate_frame()

        if reference_plant:
            # A user who explicitly names a reference plant already knows
            # their starting point — they shouldn't be at the mercy of
            # whatever (at most `max_reference_plants`, default 12)
            # plants the indication-based selection happens to surface
            # first. Previously this searched only within that small,
            # indication-restricted shortlist post-hoc (line below used
            # to be `for _, ref in references.iterrows()` where
            # `references` came from _get_reference_plants() BEFORE this
            # name filter ran) — if the named plant wasn't among those
            # first ~12 candidates, EVERY row got filtered out and Step 5
            # silently returned "No R&D candidates found", regardless of
            # whether the plant actually exists in the database at all.
            # Searching the full, unrestricted candidate universe here
            # instead means an explicitly-named reference plant is found
            # whenever it exists anywhere in the database, for any
            # indication, any plant.
            #
            # _norm_taxon (not just _norm) is used for this comparison:
            # many real botanical database entries use full taxonomic
            # nomenclature — a hybrid marker ("×"/" x ") and
            # infraspecific rank qualifiers ("subsp.", "var.", "f.",
            # "cv.") — that a person typing a common working name (e.g.
            # "Mentha piperita" for what the database has filed as
            # "Mentha x piperita subsp. nothosubsp. piperita") won't
            # include. Plain substring matching breaks here because the
            # hybrid marker sits in the middle, splitting what would
            # otherwise be a clean substring match. Stripping these
            # taxonomic embellishments before comparing (for matching
            # purposes only — the database's full name is still what's
            # displayed and used downstream) fixes this for any hybrid
            # or infraspecific taxon, not just this one species.
            name_norm = self._norm_taxon(reference_plant)
            references = all_candidates[
                all_candidates["Scientific_Name"].map(self._norm_taxon).apply(
                    lambda n: name_norm in n or n in name_norm
                )
            ]
        else:
            references = self._get_reference_plants(
                problem=problem,
                dosage_form=dosage_form,
                market=market,
                max_reference_plants=max_reference_plants,
            )

        if references.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        rows = []
        (
            evidence_index,
            evidence_source_index,
            evidence_applicability_index,
            evidence_authority_index,
            evidence_records_index,
        ) = self._build_evidence_text_index()

        # Task 11.1 — built once per run(), exposed as an instance
        # attribute (self.scientific_evidence_index), NOT as a new
        # OUTPUT_COLUMNS/DataFrame column — rule 7 of this task is to
        # preserve every existing public output unchanged. This index
        # is a capability for callers that want structured, typed
        # access to one exact evidence record (by id), not a value
        # that appears in the result table.
        self.scientific_evidence_index = self._build_scientific_evidence_index()

        # Precompute the alternative-candidate list ONCE, outside the
        # reference/compound loops below. Previously `all_candidates
        # .iterrows()` re-ran inside the innermost loop — once per
        # (reference plant × reference compound) — rebuilding pandas
        # Series objects for every one of the (now 2,000+, since the
        # Dr. Duke's import) alt-candidate rows on every single
        # iteration. With dozens of reference compounds that meant this
        # full scan happened dozens of times instead of once, which is
        # what made run() take minutes instead of seconds at this scale.
        alt_candidate_records = []
        for _, alt in all_candidates.iterrows():
            alt_plant = self._pick(alt, ["Scientific_Name"])
            if not alt_plant:
                continue
            alt_targets = self._split_terms(
                self._pick(alt, ["Known_Targets"])
            )
            alt_compounds = self._split_compound_terms(
                self._pick(alt, ["Known_Active_Compounds"])
            )
            alt_compound_norms = [self._norm(c) for c in alt_compounds]
            alt_candidate_records.append({
                "alt_plant": alt_plant,
                "alt_compounds": alt_compounds,
                "alt_compound_norms": alt_compound_norms,
                "alt_compound_norm_map": dict(
                    zip(alt_compound_norms, alt_compounds)
                ),
                "alt_targets": alt_targets,
                "alt_target_norms": [self._norm(t) for t in alt_targets],
                "row": alt,
            })

        # Phase 2D-B (performance correction) — Phase 2D-A built
        # self._canonical_regulatory_by_plant HERE, unconditionally,
        # for every unique alt-plant (potentially 1,000-2,000+, per the
        # "Dr. Duke's" scale noted elsewhere in this file). That is
        # exactly the unbounded-lookup cost
        # enrich_candidates_with_market_landscape()'s own docstring
        # (below) already warned against avoiding: "NOT called by
        # run() itself ... baking that into every default run without
        # review is exactly the unreviewed cost/latency change earlier
        # passes ... deliberately avoided." Phase 2D-A violated that
        # principle and caused a confirmed Streamlit CPU-throttling
        # regression (see the Phase 2D performance audit).
        #
        # DESIGN DECISION (Option B, per the audit): canonical EMA
        # enrichment stays opt-in via the pre-existing, separate,
        # explicitly-capped enrich_candidates_with_market_landscape()
        # path (max_plants=30 by default) — NOT built automatically
        # here. Option A (enrich only the bounded final
        # shortlist/top-candidates set, after row generation) was
        # considered and rejected: Market_Status already flows into
        # _score_candidate()'s market-signal component DURING row
        # generation, before any "final candidates" selection exists.
        # Patching Market_Status for only a bounded subset AFTER
        # scoring would make the displayed Market_Status inconsistent
        # with the Market_Status the score was actually computed from
        # — exactly the "internal inconsistency" this correction must
        # avoid, and _score_candidate() is explicitly out of scope to
        # touch or re-run in this phase.
        #
        # self._canonical_regulatory_by_plant therefore stays at its
        # __init__ default ({}) throughout default Candidate Discovery.
        # _market_status()'s canonical-aware branches (Phase 2D-A,
        # including the manually_curated correction) are left fully
        # intact — they simply have no cached entries to find, so every
        # lookup falls through to the pre-Phase-2D-A behavior, byte-
        # for-byte. The architecture is preserved; only the automatic,
        # unbounded population of it is removed. Canonical EMA/HMPC
        # data still reaches the user through the separate
        # Market_Landscape_EMA_HMPC_* columns via the opt-in "Enrich
        # with market/patent landscape" button, unchanged.

        # Index alt-candidates by exact compound name and by chemical
        # class, so matching a single reference compound is a couple of
        # dict lookups instead of a full scan of every alt-candidate (now
        # 2,000+ since the Dr. Duke's import). _match_compounds() itself
        # is left completely unchanged below — any alt-candidate NOT
        # reachable through either index is guaranteed to return "none"
        # from it anyway (no exact-string match and no shared chemical
        # class), so this is a pure speed-up, not a behavior change.
        exact_compound_index = defaultdict(set)
        class_compound_index = defaultdict(set)
        for alt_idx, rec in enumerate(alt_candidate_records):
            for norm_c in rec["alt_compound_norms"]:
                exact_compound_index[norm_c].add(alt_idx)
                cls = self.compound_to_class.get(norm_c, "")
                if cls:
                    class_compound_index[cls].add(alt_idx)

        for _, ref in references.iterrows():
            ref_plant = self._pick(
                ref,
                ["Scientific_Name", "scientific_name", "Plant", "plant"],
            )
            ref_plant_part = self._pick(ref, ["Plant_Part", "plant_part"])

            # No further reference_plant filtering needed here — the
            # `references` DataFrame built above (via _norm_taxon) is
            # already exactly the reference-plant-restricted set. An
            # older version of this function re-checked `reference_plant`
            # here too, using plain _norm instead of _norm_taxon — which
            # silently re-excluded the very row that had just been
            # correctly matched upstream whenever the database's full
            # taxonomic name (hybrid marker, subspecies, etc.) didn't
            # literally contain the plain user-typed name as a substring
            # (e.g. "Mentha piperita" vs "Mentha x piperita subsp.
            # nothosubsp. piperita"). Keeping a second, inconsistent
            # filter here defeats the fix above for any hybrid or
            # infraspecific taxon, not just this one.

            ref_compounds = self._split_compound_terms(
                self._pick(
                    ref,
                    [
                        "Known_Active_Compounds",
                        "compound_name",
                        "Compound",
                        "compound",
                    ],
                )
            )

            if reference_compound:
                filtered = [
                    compound for compound in ref_compounds
                    if self._norm(reference_compound) in self._norm(compound)
                ]
                ref_compounds = filtered or [reference_compound]

            ref_targets = self._split_terms(
                self._pick(
                    ref,
                    [
                        "Known_Targets",
                        "major_target",
                        "target",
                        "mechanism",
                    ],
                )
            )
            ref_target_norms = {self._norm(t) for t in ref_targets}

            for ref_compound in ref_compounds:
                if not ref_compound:
                    continue

                ref_norm = self._norm(ref_compound)
                ref_class = self.compound_to_class.get(ref_norm, "")

                candidate_idxs = set(exact_compound_index.get(ref_norm, ()))
                if ref_class:
                    candidate_idxs |= class_compound_index.get(ref_class, set())

                for alt_idx in candidate_idxs:
                    alt_record = alt_candidate_records[alt_idx]
                    alt_plant = alt_record["alt_plant"]
                    alt_compounds = alt_record["alt_compounds"]
                    alt = alt_record["row"]
                    alt_plant_part = self._pick(alt, ["Plant_Part", "plant_part"])

                    matched_compound, match_quality, target_specificity, target_provenance = (
                        self._match_compounds(
                            ref_compound,
                            alt_compounds,
                            alt_norm=alt_record["alt_compound_norm_map"],
                        )
                    )

                    if not matched_compound:
                        continue

                    raw_evidence, evidence_source_ids, evidence_authority_factor, evidence_contributing_records = (
                        self._collect_raw_evidence(
                            evidence_index=evidence_index,
                            plant=alt_plant,
                            compound=matched_compound,
                            problem=problem,
                            source_index=evidence_source_index,
                            authority_index=evidence_authority_index,
                            records_index=evidence_records_index,
                        )
                    )

                    has_real_evidence = bool(raw_evidence.strip())
                    evidence_level = self._evidence_level(raw_evidence)
                    evidence_hierarchy_detail = classify_evidence_hierarchy(raw_evidence)
                    negative_evidence = classify_negative_evidence(raw_evidence)

                    # Phase 1 (audit: Study_Design vs Evidence_Direction
                    # must be independent) — see evidence_interpretation.py
                    # for the full rationale. Study_Design and
                    # Evidence_Direction are stored as their own columns
                    # below; evidence_direction_contribution is the ONLY
                    # value this feeds into _score_candidate(), and only
                    # replaces the Clinical-evidence tier's contribution
                    # (Regulatory/Preclinical/General-literature tier
                    # weights are untouched — out of Phase 1 scope).
                    #
                    # Phase 3, problem 1 — evidence_authority_factor is now
                    # the REAL per-source Source Authority factor derived
                    # from whichever evidence_df row(s) actually contributed
                    # `raw_evidence` at this compound/problem/plant key (see
                    # _collect_raw_evidence()), not a hardcoded 1.0. It can
                    # only scale contribution's magnitude toward/away from
                    # zero — never its sign — exactly like quality_factor
                    # and applicability_factor already do inside
                    # interpret_evidence().
                    evidence_interpretation_result = interpret_evidence(
                        raw_evidence,
                        clinical_weight=self.scoring_config.evidence_clinical,
                        source_authority_factor=evidence_authority_factor,
                    )
                    study_design = evidence_interpretation_result.study_design
                    evidence_direction = evidence_interpretation_result.evidence_direction
                    evidence_quality_label = evidence_interpretation_result.evidence_quality
                    evidence_applicability_label = evidence_interpretation_result.evidence_applicability
                    evidence_direction_contribution = (
                        evidence_interpretation_result.contribution
                    )

                    extraction = self._best_extraction(
                        alt, raw_evidence, alt_plant=alt_plant, matched_compound=matched_compound,
                    )
                    concentration = self._extract_concentration(raw_evidence)
                    industrial_feasibility = classify_industrial_feasibility(
                        extraction_fit_score=self._extraction_fit_score(extraction, dosage_form),
                        has_concentration_data=bool(concentration),
                    )
                    co_compounds = self._co_compounds(
                        compounds=alt_compounds,
                        matched=matched_compound,
                        compound_norms=alt_record["alt_compound_norms"],
                    )

                    target = self._target_or_mechanism_fast(
                        ref_targets,
                        ref_target_norms,
                        alt_record["alt_targets"],
                        alt_record["alt_target_norms"],
                    )

                    # Free-text safety terms found in collected literature
                    # evidence, PLUS concerning activities the database
                    # itself already documents for the SPECIFIC matched
                    # compound (e.g. "Lithogenic", "Emetic").
                    #
                    # Deliberately NOT using `target` here: for
                    # "class_only" matches (no confirmed shared target),
                    # `target` falls back to the alt plant's WHOLE pooled
                    # activity list across every compound it has — not
                    # just the one that's actually shared/matched. Using
                    # that broad fallback for a safety decision meant one
                    # unrelated compound out of dozens in a plant's full
                    # profile (Dr. Duke's data tags compounds with every
                    # activity ever reported anywhere, including from
                    # old/edge-case studies) could flag every single
                    # candidate row for that plant as a "safety concern",
                    # regardless of whether the flagged activity had
                    # anything to do with the compound actually being
                    # proposed. Looking up only the matched compound's own
                    # known activities keeps this precise, for any
                    # compound, any plant, any indication.
                    matched_clean = matched_compound.split("[")[0].strip()
                    matched_own_targets = self.compound_own_targets.get(
                        self._norm(matched_clean), set()
                    )

                    safety_flags = self._extract_flags_negation_aware(
                        raw_evidence,
                        SAFETY_TERMS,
                    )
                    db_safety_flags = self._extract_hazard_flags_exact(
                        matched_own_targets,
                        DB_ACTIVITY_SAFETY_TERMS,
                    )
                    if db_safety_flags:
                        pieces = []
                        if safety_flags:
                            pieces.extend(safety_flags.split("; "))
                        pieces.extend(db_safety_flags.split("; "))
                        safety_flags = "; ".join(sorted(set(pieces)))

                    interaction_flags = self._extract_flags_negation_aware(
                        raw_evidence,
                        INTERACTION_TERMS,
                    )

                    # Critical Safety False-Negative remediation (Case
                    # 006) — structured interaction/contraindication
                    # assertion classification, independent of both
                    # SAFETY_TERMS and DB_ACTIVITY_SAFETY_TERMS. See
                    # interaction_severity_classifier.py. Folded into
                    # safety_flags via the SAME merge pattern
                    # db_safety_flags already uses just below, so every
                    # downstream consumer of safety_flags (this row's
                    # own eligibility computation, _decision_class(),
                    # _evaluate_gates(), _hard_safety_gate()) picks up
                    # the new signal automatically through the existing
                    # Safety_Flags ∩ HARD_SAFETY_TERMS mechanism, with
                    # zero changes required at any of those call sites.
                    interaction_assertion = _classify_interaction_assertion(raw_evidence)
                    structured_interaction_terms = set(
                        _interaction_hard_hit_terms_for(interaction_assertion)
                    ) | set(
                        _interaction_informational_terms_for(interaction_assertion)
                    )
                    if structured_interaction_terms:
                        pieces = []
                        if safety_flags:
                            pieces.extend(safety_flags.split("; "))
                        pieces.extend(sorted(structured_interaction_terms))
                        safety_flags = "; ".join(sorted(set(pieces)))

                    # Pharmaceutical-grade Safety hardening: raw lexical
                    # extraction is converted into a structured assertion
                    # first. Gate behavior is then driven by the assertion's
                    # semantic severity, not by the keyword itself. This
                    # closes the generic false-negative where an explicit
                    # contraindication with no whitelisted drug class was
                    # previously downgraded to MODERATE.
                    pooled_safety_assertions = _classify_safety_assertions(
                        raw_evidence, authority_score=evidence_authority_factor
                    )
                    pooled_serious_assertions = [
                        a for a in pooled_safety_assertions
                        if a.polarity == _SafetyAssertionPolarity.RISK_PRESENT
                        and a.severity.value == "SERIOUS"
                    ]
                    if pooled_serious_assertions:
                        pieces = []
                        if safety_flags:
                            pieces.extend(safety_flags.split("; "))
                        pieces.append(_INTERACTION_HARD_GATE_SIGNAL_TERM)
                        pieces.extend(
                            f"structured serious safety assertion ({a.assertion_type.value})"
                            for a in pooled_serious_assertions
                        )
                        safety_flags = "; ".join(sorted(set(pieces)))

                    # Phase 8: Market_Status is commercial/market-only.
                    # Regulatory recognition is retained independently; it
                    # no longer contributes to the market score/component.
                    regulatory_recognition_status = self._market_status(
                        alt=alt,
                        evidence=raw_evidence,
                        market=market,
                    )
                    market_status = self._market_evidence_status(raw_evidence)
                    _regulatory_assertion_text = " ".join(
                        str(_r.get("assertion_text") or "")
                        for _r in evidence_contributing_records
                        if str(_r.get("assertion_text") or "").strip()
                    )
                    regulatory_barrier_result = classify_regulatory_barriers(
                        _regulatory_assertion_text or raw_evidence
                    )

                    # How many distinct plants (in the WHOLE database,
                    # independent of this indication) already contain the
                    # matched compound. This is the generic signal used
                    # below to stop ubiquitous compounds (found across
                    # hundreds/thousands of unrelated species) from being
                    # scored/labelled as if they were a specific,
                    # differentiating match — for any indication, any
                    # plant, any compound.
                    compound_plant_count, compound_is_common = (
                        self._compound_commonality(matched_compound)
                    )

                    novelty_status = self._novelty_status(
                        ref_plant=ref_plant,
                        alt_plant=alt_plant,
                        matched=matched_compound,
                        ref_compound=ref_compound,
                        alt=alt,
                        compound_is_common=compound_is_common,
                        compound_plant_count=compound_plant_count,
                    )

                    score, score_components = self._score_candidate(
                        same_plant=self._norm(ref_plant) == self._norm(alt_plant),
                        matched_compound=matched_compound,
                        reference_compound=ref_compound,
                        match_quality=match_quality,
                        concentration=concentration,
                        extraction=extraction,
                        dosage_form=dosage_form,
                        co_compounds=co_compounds,
                        safety_flags=safety_flags,
                        interaction_flags=interaction_flags,
                        market_status=market_status,
                        novelty_status=novelty_status,
                        target=target,
                        evidence=raw_evidence,
                        evidence_level=evidence_level,
                        compound_plant_count=compound_plant_count,
                        target_specificity=target_specificity,
                        evidence_direction_contribution=evidence_direction_contribution,
                    )

                    decision = self._decision_class(
                        score=score,
                        safety_flags=safety_flags,
                        interaction_flags=interaction_flags,
                        has_evidence=has_real_evidence,
                        match_quality=match_quality,
                        evidence_level=evidence_level,
                        compound_is_common=compound_is_common,
                        target_specificity=target_specificity,
                        same_plant=self._norm(ref_plant) == self._norm(alt_plant),
                        regulatory_barrier_types=(
                            regulatory_barrier_result.barrier_types
                            if raw_evidence and raw_evidence.strip()
                            else None
                        ),
                        has_evidence_text=bool(raw_evidence and raw_evidence.strip()),
                    )

                    # Task 1 — Formal Gate Layer. Purely additive: built
                    # from signals already computed above for this same
                    # row (safety_flags, match_quality, has_real_evidence,
                    # evidence_level, regulatory_barrier_result), never
                    # read by anything upstream of this line. See
                    # _evaluate_gates()'s own docstring for what each
                    # gate means — as of Task 4, both "safety" and
                    # "regulatory" are behaviorally tied to Decision_Class.
                    gate_results = self._evaluate_gates(
                        safety_flags=safety_flags,
                        match_quality=match_quality,
                        has_evidence=has_real_evidence,
                        evidence_level=evidence_level,
                        regulatory_barrier_types=(
                            regulatory_barrier_result.barrier_types
                            if raw_evidence and raw_evidence.strip()
                            else None
                        ),
                        same_plant=self._norm(ref_plant) == self._norm(alt_plant),
                        has_evidence_text=bool(raw_evidence and raw_evidence.strip()),
                    )

                    # Phase 4 — Eligibility Gate. Computed from the same
                    # signals _decision_class() above already used
                    # (hit_terms/regulatory_barrier_result/same_plant/
                    # whether raw_evidence existed), plus the
                    # evidence_source_ids already collected for this row
                    # (Gap 1), reused here as Gate_Evidence_IDs so a
                    # no-go/expert-review row's reason is traceable back
                    # to specific evidence records. See eligibility_gate.py.
                    _row_same_plant = self._norm(ref_plant) == self._norm(alt_plant)
                    _row_flagged_terms = frozenset(
                        {t.strip() for t in safety_flags.split("; ") if t.strip()}
                    ) if safety_flags else frozenset()
                    _row_hit_terms = _row_flagged_terms & HARD_SAFETY_TERMS
                    _row_has_evidence_text = bool(raw_evidence and raw_evidence.strip())

                    # Phase 4 (correction round) — finding-specific
                    # evidence IDs: only EvidenceRecords whose OWN text
                    # (not the row's pooled evidence_source_ids, which
                    # is candidate-level) contains the matched hit term
                    # (safety) or barrier phrase (regulatory). Re-runs
                    # the SAME extraction functions the row-level
                    # signals already used (_extract_flags_negation_aware/
                    # classify_regulatory_barriers), just once per
                    # individual contributing record instead of once on
                    # the pooled blob.
                    # The structured interaction/contraindication hard
                    # term (if present in _row_hit_terms) is a synthetic
                    # marker, never literal text in any evidence
                    # record — _extract_flags_negation_aware's substring
                    # check can never match it. Per-record attribution
                    # for that specific signal instead re-runs
                    # classify_interaction_assertion() on each record's
                    # own text, the same "re-run the same extraction
                    # once per record" pattern this loop already uses
                    # for the other two signals below.
                    _row_has_structured_interaction_hit = bool(
                        _row_hit_terms & {_INTERACTION_HARD_GATE_SIGNAL_TERM}
                    )
                    _row_hit_terms_for_text_match = _row_hit_terms - {_INTERACTION_HARD_GATE_SIGNAL_TERM}

                    _safety_gate_evidence_ids = []
                    _regulatory_gate_evidence_ids = []
                    for _rec in evidence_contributing_records:
                        _rec_id = _rec.get("evidence_record_id")
                        _rec_text = _rec.get("text") or ""
                        if not _rec_id or not _rec_text.strip():
                            continue
                        if _row_hit_terms_for_text_match and self._extract_flags_negation_aware(
                            _rec_text, _row_hit_terms_for_text_match
                        ):
                            _safety_gate_evidence_ids.append(_rec_id)
                        elif (
                            _row_has_structured_interaction_hit
                            and _classify_interaction_assertion(_rec_text).tier
                            in (
                                _InteractionSeverityTier.SERIOUS_CONTRAINDICATION,
                                _InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION,
                            )
                        ):
                            _safety_gate_evidence_ids.append(_rec_id)
                        if regulatory_barrier_result.barrier_types:
                            _rec_barrier_result = classify_regulatory_barriers(
                                _rec.get("assertion_text") or _rec_text
                            )
                            if _rec_barrier_result.has_barrier:
                                _regulatory_gate_evidence_ids.append(_rec_id)
                    _safety_gate_evidence_ids = tuple(dict.fromkeys(_safety_gate_evidence_ids))
                    _regulatory_gate_evidence_ids = tuple(dict.fromkeys(_regulatory_gate_evidence_ids))

                    # Structured record-level Safety Assertions preserve the
                    # exact sentence, authority, evidence id, preparation,
                    # dose/route context and polarity. Positive and reassuring
                    # records are both retained so conflict cannot be erased by
                    # pooled-text winner-takes-all logic.
                    _structured_safety_assertions = []
                    for _rec in evidence_contributing_records:
                        _structured_safety_assertions.extend(_classify_safety_assertions(
                            _rec.get("assertion_text") or _rec.get("text") or "",
                            evidence_record_id=str(_rec.get("evidence_record_id") or ""),
                            authority=str(_rec.get("authority_label") or "Unknown Source"),
                            authority_score=float(_rec.get("authority_factor") or 0.5),
                            source_url=str(_rec.get("source_url") or ""),
                            preparation=str(_rec.get("preparation") or ""),
                            dose_dependency=(str(_rec.get("dose") or "unknown") if _rec.get("dose") else "unknown"),
                            route=str(_rec.get("route") or ""),
                            affected_population=tuple(
                                x.strip().lower() for x in str(_rec.get("population") or "").replace(";", ",").split(",") if x.strip()
                            ),
                        ))
                    if not _structured_safety_assertions:
                        _structured_safety_assertions = list(pooled_safety_assertions)
                    _structured_safety_assertions = tuple(_structured_safety_assertions)
                    _safety_assertion_summary = _summarize_safety_assertions(_structured_safety_assertions)

                    _safety_finding = _classify_safety_finding(
                        hit_terms=_row_hit_terms,
                        flagged_terms=_row_flagged_terms,
                        has_evidence_text=_row_has_evidence_text,
                        same_plant=_row_same_plant,
                        evidence_ids=_safety_gate_evidence_ids,
                        assertions=_structured_safety_assertions,
                    )
                    _regulatory_finding = _classify_regulatory_finding(
                        barrier_types=(
                            frozenset(regulatory_barrier_result.barrier_types)
                            if (_row_has_evidence_text and regulatory_barrier_result.barrier_types)
                            else frozenset()
                        ),
                        has_evidence_text=_row_has_evidence_text,
                        same_plant=_row_same_plant,
                        finding_text=_regulatory_assertion_text,
                        candidate_dosage_form=dosage_form,
                        evidence_ids=_regulatory_gate_evidence_ids,
                    )
                    eligibility_decision = _evaluate_eligibility(_safety_finding, _regulatory_finding)
                    scientific_evidence_resolution = resolve_scientific_evidence(
                        evidence_contributing_records
                    )
                    final_decision = decide_final(
                        eligibility_decision,
                        scientific_evidence_resolution,
                        assessment_domain=assessment_domain_from_indication(indication),
                        records=evidence_contributing_records,
                    )

                    # The structured EligibilityDecision is authoritative.
                    # _decision_class() is called earlier for backward-compatible
                    # score-tier logic, but it does not have the record-level
                    # scope/context available here. Reconcile only hard/abstention
                    # states so the displayed final recommendation cannot disagree
                    # with the structured gate.
                    if eligibility_decision.status == _EligibilityStatus.NO_GO_SAFETY:
                        decision = "Safety concern — not suitable without expert review"
                    elif eligibility_decision.status == _EligibilityStatus.NO_GO_REGULATORY:
                        decision = REGULATORY_PROHIBITION_DECISION_CLASS
                    elif eligibility_decision.status == _EligibilityStatus.EXPERT_REVIEW_REQUIRED:
                        decision = (
                            "Expert review required — not eligible for normal ranking "
                            "until safety/regulatory scope is confirmed"
                        )
                    elif eligibility_decision.status == _EligibilityStatus.INCOMPLETE:
                        decision = "Incomplete — insufficient safety/regulatory evidence for a validated recommendation"
                    elif final_decision.status == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED:
                        decision = "Expert review required — conflicting governing scientific evidence"
                    elif final_decision.status == FinalDecisionStatus.INSUFFICIENT_EVIDENCE:
                        decision = "Insufficient evidence — governing evidence does not support GO"
                    elif final_decision.status == FinalDecisionStatus.GO_WITH_CAUTION:
                        decision = "Go with caution — governing scientific evidence is supportive but requires caution"

                    gate_results["eligibility"] = {
                        "gate_name": "eligibility",
                        "status": eligibility_decision.status.value,
                        "reason": eligibility_decision.gate_reason,
                        "evidence": "; ".join(eligibility_decision.gate_evidence_ids),
                    }

                    # Task 10.2 — Evidence-level Preparation Applicability,
                    # candidate-level summary. Purely additive, read-only
                    # aggregation over evidence_applicability_index (built
                    # once, alongside evidence_index/evidence_source_index,
                    # by _build_evidence_text_index()); never influences
                    # score, decision, or gate_results above.
                    applicability_items = self._collect_applicability_items(
                        applicability_index=evidence_applicability_index,
                        plant=alt_plant,
                        compound=matched_compound,
                    )
                    applicability_summary = self._summarize_applicability(applicability_items)

                    evidence_confidence = compute_evidence_confidence(
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                        evidence_level=evidence_level,
                        has_negative_evidence=negative_evidence.is_negative,
                        evidence_text=raw_evidence,
                        evidence_direction=evidence_interpretation_result.evidence_direction,
                        evidence_applicability=evidence_interpretation_result.evidence_applicability,
                        is_completed_study=evidence_interpretation_result.is_completed_study,
                        study_design=evidence_interpretation_result.study_design,
                        evidence_quality=evidence_interpretation_result.evidence_quality,
                    )
                    confidence_note = confidence_adjusted_framing_note(
                        rd_opportunity_score=score,
                        evidence_confidence=evidence_confidence,
                    )
                    decision_class_ah = classify_decision_ah(
                        existing_decision_class=decision,
                        evidence_confidence=evidence_confidence,
                        rd_opportunity_score=score,
                        market_status=market_status,
                        match_quality=match_quality,
                        same_plant=self._norm(ref_plant) == self._norm(alt_plant),
                    )
                    white_space_type = classify_white_space(
                        evidence_confidence=evidence_confidence,
                        market_status=market_status,
                        use_live_search=self.use_live_search,
                        regulatory_status=regulatory_recognition_status,
                    )
                    occurrence_corroboration = self._occurrence_corroboration(evidence_source_ids)
                    candidate_evidence_strength_tier = classify_candidate_evidence_strength(
                        occurrence_corroboration=occurrence_corroboration,
                        evidence_confidence=evidence_confidence,
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                    )

                    # Task 2 — GRADE-style clinical-evidence certainty
                    # grading (previously "Designed only" — see
                    # grade_certainty_classifier.py's module docstring
                    # for the full documented method and its declared
                    # limitations). Purely additive: built entirely
                    # from signals already computed above
                    # (evidence_hierarchy_detail, raw_evidence,
                    # negative_evidence, occurrence_corroboration,
                    # applicability_summary's strongest_category) —
                    # never reads or influences R&D_Opportunity_Score,
                    # Decision_Class, Decision_Class_AH, Gate_Results,
                    # or Evidence_Confidence.
                    grade_certainty_result = classify_grade_certainty(
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                        evidence_text=raw_evidence,
                        has_negative_evidence=negative_evidence.is_negative,
                        occurrence_corroboration=occurrence_corroboration,
                        applicability_classification=applicability_summary.get("strongest_category"),
                    )

                    # Gap 6 + Gap 8: structured rationale, built purely
                    # from signals already computed above — no new data
                    # collection, no LLM call. See structured_rationale.py.
                    go_call = go_investigate_hold_no_go(
                        decision_class_ah,
                        fallback_occurred=not self.data_source_reliable,
                    )
                    sci_rationale = scientific_rationale(
                        match_quality=match_quality,
                        target_provenance=target_provenance,
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                        occurrence_corroboration=occurrence_corroboration,
                        has_negative_evidence=negative_evidence.is_negative,
                    )
                    comm_reg_rationale = commercial_regulatory_rationale(
                        market_status=market_status,
                        white_space_type=white_space_type or "",
                        regulatory_barriers="; ".join(regulatory_barrier_result.barrier_types),
                    )
                    strengths = evidence_strengths(
                        match_quality=match_quality,
                        evidence_confidence=evidence_confidence,
                        occurrence_corroboration=occurrence_corroboration,
                        market_status=market_status,
                    )
                    weaknesses = evidence_weaknesses(
                        evidence_confidence=evidence_confidence,
                        occurrence_corroboration=occurrence_corroboration,
                        has_negative_evidence=negative_evidence.is_negative,
                        negative_evidence_types="; ".join(negative_evidence.finding_types),
                        safety_flags=safety_flags or "No explicit flag found",
                        market_status=market_status,
                        regulatory_barriers="; ".join(regulatory_barrier_result.barrier_types),
                    )
                    next_experiment = next_experiment_suggestion(
                        decision_class_ah=decision_class_ah,
                        evidence_weaknesses_list=weaknesses,
                        alt_plant=alt_plant,
                    )
                    conflict_reasoning = evidence_conflict_reasoning(
                        occurrence_corroboration=occurrence_corroboration,
                        has_negative_evidence=negative_evidence.is_negative,
                        negative_evidence_types="; ".join(negative_evidence.finding_types),
                        evidence_confidence=evidence_confidence,
                        raw_evidence_text=raw_evidence,
                    )
                    evidence_conflict_structured = build_evidence_conflict_structured(
                        occurrence_corroboration=occurrence_corroboration,
                        has_negative_evidence=negative_evidence.is_negative,
                        negative_evidence_types="; ".join(negative_evidence.finding_types),
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                        evidence_level=evidence_level,
                        safety_flags=safety_flags,
                        market_status=market_status,
                        evidence_conflict_reasoning_text=conflict_reasoning,
                        raw_evidence_text=raw_evidence,
                    )
                    confidence_statement = recommendation_confidence_statement(
                        go_call=go_call,
                        candidate_evidence_strength_tier=candidate_evidence_strength_tier,
                        evidence_confidence=evidence_confidence,
                        has_negative_evidence=negative_evidence.is_negative,
                    )
                    competitive_positioning = competitive_positioning_statement(
                        market_status=market_status,
                        candidate_evidence_strength_tier=candidate_evidence_strength_tier,
                        regulatory_barriers="; ".join(regulatory_barrier_result.barrier_types),
                        white_space_type=white_space_type or "",
                    )
                    regulatory_rationale_text = regulatory_rationale(
                        market_status=regulatory_recognition_status,
                        regulatory_barriers="; ".join(regulatory_barrier_result.barrier_types),
                    )
                    commercial_rationale_text = commercial_rationale(
                        market_status=market_status,
                        white_space_type=white_space_type or "",
                    )
                    safety_rationale_text = safety_rationale(
                        safety_flags=safety_flags or "No explicit flag found",
                        interaction_flags=interaction_flags or "No explicit flag found",
                    )
                    clinical_rationale_text = clinical_rationale(
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                        evidence_confidence=evidence_confidence,
                        has_negative_evidence=negative_evidence.is_negative,
                    )

                    rows.append(
                        {
                            "Reference_Plant": ref_plant,
                            "Reference_Plant_Part": ref_plant_part or "Not specified in database",
                            "Reference_Compound": ref_compound,
                            "Alternative_Plant": alt_plant,
                            "Alternative_Plant_Part": alt_plant_part or "Not specified in database",
                            "Shared_or_Similar_Compound": matched_compound,
                            "Target_or_Mechanism": target or "Not clearly extracted",
                            "Target_Provenance": target_provenance or "Not applicable (no shared-target claim for this match type)",
                            "Concentration_Info": concentration or "Not clearly reported",
                            "Extraction_Method": extraction or "Not clearly reported",
                            "Industrial_Feasibility": industrial_feasibility,
                            "Co_Compounds": co_compounds or "Not clearly extracted",
                            "Safety_Flags": safety_flags or "No explicit flag found",
                            "Interaction_Flags": interaction_flags or "No explicit flag found",
                            "Evidence_Source": self._evidence_source(
                                alt_plant,
                                matched_compound,
                                raw_evidence,
                            ),
                            "Source_Record_IDs": "; ".join(evidence_source_ids) if evidence_source_ids else "No specific source record identified",
                            "Occurrence_Corroboration": occurrence_corroboration,
                            "Candidate_Evidence_Strength_Tier": candidate_evidence_strength_tier,
                            "Evidence_Level": evidence_level,
                            "Evidence_Hierarchy_Detail": evidence_hierarchy_detail or "Unclassified",
                            "Study_Design": study_design,
                            "Evidence_Direction": evidence_direction,
                            "Evidence_Quality": evidence_quality_label,
                            "Evidence_Applicability": evidence_applicability_label,
                            "Has_Negative_Evidence": negative_evidence.is_negative,
                            "Negative_Evidence_Types": "; ".join(negative_evidence.finding_types),
                            "Market_Status": market_status,
                            "Regulatory_Recognition_Status": regulatory_recognition_status,
                            "Regulatory_Barriers": "; ".join(regulatory_barrier_result.barrier_types) if regulatory_barrier_result.has_barrier else "None identified",
                            "Novelty_Status": novelty_status,
                            "R&D_Opportunity_Score": score,
                            "Score_Breakdown": self._format_score_breakdown(score_components),
                            "Evidence_Confidence": evidence_confidence,
                            "Decision_Class": decision,
                            "Decision_Class_AH": decision_class_ah,
                            "Gate_Results": gate_results,
                            "Scoring_Config_Version": self.scoring_config.version,
                            "Applicability_Summary": applicability_summary,
                            "GRADE_Certainty": grade_certainty_result.certainty,
                            "GRADE_Certainty_Rationale": grade_certainty_result.rationale,
                            "White_Space_Type": white_space_type or "",
                            "Confidence_Note": confidence_note or "",
                            # Phase 4 — Eligibility Gate. See eligibility_gate.py.
                            "Eligibility_Status": eligibility_decision.status.value,
                            "Hard_No_Go": eligibility_decision.hard_no_go,
                            "Eligible_For_Normal_Ranking": final_decision.status in {
                                FinalDecisionStatus.GO, FinalDecisionStatus.GO_WITH_CAUTION
                            },
                            "Ranking_Partition": (
                                _RankingPartition.EXCLUDED_NO_GO.value
                                if final_decision.status in {FinalDecisionStatus.NO_GO_SAFETY, FinalDecisionStatus.NO_GO_REGULATORY}
                                else _RankingPartition.PRELIMINARY_OR_EXPERT_REVIEW.value
                                if final_decision.status in {FinalDecisionStatus.EXPERT_REVIEW_REQUIRED, FinalDecisionStatus.INSUFFICIENT_EVIDENCE}
                                else _RankingPartition.NORMAL.value
                            ),
                            "Score_Validity": (
                                _ScoreValidity.AUDIT_ONLY.value
                                if final_decision.status in {FinalDecisionStatus.NO_GO_SAFETY, FinalDecisionStatus.NO_GO_REGULATORY}
                                else _ScoreValidity.PRELIMINARY.value
                                if final_decision.status in {FinalDecisionStatus.EXPERT_REVIEW_REQUIRED, FinalDecisionStatus.INSUFFICIENT_EVIDENCE}
                                else _ScoreValidity.VALID.value
                            ),
                            "Gate_Type": eligibility_decision.gate_type,
                            "Gate_Reason": eligibility_decision.gate_reason,
                            "Gate_Evidence_IDs": "; ".join(eligibility_decision.gate_evidence_ids)
                                if eligibility_decision.gate_evidence_ids else "",
                            "Final_Decision_Status": final_decision.status.value,
                            "Safety_Gate_Evidence_IDs": "; ".join(eligibility_decision.safety_finding.evidence_ids)
                                if eligibility_decision.safety_finding.evidence_ids else "",
                            "Regulatory_Gate_Evidence_IDs": "; ".join(eligibility_decision.regulatory_finding.evidence_ids)
                                if eligibility_decision.regulatory_finding.evidence_ids else "",
                            "Safety_Assertions": json.dumps(
                                [a.to_dict() for a in eligibility_decision.safety_finding.assertions],
                                sort_keys=True, ensure_ascii=False,
                            ),
                            "Safety_Decision_Confidence": eligibility_decision.safety_finding.confidence.value,
                            "Safety_Evidence_Conflict": eligibility_decision.safety_finding.evidence_conflict,
                            "Safety_Severity_Rule": eligibility_decision.safety_finding.severity_rule,
                            "Safety_Severity": eligibility_decision.safety_finding.severity.value,
                            "Safety_Scope": eligibility_decision.safety_finding.scope.value,
                            "Safety_Context_Relevance": eligibility_decision.safety_finding.context_relevance.value,
                            "Regulatory_Status": eligibility_decision.regulatory_finding.status.value,
                            "Regulatory_Scope": eligibility_decision.regulatory_finding.scope.value,
                            "Regulatory_Context_Relevance": eligibility_decision.regulatory_finding.context_relevance.value,
                            "Data_Completeness": eligibility_decision.data_completeness.value,
                            "Requires_Expert_Review": (
                                eligibility_decision.requires_expert_review
                                or final_decision.status == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
                            ),
                            # Internal-only — used by _merge_multi_compound_matches
                            # to correctly recompute Decision_Class_AH after a
                            # merge, then dropped by the final
                            # output[OUTPUT_COLUMNS] selection at the end of
                            # run(). Never reaches the CSV.
                            "_match_quality": match_quality,
                            "_same_plant": self._norm(ref_plant) == self._norm(alt_plant),
                            "Go_Investigate_Hold_NoGo": go_call,
                            "Scientific_Rationale": sci_rationale,
                            "Commercial_Regulatory_Rationale": comm_reg_rationale,
                            "Evidence_Strengths": "; ".join(strengths) if strengths else "None identified",
                            "Evidence_Weaknesses": "; ".join(weaknesses) if weaknesses else "None identified",
                            "Next_Experiment_Suggestion": next_experiment,
                            "Evidence_Conflict_Reasoning": conflict_reasoning,
                            "Evidence_Conflict_Structured": evidence_conflict_structured,
                            "Recommendation_Confidence_Statement": confidence_statement,
                            "Competitive_Positioning": competitive_positioning,
                            "Regulatory_Rationale": regulatory_rationale_text,
                            "Commercial_Rationale": commercial_rationale_text,
                            "Safety_Rationale": safety_rationale_text,
                            "Clinical_Rationale": clinical_rationale_text,
                            "Rationale": self._rationale(
                                product_type=product_type,
                                problem=problem,
                                dosage_form=dosage_form,
                                ref_plant=ref_plant,
                                ref_compound=ref_compound,
                                alt_plant=alt_plant,
                                matched=matched_compound,
                                match_quality=match_quality,
                                has_evidence=has_real_evidence,
                                evidence_level=evidence_level,
                                extraction=extraction,
                                concentration=concentration,
                                co_compounds=co_compounds,
                                market_status=market_status,
                                novelty_status=novelty_status,
                                decision=decision,
                            ),
                        }
                    )

        if not rows:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        output = pd.DataFrame(rows)

        # Sort by score first so, when two rows differ only by letter case in
        # the compound name (a real data-quality issue seen in some source
        # records — e.g. "Withanolide D" / "withanolide D" / "WITHANOLIDE
        # D" all meaning the same compound), the highest-scoring version is
        # the one kept.
        output = output.sort_values(
            by=["R&D_Opportunity_Score"],
            ascending=False,
        )

        dedup_key = pd.DataFrame({
            "Reference_Plant": output["Reference_Plant"].map(self._norm),
            "Reference_Compound": output["Reference_Compound"].map(self._norm),
            "Alternative_Plant": output["Alternative_Plant"].map(self._norm),
            "Shared_or_Similar_Compound": output["Shared_or_Similar_Compound"].map(self._norm),
        })

        output = output[~dedup_key.duplicated(keep="first")]

        output = self._merge_multi_compound_matches(output)

        # Correction round (2nd pass) — final sort is now
        # Ranking_Partition FIRST, R&D_Opportunity_Score second: a
        # NO_GO row's raw score (however high) can no longer place it
        # ahead of a genuinely NORMAL-partition row in this DataFrame's
        # own order. This DataFrame remains audit-complete — every row
        # produced is still present here, nothing is dropped — only the
        # ORDER changes. Extracted as its own module-level function
        # (sort_by_ranking_partition_then_score, below) so it has one
        # implementation shared by run() and directly testable on its
        # own, without needing a full engine run to exercise the sort
        # logic itself.
        output = sort_by_ranking_partition_then_score(output)

        # Architecture audit Q2 ("why were the others rejected?"): a
        # post-processing pass over the now-complete, now-merged result
        # — every row's FINAL score has to exist before any comparison
        # is meaningful, so this runs last, exactly like
        # _merge_multi_compound_matches already does one pass earlier.
        output["Comparative_Rationale"] = build_comparative_rationale(output)
        # Sprint 2: additive structured companion to the string above —
        # never replaces it, never changes its type.
        output["Comparative_Rationale_Structured"] = build_comparative_rationale_structured(output)

        # Task 15 — reproducibility metadata, attached ONCE here (the
        # single final row-assembly point every candidate row already
        # passes through, regardless of which earlier code path built
        # it — the primary per-row loop or _merge_multi_compound_matches()'s
        # rebuild). A whole-column broadcast assignment, not a loop, so
        # the DECISION_ENGINE_VERSION string literal is written exactly
        # once in this file, not duplicated across multiple row-
        # construction sites. Metadata only — set after every score/
        # gate/decision/ranking-affecting computation above has already
        # finished; nothing below this line reads it back into anything.
        output["Decision_Engine_Version"] = DECISION_ENGINE_VERSION

        return output[OUTPUT_COLUMNS]

    def _merge_multi_compound_matches(self, output):
        """When the SAME alternative plant matches the SAME reference
        plant on more than one distinct compound (e.g. it independently
        contains both reference compound X and reference compound Z), that
        is a materially stronger candidate than one that only shares a
        single compound — it means multiple active substances line up, not
        just one. Previously each compound match became its own separate
        row with no acknowledgment that they came from the same
        plant/plant pairing. This merges those rows into one, combines the
        matched compounds into a single field, and adds a score bonus per
        additional independently-matched compound (capped, and still
        subject to the same safety/evidence caps as any other candidate).
        """
        if output.empty:
            return output

        group_keys = (
            output["Reference_Plant"].map(self._norm)
            + "||" + output["Alternative_Plant"].map(self._norm)
        )

        # Ranked worst-to-best. "Safety concern" sits below "Low priority"
        # since it's a harder, more certain reason to deprioritize a
        # candidate than merely having a weak/generic match. This list
        # must stay in sync with every Decision_Class string
        # _decision_class() can produce — an earlier version of this list
        # didn't know about "Safety concern — not suitable without expert
        # review" (added later, see _decision_class), which crashed
        # order.index() below the moment any duplicate-reference-plant
        # group contained a safety-flagged row.
        order = [
            "Safety concern — not suitable without expert review",
            "Low priority / insufficient data",
            "Early-stage candidate; more evidence needed",
            "Promising candidate; verify safety and standardization",
            "Strong R&D candidate",
        ]

        def _rank(decision):
            decision = str(decision)
            # Task 4 — REGULATORY_PROHIBITION_DECISION_CLASS is a second
            # hard-stop string, exactly as decisive as "Safety concern"
            # above, but deliberately NOT inserted into `order` itself:
            # doing so would shift every other entry's index, which
            # nothing downstream should need to care about but which is
            # an unnecessary risk to introduce in an additive change.
            # Instead both hard-stop strings rank below (worse than)
            # everything in `order`, including "Safety concern" at index
            # 0 — same relative ordering as before, just expressed via
            # this explicit membership check rather than list position.
            if decision in HARD_STOP_DECISION_CLASSES:
                return -1
            return order.index(decision) if decision in order else 0

        merged_rows = []

        for _, group in output.groupby(group_keys, sort=False):
            if len(group) == 1:
                merged_rows.append(group.iloc[0].to_dict())
                continue

            group = group.sort_values("R&D_Opportunity_Score", ascending=False)
            best = group.iloc[0].to_dict()

            distinct_ref_compounds = self._unique_clean_list(group["Reference_Compound"])
            distinct_matched = self._unique_clean_list(group["Shared_or_Similar_Compound"])
            num_matches = len(distinct_matched)

            if num_matches <= 1:
                merged_rows.append(best)
                continue

            bonus = min(20, (num_matches - 1) * 10)
            new_score = round(min(100, best["R&D_Opportunity_Score"] + bonus), 1)
            if "Score_Breakdown" in best and bonus:
                # The merge bonus is a real, separate contribution to
                # the final score (rewarding multiple independent
                # compound matches) that _score_candidate never saw —
                # append it explicitly rather than letting
                # Score_Breakdown silently under-report new_score's
                # actual composition.
                best["Score_Breakdown"] = (
                    f"{best['Score_Breakdown']}; Multi-compound match bonus: +{bonus:.1f}"
                )

            risky = any(
                str(v).strip() and str(v).strip() != "No explicit flag found"
                for v in group["Safety_Flags"]
            ) or any(
                str(v).strip() and str(v).strip() != "No explicit flag found"
                for v in group["Interaction_Flags"]
            )

            if new_score >= 78 and not risky:
                new_decision = "Strong R&D candidate"
            elif new_score >= 62:
                new_decision = "Promising candidate; verify safety and standardization"
            elif new_score >= 45:
                new_decision = "Early-stage candidate; more evidence needed"
            else:
                new_decision = "Low priority / insufficient data"

            # Stay conservative: never let the merge produce a HIGHER
            # confidence tier than the most cautious *informative*
            # individual match already earned (e.g. if one of the matches
            # has no real evidence behind it, the merged row shouldn't
            # claim more confidence than that).
            #
            # BUT: a sub-row whose own match rests on a common,
            # non-specific compound (the same "found in dozens/hundreds
            # of unrelated plants database-wide" signal _score_candidate
            # and _decision_class already penalize on that sub-row itself
            # — see the "Common"/"non-specific" checks elsewhere in this
            # file) is not informative about the OVERALL multi-compound
            # candidate. Letting it also act as a veto on the merged
            # result is double-penalizing the same weak signal, and once
            # a candidate matches on enough distinct compounds (which is
            # exactly what should make it a STRONGER candidate), at least
            # one such common/trace compound is almost always present —
            # silently dragging nearly every multi-compound match down to
            # "Low priority" regardless of how strong the rest of the
            # evidence is. Only sub-rows that aren't themselves flagged
            # as common/non-specific get a vote in the conservative cap.
            # If every sub-row in the group is common/non-specific, none
            # of them are informative, so the cap falls back to the full,
            # unfiltered group — the conservative behavior is preserved
            # exactly for the case it exists for: a group with no strong
            # signal at all.
            def _is_common_match(novelty_status):
                text = str(novelty_status)
                return "Common" in text or "non-specific" in text

            informative = group[~group["Novelty_Status"].map(_is_common_match)]
            tightest_pool = informative if not informative.empty else group

            tightest = min(
                (str(d) for d in tightest_pool["Decision_Class"]),
                key=_rank,
            )
            if _rank(new_decision) > _rank(tightest):
                new_decision = tightest

            # Preserve scientific abstention states across compound merging.
            # These states were derived from record-level evidence and must not
            # be overwritten by a higher merged score.
            _group_decisions = tuple(str(v) for v in group["Decision_Class"])
            _group_has_scientific_conflict = any(
                d.startswith("Expert review required — conflicting governing scientific evidence")
                for d in _group_decisions
            )
            _group_has_scientific_insufficiency = any(
                d.startswith("Insufficient evidence — governing evidence does not support GO")
                for d in _group_decisions
            )

            best["Reference_Compound"] = "; ".join(distinct_ref_compounds)
            best["Shared_or_Similar_Compound"] = "; ".join(distinct_matched)
            best["R&D_Opportunity_Score"] = new_score
            best["Decision_Class"] = new_decision

            # The decision above already accounts for flags anywhere in
            # the group, not just on the single highest-scoring sub-row
            # ("best"). The displayed Safety_Flags/Interaction_Flags must
            # do the same — otherwise a merged row can show "Safety
            # concern" with a Safety_Flags column that says "No explicit
            # flag found", because that column silently kept whichever
            # value the (unflagged) top-scoring sub-row happened to have
            # while a DIFFERENT, lower-scoring sub-row in the same group
            # was the one that actually carried the flag. A decision the
            # displayed columns can't explain isn't trustworthy, for any
            # plant, any compound, any indication.
            def _merged_flags(column):
                pieces = []
                for v in group[column]:
                    v = str(v).strip()
                    if v and v != "No explicit flag found":
                        pieces.extend(p.strip() for p in v.split("; ") if p.strip())
                return "; ".join(sorted(set(pieces))) if pieces else "No explicit flag found"

            best["Safety_Flags"] = _merged_flags("Safety_Flags")
            best["Interaction_Flags"] = _merged_flags("Interaction_Flags")

            # Pharmaceutical-grade safety merge: structured eligibility
            # must be recomputed from ALL sub-row assertions. Keeping the
            # highest-scoring sub-row's Eligibility_Status while merely
            # merging Safety_Flags is a fail-open path: a serious assertion
            # on a lower-scoring compound could otherwise disappear from the
            # authoritative eligibility fields used downstream.
            if "Safety_Assertions" in group.columns:
                _merged_assertions = []
                _seen_assertions = set()
                for _raw in group["Safety_Assertions"]:
                    try:
                        _payload = json.loads(_raw) if isinstance(_raw, str) else (_raw or [])
                    except (TypeError, ValueError, json.JSONDecodeError):
                        _payload = []
                    if not isinstance(_payload, list):
                        continue
                    for _item in _payload:
                        if not isinstance(_item, dict):
                            continue
                        try:
                            _a = _safety_assertion_from_dict(_item)
                        except (KeyError, TypeError, ValueError):
                            continue
                        _key = (
                            _a.assertion_type.value, _a.severity.value, _a.polarity.value,
                            _a.evidence_record_id, _a.source_sentence, _a.matched_language,
                        )
                        if _key not in _seen_assertions:
                            _seen_assertions.add(_key)
                            _merged_assertions.append(_a)
                _merged_assertions = tuple(_merged_assertions)

                _merged_flag_terms = frozenset(
                    p.strip() for p in str(best.get("Safety_Flags", "")).split("; ")
                    if p.strip() and p.strip() != "No explicit flag found"
                )
                _merged_hit_terms = _merged_flag_terms & HARD_SAFETY_TERMS
                _merged_safety_ids = tuple(dict.fromkeys(
                    eid.strip()
                    for value in group.get("Safety_Gate_Evidence_IDs", [])
                    for eid in str(value or "").split(";")
                    if eid.strip()
                ))
                _merged_reg_ids = tuple(dict.fromkeys(
                    eid.strip()
                    for value in group.get("Regulatory_Gate_Evidence_IDs", [])
                    for eid in str(value or "").split(";")
                    if eid.strip()
                ))
                _merged_barrier_types = set()
                if "Regulatory_Barriers" in group.columns:
                    for _v in group["Regulatory_Barriers"]:
                        _txt = str(_v or "").strip()
                        if _txt and _txt != "None identified":
                            _merged_barrier_types.update(x.strip() for x in _txt.split("; ") if x.strip())
                _merged_has_evidence = any(
                    str(v or "").strip() not in {"", "No specific source record identified"}
                    for v in group.get("Source_Record_IDs", [])
                ) or any(str(v or "").strip() != "No direct evidence" for v in group.get("Evidence_Level", []))

                _merged_safety_finding = _classify_safety_finding(
                    hit_terms=_merged_hit_terms,
                    flagged_terms=_merged_flag_terms,
                    has_evidence_text=_merged_has_evidence,
                    same_plant=bool(best.get("_same_plant", False)),
                    evidence_ids=_merged_safety_ids,
                    assertions=_merged_assertions,
                )
                _merged_reg_finding = _classify_regulatory_finding(
                    barrier_types=frozenset(_merged_barrier_types),
                    has_evidence_text=_merged_has_evidence,
                    same_plant=bool(best.get("_same_plant", False)),
                    evidence_ids=_merged_reg_ids,
                )
                _merged_eligibility = _evaluate_eligibility(_merged_safety_finding, _merged_reg_finding)
                best["Eligibility_Status"] = _merged_eligibility.status.value
                best["Hard_No_Go"] = _merged_eligibility.hard_no_go
                best["Eligible_For_Normal_Ranking"] = _merged_eligibility.eligible_for_normal_ranking
                best["Ranking_Partition"] = _merged_eligibility.ranking_partition.value
                best["Score_Validity"] = _merged_eligibility.score_validity.value
                best["Gate_Type"] = _merged_eligibility.gate_type
                best["Gate_Reason"] = _merged_eligibility.gate_reason
                best["Gate_Evidence_IDs"] = "; ".join(_merged_eligibility.gate_evidence_ids)
                best["Safety_Gate_Evidence_IDs"] = "; ".join(_merged_eligibility.safety_finding.evidence_ids)
                best["Regulatory_Gate_Evidence_IDs"] = "; ".join(_merged_eligibility.regulatory_finding.evidence_ids)
                best["Safety_Assertions"] = json.dumps([a.to_dict() for a in _merged_assertions], sort_keys=True, ensure_ascii=False)
                best["Safety_Decision_Confidence"] = _merged_eligibility.safety_finding.confidence.value
                best["Safety_Evidence_Conflict"] = _merged_eligibility.safety_finding.evidence_conflict
                best["Safety_Severity_Rule"] = _merged_eligibility.safety_finding.severity_rule
                best["Safety_Severity"] = _merged_eligibility.safety_finding.severity.value
                best["Safety_Scope"] = _merged_eligibility.safety_finding.scope.value
                best["Safety_Context_Relevance"] = _merged_eligibility.safety_finding.context_relevance.value
                best["Regulatory_Status"] = _merged_eligibility.regulatory_finding.status.value
                best["Regulatory_Scope"] = _merged_eligibility.regulatory_finding.scope.value
                best["Regulatory_Context_Relevance"] = _merged_eligibility.regulatory_finding.context_relevance.value
                best["Data_Completeness"] = _merged_eligibility.data_completeness.value

                # Reconcile the merged row with the same six-class final
                # decision semantics used before merging.  Eligibility remains
                # authoritative for hard safety/regulatory outcomes, while a
                # governing scientific conflict/insufficiency remains an
                # abstention even if the multi-compound score rises.
                if _merged_eligibility.status == _EligibilityStatus.NO_GO_SAFETY:
                    best["Decision_Class"] = "Safety concern — not suitable without expert review"
                elif _merged_eligibility.status == _EligibilityStatus.NO_GO_REGULATORY:
                    best["Decision_Class"] = REGULATORY_PROHIBITION_DECISION_CLASS
                elif _merged_eligibility.status == _EligibilityStatus.EXPERT_REVIEW_REQUIRED:
                    best["Decision_Class"] = "Expert review required — unresolved safety/regulatory context"
                elif _group_has_scientific_conflict:
                    best["Decision_Class"] = "Expert review required — conflicting governing scientific evidence"
                elif _merged_eligibility.status == _EligibilityStatus.INCOMPLETE:
                    best["Decision_Class"] = "Incomplete — insufficient safety/regulatory evidence for a validated recommendation"
                elif _group_has_scientific_insufficiency:
                    best["Decision_Class"] = "Insufficient evidence — governing evidence does not support GO"
                elif _merged_eligibility.status == _EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS:
                    best["Decision_Class"] = "Go with caution — regulatory or safety restrictions apply"

                if _merged_eligibility.status == _EligibilityStatus.NO_GO_SAFETY:
                    best["Final_Decision_Status"] = FinalDecisionStatus.NO_GO_SAFETY.value
                elif _merged_eligibility.status == _EligibilityStatus.NO_GO_REGULATORY:
                    best["Final_Decision_Status"] = FinalDecisionStatus.NO_GO_REGULATORY.value
                elif _merged_eligibility.status == _EligibilityStatus.EXPERT_REVIEW_REQUIRED or _group_has_scientific_conflict:
                    best["Final_Decision_Status"] = FinalDecisionStatus.EXPERT_REVIEW_REQUIRED.value
                elif _merged_eligibility.status == _EligibilityStatus.INCOMPLETE or _group_has_scientific_insufficiency:
                    best["Final_Decision_Status"] = FinalDecisionStatus.INSUFFICIENT_EVIDENCE.value
                elif _merged_eligibility.status == _EligibilityStatus.ELIGIBLE_WITH_RESTRICTIONS:
                    best["Final_Decision_Status"] = FinalDecisionStatus.GO_WITH_CAUTION.value
                else:
                    best["Final_Decision_Status"] = FinalDecisionStatus.GO.value

                _merged_final_status = final_status_from_engine_row(best)
                _final_blocks_normal_ranking = _merged_final_status in {
                    FinalDecisionStatus.NO_GO_SAFETY,
                    FinalDecisionStatus.NO_GO_REGULATORY,
                    FinalDecisionStatus.EXPERT_REVIEW_REQUIRED,
                    FinalDecisionStatus.INSUFFICIENT_EVIDENCE,
                }
                best["Eligible_For_Normal_Ranking"] = not _final_blocks_normal_ranking
                if _merged_final_status in {
                    FinalDecisionStatus.NO_GO_SAFETY, FinalDecisionStatus.NO_GO_REGULATORY
                }:
                    best["Ranking_Partition"] = _RankingPartition.EXCLUDED_NO_GO.value
                    best["Score_Validity"] = _ScoreValidity.AUDIT_ONLY.value
                elif _merged_final_status in {
                    FinalDecisionStatus.EXPERT_REVIEW_REQUIRED, FinalDecisionStatus.INSUFFICIENT_EVIDENCE
                }:
                    best["Ranking_Partition"] = _RankingPartition.PRELIMINARY_OR_EXPERT_REVIEW.value
                    best["Score_Validity"] = _ScoreValidity.PRELIMINARY.value
                else:
                    best["Ranking_Partition"] = _merged_eligibility.ranking_partition.value
                    best["Score_Validity"] = _merged_eligibility.score_validity.value
                best["Requires_Expert_Review"] = (
                    _merged_eligibility.requires_expert_review
                    or _merged_final_status == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
                )

            # Same reasoning as Safety_Flags/Interaction_Flags just
            # above, applied to negative evidence (audit 4.15): if ANY
            # sub-row in this group carries a negative/contradictory
            # finding, the merged row must show it — a negative finding
            # attached to one of several matched compounds silently
            # vanishing because a DIFFERENT compound's sub-row happened
            # to score higher is exactly the confirmation-bias failure
            # mode this column exists to prevent.
            if "Has_Negative_Evidence" in group.columns:
                best["Has_Negative_Evidence"] = bool(group["Has_Negative_Evidence"].any())
            if "Negative_Evidence_Types" in group.columns:
                types = []
                for v in group["Negative_Evidence_Types"]:
                    v = str(v).strip()
                    if v:
                        types.extend(t.strip() for t in v.split("; ") if t.strip())
                best["Negative_Evidence_Types"] = "; ".join(sorted(set(types)))

            # Q8 (regulatory barriers): same union-across-group
            # reasoning as Negative_Evidence_Types just above — a
            # barrier attached to one matched compound must not vanish
            # because a different compound's sub-row scored higher.
            if "Regulatory_Barriers" in group.columns:
                barrier_types = []
                for v in group["Regulatory_Barriers"]:
                    v = str(v).strip()
                    if v and v != "None identified":
                        barrier_types.extend(t.strip() for t in v.split("; ") if t.strip())
                best["Regulatory_Barriers"] = (
                    "; ".join(sorted(set(barrier_types))) if barrier_types else "None identified"
                )

            # Gap 1 (traceability): union every source ID cited by ANY
            # sub-row in this group, same reasoning as
            # Negative_Evidence_Types just above — a citation backing
            # one of several matched compounds must not vanish because
            # a different compound's sub-row happened to score higher.
            if "Source_Record_IDs" in group.columns:
                ids = []
                for v in group["Source_Record_IDs"]:
                    v = str(v).strip()
                    if v and v != "No specific source record identified":
                        ids.extend(i.strip() for i in v.split("; ") if i.strip())
                best["Source_Record_IDs"] = (
                    "; ".join(sorted(set(ids))) if ids else "No specific source record identified"
                )
                # Gap 3: recompute corroboration from the just-unioned
                # source list — merging can genuinely INCREASE
                # corroboration (multiple matched compounds can each
                # bring their own independent source), so this must be
                # derived AFTER the union above, not carried over from
                # whichever single sub-row happened to score highest.
                best["Occurrence_Corroboration"] = self._occurrence_corroboration(ids)

            # Evidence_Confidence and Confidence_Note (Phase 6, audit
            # 4.16) must be recomputed here too — otherwise they'd stay
            # frozen at whatever the single pre-merge "best" sub-row had,
            # silently going stale the moment new_score (just above)
            # differs from that sub-row's original score. Confidence
            # itself uses the MAX across the group's sub-rows: if any one
            # matched compound has strong evidence behind it, that's a
            # genuine, real signal about the candidate as a whole, the
            # same "any sub-row can contribute a real positive" logic
            # already used for Has_Negative_Evidence above (just the
            # positive-signal direction of it).
            if "Evidence_Confidence" in group.columns:
                best["Evidence_Confidence"] = float(group["Evidence_Confidence"].max())
                best["Confidence_Note"] = confidence_adjusted_framing_note(
                    rd_opportunity_score=new_score,
                    evidence_confidence=best["Evidence_Confidence"],
                ) or ""

            if "Candidate_Evidence_Strength_Tier" in group.columns:
                # Depends on Occurrence_Corroboration and Evidence_Confidence,
                # both just finalized above — recomputed here, not carried
                # over from the pre-merge best sub-row, for the same
                # staleness reasons as every other derived column in
                # this function.
                best["Candidate_Evidence_Strength_Tier"] = classify_candidate_evidence_strength(
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    evidence_confidence=best["Evidence_Confidence"],
                    evidence_hierarchy_detail=str(best.get("Evidence_Hierarchy_Detail", "")),
                )

            if "Decision_Class_AH" in group.columns:
                # best's own _match_quality/_same_plant (from the
                # highest-scoring sub-row) are reused here — same
                # "best sub-row's own values, recombined with the
                # group-level recomputed score/decision" pattern the
                # rest of this merge function already uses.
                best["Decision_Class_AH"] = classify_decision_ah(
                    existing_decision_class=new_decision,
                    evidence_confidence=best["Evidence_Confidence"],
                    rd_opportunity_score=new_score,
                    market_status=str(best.get("Market_Status", "")),
                    match_quality=str(best.get("_match_quality", "")),
                    same_plant=bool(best.get("_same_plant", False)),
                )

            if "Applicability_Summary" in group.columns:
                # Task 10.2 — a merged row can combine several sub-rows,
                # each matched to a different compound and therefore
                # each potentially carrying a DIFFERENT set of evidence
                # items (_collect_applicability_items() is scoped per
                # matched compound) — same "recompute from the merged
                # group, don't just keep whichever sub-row scored
                # highest" reasoning as every other field in this
                # function.
                #
                # Correction (post-acceptance): each PERSISTED evidence
                # record is now counted EXACTLY ONCE by its stable
                # evidence_record_id, even if it contributed to more
                # than one matched compound's sub-row — see
                # _merge_applicability_summaries()'s own docstring for
                # how (it deduplicates each sub-row's evidence_items
                # list, then re-derives counts/strongest_category/
                # mismatches from that single deduplicated set via
                # _summarize_applicability(), rather than summing
                # pre-aggregated counts across sub-rows). Only items
                # with no evidence_record_id at all (never persisted)
                # still rely on a documented, disclosed fallback
                # signature — see that docstring for the exact,
                # narrow limitation this leaves.
                summaries = [s for s in group["Applicability_Summary"] if isinstance(s, dict)]
                best["Applicability_Summary"] = self._merge_applicability_summaries(summaries)

            if "GRADE_Certainty" in group.columns:
                # Task 2 — same "any one matched compound with a real,
                # strong signal is a genuine signal about the candidate
                # as a whole" reasoning already used for
                # Evidence_Confidence's merge above (group.max()),
                # applied to a categorical rating instead of a numeric
                # score: picks whichever sub-row's GRADE_Certainty
                # ranks highest ("Not GRADE-applicable" ranks lowest,
                # below "Very Low", so a genuinely-graded sub-row is
                # always preferred over an ungraded one when both
                # exist in the same group).
                _rank_map = {
                    "High": 3, "Moderate": 2, "Low": 1, "Very Low": 0,
                }
                best_idx = group["GRADE_Certainty"].map(
                    lambda c: _rank_map.get(c, -1)
                ).idxmax()
                best["GRADE_Certainty"] = group.loc[best_idx, "GRADE_Certainty"]
                best["GRADE_Certainty_Rationale"] = group.loc[best_idx, "GRADE_Certainty_Rationale"]

            if "Gate_Results" in group.columns:
                # Task 1 — a merged row can combine multiple sub-rows'
                # safety/regulatory signal (see the Safety_Flags/
                # Regulatory_Barriers merges above), so gates must be
                # recomputed from those already-merged fields — same
                # staleness reasoning as every other derived column in
                # this function — rather than carrying over whichever
                # single sub-row happened to be "best" pre-merge.
                # has_evidence is approximated from Evidence_Level here
                # (the per-row has_real_evidence boolean isn't itself a
                # merged column) — acceptable because minimum_evidence
                # is informational-only in this task, same as identity
                # and regulatory; only "safety" (driven by the already
                # correctly-merged Safety_Flags) is behaviorally tied to
                # Decision_Class.
                merged_evidence_level = str(best.get("Evidence_Level", "No direct evidence"))
                regulatory_barriers_str = str(best.get("Regulatory_Barriers", "") or "")
                if regulatory_barriers_str and regulatory_barriers_str != "None identified":
                    merged_barrier_types = [
                        b.strip() for b in regulatory_barriers_str.split("; ") if b.strip()
                    ]
                else:
                    merged_barrier_types = []
                best["Gate_Results"] = self._evaluate_gates(
                    safety_flags=str(best.get("Safety_Flags", "") or ""),
                    match_quality=str(best.get("_match_quality", "")),
                    has_evidence=merged_evidence_level != "No direct evidence",
                    evidence_level=merged_evidence_level,
                    regulatory_barrier_types=merged_barrier_types,
                    same_plant=bool(best.get("_same_plant", False)),
                )

            if "White_Space_Type" in group.columns:
                best["White_Space_Type"] = classify_white_space(
                    evidence_confidence=best["Evidence_Confidence"],
                    market_status=str(best.get("Market_Status", "")),
                    use_live_search=self.use_live_search,
                ) or ""

            if "Go_Investigate_Hold_NoGo" in group.columns:
                # Recomputed from the just-updated Decision_Class_AH,
                # Evidence_Confidence, Market_Status, White_Space_Type,
                # etc. — the same staleness concern as every other
                # merge-recomputed field above: these must reflect the
                # GROUP-level merged result, not whichever single
                # sub-row happened to score highest before merging.
                best["Go_Investigate_Hold_NoGo"] = go_investigate_hold_no_go(
                    str(best.get("Decision_Class_AH", "")),
                    fallback_occurred=not self.data_source_reliable,
                )
                best["Scientific_Rationale"] = scientific_rationale(
                    match_quality=str(best.get("_match_quality", "")),
                    target_provenance=str(best.get("Target_Provenance", "")),
                    evidence_hierarchy_detail=str(best.get("Evidence_Hierarchy_Detail", "")),
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                )
                best["Commercial_Regulatory_Rationale"] = commercial_regulatory_rationale(
                    market_status=str(best.get("Market_Status", "")),
                    white_space_type=str(best.get("White_Space_Type", "")),
                    regulatory_barriers=(
                        str(best.get("Regulatory_Barriers", ""))
                        if str(best.get("Regulatory_Barriers", "")) != "None identified"
                        else None
                    ),
                )
                merged_strengths = evidence_strengths(
                    match_quality=str(best.get("_match_quality", "")),
                    evidence_confidence=best["Evidence_Confidence"],
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    market_status=str(best.get("Market_Status", "")),
                )
                merged_weaknesses = evidence_weaknesses(
                    evidence_confidence=best["Evidence_Confidence"],
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                    negative_evidence_types=str(best.get("Negative_Evidence_Types", "")),
                    safety_flags=str(best.get("Safety_Flags", "")),
                    market_status=str(best.get("Market_Status", "")),
                    regulatory_barriers=(
                        str(best.get("Regulatory_Barriers", ""))
                        if str(best.get("Regulatory_Barriers", "")) != "None identified"
                        else None
                    ),
                )
                best["Evidence_Strengths"] = "; ".join(merged_strengths) if merged_strengths else "None identified"
                best["Evidence_Weaknesses"] = "; ".join(merged_weaknesses) if merged_weaknesses else "None identified"
                best["Next_Experiment_Suggestion"] = next_experiment_suggestion(
                    decision_class_ah=str(best.get("Decision_Class_AH", "")),
                    evidence_weaknesses_list=merged_weaknesses,
                    alt_plant=str(best.get("Alternative_Plant", "")),
                )
                best["Evidence_Conflict_Reasoning"] = evidence_conflict_reasoning(
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                    negative_evidence_types=str(best.get("Negative_Evidence_Types", "")),
                    evidence_confidence=best["Evidence_Confidence"],
                )
                best["Evidence_Conflict_Structured"] = build_evidence_conflict_structured(
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                    negative_evidence_types=str(best.get("Negative_Evidence_Types", "")),
                    evidence_hierarchy_detail=str(best.get("Evidence_Hierarchy_Detail", "")),
                    evidence_level=str(best.get("Evidence_Level", "")),
                    safety_flags=str(best.get("Safety_Flags", "")),
                    market_status=str(best.get("Market_Status", "")),
                    evidence_conflict_reasoning_text=best["Evidence_Conflict_Reasoning"],
                    # raw_evidence_text intentionally omitted — not carried as a
                    # stored column post-merge (same limitation already
                    # documented for Evidence_Conflict_Reasoning's own WHY-hint
                    # above); possible_explanations honestly comes back empty
                    # here rather than guessing from stale pre-merge text.
                )
                best["Recommendation_Confidence_Statement"] = recommendation_confidence_statement(
                    go_call=str(best.get("Go_Investigate_Hold_NoGo", "")),
                    candidate_evidence_strength_tier=str(best.get("Candidate_Evidence_Strength_Tier", "")),
                    evidence_confidence=best["Evidence_Confidence"],
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                )
                best["Competitive_Positioning"] = competitive_positioning_statement(
                    market_status=str(best.get("Market_Status", "")),
                    candidate_evidence_strength_tier=str(best.get("Candidate_Evidence_Strength_Tier", "")),
                    regulatory_barriers=(
                        str(best.get("Regulatory_Barriers", ""))
                        if str(best.get("Regulatory_Barriers", "")) != "None identified"
                        else None
                    ),
                    white_space_type=str(best.get("White_Space_Type", "")),
                )
                best["Regulatory_Rationale"] = regulatory_rationale(
                    market_status=str(best.get("Market_Status", "")),
                    regulatory_barriers=(
                        str(best.get("Regulatory_Barriers", ""))
                        if str(best.get("Regulatory_Barriers", "")) != "None identified"
                        else None
                    ),
                )
                best["Commercial_Rationale"] = commercial_rationale(
                    market_status=str(best.get("Market_Status", "")),
                    white_space_type=str(best.get("White_Space_Type", "")),
                )
                best["Safety_Rationale"] = safety_rationale(
                    safety_flags=str(best.get("Safety_Flags", "No explicit flag found")),
                    interaction_flags=str(best.get("Interaction_Flags", "No explicit flag found")),
                )
                best["Clinical_Rationale"] = clinical_rationale(
                    evidence_hierarchy_detail=str(best.get("Evidence_Hierarchy_Detail", "")),
                    evidence_confidence=best["Evidence_Confidence"],
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                )

            # The pre-merge Rationale text (from _rationale(), on the
            # single "best" sub-row) ends with a hardcoded
            # "Decision: <that sub-row's own decision>." sentence. If the
            # group-level recompute above changed the decision (e.g. a
            # DIFFERENT sub-row's safety flag pulled the merged result
            # down to "Safety concern"), that trailing sentence goes
            # stale — the Rationale text would keep saying "Decision:
            # Strong R&D candidate" even though the Decision_Class column
            # right next to it says "Safety concern". Replacing it here
            # keeps the free text and the structured column in agreement,
            # for any decision change, not just this one.
            old_rationale = str(best["Rationale"])
            best["Rationale"] = re.sub(
                r"Decision: .+\.$",
                f"Decision: {new_decision}.",
                old_rationale,
            )

            best["Rationale"] = (
                f"Matches {num_matches} independent reference compounds "
                f"({', '.join(distinct_matched)}) — a materially stronger "
                f"signal than a single shared compound. " + str(best["Rationale"])
            )

            merged_rows.append(best)

        return pd.DataFrame(merged_rows)

    def _get_reference_plants(
        self,
        problem,
        dosage_form,
        market,
        max_reference_plants,
    ):
        if self.candidate_source == "supabase":
            direct = self._reference_plants_from_supabase(
                problem, max_reference_plants
            )
            if not direct.empty:
                return direct.head(max_reference_plants)

        try:
            ranked = rank_global_candidates(
                indication=problem,
                dosage_form=dosage_form,
                market=market,
                target_count=max_reference_plants,
            )
        except Exception:
            ranked = pd.DataFrame()

        ranked = self._to_dataframe(ranked)

        if ranked.empty:
            candidate_df = self._candidate_frame()
            problem_norm = self._norm(problem)

            ranked = candidate_df[
                candidate_df["Indications_Text_Norm"].str.contains(
                    problem_norm,
                    na=False,
                    regex=False,
                )
            ]

        # Also check the known_inventory-based fallback (TARGET_DISEASES ->
        # COMPOUND_TARGETS -> PLANT_COMPOUNDS / Supabase plant_compounds) —
        # the same chain Step 1/Step 4 ("Existing Scientific Knowledge")
        # already uses successfully. A plant only gets manually tagged with
        # an exact indication in GLOBAL_PLANT_CANDIDATES for a handful of
        # cases (e.g. only Centella asiatica is tagged "Wound healing",
        # even though 20+ other plants have wound-healing-relevant
        # compounds per COMPOUND_TARGETS). Whichever source finds MORE
        # reference plants wins, instead of always stopping at the first
        # non-empty one — otherwise a single narrowly-tagged plant silently
        # shadows a much richer, already-working result.
        from_inventory = self._reference_plants_from_known_inventory(
            problem, max_reference_plants
        )

        if len(from_inventory) > len(ranked):
            ranked = from_inventory

        return ranked.head(max_reference_plants)

    def _reference_plants_from_known_inventory(self, problem, max_reference_plants):
        inventory = self.known_inventory_df(problem)

        if inventory.empty:
            return pd.DataFrame()

        rows = []

        for plant, group in inventory.groupby("Known_Plant"):
            compounds = sorted(
                c for c in group["Known_Compound"].dropna().unique() if c
            )
            targets = sorted(
                t for t in group["Known_Target"].dropna().unique() if t
            )

            if not plant or not compounds:
                continue

            rows.append({
                "Scientific_Name": plant,
                "Known_Active_Compounds": "; ".join(compounds),
                "Known_Targets": "; ".join(targets),
            })

        return pd.DataFrame(rows).head(max_reference_plants)

    def _reference_plants_from_supabase(self, problem, max_reference_plants):
        """Select reference plants from evidence-bearing tables first.

        Source priority:
        1. ``scientific_evidence`` (source-linked scientific records),
        2. ``evidence_records`` (structured extracted evidence),
        3. curated/non-compilation rows in ``plant_compounds`` only as a
           conservative fallback.

        ``plant_compounds.indication`` is deliberately *not* treated as direct
        evidence when the row is labelled as a broad phytochemical compilation
        (for example ``Phytochemical literature compilation (not clinical)``).
        Those rows often list dozens of conditions and previously caused nearly
        the entire botanical catalogue to be returned for a single question.
        """
        problem_norm = self._norm(problem)
        if not problem_norm:
            return pd.DataFrame()

        plant_scores = defaultdict(float)
        plant_support = defaultdict(int)
        plant_sources = defaultdict(set)

        def add_score(plant, score, source):
            plant = str(plant or "").strip()
            if not plant or score <= 0:
                return
            plant_scores[plant] += float(score)
            plant_support[plant] += 1
            plant_sources[plant].add(source)

        # 1) Scientific evidence: strongest retrieval signal.
        se = self.scientific_evidence_df
        if se is not None and not se.empty and "plant" in se.columns:
            for _, row in se.iterrows():
                indication_text = str(row.get("indication") or "")
                match = self._semantic_indication_match_score(problem_norm, indication_text)
                if match <= 0:
                    continue
                quality = self._safe_float(row.get("final_scientific_score"), 0.0)
                if quality <= 0:
                    quality = self._safe_float(row.get("overall_evidence_score"), 0.0)
                if quality <= 0:
                    quality = self._safe_float(row.get("evidence_score"), 0.0)
                quality_bonus = min(max(quality, 0.0), 100.0) / 100.0
                add_score(row.get("plant"), 10.0 * match + quality_bonus, "scientific_evidence")

        # 2) Structured evidence records.  Search every indication field, but
        # reward direct-for-product records and stronger evidence scores.
        er = self.evidence_records_df
        if er is not None and not er.empty:
            indication_cols = [
                c for c in (
                    "target_indication", "extracted_indication",
                    "detected_indications", "target_indication_detected",
                ) if c in er.columns
            ]
            for _, row in er.iterrows():
                best = 0.0
                for col in indication_cols:
                    best = max(
                        best,
                        self._semantic_indication_match_score(
                            problem_norm, str(row.get(col) or "")
                        ),
                    )
                if best <= 0:
                    continue
                plant = row.get("plant")
                direct = str(row.get("direct_for_selected_product") or "").strip().lower()
                direct_bonus = 1.0 if direct in {"true", "yes", "direct", "1"} else 0.0
                evidence_bonus = min(
                    max(self._safe_float(row.get("evidence_score"), 0.0), 0.0),
                    100.0,
                ) / 100.0
                add_score(plant, 7.0 * best + direct_bonus + evidence_bonus, "evidence_records")

        # 3) Conservative plant_compounds fallback.  Broad compilations are
        # excluded because their semicolon lists are hypothesis-generating, not
        # plant-level indication evidence.
        pc = self.plant_compounds_df
        if pc is not None and not pc.empty and {"scientific_name", "indication"}.issubset(pc.columns):
            for _, row in pc.iterrows():
                evidence_level = str(row.get("evidence_level") or "").lower()
                source = str(row.get("source") or "").lower()
                is_broad_compilation = (
                    "not clinical" in evidence_level
                    or "compilation" in evidence_level
                    or "dr. duke" in source
                    or "dr duke" in source
                )
                if is_broad_compilation:
                    continue
                match = self._semantic_indication_match_score(
                    problem_norm, str(row.get("indication") or "")
                )
                if match <= 0:
                    continue
                confidence = self._safe_float(row.get("confidence_score"), 0.0)
                confidence_bonus = min(max(confidence, 0.0), 100.0) / 200.0
                add_score(row.get("scientific_name"), 2.0 * match + confidence_bonus, "plant_compounds")

        if not plant_scores:
            return self._reference_plants_from_candidate_data(problem, max_reference_plants)

        ranked_plants = sorted(
            plant_scores,
            key=lambda plant: (
                -plant_scores[plant],
                -len(plant_sources[plant]),
                -plant_support[plant],
                plant.lower(),
            ),
        )[:max_reference_plants]

        rows = []
        for plant in ranked_plants:
            group = pd.DataFrame()
            if pc is not None and not pc.empty and "scientific_name" in pc.columns:
                group = pc[
                    pc["scientific_name"].fillna("").astype(str).str.strip() == plant
                ]

            compounds = []
            targets = []
            plant_part = ""
            if not group.empty:
                # Use a small, deterministic compound set.  This prevents one
                # evidence-supported plant from fanning out through every common
                # phytochemical ever reported for it.
                ranked_group = group.copy()
                if "confidence_score" in ranked_group.columns:
                    ranked_group["_confidence"] = pd.to_numeric(
                        ranked_group["confidence_score"], errors="coerce"
                    ).fillna(0)
                    ranked_group = ranked_group.sort_values("_confidence", ascending=False)
                compounds = self._unique_clean_list(ranked_group.get("compound_name"))[:8]
                if "target" in ranked_group.columns:
                    targets = self._unique_clean_list(
                        self._split_series_terms(ranked_group.get("target"))
                    )[:12]
                if "plant_part" in ranked_group.columns:
                    plant_part = self._first_non_empty(ranked_group["plant_part"])

            rows.append({
                "Scientific_Name": plant,
                "Known_Active_Compounds": "; ".join(compounds),
                "Known_Targets": "; ".join(targets),
                "Plant_Part": plant_part,
                "Retrieval_Sources": "; ".join(sorted(plant_sources[plant])),
                "Retrieval_Score": round(plant_scores[plant], 3),
            })

        return pd.DataFrame(rows)

    def _semantic_indication_match_score(self, query_norm, candidate_text):
        """Conservative indication matching with a small domain synonym map.

        Matching is performed against individual semicolon-separated concepts,
        never against an enormous condition list as one undifferentiated string.
        """
        candidate_norm = self._norm(candidate_text)
        if not query_norm or not candidate_norm:
            return 0.0

        concept_groups = {
            "metabolic blood sugar support": {
                "diabetes", "type 2 diabetes", "blood sugar", "glucose",
                "glycemic control", "glycaemic control", "hyperglycemia",
                "hyperglycaemia", "insulin resistance", "metabolic syndrome",
                "syndrome x",
            },
            "energy fatigue": {
                "fatigue", "chronic fatigue syndrome", "tiredness",
                "asthenia", "energy", "stamina", "anti fatigue",
            },
            "sleep": {
                "sleep", "insomnia", "sleep disorder", "sleep quality",
            },
            "anxiety stress": {
                "anxiety", "stress", "anxiety disorders",
            },
        }

        # Canonicalise separators/connectors before selecting a synonym group.
        # Without this, a UI label such as ``Metabolic & blood sugar support``
        # normalises to ``metabolic & blood sugar support`` and fails to match
        # the concept-group key ``metabolic blood sugar support``.
        query_key = re.sub(r"[^a-z0-9]+", " ", query_norm)
        query_key = re.sub(r"\b(and|support|health)\b", " ", query_key)
        query_key = re.sub(r"\s+", " ", query_key).strip()

        query_terms = set()
        for key, terms in concept_groups.items():
            key_norm = re.sub(r"[^a-z0-9]+", " ", key)
            key_norm = re.sub(r"\b(and|support|health)\b", " ", key_norm)
            key_norm = re.sub(r"\s+", " ", key_norm).strip()
            if key_norm in query_key or any(self._norm(term) in query_norm for term in terms):
                query_terms.update(terms)
        if not query_terms:
            query_terms.add(query_norm)

        concepts = [
            self._norm(part)
            for part in re.split(r"[;|\n]+", str(candidate_text))
            if self._norm(part)
        ]
        best = 0.0
        for concept in concepts:
            if concept == query_norm:
                best = max(best, 1.0)

            matched_terms = set()
            reverse_matches = set()
            for term in query_terms:
                term_norm = self._norm(term)
                if concept == term_norm:
                    best = max(best, 0.95)
                    matched_terms.add(term_norm)
                elif len(term_norm) >= 5 and term_norm in concept:
                    matched_terms.add(term_norm)
                elif len(concept) >= 5 and concept in term_norm:
                    reverse_matches.add(term_norm)

            # Reward concepts that express more than one relevant idea.  This
            # keeps ``Energy fatigue`` above a noisy phrase such as
            # ``unrelated fatigue marker`` instead of resolving the tie
            # alphabetically.
            if len(matched_terms) >= 2:
                best = max(best, 0.90)
            # A single synonym occurring inside a longer phrase is too weak
            # for a multi-concept therapeutic-area query. Exact single-term
            # concepts (for example ``fatigue`` or ``diabetes``) were already
            # accepted above at 0.95; noisy phrases such as ``unrelated fatigue
            # marker`` are rejected here instead of entering the inventory.
            elif reverse_matches and len(self._meaningful_tokens(concept)) <= 2:
                best = max(best, 0.70)
        return best

    def _reference_plants_from_candidate_data(self, problem, max_reference_plants):
        """Fallback used only when the raw plant_compounds_df doesn't have
        the columns needed for row-level indication filtering (e.g. a
        candidate_data override was supplied directly instead of a real
        Supabase table). Less precise than the row-level method above —
        this works off whole-plant aggregated compound lists — but keeps
        old override-based usage working.
        """
        problem_norm = self._norm(problem)

        exact_matched = [
            item for item in self.candidate_data
            if any(
                problem_norm in self._norm(indication)
                or self._norm(indication) in problem_norm
                for indication in item.get("Indications", [])
            )
        ]

        problem_tokens = self._meaningful_tokens(problem_norm)
        token_matched = [
            item for item in self.candidate_data
            if problem_tokens
            and any(
                self._tokens_overlap(
                    problem_tokens,
                    self._meaningful_tokens(self._norm(indication)),
                )
                for indication in item.get("Indications", [])
            )
        ]

        # Union both, preserving order, deduplicated by Scientific_Name.
        # As with _reference_plants_from_supabase above: a single narrow
        # exact-substring match must not suppress the (usually much
        # richer) token-overlap matches.
        seen_names = set()
        matched = []
        for item in exact_matched + token_matched:
            name = item.get("Scientific_Name")
            if name not in seen_names:
                seen_names.add(name)
                matched.append(item)

        if not matched:
            return pd.DataFrame()

        def _specificity_key(item):
            indications_text = "; ".join(item.get("Indications", []))
            return len(indications_text)

        matched = sorted(matched, key=_specificity_key)

        rows = []
        for item in matched[:max_reference_plants]:
            row = dict(item)
            row["Known_Active_Compounds"] = "; ".join(
                item.get("Known_Active_Compounds", [])
            )
            row["Known_Targets"] = ", ".join(item.get("Known_Targets", []))
            row["Indications_Text"] = ", ".join(item.get("Indications", []))
            rows.append(row)

        return pd.DataFrame(rows)

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            if value is None or str(value).strip().lower() in {"", "nan", "none", "null"}:
                return float(default)
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _load_supabase_df(explicit_df, loader):
        """Returns (df, succeeded). An explicitly-provided DataFrame is
        always treated as succeeded=True — the caller who provided it
        is responsible for having already checked its own load (see
        step_rd_candidates.py's _cached_engine, which does exactly
        that and passes the combined result via data_source_reliable
        instead). succeeded=False only ever reflects a failure THIS
        method itself encountered while loading on its own."""
        if explicit_df is not None:
            return BotanicalRDCandidateEngine._to_dataframe(explicit_df), True

        try:
            loaded = loader()
        except Exception:
            return pd.DataFrame(), False

        return (loaded if isinstance(loaded, pd.DataFrame) else pd.DataFrame()), True

    def _candidates_from_plant_compounds(self):
        """Build the GLOBAL_PLANT_CANDIDATES-shaped list directly from the
        real plant_compounds table (grouped by scientific_name), instead
        of the small hardcoded local list.
        """
        df = self.plant_compounds_df.copy()

        if "scientific_name" not in df.columns:
            return GLOBAL_PLANT_CANDIDATES

        df["scientific_name"] = df["scientific_name"].fillna("").astype(str).str.strip()
        df = df[df["scientific_name"] != ""]

        if df.empty:
            return GLOBAL_PLANT_CANDIDATES

        candidates = []

        for scientific_name, group in df.groupby("scientific_name"):
            candidates.append({
                "Scientific_Name": scientific_name,
                "Common_Name": self._first_non_empty(group.get("common_name")),
                "Region": get_region(scientific_name),
                "Indications": self._unique_clean_list(group.get("indication")),
                "Known_Active_Compounds": self._unique_clean_list(
                    group.get("compound_name")
                ),
                "Known_Targets": self._unique_clean_list(
                    self._split_series_terms(group.get("target"))
                ),
                "Plant_Part": self._first_non_empty(group.get("plant_part")),
                "Extraction_Method": self._first_non_empty(
                    group.get("extraction_method")
                ),
                "EMA_Status": "",
            })

        return candidates or GLOBAL_PLANT_CANDIDATES

    @staticmethod
    def _unique_clean_list(values):
        if values is None:
            return []

        seen = []
        for value in values:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"nan", "none", "null"} and text not in seen:
                seen.append(text)

        return seen

    @staticmethod
    def _first_non_empty(values):
        if values is None:
            return ""

        for value in values:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"nan", "none", "null"}:
                return text

        return ""

    def _split_series_terms(self, values):
        if values is None:
            return []

        terms = []
        for value in values:
            terms.extend(self._split_terms(value))

        return terms

    @staticmethod
    def _seed_data_only_candidates():
        """Every plant in seed_data.PLANT_COMPOUNDS that ISN'T already in
        GLOBAL_PLANT_CANDIDATES, reshaped into the same candidate-dict
        format (Known_Active_Compounds / Known_Targets / Region), so it
        can be searched as an alternative-plant match target. No
        Indications tag on purpose — see the comment where this is called.
        """
        already_covered = {
            item["Scientific_Name"] for item in GLOBAL_PLANT_CANDIDATES
        }

        candidates = []

        for plant, compounds in PLANT_COMPOUNDS.items():
            if plant in already_covered:
                continue

            compound_names = [name for name, _cls, _extraction in compounds]
            targets = sorted({
                target
                for name in compound_names
                for target in COMPOUND_TARGETS.get(name, [])
            })
            extraction = next(
                (ext for _name, _cls, ext in compounds if ext), ""
            )

            candidates.append({
                "Scientific_Name": plant,
                "Common_Name": "",
                "Region": get_region(plant),
                "Indications": [],
                "Known_Active_Compounds": compound_names,
                "Known_Targets": targets,
                "Plant_Part": "",
                "Extraction_Method": extraction,
                "EMA_Status": "",
            })

        return candidates

    def _candidate_frame(self):
        rows = []

        for item in self.candidate_data:
            row = dict(item)

            # Phase 2C (regulatory single-source-of-truth cleanup) —
            # neutralize any EMA_Status this candidate-data row might
            # carry, unconditionally, regardless of source. The ONLY
            # consumer of a candidate row's "EMA_Status" is
            # _market_status() (via self._pick(alt, ["EMA_Status"])),
            # which exists specifically to reflect the CANONICAL EMA
            # connector's result — never a second, independently
            # maintained regulatory judgment. _candidates_from_plant_
            # compounds() (the live/Supabase candidate path) already
            # sets this to "" for exactly that reason; this makes
            # GLOBAL_PLANT_CANDIDATES's hardcoded per-plant "Yes"/"No"
            # values (the local_fallback path, used only when Supabase
            # data is unavailable) behave identically instead of
            # silently overriding the real connector for whichever
            # plants that hardcoded reference happens to cover.
            #
            # Deliberately done HERE, not in global_plant_candidate_
            # database.py itself: that file's EMA_Status field is also
            # read independently by global_candidate_ranking_engine.py's
            # own, separate candidate-ranking score (a different,
            # already-scoped pipeline this phase must not touch) — so
            # the underlying data is left completely intact, and is
            # only ever neutralized at this one boundary, where a
            # candidate row becomes an "alt" input to this engine's
            # regulatory-status function.
            row["EMA_Status"] = ""

            row["Known_Active_Compounds"] = "; ".join(
                item.get("Known_Active_Compounds", [])
            )

            row["Known_Targets"] = ", ".join(
                item.get("Known_Targets", [])
            )

            row["Indications_Text"] = ", ".join(
                item.get("Indications", [])
            )

            row["Indications_Text_Norm"] = self._norm(
                row["Indications_Text"]
            )

            rows.append(row)

        return pd.DataFrame(rows)

    def _build_evidence_text_index(self):
        """Returns (text_index, source_index, applicability_index,
        authority_index).

        text_index: dict of normalized_key -> concatenated evidence
        text, used for Evidence_Level/safety-flag/hierarchy extraction.
        As of Task 10.2, the self.evidence_df pass concatenates only
        EVIDENCE_TEXT_INDEX_ALLOWLIST's columns (source-derived fields),
        not every column — see that constant's docstring for why.

        source_index: (audit "Gap 1: traceability"). Every connector
        that saves evidence to Supabase already writes a real
        Source_URL for that specific record (pubmed_connector.py:
        https://pubmed.ncbi.nlm.nih.gov/{pmid}/, and the same pattern in
        chembl_connector.py, clinicaltrials_connector.py,
        crossref_connector.py, chebi_connector.py, etc.) — that URL was
        previously discarded the moment a row got folded into the flat
        text_index string. source_index keeps the SAME normalized_key
        structure as text_index, but maps to a list of the specific
        Source_URLs that contributed to that key, so a downstream
        candidate row can cite exactly which record(s) it came from
        instead of only a generic "Live-collected evidence" label.

        applicability_index: NEW (Task 10.2). SAME normalized_key
        structure as text_index/source_index, but maps to a list of
        small structured dicts — one per self.evidence_df row that
        contributed to that key — each carrying that row's
        Evidence_Record_ID/Applicability_Classification/rationale/
        missing dimensions/mismatches. Built from self.evidence_df
        only: self.scientific_evidence_df has no Task 10.2 applicability
        columns (that table has no active write path at all — see
        repo_dependency_audit.py's legacy_candidates classification of
        scientific_evidence_collector.py — so there is nothing to read
        there). Kept STRUCTURED (never folded into the free-text
        string) specifically so a candidate-level summary can read
        exact classifications/ids rather than re-parsing text.

        authority_index: (Phase 3, problem 1). SAME normalized_key
        structure again, mapping to a list of small structured dicts —
        one per contributing self.evidence_df row — carrying that row's
        Evidence_Record_ID/Source Authority label/factor (via
        evidence_authority.classify_source_authority_from_row). See
        _collect_raw_evidence() for how a single representative factor
        is derived from this per row-set-that-actually-contributed-text.
        """
        index = defaultdict(str)
        source_index = defaultdict(list)
        applicability_index = defaultdict(list)
        authority_index = defaultdict(list)
        # Phase 4 (correction round) — per-EvidenceRecord (id, text)
        # pairs, SAME normalized_key structure as the indexes above.
        # Needed so Safety_Gate_Evidence_IDs / Regulatory_Gate_Evidence_IDs
        # can be finding-specific: only the records whose OWN text
        # actually contains the matched hit term / barrier phrase, not
        # every record that happened to contribute to this key's pooled
        # text blob (which is what evidence_source_ids gives — a
        # candidate-level, not finding-level, id list). See
        # _collect_raw_evidence()'s new evidence_records return value
        # and the row-loop's _safety_gate_evidence_ids/
        # _regulatory_gate_evidence_ids construction in run().
        evidence_records_index = defaultdict(list)

        def _record_evidence_record(key, row, text):
            if not text or not text.strip():
                return
            record_id = self._pick(row, ["Evidence_Record_ID", "evidence_record_id"])
            classification = classify_source_authority_from_row(row)
            assertion_text = " ".join(
                str(row.get(col))
                for col in (
                    "Notes", "Regulatory_Evidence", "Safety_Signal",
                    "Primary_Outcome", "Result_Direction", "Evidence_Type",
                    "Evidence_Level", "Clinical_Level", "Meta_Level",
                    "Drug_Interaction_Level", "Safety_Level",
                )
                if col in row.index and pd.notna(row.get(col)) and str(row.get(col)).strip()
            )
            evidence_records_index[key].append({
                "evidence_record_id": record_id or None,
                "text": text,
                "assertion_text": assertion_text or text,
                "authority_label": classification.label,
                "authority_factor": classification.score,
                "source_url": self._pick(row, ["Source_URL", "source_url", "URL", "url"]) or "",
                "source_type": self._pick(row, ["Source_Type", "source_type"]) or "",
                "study_design": self._pick(row, ["Study_Type", "study_type", "Study_Design", "study_design"]) or "",
                "preparation": self._pick(row, ["Preparation", "preparation", "Extraction_Method", "extraction_method"]) or "",
                "dose": self._pick(row, ["Dose", "dose"]) or "",
                "route": self._pick(row, ["Administration_Route", "administration_route", "Route", "route"]) or "",
                "population": self._pick(row, ["Population", "population"]) or "",
                "target_indication": self._pick(row, ["Target_Indication", "target_indication", "Indication", "indication"]) or "",
                "source_year": self._pick(row, ["Source_Year", "source_year", "Publication_Year", "publication_year", "Year", "year"]) or "",
                "evidence_quality": self._pick(row, ["Evidence_Quality", "evidence_quality", "Evidence_Level", "evidence_level"]) or "",
                "reported_direction": self._pick(row, ["Evidence_Direction", "evidence_direction", "Result_Direction", "result_direction"]) or "",
                "pmid": self._pick(row, ["PMID", "pmid"]) or "",
                "doi": self._pick(row, ["DOI", "doi"]) or "",
            })

        def _record_source(key, row):
            url = self._pick(row, ["Source_URL", "source_url", "URL", "url"])
            if url:
                source_index[key].append(url)

        def _record_authority(key, row):
            # Phase 3, problem 1 — real per-source Source Authority,
            # SAME pattern as _record_applicability() just above: kept as
            # a small structured entry (evidence_record_id/label/factor),
            # never folded into the free-text string, so a downstream
            # candidate row can look up which SPECIFIC row(s) actually
            # backed this key's evidence text and how authoritative each
            # one was — instead of guessing or defaulting every row to
            # 1.0 regardless of whether an EMA/WHO/ESCOP/Cochrane source
            # is actually present. Only evidence_df rows are classified
            # here (they carry Source_Organization/Source_Type/
            # Source_Category — the fields classify_source_authority_from_row
            # actually reads); this does not redesign or widen scope
            # beyond the existing index-building pass.
            classification = classify_source_authority_from_row(row)
            authority_index[key].append({
                "evidence_record_id": self._pick(
                    row, ["Evidence_Record_ID", "evidence_record_id"]
                ) or None,
                "authority_label": classification.label,
                "authority_factor": classification.score,
            })

        def _record_applicability(key, row):
            # Backward compatible with rows saved before Task 10.2 (or
            # loaded from a Supabase table that hasn't had the new
            # columns added yet, per database.py's documented
            # degrade-to-"" behavior): a row with no classification is
            # simply not appended here, rather than appended as a
            # fabricated "Not assessable" entry with no evidence record
            # actually behind it.
            classification = self._pick(
                row, ["Applicability_Classification", "applicability_classification"]
            )
            if not classification:
                return

            def _split(value):
                value = value or ""
                return [part.strip() for part in str(value).split(";") if part.strip()]

            applicability_index[key].append({
                "evidence_record_id": self._pick(
                    row, ["Evidence_Record_ID", "evidence_record_id"]
                ) or None,
                "classification": classification,
                "rationale": self._pick(
                    row, ["Applicability_Rationale", "applicability_rationale"]
                ) or "",
                "evaluated_dimensions": _split(self._pick(
                    row, ["Applicability_Evaluated_Dimensions", "applicability_evaluated_dimensions"]
                )),
                "missing_dimensions": _split(self._pick(
                    row, ["Applicability_Missing_Dimensions", "applicability_missing_dimensions"]
                )),
                "detected_mismatches": _split(self._pick(
                    row, ["Applicability_Detected_Mismatches", "applicability_detected_mismatches"]
                )),
            })

        if not self.evidence_df.empty:
            for _, row in self.evidence_df.iterrows():
                text = " ".join(
                    str(row.get(col))
                    for col in EVIDENCE_TEXT_INDEX_ALLOWLIST
                    if col in row.index and pd.notna(row.get(col)) and str(row.get(col)).strip()
                )

                plant = self._pick(
                    row,
                    [
                        "Scientific_Name",
                        "scientific_name",
                        "Plant",
                        "plant",
                        "Common_Name",
                        "common_name",
                    ],
                )

                if plant:
                    plant_key = _botanical_taxonomy.taxon_match_key(plant)
                    index[plant_key] += " " + text
                    _record_source(plant_key, row)
                    _record_applicability(plant_key, row)
                    _record_authority(plant_key, row)
                    _record_evidence_record(plant_key, row, text)

                for compound in self._known_compounds_from_text(text):
                    compound_key = self._norm(compound)
                    index[compound_key] += " " + text
                    _record_source(compound_key, row)
                    _record_applicability(compound_key, row)
                    _record_authority(compound_key, row)
                    _record_evidence_record(compound_key, row, text)

        if not self.scientific_evidence_df.empty:
            text_columns = [
                "title", "abstract", "decision_reason",
                "evidence_flags", "decision_class", "indication",
            ]

            for _, row in self.scientific_evidence_df.iterrows():
                text = " ".join(
                    str(row.get(col))
                    for col in text_columns
                    if pd.notna(row.get(col, None)) and str(row.get(col)).strip()
                )

                plant = str(row.get("plant") or "").strip()

                if plant:
                    plant_key = _botanical_taxonomy.taxon_match_key(plant)
                    index[plant_key] += " " + text
                    _record_source(plant_key, row)
                    _record_evidence_record(plant_key, row, text)

                for compound in self._known_compounds_from_text(text):
                    compound_key = self._norm(compound)
                    index[compound_key] += " " + text
                    _record_source(compound_key, row)
                    _record_evidence_record(compound_key, row, text)

        # Curated regulatory/clinical evidence (seed_data.SLEEP_TEA_EVIDENCE)
        # — this is the manually-verified EMA/WHO/ESCOP + cited-study
        # research Yalda already did for the sleep/anxiety plants. It must
        # count as real evidence, not be treated the same as "nothing
        # found", or every one of these plants gets its confidence capped
        # despite having genuinely reviewed sources.
        for plant, curated in SLEEP_TEA_EVIDENCE.items():
            text = (
                f"{curated.get('study_type', '')}. "
                f"{curated.get('outcome', '')} "
                f"EMA: {curated.get('ema_status', '')}. "
                f"WHO: {curated.get('who_status', '')}. "
                f"ESCOP: {curated.get('escop_status', '')}. "
                f"Safety: {curated.get('safety_desc', '')}."
            )
            plant_key = _botanical_taxonomy.taxon_match_key(plant)
            index[plant_key] += " " + text
            # Curated evidence has no per-record URL, but it does have a
            # named, citable source — record that instead of leaving
            # this key's source list empty.
            source_index[plant_key].append("seed_data.SLEEP_TEA_EVIDENCE")

        return index, source_index, applicability_index, authority_index, evidence_records_index

    def _build_scientific_evidence_index(self):
        """Task 11.1 — evidence_record_id -> ScientificEvidence.

        Deliberately a SEPARATE pass over self.evidence_df, not folded
        into _build_evidence_text_index()'s existing three-index build
        above — that method's signature/return shape is already relied
        on by Task 10.2's own call site and tests; adding a fourth
        element there would be a needless second change to an
        already-stable interface. This method only reads
        self.evidence_df (never self.scientific_evidence_df, which has
        no active write path at all — see the Task 10.2 correction's
        allowlist technical-debt note) and builds data_contracts.
        ScientificEvidence objects via standard_evidence_builder.
        build_scientific_evidence(), the same adapter used wherever
        else this contract needs activating.

        NEVER READ BY SCORING/APPRAISAL. This index exists purely so a
        caller can look up "what do we structurally know about THIS
        exact evidence record" by id — nothing in _score_candidate(),
        _decision_class(), classify_evidence_hierarchy(),
        compute_evidence_confidence(), or classify_negative_evidence()
        reads it, and none of those functions' inputs change because
        of this method's existence. Object field VALUES are also never
        concatenated into any free-text index — only structured,
        typed field access, the same discipline
        _build_evidence_text_index()'s applicability_index already
        established.

        Rows with no Evidence_Record_ID (never persisted, e.g. an
        in-memory-only record from a test) are skipped — this index is
        keyed by a stable id, so an item with no id has no key to
        index it under; it remains fully visible in the free-text
        index and applicability_index exactly as before, just absent
        from THIS lookup.

        Returns {evidence_record_id: ScientificEvidence}. A row whose
        Evidence_Record_ID collides with an earlier row's (should not
        happen — it's the table's own primary key) keeps the LAST row,
        same "last one wins" convention as occurrence_seed.
        build_occurrence_lookup().

        KNOWN PANDAS DTYPE CAVEAT (disclosed, not fixed here — out of
        this correction's scope, which is missing-VALUE handling, not
        numeric-formatting): if an Evidence_Record_ID column contains
        BOTH a real integer id and a missing (NaN) cell, pandas silently
        upcasts the whole column to float64 — a valid id like 7 becomes
        7.0, which this method then stringifies as "7.0", not "7". This
        cannot happen for a real evidence_records table (its `id` column
        is never actually null for a persisted row), so it is a
        test-fixture/in-memory-only concern, not a production one — but
        it is real and worth knowing if a future test mixes a NaN id row
        with an integer id row in one DataFrame.
        """
        index = {}
        if self.evidence_df.empty:
            return index

        for _, row in self.evidence_df.iterrows():
            # Task 11.1 correction — explicit normalize_missing_value() call,
            # not just self._pick()'s incidental NaN handling: a pandas
            # row with a missing "Evidence_Record_ID" cell holds
            # float('nan') there, not None or "" — normalizing before
            # the `if record_id is None` check is what guarantees this
            # index never gets a "nan" string key, and that the SAME
            # id value (once stringified) is used here as the key and
            # inside build_scientific_evidence()'s own
            # source_record_id field below, so the two never disagree.
            record_id = normalize_missing_value(row.get("Evidence_Record_ID"))
            if record_id is None:
                record_id = normalize_missing_value(row.get("evidence_record_id"))
            if record_id is None:
                continue
            index[str(record_id)] = build_scientific_evidence(row.to_dict())

        return index

    def _collect_raw_evidence(
        self,
        evidence_index,
        plant,
        compound,
        problem,
        source_index=None,
        authority_index=None,
        records_index=None,
    ):
        """Builds the evidence text used to determine Evidence_Level and
        safety flags for one candidate row, and (Gap 1) the specific
        source identifiers that back it.

        `evidence_index` has two kinds of entries per record: one bucket
        keyed by PLANT (every evidence record tied to that plant, however
        many different compounds those records are actually about), and
        one bucket keyed by COMPOUND (every evidence record whose text
        mentions that specific compound, across whichever plants). The
        compound bucket is the one that's actually scoped to what this
        row's claim is about; the plant bucket is not — it was the
        source of the whole-plant-pooling cross-contamination problem
        (a plant's evidence about an unrelated compound getting credited
        to a completely different compound match just because it's the
        "same plant").
        
        So: compound- and problem-specific text is used as the PRIMARY
        signal. The whole-plant bucket is only added as a fallback when
        there is no compound-specific evidence at all for this compound
        — better than nothing when that's genuinely all there is, but no
        longer blended in unconditionally on every row regardless of
        whether it's actually relevant to the compound being evaluated.

        Returns (text, source_ids, authority_factor, contributing_records)
        — source_ids empty list and authority_factor 1.0 (neutral,
        matches interpret_evidence()'s own "no effect" default) when
        source_index/authority_index aren't provided, so this callable
        still works exactly as before for any caller that only wants
        the text (Gap 1 backward compatibility preserved).
        contributing_records (Phase 4 correction round): list of
        {"evidence_record_id", "text"} dicts — one per individual
        EvidenceRecord that actually contributed to the returned `text`,
        from records_index (see _build_evidence_text_index()'s
        evidence_records_index). Empty list when records_index isn't
        provided. This is what makes Safety_Gate_Evidence_IDs /
        Regulatory_Gate_Evidence_IDs finding-specific: the caller can
        check EACH record's own `text` for the matched hit term/barrier
        phrase, rather than crediting every id in `source_ids` (which is
        candidate-level, not finding-level).

        authority_factor (Phase 3, problem 1): the REAL per-source
        Source Authority factor for whichever row(s) actually
        contributed the returned text, not a hardcoded 1.0. Since
        `text` itself can be a pooled blob from several rows at the
        same key, the single most defensible, non-invented number to
        represent it is the STRONGEST verified authority among the
        rows that actually contributed — i.e. if a real EMA/WHO/ESCOP/
        Cochrane/RCT source is genuinely among the contributors, that
        drives the factor; if only Unknown-Source rows contributed,
        the conservative Unknown factor is used, exactly as if a single
        row had been classified directly. Never averaged/blended into a
        value no single real row actually has, and never applied to
        rows that did not contribute to this specific key's text.
        """
        source_index = source_index or {}
        authority_index = authority_index or {}
        records_index = records_index or {}
        compound_clean = compound.split("[")[0].strip()

        compound_key = self._norm(compound_clean)
        problem_key = self._norm(problem)

        def _strongest_authority_factor(keys):
            entries = [
                entry
                for key in keys
                for entry in authority_index.get(key, [])
            ]
            if not entries:
                return 1.0
            return max(entry["authority_factor"] for entry in entries)

        compound_text = evidence_index.get(compound_key, "")

        # Direct botanical + indication evidence must not disappear merely
        # because the candidate also has compound-level evidence.  Select only
        # plant records whose own structured target indication matches this
        # question, avoiding the old whole-plant pooling contamination while
        # preserving directly relevant clinical/review evidence.
        plant_key = _botanical_taxonomy.taxon_match_key(plant)
        direct_plant_records = [
            rec for rec in records_index.get(plant_key, [])
            if problem_key
            and self._norm(rec.get("target_indication") or "") == problem_key
        ]
        direct_plant_text = " ".join(
            str(rec.get("text") or "").strip()
            for rec in direct_plant_records
            if str(rec.get("text") or "").strip()
        )

        primary = " ".join(part for part in (compound_text, direct_plant_text) if part).strip()

        if primary:
            compound_records = list(records_index.get(compound_key, []))
            contributing_records = []
            seen = set()
            for rec in compound_records + direct_plant_records:
                rid = rec.get("evidence_record_id")
                sig = rid or (rec.get("source_url"), rec.get("text"))
                if sig in seen:
                    continue
                seen.add(sig)
                contributing_records.append(rec)

            sources = list(dict.fromkeys(
                source_index.get(compound_key, [])
                + [str(rec.get("source_url")) for rec in direct_plant_records if rec.get("source_url")]
            ))
            factors = [float(rec.get("authority_factor") or 0.0) for rec in contributing_records]
            authority_factor = max(factors) if factors else _strongest_authority_factor((compound_key,))
            return primary[:6000], sources, authority_factor, contributing_records

        # No compound-specific or direct plant+indication evidence found — fall back to
        # whatever's known about the plant in general, clearly weaker
        # but still better than treating it as zero evidence outright.
        plant_text = evidence_index.get(plant_key, "")
        return (
            plant_text.strip()[:6000],
            list(dict.fromkeys(source_index.get(plant_key, []))),
            _strongest_authority_factor((plant_key,)),
            records_index.get(plant_key, []),
        )

    def _collect_applicability_items(self, applicability_index, plant, compound):
        """Task 10.2 — structured counterpart to _collect_raw_evidence().

        Same compound-key-first, plant-key-fallback lookup as
        _collect_raw_evidence() (see that method's docstring for why:
        compound-specific evidence is the primary, correctly-scoped
        signal; the whole-plant bucket is a fallback only used when no
        compound-specific evidence exists at all), but returns the
        structured applicability dicts built by
        _build_evidence_text_index()'s _record_applicability(), not
        free text. Deduplicated by evidence_record_id so an item
        present under both the compound and problem key is not double
        counted.

        Returns a list[dict], each with exactly the keys
        _record_applicability() writes: evidence_record_id,
        classification, rationale, evaluated_dimensions,
        missing_dimensions, detected_mismatches. Empty list when
        nothing is found anywhere — never fabricated.
        """
        compound_clean = compound.split("[")[0].strip()
        compound_key = self._norm(compound_clean)
        plant_key = _botanical_taxonomy.taxon_match_key(plant)

        items = (
            applicability_index.get(compound_key, []) +
            applicability_index.get(plant_key, [])
        )

        deduped = []
        seen_ids = set()
        seen_signatures = set()
        for item in items:
            record_id = item.get("evidence_record_id")
            if record_id is not None:
                if record_id in seen_ids:
                    continue
                seen_ids.add(record_id)
            else:
                # No id available (e.g. a row saved before Task 10.2's
                # id capture, or an in-memory-only record never
                # persisted) — fall back to de-duplicating on the
                # content itself so the same unattributable item isn't
                # counted twice.
                signature = (item.get("classification"), item.get("rationale"))
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
            deduped.append(item)

        return deduped

    @staticmethod
    def _summarize_applicability(items):
        """Task 10.2 — candidate-level Applicability_Summary, built by
        counting/aggregating the evidence-ITEM-level classifications in
        `items` (as returned by _collect_applicability_items(), or by
        _merge_applicability_summaries()'s own deduplicated item list —
        both shapes carry the same evidence_record_id/classification/
        detected_mismatches/missing_dimensions keys this method reads).

        Deliberately does NOT collapse the items into one derived
        applicability verdict for the candidate (explicitly out of
        scope for this task) — it counts and surfaces what is there,
        keyed by the same EvidenceApplicability vocabulary, so a
        reviewer can see the underlying distribution rather than one
        opaque label. Every evidence_record_id in `items` is preserved
        in evidence_record_ids, so the individual evidence items behind
        this summary remain independently traceable back to specific
        evidence_records rows — not merely to a plant or compound name.

        evidence_items (Task 10.2 correction): the same per-item
        breakdown this method just counted, kept on the returned dict
        so _merge_applicability_summaries() can later deduplicate and
        exactly recompute a merged candidate's counts by
        evidence_record_id, instead of summing pre-aggregated counts
        across sub-rows (which could double-count a persisted record
        that contributed to more than one matched compound).

        Never reads or writes R&D_Opportunity_Score, Decision_Class,
        Decision_Class_AH, gate_results, or any scoring input — this is
        a pure, read-only aggregation over already-computed evidence-
        level fields.
        """
        counts = {
            EvidenceApplicability.DIRECTLY_APPLICABLE.value: 0,
            EvidenceApplicability.PARTIALLY_APPLICABLE.value: 0,
            EvidenceApplicability.INDIRECTLY_RELEVANT.value: 0,
            EvidenceApplicability.NOT_ASSESSABLE.value: 0,
            EvidenceApplicability.NOT_APPLICABLE.value: 0,
        }
        critical_mismatches = []
        missing_dimensions = set()
        evidence_record_ids = []
        evidence_items = []

        for item in items:
            classification = item.get("classification")
            detected_mismatches = list(item.get("detected_mismatches", []))
            item_missing_dimensions = list(item.get("missing_dimensions", []))

            if classification in counts:
                counts[classification] += 1

            for mismatch in detected_mismatches:
                label = f"{classification}: {mismatch}" if classification else mismatch
                if label not in critical_mismatches:
                    critical_mismatches.append(label)

            missing_dimensions.update(item_missing_dimensions)

            record_id = item.get("evidence_record_id")
            if record_id is not None and record_id not in evidence_record_ids:
                evidence_record_ids.append(record_id)

            evidence_items.append({
                "evidence_record_id": record_id,
                "classification": classification,
                "detected_mismatches": detected_mismatches,
                "missing_dimensions": item_missing_dimensions,
            })

        total_evidence_items = len(items)
        not_assessable_items = counts[EvidenceApplicability.NOT_ASSESSABLE.value]
        assessable_items = total_evidence_items - not_assessable_items

        strongest_category = None
        for candidate in APPLICABILITY_STRENGTH_ORDER:
            if counts.get(candidate.value, 0) > 0:
                strongest_category = candidate.value
                break

        if total_evidence_items == 0:
            summary_rationale = (
                "No evidence item with an Applicability_Classification was found "
                "for this candidate."
            )
        else:
            summary_rationale = (
                f"{total_evidence_items} evidence item(s) assessed for preparation "
                f"applicability: {counts[EvidenceApplicability.DIRECTLY_APPLICABLE.value]} directly "
                f"applicable, {counts[EvidenceApplicability.PARTIALLY_APPLICABLE.value]} partially "
                f"applicable, {counts[EvidenceApplicability.INDIRECTLY_RELEVANT.value]} indirectly "
                f"relevant, {not_assessable_items} not assessable, "
                f"{counts[EvidenceApplicability.NOT_APPLICABLE.value]} not applicable."
            )
            if critical_mismatches:
                summary_rationale += f" Critical mismatch(es): {'; '.join(critical_mismatches)}."

        return {
            "counts": counts,
            "total_evidence_items": total_evidence_items,
            "assessable_items": assessable_items,
            "not_assessable_items": not_assessable_items,
            "strongest_category": strongest_category,
            "critical_mismatches": critical_mismatches,
            "missing_dimensions": sorted(missing_dimensions),
            "evidence_record_ids": evidence_record_ids,
            "evidence_items": evidence_items,
            "summary_rationale": summary_rationale,
        }

    @staticmethod
    def _merge_applicability_summaries(summaries):
        """Task 10.2 correction — combines multiple sub-rows'
        Applicability_Summary dicts (one per matched compound) into one
        for a merged candidate row, counting each PERSISTED evidence
        record EXACTLY ONCE by its stable evidence_record_id, even when
        it contributed to more than one matched compound's sub-row.

        HOW THIS IS EXACT, NOT AN APPROXIMATION
        Rather than summing each sub-row summary's pre-aggregated
        `counts` (the pre-correction behavior, which could double-count
        a record present under two compounds), this deduplicates each
        sub-row's own `evidence_items` list first, then calls
        _summarize_applicability() ONCE on that deduplicated set — every
        count, strongest_category, critical_mismatches, and
        missing_dimensions value below is therefore derived from the
        exact same deduplicated item set, reusing the single counting
        implementation rather than a second, parallel one.

        FALLBACK DEDUP FOR ITEMS WITH NO evidence_record_id
        An in-memory-only record (never persisted, so no id exists at
        all) is deduplicated by a documented signature — (classification,
        sorted detected_mismatches, sorted missing_dimensions) — instead.
        This is a real, disclosed limitation, not a formality: two
        SCIENTIFICALLY DISTINCT evidence items that happen to produce an
        identical classification and identical dimension text would be
        indistinguishable to this fallback and would be merged into one.
        This can only ever affect items with no evidence_record_id —
        every item that has a real, persisted id is deduplicated by that
        id alone, never by this signature.
        """
        if not summaries:
            return BotanicalRDCandidateEngine._summarize_applicability([])

        deduped_items = []
        seen_ids = set()
        seen_signatures = set()

        for summary in summaries:
            for item in summary.get("evidence_items") or []:
                record_id = item.get("evidence_record_id")
                if record_id is not None:
                    if record_id in seen_ids:
                        continue
                    seen_ids.add(record_id)
                else:
                    signature = (
                        item.get("classification"),
                        tuple(sorted(item.get("detected_mismatches") or [])),
                        tuple(sorted(item.get("missing_dimensions") or [])),
                    )
                    if signature in seen_signatures:
                        continue
                    seen_signatures.add(signature)
                deduped_items.append(item)

        return BotanicalRDCandidateEngine._summarize_applicability(deduped_items)

    def _match_compounds(
        self,
        reference_compound,
        alternative_compounds,
        alt_norm=None,
    ):
        """Returns (matched_compound_label, match_quality, target_specificity,
        target_provenance).

        match_quality is one of:
          "exact"           - the alternative plant contains the exact
                               same reference compound.
          "target_verified" - a different compound, in the same broad
                               chemical class, that ALSO shares a known
                               biological target with the reference
                               compound (per seed_data.COMPOUND_TARGETS).
                               How MUCH this is worth is not a yes/no —
                               see target_specificity below.
          "class_only"       - a different compound sharing only the
                               broad chemical class label (e.g. both are
                               "flavonoids"), with no shared target at
                               all — a weak, hypothesis-level link.
          "none"             - no match at all.

        target_specificity is the number of DISTINCT compounds (across
        the whole COMPOUND_TARGETS / compound_profiles knowledge base)
        that carry the best (rarest) shared target — or None when
        match_quality isn't "target_verified". This is deliberately a
        continuous count, not a binary "generic vs specific" classifier:
        an early version used a single statistical cutoff (90th
        percentile of target frequency) to split target_verified into a
        "strong" and "weak" tier, but on a database this size that
        cutoff has a hard edge — a pathway shared by 5 compounds got a
        full score, one shared by 6 got almost none, even though neither
        is meaningfully more specific than the other. The count is
        instead fed into _score_candidate, which discounts the
        chemical-link bonus smoothly as the shared target gets less
        specific (see there), for any pathway, any chemical class, any
        indication — no hardcoded cutoff to sit right next to.

        target_provenance (Gap 5, "target relationship provenance"):
        which source(s) — the hardcoded seed_data.COMPOUND_TARGETS
        knowledge base, the real/maintained Supabase compound_profiles
        table, or both — actually asserted the shared target that
        earned this match its "target_verified" quality. Empty string
        when match_quality isn't "target_verified" (there's no specific
        target claim to attribute for an exact or class-only match).

        `alt_norm` (norm(compound) -> original compound) can be passed in
        precomputed once per alt-candidate, instead of being rebuilt from
        `alternative_compounds` on every call — at Dr. Duke's data scale
        this function is called millions of times per run(), and rebuilding
        this dict every time was a major hot spot.
        """
        ref = self._norm(reference_compound)

        if alt_norm is None:
            alt_norm = {
                self._norm(compound): compound
                for compound in alternative_compounds
            }

        if ref in alt_norm:
            return alt_norm[ref], "exact", None, ""

        ref_class = self.compound_to_class.get(ref, "")

        if not ref_class:
            return "", "none", None, ""

        ref_targets = self.compound_to_targets.get(ref, set())

        class_matches = [
            alt_value
            for alt_key, alt_value in alt_norm.items()
            if self.compound_to_class.get(alt_key, "") == ref_class
        ]

        if not class_matches:
            return "", "none", None, ""

        if ref_targets:
            # Across every class-mate, find whichever shared target is
            # the RAREST (lowest compound_count) — that is the strongest
            # possible confirmation available for this pair, and its
            # count is what determines how much it's actually worth.
            best = None  # (alt_value, target, count)

            for alt_value in class_matches:
                alt_targets = self.compound_to_targets.get(
                    self._norm(alt_value), set()
                )
                shared = alt_targets & ref_targets
                for target in shared:
                    count, _ = self._target_specificity(target)
                    if best is None or count < best[2]:
                        best = (alt_value, target, count)

            if best is not None:
                alt_value, target, count = best
                sources = self.compound_to_target_sources.get(
                    self._norm(alt_value), {}
                ).get(target, frozenset())
                provenance = "; ".join(sorted(sources)) if sources else "Source not tracked"
                return (
                    f"{alt_value} [similar: {ref_class}; shared target: "
                    f"{target} (shared by {count} known compounds)]",
                    "target_verified",
                    count,
                    provenance,
                )

        return (
            f"{class_matches[0]} [similar: {ref_class}; class-only, "
            f"target not confirmed]",
            "class_only",
            None,
            "",
        )


    def _build_compound_indexes(self):
        """Returns (compound_to_class, compound_to_targets, compound_to_target_sources).

        Layered, cheapest/narrowest first so richer sources can override:
          1. seed_data.PLANT_COMPOUNDS's own per-compound chemical class
             (already collected there for every plant, e.g. "Isoquinoline
             alkaloid" for Berberine — previously computed but never fed
             into cross-plant matching, which silently starved newer
             indications like metabolic/energy of any alternative-plant
             results even when a real class match existed).
          2. SIMILAR_COMPOUND_GROUPS — a small hand-curated set of extra
             families for compounds not listed with a class anywhere else.
          3. The real Supabase `compound_profiles` table (310 records) —
             the richest, maintained source — wins over both when present.

        compound_to_target_sources (Gap 5, "target relationship
        provenance"): a target claim from the hardcoded seed dict
        (COMPOUND_TARGETS) and one confirmed by a real, maintained
        Supabase record (compound_profiles.major_target) are very
        different claims — one is an editorial judgment call baked into
        this codebase, the other is a specific database record someone
        can go look up. Both used to get unioned into the same
        compound_to_targets set with no way to tell which was which.
        This parallel index keeps that distinction: for every
        (compound, target) pair, which source(s) actually asserted it.
        """
        class_index = {}

        for compounds in PLANT_COMPOUNDS.values():
            for compound_name, chem_class, _extraction in compounds:
                if chem_class:
                    class_index[self._norm(compound_name)] = chem_class

        for compound_class, compounds in SIMILAR_COMPOUND_GROUPS.items():
            for compound in compounds:
                class_index[self._norm(compound)] = compound_class

        target_index = defaultdict(set)
        target_source_index = defaultdict(lambda: defaultdict(set))

        SEED_SOURCE_LABEL = "seed_data.COMPOUND_TARGETS (hardcoded knowledge base, not a specific study/database record)"
        SUPABASE_SOURCE_LABEL = "Supabase compound_profiles.major_target (maintained database record)"

        for compound, targets in COMPOUND_TARGETS.items():
            compound_key = self._norm(compound)
            for target in targets:
                target_key = self._norm(target)
                target_index[compound_key].add(target_key)
                target_source_index[compound_key][target_key].add(SEED_SOURCE_LABEL)

        if not self.compound_profiles_df.empty:
            for _, row in self.compound_profiles_df.iterrows():
                compound = self._norm(row.get("compound_name"))

                if not compound:
                    continue

                compound_class = str(row.get("compound_class") or "").strip()
                if compound_class:
                    # Supabase is the richer, maintained source — it wins
                    # over the small local class map when both exist.
                    class_index[compound] = compound_class

                for target in self._split_terms(row.get("major_target")):
                    target_key = self._norm(target)
                    target_index[compound].add(target_key)
                    target_source_index[compound][target_key].add(SUPABASE_SOURCE_LABEL)

        # Convert the nested defaultdict to plain dicts of frozensets so
        # this behaves like a normal, picklable, easily-tested data
        # structure once construction is done.
        plain_target_source_index = {
            compound: {target: frozenset(sources) for target, sources in targets.items()}
            for compound, targets in target_source_index.items()
        }

        return class_index, dict(target_index), plain_target_source_index

    def _build_target_frequency_index(self, compound_to_targets):
        """Same idea as _build_compound_frequency_index, but for TARGETS
        instead of compound names.

        Why this is needed: fixing compound-name commonality alone (e.g.
        for an abundant flavonoid matched by exact name) does not fix a
        second, independent source of over-matching — "target_verified"
        matches confirmed only through a broad mechanism/pathway label
        (e.g. "NF-kB", "Anti-inflammatory pathways", "Oxidative stress
        pathways") that dozens of unrelated compounds in the same broad
        chemical class ALSO happen to be tagged with. Two flavonoids
        sharing a pathway that most flavonoids share is not a specific,
        differentiating confirmation — it is nearly as generic as bare
        class membership. This applies to any chemical class or
        indication, not just flavonoids, so the threshold is again
        derived from the actual data rather than a hardcoded pathway
        list.
        """
        target_to_compounds = defaultdict(set)
        for compound, targets in compound_to_targets.items():
            for target in targets:
                target_to_compounds[target].add(compound)

        counts = {t: len(compounds) for t, compounds in target_to_compounds.items()}

        if not counts:
            return counts, None

        values = sorted(counts.values())
        n = len(values)
        if n >= 5:
            idx = int(round(0.90 * (n - 1)))
            threshold = max(float(values[idx]), 4.0)
        else:
            threshold = max(float(values[-1]) + 1, 4.0)

        return counts, threshold

    def _target_specificity(self, target_norm):
        """Returns (compound_count, is_generic) for a single normalized
        target/pathway label."""
        count = self.target_compound_count.get(target_norm, 0)
        is_generic = (
            self.target_genericity_threshold is not None
            and count >= self.target_genericity_threshold
        )
        return count, is_generic

    @staticmethod
    def _structured_occurrence(alt_plant, matched_compound):
        """Task 7 — O(1) lookup into the module-level _OCCURRENCE_LOOKUP
        (see occurrence_seed.py). Returns None whenever there is no
        populated structured record for this exact (plant, compound)
        pair — which is the common case for anything outside
        seed_data.py's curated set, and is exactly when callers must
        fall back to their existing free-text/row-based logic
        unchanged."""
        if not alt_plant or not matched_compound:
            return None
        return _OCCURRENCE_LOOKUP.get((
            BotanicalRDCandidateEngine._norm(alt_plant),
            BotanicalRDCandidateEngine._norm(matched_compound),
        ))

    def _best_extraction(self, alt, evidence, alt_plant=None, matched_compound=None):
        # Task 7 — prefer the structured occurrence's own
        # extraction_solvent (specific to THIS matched compound) when
        # one is populated; this is additive only — when no structured
        # occurrence exists for this (plant, compound) pair (the
        # common case today), the return value is byte-identical to
        # the pre-Task-7 behavior below.
        occurrence = self._structured_occurrence(alt_plant, matched_compound)
        if occurrence is not None and occurrence.extraction_solvent:
            parts = [occurrence.extraction_solvent]
            if occurrence.plant_part:
                parts.append(f"(from {occurrence.plant_part})")
            if occurrence.dry_fresh_basis:
                parts.append(f"[{occurrence.dry_fresh_basis}]")
            return " ".join(parts)

        base = self._pick(alt, ["Extraction_Method"])
        found = self._extract_extraction(evidence)

        if base and found:
            return f"{base}; evidence mentions: {found}"

        return base or found

    def _score_candidate(
        self,
        same_plant,
        matched_compound,
        reference_compound,
        match_quality,
        concentration,
        extraction,
        dosage_form,
        co_compounds,
        safety_flags,
        interaction_flags,
        market_status,
        novelty_status,
        target,
        evidence,
        evidence_level="No direct evidence",
        compound_plant_count=0,
        target_specificity=None,
        evidence_direction_contribution=None,
    ):
        """Returns (score, components).

        evidence_direction_contribution: optional override for the
        "Evidence quality" component's Clinical-evidence tier only (see
        evidence_interpretation.py, Phase 1). When evidence_level is
        "Clinical / human evidence" and this is not None, it REPLACES
        the flat evidence_clinical weight so that a negative/null/
        unclear/future-mention clinical study can no longer earn the
        same positive contribution as a genuinely positive, completed
        RCT. Left as None (the default), behavior is IDENTICAL to
        before this parameter existed — every other evidence tier
        (Regulatory / Preclinical / General literature / No direct
        evidence) is completely untouched by this parameter.

        score: R&D_Opportunity_Score (0-100). See evidence_confidence.py
        for the SEPARATE Evidence_Confidence score (audit 4.16) — this
        function is intentionally untouched by that split; every weight
        below is exactly what it was before Phase 6.

        components: dict of {section name: points contributed by that
        section}, summing to `score` before the final 0-100 clamp.
        Added to answer the architecture-audit question "which evidence
        contributed MOST to this score?" — previously only the summed
        total was ever returned, so a row's score couldn't be decomposed
        without recomputing this whole function a second time (which
        would have meant duplicating this logic in a second place —
        exactly what was avoided by extending this function's return
        value instead of writing a parallel scoring function).

        COMPLETE WEIGHTS TABLE (audit 4.16: "تمام weightها مستند شوند").
        All numbers below are verified against the code in this function
        as of Phase 6 — this docstring documents, it does not define;
        if the code below changes, this table must be updated with it.

        1) Chemical/mechanistic link (base, before the two modifiers
           below):
             exact match                    22
             target_verified match          15
             class-only/similar match        5
           target_verified modifier: multiplied by min(1.0, 2.0 /
             target_specificity) — full bonus only when the shared
             target is carried by just 2 compounds DB-wide, decaying
             smoothly as more compounds share it.
           commonality modifier: multiplied by (1 - penalty_ratio),
             where penalty_ratio = min(0.8, overage / 3.0) and
             overage = max(0, compound_plant_count/threshold - 1.0) —
             no penalty at or below the DB's own commonality threshold,
             up to 80% removed at 4x that threshold or more.

        2) Evidence quality (evidence_points, by Evidence_Level):
             Clinical / human evidence         24
             Regulatory / monograph evidence   20
             Preclinical / mechanistic ev.     12
             General literature signal          7
             No direct evidence                 0

        3) Product-development fit:
             concentration reported            +10  (else +2)
             extraction fit                     up to +18 (see
                                                  _extraction_fit_score's
                                                  own weights below)
             co-compounds (2 pts each)          up to +8
             target/mechanism identified        +8   (else +1)

        4) Novelty (only awarded when evidence_level != "No direct
           evidence" — novelty on an unevidenced candidate isn't a real
           finding yet):
             "Common"/"non-specific" novelty     +0
             "Alternative"/"Cross-region"        +10
             anything else                       +2

        5) Market signal (small modifier; matches the
           MarketVerificationStatus vocabulary from _market_status(),
           Phase 5/audit 4.6-4.7):
             "Verified marketed product"         +1
             "Regulatory monograph exists" /
               "Traditional-use status"          +2
             "Commercial evidence reported..."   +2
             "No verified product found"         +6   (currently a dead
                                                  code path — no real
                                                  retail/patent search
                                                  is wired in yet, so
                                                  _market_status never
                                                  actually returns this)
             "Search not performed" / "Source
               unavailable" / "Unknown"          +3   (neutral default)

        6) Safety/interaction/self-row penalties:
             any safety flag                    -14
             any interaction flag               -10
             same_plant (reference-vs-itself)   -15

        Final score: round(max(0, min(100, sum_of_above)), 1).

        _extraction_fit_score's own internal weights (feeds into #3
        above, capped there at 18):
             no extraction method reported        3
             any extraction method reported       8  (base)
             aqueous/water/infusion/decoction    +10 (+8 more if dosage
                                                   form is infusion/tea/
                                                   herbal)
             ethanol/hydroalcoholic/extract       +8 (+6 more if dosage
                                                   form is capsule/
                                                   tablet/extract/cream/
                                                   gel/ointment)
             essential oil/distillation           +6 (+5 more if dosage
                                                   form is cream/gel/
                                                   essential oil)
        """
        score = 0
        components = {}

        # 1) Chemical/mechanistic link. Exact shared compound is strong;
        # target-verified similarity is moderate; class-only similarity
        # is weak. The target-verified bonus below is further scaled by
        # HOW specific the confirming shared target actually is.
        if match_quality == "exact":
            chem_bonus = self.scoring_config.chem_link_exact
        elif match_quality == "target_verified":
            chem_bonus = self.scoring_config.chem_link_target_verified
        else:
            chem_bonus = self.scoring_config.chem_link_class_only

        # A "target_verified" match is only as informative as the target
        # itself is specific. Two compounds sharing a pathway that only
        # 2 compounds in the whole knowledge base carry is a real,
        # differentiating confirmation. Two compounds sharing a pathway
        # that 20 compounds carry (e.g. "Anti-inflammatory pathways") is
        # barely more informative than bare class membership. This is
        # deliberately a smooth 1/count decay rather than a single
        # "generic vs specific" statistical cutoff — a fixed cutoff has
        # a hard edge (a target shared by 5 compounds scored completely
        # differently from one shared by 6), which doesn't reflect
        # reality and doesn't generalize well to a knowledge base this
        # size. This applies the same way to any pathway, any chemical
        # class, any indication.
        if match_quality == "target_verified" and target_specificity:
            # Full bonus only when the shared target is carried by 2
            # compounds (the minimum for it to be "shared" at all);
            # decays smoothly as more compounds carry it.
            chem_bonus *= min(1.0, 2.0 / target_specificity)

        # A compound found in only a handful of plants IS the strong
        # signal this score is meant to reward — two species sharing a
        # rare, specific compound is genuinely informative. A compound
        # found across hundreds/thousands of unrelated plants tells you
        # almost nothing about THIS pair, no matter which two plants it
        # is (any indication, any species) — so its contribution is
        # scaled down smoothly as commonality grows, using the same
        # database-derived threshold everywhere in the engine, rather
        # than being capped by a fixed number of "known common
        # compounds".
        threshold = self.compound_commonality_threshold
        if threshold and compound_plant_count > 0:
            # 1x threshold -> no penalty yet; 4x threshold or more -> up
            # to ~80% of the chemical-link bonus removed.
            overage = max(0.0, (compound_plant_count / threshold) - 1.0)
            penalty_ratio = min(0.8, overage / 3.0)
            chem_bonus = chem_bonus * (1 - penalty_ratio)

        score += chem_bonus
        components["Chemical/mechanistic link"] = round(chem_bonus, 1)

        # 2) Evidence quality. The previous engine rewarded any text too much.
        # Here weak/no evidence cannot produce a high-confidence candidate.
        evidence_points = {
            "Clinical / human evidence": self.scoring_config.evidence_clinical,
            "Regulatory / monograph evidence": self.scoring_config.evidence_regulatory,
            "Preclinical / mechanistic evidence": self.scoring_config.evidence_preclinical,
            "General literature signal": self.scoring_config.evidence_general_literature,
            "No direct evidence": self.scoring_config.evidence_none,
        }
        if evidence_level == "Clinical / human evidence" and evidence_direction_contribution is not None:
            # Phase 1: the study's reported OUTCOME DIRECTION (positive/
            # negative/null/mixed/unclear — see evidence_interpretation.py)
            # determines this tier's contribution instead of the flat
            # weight, so a failed/null/future/protocol "clinical trial"
            # mention can no longer score identically to a genuinely
            # positive, completed RCT.
            evidence_component = evidence_direction_contribution
        else:
            evidence_component = evidence_points.get(evidence_level, 0)
        score += evidence_component
        components["Evidence quality"] = evidence_component

        # 3) Product-development fit. These matter, but they must not
        # overpower poor evidence.
        product_fit_component = 0
        product_fit_component += (
            self.scoring_config.product_fit_concentration_reported if concentration
            else self.scoring_config.product_fit_concentration_missing
        )
        product_fit_component += min(
            self.scoring_config.product_fit_extraction_cap,
            self._extraction_fit_score(extraction, dosage_form),
        )
        product_fit_component += min(
            self.scoring_config.product_fit_co_compound_cap,
            len(self._split_compound_terms(co_compounds)) * self.scoring_config.product_fit_co_compound_per_item,
        )
        product_fit_component += (
            self.scoring_config.product_fit_target_identified if target
            else self.scoring_config.product_fit_target_missing
        )
        score += product_fit_component
        components["Product-development fit"] = product_fit_component

        # 4) Novelty is valuable only after some scientific basis exists.
        # A "common compound" novelty label (see _novelty_status) must
        # NOT collect this bonus — a compound found everywhere is the
        # opposite of a novel, differentiating finding.
        novelty_component = 0
        if evidence_level != "No direct evidence":
            if "Common" in novelty_status or "non-specific" in novelty_status:
                novelty_component = self.scoring_config.novelty_common
            elif "Alternative" in novelty_status or "Cross-region" in novelty_status:
                novelty_component = self.scoring_config.novelty_alternative
            else:
                novelty_component = self.scoring_config.novelty_other
        score += novelty_component
        components["Novelty"] = novelty_component

        # 5) Market signal is a small modifier, not the core scientific score.
        # Matches the MarketVerificationStatus vocabulary from
        # _market_status() (audit 4.6/4.7, extended Gap 2). "Search not
        # performed" is deliberately neutral, not a white-space bonus —
        # a real product/patent search hasn't actually been run, so
        # this must not be scored as if emptiness had been confirmed.
        # "No verified product found" (only returned once a real
        # retail/patent search is wired in — currently dead code path,
        # kept for forward compatibility) is the only status that earns
        # the white-space-style bonus, because it's the only one that
        # reflects an actual completed search.
        market_lower = market_status.lower()
        if "verified marketed product" in market_lower:
            market_component = self.scoring_config.market_verified_marketed_product
        elif "regulatory monograph" in market_lower or "traditional-use" in market_lower:
            market_component = self.scoring_config.market_regulatory_monograph_or_traditional_use
        elif "commercial evidence reported" in market_lower:
            market_component = self.scoring_config.market_commercial_evidence_reported
        elif "no verified product found" in market_lower:
            market_component = self.scoring_config.market_no_verified_product_found
        elif "conflicting market evidence" in market_lower:
            # A real, detected disagreement between two signals (e.g.
            # regulatory recognition vs. a discontinuation mention) is
            # worth flagging with a small penalty, not treated as
            # neutral — it means the market picture for this candidate
            # genuinely needs a human to resolve before acting on it.
            market_component = self.scoring_config.market_conflicting_evidence
        elif "search incomplete" in market_lower:
            # Slightly more informative than "not performed" (a live
            # search did run this session), but still no market signal
            # was actually found — same neutral treatment as "not
            # performed", not a bonus.
            market_component = self.scoring_config.market_search_incomplete
        else:  # "Search not performed", "Source unavailable", "Unknown"
            market_component = self.scoring_config.market_neutral_default
        score += market_component
        components["Market signal"] = market_component

        # 6) Penalize safety and interaction flags strongly. A candidate with
        # clear safety issues should not be presented as attractive without
        # qualification.
        safety_component = 0
        if safety_flags:
            safety_component += self.scoring_config.safety_flag_penalty

        if interaction_flags:
            safety_component += self.scoring_config.interaction_flag_penalty

        if same_plant:
            safety_component += self.scoring_config.same_plant_penalty

        score += safety_component
        components["Safety/interaction/self-row penalty"] = safety_component

        final_score = round(max(0, min(100, score)), 1)
        return final_score, components

    def _extraction_fit_score(self, extraction, dosage_form):
        extraction_norm = self._norm(extraction)
        dosage_norm = self._norm(dosage_form)

        if not extraction_norm:
            return 3

        score = 8

        if any(
            term in extraction_norm
            for term in ["aqueous", "water", "infusion", "decoction"]
        ):
            score += 10

            if any(
                term in dosage_norm
                for term in ["infusion", "tea", "herbal"]
            ):
                score += 8

        if any(
            term in extraction_norm
            for term in ["ethanol", "hydroalcoholic", "extract"]
        ):
            score += 8

            if any(
                term in dosage_norm
                for term in [
                    "capsule",
                    "tablet",
                    "extract",
                    "cream",
                    "gel",
                    "ointment",
                ]
            ):
                score += 6

        if any(
            term in extraction_norm
            for term in ["essential oil", "distillation"]
        ):
            score += 6

            if any(
                term in dosage_norm
                for term in ["cream", "gel", "essential oil"]
            ):
                score += 5

        return min(score, 26)

    @staticmethod
    def _ema_listed(ema_status) -> bool:
        """Phase A / Sprint 5 bug fix — the ONE place that decides
        whether an EMA_Status value means 'genuinely listed in the HMPC
        inventory'. Recognizes ema_regulatory_connector.py's real
        output prefix ("Listed in HMPC inventory as ...") and, only for
        backward compatibility with any already-stored historical data,
        the legacy stub's literal "Yes" — new data should never produce
        "Yes" again now that the fabricated stub is excluded from
        production (see Phase A Issue 2, regulatory_connector.py)."""
        if not ema_status:
            return False
        return ema_status == "Yes" or ema_status.startswith("Listed in HMPC inventory")

    def _market_evidence_status(self, evidence):
        """Phase 8 market-only status. Regulatory recognition, safety,
        efficacy and scientific evidence are intentionally ignored here.

        Until the opt-in retail connector is genuinely implemented, this
        method can only distinguish unverified commercial prose from honest
        missing/search states; it never claims a verified product or low
        saturation from missing data.
        """
        text = self._norm(evidence)
        commercial_phrase_patterns = [
            r"\bmarketed as\b", r"\bmarketed product\b",
            r"\bavailable as a supplement\b", r"\bavailable as an? product\b",
            r"\bcommercially available\b", r"\bsold as\b", r"\bbranded as\b",
        ]
        discontinued_patterns = [
            r"\bdiscontinued\b", r"\bwithdrawn from the market\b",
            r"\bno longer (?:available|marketed|sold)\b",
            r"\bnot currently (?:available|marketed|sold)\b", r"\bproduct recall\b",
        ]
        commercial_signal = any(re.search(p, text) for p in commercial_phrase_patterns)
        discontinued_signal = any(re.search(p, text) for p in discontinued_patterns)
        if commercial_signal and discontinued_signal:
            return "Conflicting market evidence"
        if commercial_signal:
            return "Commercial evidence reported, not independently verified"
        if self.use_live_search:
            return "Search incomplete"
        return "Search not performed"

    def _market_status(self, alt, evidence, market):
        """Market status, using the same controlled vocabulary as
        data_contracts.MarketVerificationStatus (audit 4.6/4.7), plus
        two additional honest states (Gap 2, "Market Intelligence
        completeness"): "Conflicting market evidence" and "Search
        incomplete" — both built from signals this function already
        computes, not from any new data source.

        HONESTY CONSTRAINT: this engine has no real retail-product or
        patent-database connection wired into this per-row path — see
        _search_retail_products() below, which literally returns "Not
        implemented", and the patent connector, which only activates
        with EPO_OPS_KEY/EPO_OPS_SECRET env vars set (those two DO run,
        but on a separate, per-plant "market landscape" panel —
        market_landscape() below — not per candidate row; calling them
        here would mean a live network/API call for every single
        alternative-plant row in a run, which is a cost/latency
        decision that deserves its own review, not a side effect of
        this fix). So "Verified marketed product" and "No verified
        product found" remain unreachable from this function specifically
        — kept in the vocabulary for forward compatibility with
        market_landscape()'s own, separately-verified results.

        "Conflicting market evidence": when two of this function's OWN
        signals disagree — e.g. EMA_Status shows genuine EMA/HMPC
        recognition (inventory listing, monograph, or traditional-use
        support) but the same evidence text explicitly says the product
        has been discontinued/withdrawn. That's a genuine, detectable
        disagreement between two real, present signals, not a guess.

        "Search incomplete": distinguishes "a live search ran this
        session but returned nothing about this SPECIFIC candidate"
        (self.use_live_search is True, evidence is still empty) from
        "no search was ever attempted for this candidate at all"
        (self.use_live_search is False — a curated/seed-only run). The
        old version treated both as identically "Search not performed",
        which overstated how little was actually done for the
        live-search case.
        """
        ema = self._pick(alt, ["EMA_Status"])
        text = self._norm(evidence)

        # Phase 2D-A — PRIMARY source is now the canonical EMA/HMPC
        # connector result, cached once per unique plant per run() call
        # (see run()'s unconditional rebuild of
        # self._canonical_regulatory_by_plant, right after
        # alt_candidate_records is built). alt["EMA_Status"] itself is
        # always "" here (Phase 2C's _candidate_frame() neutralization)
        # — classify_ema_hmpc_signal(ema) below is kept ONLY as the
        # harmless, byte-for-byte-unchanged fallback path for whatever
        # this plant's canonical lookup didn't resolve, not reclassified
        # or reparsed from any display string. getattr() guards callers/
        # tests that construct this engine via __new__() without
        # __init__() (so the attribute may not exist at all).
        canonical = getattr(self, "_canonical_regulatory_by_plant", {}).get(
            self._pick(alt, ["Scientific_Name"])
        ) or {}
        canonical_category = canonical.get("EMA_HMPC_Match_Category")
        canonical_compact_status = canonical.get("EMA_HMPC_Status")

        if canonical_category in (
            "exact_species_match", "verified_synonym_match", "verified_pharmacopoeial_name_match",
        ):
            # A confident species-level (or verified synonym/
            # pharmacopoeial-name) match. Still does NOT imply
            # monograph status unless the connector's OWN compact
            # status independently says so — never inferred from the
            # match category alone.
            if canonical_compact_status == "HMPC monograph available":
                ema_signal = "monograph_exists"
            elif canonical_compact_status == "Traditional-use status":
                ema_signal = "traditional_use"
            else:
                ema_signal = "inventory_listed"
        elif canonical_category == "manually_curated":
            # Phase 2D-A correction — the hand-curated/manually-verified
            # path (seed_data.py, via _curated_evidence_for()) is a
            # genuine canonical source too, just not a live connector
            # match. Unlike the three confident-match categories above,
            # a "manually_curated" entry is NOT by itself evidence of
            # inventory presence — the curator may equally well have
            # recorded "not found" or left it unverified. So this
            # branch must read canonical_compact_status explicitly for
            # every case, never default to "inventory_listed" the way
            # the confident-match branch above safely can.
            if canonical_compact_status == "HMPC monograph available":
                ema_signal = "monograph_exists"
            elif canonical_compact_status == "Traditional-use status":
                ema_signal = "traditional_use"
            elif canonical_compact_status == "Listed in HMPC inventory":
                ema_signal = "inventory_listed"
            else:
                # "Not found in HMPC inventory", "Source unavailable",
                # "Not verified", empty, or any other/unrecognized
                # compact status -> no positive regulatory claim.
                ema_signal = "unknown"
        elif canonical_category in ("parsing_failed", "source_unavailable"):
            # A genuine connector/source failure must never collapse
            # into "searched, not found" — that would silently claim a
            # completed negative search that never actually happened.
            ema_signal = "source_unavailable"
        else:
            # genus_only_match / related_species_only / ambiguous_match
            # / searched_not_found / unknown / no canonical entry at
            # all for this plant — none of these may ever upgrade to a
            # listed/monograph/traditional-use claim here. Falls
            # through to the pre-Phase-2D-A behavior
            # (classify_ema_hmpc_signal on alt["EMA_Status"], which is
            # always "" -> "unknown" -> no recognition), unchanged.
            ema_signal = classify_ema_hmpc_signal(ema)

        ema_recognized = ema_signal in ("inventory_listed", "monograph_exists", "traditional_use")

        # Narrow, multi-word phrase patterns — not bare words like
        # "product" or "market", which show up constantly in text that
        # has nothing to do with a real commercial product ("the
        # product of this reaction", "on the world market for herbal
        # teas in general").
        commercial_phrase_patterns = [
            r"\bmarketed as\b", r"\bmarketed product\b",
            r"\bavailable as a supplement\b", r"\bavailable as an? product\b",
            r"\bcommercially available\b", r"\bsold as\b", r"\bbranded as\b",
        ]
        commercial_signal = any(re.search(p, text) for p in commercial_phrase_patterns)

        discontinued_patterns = [
            r"\bdiscontinued\b", r"\bwithdrawn from the market\b",
            r"\bno longer (?:available|marketed|sold)\b",
            r"\bnot currently (?:available|marketed|sold)\b",
            r"\bproduct recall\b",
        ]
        discontinued_signal = any(re.search(p, text) for p in discontinued_patterns)

        # A real disagreement: something asserts market presence
        # (regulatory recognition or a commercial-phrase mention) AND
        # something else in the SAME evidence asserts the product is
        # gone/unavailable. Checked first — this is more informative to
        # surface than picking one side and silently discarding the other.
        if (ema_recognized or commercial_signal) and discontinued_signal:
            return "Conflicting market evidence"

        if ema_signal == "monograph_exists":
            return "Regulatory monograph exists"

        if ema_signal == "traditional_use":
            return "Traditional-use status"

        if ema_signal == "inventory_listed":
            # Phase 2A — deliberately NOT "Regulatory monograph exists".
            # Being listed in EMA/HMPC's assessment inventory means the
            # substance has been formally proposed/prioritized for
            # monograph assessment; it does not by itself mean a
            # monograph has been adopted, that traditional-use or
            # well-established-use status applies, or that the product
            # is authorized/approved. Mirrors
            # MarketVerificationStatus.REGULATORY_ASSESSMENT_INVENTORY_LISTED
            # in data_contracts.py.
            return "Listed in EMA HMPC inventory — monograph not established"

        if ema_signal == "source_unavailable":
            # Phase 2D-A — a genuine connector/source failure
            # (parsing_failed or source_unavailable from the canonical
            # cache), kept distinct from "Search not performed"/
            # "Search incomplete" below: those mean no search was
            # attempted (or attempted-but-empty-for-this-candidate);
            # this means a search WAS attempted and the source itself
            # failed. Reuses MarketVerificationStatus.SOURCE_UNAVAILABLE
            # (data_contracts.py) — already-defined vocabulary, not a
            # new value.
            return "Source unavailable"

        if commercial_signal:
            return "Commercial evidence reported, not independently verified"

        traditional_use_patterns = [
            r"\btraditional(?:ly)? use\b", r"\bwell-established use\b",
            r"\btraditional medicine\b",
        ]
        if any(re.search(p, text) for p in traditional_use_patterns):
            return "Traditional-use status"

        if self.use_live_search:
            # A live search ran this session (Step 2 was used), but
            # nothing turned up about THIS specific candidate — a
            # genuinely different, more-informative claim than "no
            # search was ever attempted."
            return "Search incomplete"

        return "Search not performed"

    def _novelty_status(
        self,
        ref_plant,
        alt_plant,
        matched,
        ref_compound,
        alt,
        compound_is_common=False,
        compound_plant_count=0,
    ):
        if self._norm(ref_plant) == self._norm(alt_plant):
            return "Reference plant / benchmark"

        matched_clean = matched.split("[")[0].strip()

        # A compound this common tells you almost nothing about THIS
        # specific plant pair, whatever indication or species are
        # involved — so it must not be labelled as if it were a
        # meaningful "alternative source" finding.
        if compound_is_common:
            return (
                f"Common/non-specific compound — found in "
                f"{compound_plant_count}+ plants database-wide, "
                f"low differentiation value"
            )

        if self._norm(matched_clean) == self._norm(ref_compound):
            return "Alternative source with same compound"

        region = self._pick(alt, ["Region"])

        if region:
            return f"Cross-region similar-compound opportunity ({region})"

        return "Alternative source with similar compound"

    @staticmethod
    def _hard_safety_gate(safety_flags, same_plant):
        """Single source of truth for the hard safety auto-exclusion —
        Task 1. Both _decision_class()'s early-return and
        _evaluate_gates()'s "safety" entry call this one method, so the
        two can never silently drift apart. Behavior is byte-identical
        to the pre-Task-1 inline check in _decision_class(): a
        HARD_SAFETY_TERMS hit forces FAILED unless same_plant, in which
        case the exclusion is intentionally skipped (see the long
        comment that used to live inline here, now in _decision_class()
        immediately below) and the gate reports NOT_EVALUABLE rather
        than silently passing.

        Returns (GateStatus, hit_terms: set, flagged_terms: set).
        """
        flagged_terms = {
            term.strip() for term in safety_flags.split("; ") if term.strip()
        } if safety_flags else set()
        hit_terms = flagged_terms & HARD_SAFETY_TERMS
        if same_plant:
            return GateStatus.NOT_EVALUABLE, hit_terms, flagged_terms
        if hit_terms:
            return GateStatus.FAILED, hit_terms, flagged_terms
        return GateStatus.PASSED, hit_terms, flagged_terms

    @staticmethod
    def _hard_regulatory_gate(regulatory_barrier_types, same_plant):
        """Single source of truth for the hard regulatory-prohibition
        auto-exclusion — Task 4 (activating the regulatory gate).
        Mirrors _hard_safety_gate()'s structure exactly, so
        _decision_class() and _evaluate_gates()'s "regulatory" entry
        can never disagree.

        same_plant skips the hard exclusion for the reference plant
        matched to itself, for the identical reason _hard_safety_gate()
        does: a merged self-row can combine dozens of a plant's own
        compounds' pooled evidence text, and one trace/incidental
        compound's regulatory mention must not label the reference
        plant itself as prohibited. The flag itself stays visible in
        Regulatory_Barriers/Rationale either way — only the hard
        exclusion is skipped, and the gate reports NOT_EVALUABLE
        (like safety does) rather than silently passing.

        regulatory_barrier_types is None when no evidence text was
        ever collected for this row (never checked) — that is a data
        gap, not a prohibition, and must never be treated as a
        hard-stop; only an explicit "Prohibited / banned" entry is.

        Returns (GateStatus, banned_types: set).
        """
        if same_plant:
            return GateStatus.NOT_EVALUABLE, set()
        if regulatory_barrier_types is None:
            return GateStatus.NOT_EVALUABLE, set()
        if "Prohibited / banned" in regulatory_barrier_types:
            return GateStatus.FAILED, {"Prohibited / banned"}
        return GateStatus.PASSED, set()

    @staticmethod
    def _evaluate_gates(
        safety_flags,
        match_quality,
        has_evidence,
        evidence_level,
        regulatory_barrier_types,
        same_plant=False,
        has_evidence_text=None,
    ):
        """Task 1 — Formal Gate Layer. Additive, non-blocking output for
        two of its four gates: a gate reports whether a candidate
        clears a specific, independently-named precondition, separate
        from R&D_Opportunity_Score and Decision_Class. TWO gates are
        an exception to "non-blocking": "safety" (via
        _hard_safety_gate, unchanged since Task 1) and, as of Task 4,
        "regulatory" (via _hard_regulatory_gate) — each reports the
        SAME hard, non-compensatory exclusion that _decision_class()
        enforces, exposed here in structured form as well as the
        original string return value. Neither gate's FAILED status can
        be offset by score, market signal, or mechanistic plausibility.

        The other two gates (identity / minimum_evidence) remain
        informational only: computed and reported on every row, but
        never read by _decision_class() or _score_candidate(), and
        therefore never able to change Decision_Class,
        R&D_Opportunity_Score, or rank. Making either hard-blocking is
        a deliberate later step, gated on validating them against the
        Task 5 benchmark set first.

        Public status vocabulary is exactly GateStatus.PASSED /
        GateStatus.FAILED / GateStatus.NOT_EVALUABLE — there is no
        "needs review" state. A gate that finds a real-but-not-hard
        concern (e.g. identity resting on a class-only match) reports
        NOT_EVALUABLE with a specific reason, rather than a fourth
        status, because "class_only" is a weak signal, not an
        affirmative pass or fail of identity.

        Returns a dict of exactly four keys — safety, identity,
        minimum_evidence, regulatory — each mapping to
        {"gate_name": <same key>, "status": GateStatus, "reason": str,
        "evidence": str}.

        ARCHITECTURE NOTE — explicit evidence-to-gate attribution
        (i.e. recording exactly which Evidence_Record_ID(s) caused a
        specific gate's PASSED/FAILED/NOT_EVALUABLE status) is
        intentionally NOT implemented here, for four concrete
        architectural reasons:

        1. Not every gate is evidence-derived. "identity" comes from
           compound-database matching (_match_compounds(), against
           plant_compounds/compound_profiles) — it has no relationship
           to any evidence_records row at all, so "evidence-to-gate
           attribution" is a category error for this gate specifically.
        2. "safety" itself blends two sources with no per-source
           marker: text-derived flags (from the flattened raw_evidence
           blob) AND db_safety_flags (from matched_own_targets, a
           compound-database lookup with no Evidence_Record_ID to
           attribute to either).
        3. True per-record attribution for the text-derived signals
           (safety's text half, minimum_evidence, regulatory) would
           require preserving each evidence record's own text
           boundary through to keyword extraction — today,
           _build_evidence_text_index()/_collect_raw_evidence()
           concatenate multiple evidence_records rows into one
           candidate-scoped string BEFORE any SAFETY_TERMS/
           regulatory_barrier_classifier extraction runs, so the
           record-of-origin for any single matched term is not
           preserved past that concatenation step.
        4. Candidate-level (not per-gate) traceability already exists
           and is considered sufficient at the current evidence volume
           and validation maturity: gate_results (this method's own
           output) plus Applicability_Summary.evidence_record_ids
           (_summarize_applicability(), Task 10.2) together let a
           reviewer manually cross-check which evidence records could
           have contributed to a candidate's gate outcomes, without
           the engine claiming a precision of attribution it cannot
           currently support.

        Revisiting this is a real, separate, larger architecture task
        (restructuring the text-concatenation step to preserve
        per-record boundaries) — not a small addition to this method.
        """
        gates = {}

        # --- Safety gate: delegates to the single shared check so this
        # can never disagree with _decision_class()'s own hard-exclusion. ---
        safety_status, hit_terms, flagged_terms = (
            BotanicalRDCandidateEngine._hard_safety_gate(safety_flags, same_plant)
        )
        if safety_status == GateStatus.NOT_EVALUABLE:
            safety_reason = (
                "Reference plant matched to itself; the hard safety "
                "auto-exclusion is intentionally skipped for this "
                "self-row (see _decision_class same_plant handling)."
            )
        elif safety_status == GateStatus.FAILED:
            safety_reason = (
                f"Documented hard safety term(s) present: "
                f"{', '.join(sorted(hit_terms))}."
            )
        else:
            safety_reason = "No documented hard safety term present."
        gates["safety"] = {
            "gate_name": "safety",
            "status": safety_status,
            "reason": safety_reason,
            "evidence": "; ".join(sorted(flagged_terms)) if flagged_terms else "No explicit flag found",
        }

        # --- Identity gate: uses the same match_quality vocabulary
        # ("exact" / "target_verified" / "class_only") _decision_class()
        # already reads elsewhere (e.g. its own weak_target_match/
        # needs_cap logic) — no new identity states are introduced here.
        # A "class_only" match is NOT_EVALUABLE, not FAILED: the repo
        # has no signal that affirmatively proves an identity match is
        # WRONG, only signals of how strong a confirmed match is — so
        # the only two states an evidence-backed conclusion can support
        # here are PASSED (identity is resolved) and NOT_EVALUABLE
        # (identity is not resolved, for any reason, including a weak
        # class-only match or a missing signal). ---
        if not match_quality:
            gates["identity"] = {
                "gate_name": "identity",
                "status": GateStatus.NOT_EVALUABLE,
                "reason": "No match-quality signal was available for this row.",
                "evidence": "",
            }
        elif match_quality in {"exact", "target_verified"}:
            gates["identity"] = {
                "gate_name": "identity",
                "status": GateStatus.PASSED,
                "reason": f"Compound identity resolved via a '{match_quality}' match.",
                "evidence": match_quality,
            }
        else:
            gates["identity"] = {
                "gate_name": "identity",
                "status": GateStatus.NOT_EVALUABLE,
                "reason": (
                    "Match rests on a class-only (broad chemical-class) "
                    "similarity, not a confirmed shared compound or "
                    "target — not strong enough to affirmatively resolve "
                    "identity, and not an affirmative identity failure either."
                ),
                "evidence": match_quality,
            }

        # --- Minimum-evidence gate: PASSED requires a real, located
        # evidence record (has_evidence and evidence_level isn't the
        # generic placeholder). FAILED would require an existing
        # repository signal that affirmatively proves evidence
        # collection/evaluation occurred AND the defined minimum was
        # not met. The repository was inspected for such a signal:
        # Has_Negative_Evidence / negative_evidence.is_negative exists,
        # but it measures FINDING DIRECTION (a study was found and its
        # result was negative/failed/null) — that is a different
        # concept from evidence VOLUME being insufficient, and using it
        # here would conflate "we found evidence and it didn't work"
        # with "we didn't find enough evidence to judge." No existing
        # signal distinguishes "not searched" from "searched, found
        # nothing" for this candidate, so FAILED is not reachable here
        # — the generic no-evidence case is NOT_EVALUABLE, per Task 1's
        # explicit instruction not to invent a threshold or a new
        # evidence-state framework. ---
        if has_evidence and evidence_level != "No direct evidence":
            gates["minimum_evidence"] = {
                "gate_name": "minimum_evidence",
                "status": GateStatus.PASSED,
                "reason": f"Evidence located at level: {evidence_level}.",
                "evidence": evidence_level,
            }
        else:
            gates["minimum_evidence"] = {
                "gate_name": "minimum_evidence",
                "status": GateStatus.NOT_EVALUABLE,
                "reason": (
                    "No direct evidence is recorded for this candidate, "
                    "and the repository has no signal distinguishing "
                    "'not searched' from 'searched and none found' — "
                    "this cannot be reported as an affirmative failure."
                ),
                "evidence": evidence_level,
            }

        # --- Regulatory-prohibition gate: only an EXPLICIT prohibition
        # (regulatory_barrier_classifier's "Prohibited / banned" category)
        # fails this gate — "not available"/"unknown" market status is a
        # data gap, not a prohibition, and must never be conflated with one.
        # regulatory_barrier_types is None when no evidence text was ever
        # collected for this row (never checked), vs. an empty list when
        # evidence was reviewed and no barrier was found (checked, clear) —
        # same "never searched" vs. "searched, found nothing" distinction
        # _market_status() already makes for its own vocabulary. Any
        # non-ban restriction (prescription-only, controlled, restricted
        # access, claim-limited, etc.) stays visible in evidence/reason
        # but never fails this gate.
        #
        # Task 4 — delegates to the single shared check
        # (_hard_regulatory_gate) so this status can never disagree with
        # _decision_class()'s own hard-exclusion, exactly mirroring how
        # the "safety" gate above delegates to _hard_safety_gate(). This
        # also threads same_plant through for the first time: a
        # reference plant matched to itself skips the hard exclusion for
        # the same reason the safety gate already does (see
        # _hard_regulatory_gate()'s own docstring). ---
        regulatory_status, _banned_types = (
            BotanicalRDCandidateEngine._hard_regulatory_gate(regulatory_barrier_types, same_plant)
        )
        if same_plant:
            gates["regulatory"] = {
                "gate_name": "regulatory",
                "status": regulatory_status,
                "reason": (
                    "Reference plant matched to itself; the hard "
                    "regulatory-prohibition auto-exclusion is "
                    "intentionally skipped for this self-row (see "
                    "_decision_class same_plant handling)."
                ),
                "evidence": "; ".join(regulatory_barrier_types) if regulatory_barrier_types else "",
            }
        elif regulatory_status == GateStatus.NOT_EVALUABLE:
            gates["regulatory"] = {
                "gate_name": "regulatory",
                "status": GateStatus.NOT_EVALUABLE,
                "reason": "No evidence text was available to check for a regulatory prohibition.",
                "evidence": "",
            }
        elif regulatory_status == GateStatus.FAILED:
            gates["regulatory"] = {
                "gate_name": "regulatory",
                "status": GateStatus.FAILED,
                "reason": (
                    "Reviewed evidence text indicates this candidate is "
                    "prohibited/banned in at least one jurisdiction."
                ),
                "evidence": "; ".join(regulatory_barrier_types),
            }
        else:
            gates["regulatory"] = {
                "gate_name": "regulatory",
                "status": GateStatus.PASSED,
                "reason": "No explicit prohibition/ban found in reviewed evidence text.",
                "evidence": "; ".join(regulatory_barrier_types) if regulatory_barrier_types else "None identified",
            }

        # --- Eligibility gate (correction round, item 4): the SAME
        # decision _decision_class() derives its string from, exposed
        # here in structured form too, so Gate_Results can never
        # disagree with Eligibility_Status/Decision_Class for the same
        # row. The legacy "safety"/"regulatory" keys above are LEFT
        # UNCHANGED (still delegate to _hard_safety_gate/
        # _hard_regulatory_gate, still can report NOT_EVALUABLE for a
        # same_plant row) — they are now understood as a coarser,
        # legacy view; "eligibility" is the authoritative one a
        # consumer should actually gate on.
        hit_terms_eligibility = frozenset(
            {t.strip() for t in safety_flags.split("; ") if t.strip()} & HARD_SAFETY_TERMS
        ) if safety_flags else frozenset()
        flagged_terms_eligibility = frozenset(
            {t.strip() for t in safety_flags.split("; ") if t.strip()}
        ) if safety_flags else frozenset()
        assumed_has_text_eligibility = True if has_evidence_text is None else bool(has_evidence_text)
        eligibility_safety_finding = _classify_safety_finding(
            hit_terms=hit_terms_eligibility,
            flagged_terms=flagged_terms_eligibility,
            has_evidence_text=assumed_has_text_eligibility,
            same_plant=same_plant,
        )
        eligibility_regulatory_finding = _classify_regulatory_finding(
            barrier_types=(
                frozenset(regulatory_barrier_types) if regulatory_barrier_types else frozenset()
            ),
            has_evidence_text=assumed_has_text_eligibility,
            same_plant=same_plant,
        )
        eligibility_decision_for_gates = _evaluate_eligibility(
            eligibility_safety_finding, eligibility_regulatory_finding
        )
        gates["eligibility"] = {
            "gate_name": "eligibility",
            "status": eligibility_decision_for_gates.status.value,
            "reason": eligibility_decision_for_gates.gate_reason,
            "evidence": "; ".join(eligibility_decision_for_gates.gate_evidence_ids),
        }

        return gates

    def _decision_class(
        self,
        score,
        safety_flags,
        interaction_flags,
        has_evidence,
        match_quality,
        evidence_level="No direct evidence",
        compound_is_common=False,
        target_specificity=None,
        same_plant=False,
        regulatory_barrier_types=None,
        has_evidence_text=None,
    ):
        # Phase 4 — Eligibility Gate. Decision_Class is now DERIVED from
        # eligibility_gate.evaluate_eligibility(), not a parallel,
        # independently-maintained hard-stop check. Pre-Phase-4, this
        # method called _hard_safety_gate()/_hard_regulatory_gate()
        # directly, and `same_plant=True` made BOTH of those return
        # GateStatus.NOT_EVALUABLE — which, because nothing below this
        # point treated NOT_EVALUABLE any differently from an
        # affirmative pass, meant a same_plant self-row with a
        # documented hard safety term (e.g. "teratogenic") or an
        # explicit "Prohibited / banned" regulatory finding fell straight
        # through into the ordinary score-based tiers below and could be
        # labelled "Strong R&D candidate" — proven directly by the Phase
        # 4 audit (see the now-xfail'd characterization tests
        # test_same_plant_downgrades_decision_class_for_identical_hard_safety_flag
        # / test_same_plant_downgrades_decision_class_for_identical_prohibition
        # in test_phase4_eligibility_gate_characterization.py, which
        # documented that exact old behavior).
        #
        # _hard_safety_gate()/_hard_regulatory_gate() themselves are left
        # UNCHANGED (still used only by _evaluate_gates() for the
        # informational, additive Gate_Results column) — this method no
        # longer calls them for its own decision.
        #
        # has_evidence_text distinguishes "evidence text existed and
        # mentioned nothing concerning" from "no evidence text existed
        # to search in the first place" for the SAFETY side (the
        # regulatory side already carried this distinction natively via
        # regulatory_barrier_types being None vs. an empty/populated
        # collection — see classify_regulatory_finding()). Defaults to
        # None (treated as "assume text existed") for backward
        # compatibility with existing direct unit-test call sites that
        # predate Phase 4 and don't pass it; the live production call
        # site in run() always passes it explicitly.
        hit_terms = frozenset(
            {term.strip() for term in safety_flags.split("; ") if term.strip()} & HARD_SAFETY_TERMS
        ) if safety_flags else frozenset()
        flagged_terms = frozenset(
            {term.strip() for term in safety_flags.split("; ") if term.strip()}
        ) if safety_flags else frozenset()
        # Backward compatibility: has_evidence_text=None (the default for
        # every pre-Phase-4 caller, including 28+ existing direct unit-test
        # call sites) is treated as "assume evidence text existed" for
        # BOTH safety and regulatory findings — this preserves every
        # pre-Phase-4 caller's existing expectations (e.g. a caller that
        # never passes regulatory_barrier_types at all still gets a
        # regulatory CLEAR finding, not a manufactured INCOMPLETE). The
        # live production call site in run() always passes
        # has_evidence_text explicitly (bool(raw_evidence and
        # raw_evidence.strip())), which is what actually closes the
        # audit-proven fail-open gap.
        assumed_has_text = True if has_evidence_text is None else bool(has_evidence_text)

        safety_finding = _classify_safety_finding(
            hit_terms=hit_terms,
            flagged_terms=flagged_terms,
            has_evidence_text=assumed_has_text,
            same_plant=same_plant,
        )
        regulatory_finding = _classify_regulatory_finding(
            barrier_types=(
                frozenset(regulatory_barrier_types) if regulatory_barrier_types else frozenset()
            ),
            has_evidence_text=assumed_has_text,
            same_plant=same_plant,
        )
        eligibility = _evaluate_eligibility(safety_finding, regulatory_finding)

        if eligibility.status == _EligibilityStatus.NO_GO_SAFETY:
            return "Safety concern — not suitable without expert review"
        if eligibility.status == _EligibilityStatus.NO_GO_REGULATORY:
            return REGULATORY_PROHIBITION_DECISION_CLASS
        if eligibility.status == _EligibilityStatus.EXPERT_REVIEW_REQUIRED:
            # Deliberately does NOT contain "strong"/"promising"/
            # "recommend" (would false-positive the legacy UI's positive
            # regex) and DOES contain "not" (so it still falls into the
            # legacy UI's "weak/not recommended" bucket as defense in
            # depth, even though the real fix reads Eligibility_Status/
            # Eligible_For_Normal_Ranking directly — see
            # step_rd_candidates.py's _recommendation_block()).
            return (
                "Expert review required — not eligible for normal ranking "
                "until safety/regulatory scope is confirmed"
            )
        if eligibility.status == _EligibilityStatus.INCOMPLETE:
            return (
                "Incomplete — insufficient safety/regulatory evidence for "
                "a validated recommendation"
            )
        # ELIGIBLE / ELIGIBLE_WITH_RESTRICTIONS fall through to the
        # existing score-based tiers below, unchanged from pre-Phase-4
        # behavior for these two statuses.

        # Controversial-only flags (carcinogenic/mutagenic/genotoxic with
        # no accompanying hard-tier term) fall straight through past the
        # hard-exclusion check above — they don't force exclusion. They
        # still can't reach "Strong" on their own: `safety_flags` being
        # non-empty already makes `risky` True below, which caps the
        # ceiling at "Promising candidate; verify safety and
        # standardization" — visible and capped, but a human still gets
        # to see and weigh it rather than having it silently excluded.
        risky = bool(safety_flags) or bool(interaction_flags)

        if score >= 78 and not risky:
            base = "Strong R&D candidate"
        elif score >= 62:
            base = "Promising candidate; verify safety and standardization"
        elif score >= 45:
            base = "Early-stage candidate; more evidence needed"
        else:
            base = "Low priority / insufficient data"

        order = [
            "Low priority / insufficient data",
            "Early-stage candidate; more evidence needed",
            "Promising candidate; verify safety and standardization",
            "Strong R&D candidate",
        ]

        # Confidence caps make the output scientifically defensible.
        if not has_evidence or evidence_level == "No direct evidence":
            ceiling = (
                "Promising candidate; verify safety and standardization"
                if match_quality == "exact"
                else "Early-stage candidate; more evidence needed"
            )
        elif evidence_level in {"General literature signal", "Preclinical / mechanistic evidence"}:
            ceiling = "Promising candidate; verify safety and standardization"
        elif risky:
            ceiling = "Promising candidate; verify safety and standardization"
        else:
            ceiling = "Strong R&D candidate"

        # A match resting on a compound found across hundreds/thousands
        # of unrelated plants database-wide is not, by itself, strong
        # enough scientific grounds for a top-tier recommendation —
        # regardless of which plant, compound, or indication is involved.
        # Genuinely strong independent evidence (clinical or regulatory)
        # can still carry a candidate to "Strong", since that no longer
        # relies on the compound match being specific. The same applies
        # to a "target_verified" match whose confirming shared target is
        # carried by several other compounds too — a weak confirmation,
        # even if not literally "generic" by any fixed cutoff.
        weak_target_match = (
            match_quality == "target_verified"
            and target_specificity
            and target_specificity > 4
        )
        needs_cap = compound_is_common or weak_target_match
        if needs_cap and evidence_level not in {
            "Clinical / human evidence",
            "Regulatory / monograph evidence",
        }:
            common_ceiling = "Early-stage candidate; more evidence needed"
            if order.index(common_ceiling) < order.index(ceiling):
                ceiling = common_ceiling

        if order.index(base) > order.index(ceiling):
            return ceiling

        return base

    def _evidence_level(self, evidence):
        text = self._norm(evidence)
        if not text:
            return "No direct evidence"

        # Specific, multi-word phrases that actually indicate a real
        # clinical study design — deliberately NOT single common words
        # like "human", "patient", "subjects", or "participants". Those
        # generic words show up constantly in evidence text that has
        # NOTHING to do with an actual clinical trial (safety
        # disclaimers, food-use history, unrelated abstracts pooled in
        # from other records about the same plant) — using them as
        # triggers was silently classifying the vast majority of
        # candidates as having "Clinical / human evidence" regardless of
        # whether any such evidence actually existed.
        clinical_terms = [
            "clinical trial", "randomized controlled trial",
            "randomised controlled trial", "double-blind", "double blind",
            "placebo-controlled", "placebo controlled", "human trial",
            "human study", "clinical study", "cohort study",
            "case-control study", "phase i trial", "phase ii trial",
            "phase iii trial", "meta-analysis", "systematic review",
            "clinicaltrials.gov",
        ]
        regulatory_terms = [
            "ema", "hmpc", "hmcp", "escop", "who monograph", "monograph",
            "traditional use", "well-established use",
        ]
        preclinical_terms = [
            "in vitro", "in vivo", "animal model", "mouse model",
            "rat model", "mechanism of action", "signaling pathway",
            "receptor binding", "enzyme inhibition",
        ]

        # A term immediately preceded by a negation cue within a short
        # word window doesn't count as positive evidence — "no clinical
        # trials have been conducted" and "insufficient human studies"
        # should not be scored the same as an actual reported trial.
        # Negation handling itself now lives in scientific_phrase_matcher
        # (NEGATION_CUES there), used by _has_term below.

        def _has_term(terms):
            # Delegates to the shared scientific_phrase_matcher utility
            # instead of a local \bTERM\b-only regex. Fix for the proven
            # plural-form bug (\bclinical trial\b did not match "clinical
            # trials") — see scientific_phrase_matcher.py. Word-boundary
            # and negation-aware behavior are otherwise unchanged from
            # before (negation_aware=True is the shared utility's
            # default).
            return has_phrase_match(text, terms)

        if _has_term(clinical_terms):
            return "Clinical / human evidence"
        if _has_term(regulatory_terms):
            return "Regulatory / monograph evidence"
        if _has_term(preclinical_terms):
            return "Preclinical / mechanistic evidence"
        return "General literature signal"

    def _rationale(
        self,
        product_type,
        problem,
        dosage_form,
        ref_plant,
        ref_compound,
        alt_plant,
        matched,
        match_quality,
        has_evidence,
        evidence_level,
        extraction,
        concentration,
        co_compounds,
        market_status,
        novelty_status,
        decision,
    ):
        basis = {
            "exact": "it contains the exact same reference compound",
            "target_verified": "it contains a chemically-related compound "
                                "that ALSO shares a validated biological "
                                "target with the reference compound (see "
                                "the compound column for how many other "
                                "known compounds also carry that target — "
                                "fewer means a more specific, meaningful "
                                "link)",
            "class_only": "it contains a compound from the same broad "
                          "chemical family only — no shared biological "
                          "target has been confirmed yet, so this link is "
                          "a hypothesis, not evidence",
        }.get(match_quality, "an unspecified link")

        evidence_note = (
            f"Evidence level: {evidence_level}."
            if has_evidence else
            "No literature evidence text was found yet for this "
            "plant/compound pair — this candidate's confidence has been "
            "capped accordingly until evidence is collected."
        )

        return (
            f"For {product_type} targeting {problem}, {alt_plant} is compared "
            f"with {ref_plant} because {basis} ({matched}), linked to the "
            f"reference compound {ref_compound}. Extraction fit for "
            f"{dosage_form}: {extraction or 'not clearly reported'}. "
            f"Concentration: {concentration or 'not clearly reported'}. "
            f"Co-compounds: {co_compounds or 'not clearly extracted'}. "
            f"Market: {market_status}. Novelty: {novelty_status}. "
            f"{evidence_note} Decision: {decision}."
        )

    def _target_or_mechanism(self, ref_targets, alt):
        alt_targets = self._split_terms(
            self._pick(alt, ["Known_Targets"])
        )

        ref_target_norms = {
            self._norm(target)
            for target in ref_targets
        }

        shared = [
            target
            for target in alt_targets
            if self._norm(target) in ref_target_norms
        ]

        if shared:
            return "; ".join(shared)

        return "; ".join(alt_targets or ref_targets)

    @staticmethod
    def _target_or_mechanism_fast(
        ref_targets, ref_target_norms, alt_targets, alt_target_norms
    ):
        """Same result as _target_or_mechanism, but takes pre-normalized
        target lists so it does zero _norm() calls itself. At Dr. Duke's
        scale, target lists can be long (a compound's activities list),
        and re-normalizing both sides on every single (reference, alt)
        pair — instead of once per reference and once per alt-candidate —
        was responsible for the vast majority of run()'s runtime (tens of
        millions of redundant _norm() calls for a single indication).
        """
        shared = [
            target
            for target, norm in zip(alt_targets, alt_target_norms)
            if norm in ref_target_norms
        ]

        if shared:
            return "; ".join(shared)

        return "; ".join(alt_targets or ref_targets)

    def _extract_concentration(self, text):
        # Was: a flat set of regexes joined into one string with no
        # indication of WHAT BASIS each number was on (see audit 4.10 —
        # "0.5%; 3 mg/g" tells a reader nothing about whether those two
        # numbers are even meant to sit side by side). Now: every value
        # is classified by basis, and if a single text mixes bases, the
        # returned string says so explicitly instead of leaving it to
        # the reader to notice. See concentration_normalizer.py.
        #
        # Returns "" (not a placeholder string) when nothing is found —
        # existing callers rely on that falsiness: the score-presence
        # bonus ("score += 10 if concentration else 2") and the two
        # "concentration or 'not clearly reported'" display fallbacks
        # elsewhere in this file both break if this always returns a
        # non-empty string.
        parsed = parse_concentration(text)
        if not parsed:
            return ""
        return format_concentration_info(parsed)[:300]

    def _extract_extraction(self, text):
        text_norm = self._norm(text)
        found = []

        for label, keywords in EXTRACTION_KEYWORDS.items():
            if any(keyword in text_norm for keyword in keywords):
                found.append(label)

        return "; ".join(sorted(set(found)))

    def _co_compounds(self, compounds, matched, compound_norms=None):
        matched_base = self._norm(matched.split("[")[0])

        if compound_norms is None:
            compound_norms = [self._norm(c) for c in compounds]

        co_compounds = [
            compound
            for compound, norm in zip(compounds, compound_norms)
            if norm != matched_base
        ]

        return "; ".join(co_compounds[:8])

    def _extract_flags(self, text, terms):
        text_norm = self._norm(text)

        found = [
            term
            for term in terms
            if term in text_norm
        ]

        return "; ".join(sorted(set(found)))

    # Negation cues that flip a nearby hazard word from "present" to
    # "explicitly absent" — "no adverse events", "without toxicity",
    # "lacks contraindications" should not be flagged the same as an
    # actual reported hazard. Shared with _evidence_level's own
    # negation handling below (same technique, same reasoning).
    _NEGATION_CUES = (
        "no ", "not ", "lack of ", "lacks ", "insufficient ",
        "absence of ", "without ", "none found", "no evidence of ",
        "no direct ", "unproven", "unconfirmed", "no reported ",
        "did not show", "did not exhibit", "devoid of",
    )

    @classmethod
    def _extract_flags_negation_aware(cls, text, terms):
        """Like _extract_flags, but for free prose (paper abstracts,
        regulatory notes) rather than a database's own structured
        activity list. Two independent ways a hazard word's plain
        substring can mean the OPPOSITE of a hazard, both very common in
        safety-literature phrasing:
          1. A negation phrase just before it: "no adverse events",
             "without toxicity", "did not show hepatotoxicity".
          2. An "anti-" prefix fused directly onto the word with no
             space: "antitoxic", "antihepatotoxic" — the same collision
             already found and fixed for Dr. Duke's own structured
             activity tags (e.g. "anticonvulsant"), but free text needs
             its own check since it isn't a clean list of discrete terms
             to exact-match against.
        Applies to every term in `terms`, not a special case for any one
        word or compound.
        """
        text_norm = cls._norm(text)
        if not text_norm:
            return ""

        found = []
        for term in terms:
            idx = text_norm.find(term)
            while idx != -1:
                anti_fused = text_norm[max(0, idx - 4):idx] == "anti"
                window_start = max(0, idx - 40)
                preceding = text_norm[window_start:idx]
                negated = anti_fused or any(
                    cue in preceding[-25:] for cue in cls._NEGATION_CUES
                )
                if not negated:
                    found.append(term)
                    break
                idx = text_norm.find(term, idx + 1)

        return "; ".join(sorted(set(found)))

    @staticmethod
    def _extract_hazard_flags_exact(known_terms, hazard_terms):
        """For matching against a DISCRETE set of known activity terms
        (e.g. a compound's own Dr. Duke's Known_Target list, already
        split into individual named activities) rather than free-text
        prose. Checks each term for an EXACT match (after normalizing)
        against the hazard vocabulary, instead of substring-searching a
        joined blob.

        This distinction matters: Dr. Duke's own vocabulary includes
        both a hazard term AND its protective opposite as separate,
        deliberate entries — "Convulsant" and "Anticonvulsant",
        "Carcinogenic" and "Anticarcinogenic", "Mutagenic" and
        "Antimutagenic", "Hepatotoxic" and "Antihepatotoxic", "Emetic"
        and "Antiemetic", "Genotoxic" and "Antigenotoxic", "Hemolytic"
        and "Antihemolytic" all coexist in the same database. Substring
        matching (`"convulsant" in text`) can't tell these apart —
        "convulsant" is trivially a substring of "anticonvulsant", so a
        compound extensively documented as PROTECTIVE against seizures
        (linalool has a substantial body of published anticonvulsant
        research) was being flagged as if it caused them. Comparing
        each already-discrete term for an exact match closes this off
        for every hazard term with an "anti-" counterpart, not just
        this one compound or this one term.
        """
        known_norm = {BotanicalRDCandidateEngine._norm(t) for t in known_terms}
        found = [
            term for term in hazard_terms
            if term in known_norm
        ]
        return "; ".join(sorted(set(found)))

    def _evidence_source(self, plant, compound, evidence):
        if self._curated_evidence_for(plant):
            return (
                "Curated regulatory & clinical evidence "
                "(EMA/WHO/ESCOP-reviewed, cited studies) — "
                "seed_data.SLEEP_TEA_EVIDENCE"
            )

        if evidence:
            return "Live-collected evidence (PubMed/Europe PMC/Supabase)"

        return f"Seed candidate database: {plant} / {compound}"

    @staticmethod
    def _format_score_breakdown(components):
        """Formats _score_candidate's components dict, ranked by
        absolute contribution (largest first) — directly answers the
        architecture-audit question "which evidence contributed MOST
        to this score?" without requiring the reader to recompute
        anything."""
        if not components:
            return "No breakdown available"
        ranked = sorted(components.items(), key=lambda kv: abs(kv[1]), reverse=True)
        return "; ".join(f"{name}: {value:+.1f}" for name, value in ranked)

    @staticmethod
    def _occurrence_corroboration(evidence_source_ids):
        """Gap 3, "Alternative Source scientific defensibility": how many
        INDEPENDENT sources actually back this row's concentration/
        extraction/co-compound claims, not just whether any text was
        found at all. Built directly from Gap 1's evidence_source_ids
        (the distinct Source_URLs that contributed to this row's
        raw_evidence) — no new data collection, just an honest count of
        what's already there.

        This does NOT attempt to attribute individual claims (e.g.
        "concentration came from source A, extraction from source B")
        to specific sources — that would require preserving per-record
        text boundaries all the way through _build_evidence_text_index's
        flattening step, a larger change than this one. What this DOES
        give: a row backed by 3 independent papers is honestly
        distinguishable from a row backed by 1, or by none at all —
        the single most important defensibility signal missing before
        this, at the cost of the smallest possible change.
        """
        count = len(evidence_source_ids) if evidence_source_ids else 0
        if count == 0:
            return "No independent source identified — not corroborated"
        if count == 1:
            return "Single-source claim — not independently corroborated"
        return f"Corroborated by {count} independent sources"

    def _known_compounds_from_text(self, text):
        text_norm = self._norm(text)
        found = []

        for compound in self.compound_to_class:
            if compound in text_norm:
                found.append(compound)

        return found

    @staticmethod
    def _to_dataframe(data):
        if data is None:
            return pd.DataFrame()

        if isinstance(data, pd.DataFrame):
            return data.copy()

        return pd.DataFrame(data)

    @staticmethod
    def _meaningful_tokens(text):
        """Word tokens from an indication string, with generic/connector
        words (&, support, health, ...) removed so token-overlap fallback
        matching only fires on genuinely distinctive shared words.

        Splits on ANY run of non-alphanumeric characters, not just
        whitespace — e.g. Dr. Duke's "Premenstrual Syndrome/PMS" must
        become the two separate tokens "syndrome" and "pms", not one
        glued "syndrome/pms" token that can never match a standalone
        "pms" query token.
        """
        raw_tokens = re.split(r"[^a-z0-9]+", text)
        return {
            token for token in raw_tokens
            if token not in INDICATION_STOPWORDS and len(token) > 2
        }

    @staticmethod
    def _tokens_overlap(tokens_a, tokens_b):
        """Conservative token overlap used only as a fallback.

        A previous implementation returned True when *any one* token
        overlapped.  For multi-concept questions such as
        ``Energy / fatigue`` or ``Metabolic & blood sugar support`` this
        admitted hundreds of rows that matched one generic word and made
        the candidate universe effectively the whole database.

        The fallback is now strict:
        - one-token queries may match that token (including a safe
          prefix/suffix variant such as menstrual/premenstrual);
        - multi-token queries require every query token to be represented.

        Exact/phrase matches are still handled before this helper, so this
        only prevents broad one-word fan-out; it does not replace exact
        indication matching.
        """
        if not tokens_a or not tokens_b:
            return False

        def represented(query_token):
            if query_token in tokens_b:
                return True
            return any(
                len(query_token) >= 5
                and len(candidate_token) >= 5
                and (query_token in candidate_token or candidate_token in query_token)
                for candidate_token in tokens_b
            )

        return all(represented(token) for token in tokens_a)

    @classmethod
    def _indication_match_score(cls, query_text, candidate_text):
        """Return a transparent indication-relevance score (0 = reject).

        This is intentionally a retrieval score, not an R&D score.  It is
        used only to construct the reference-plant universe before the
        decision engine fans out through shared compounds.
        """
        query_norm = cls._norm(query_text)
        candidate_norm = cls._norm(candidate_text)
        if not query_norm or not candidate_norm:
            return 0
        if query_norm == candidate_norm:
            return 100
        if query_norm in candidate_norm or candidate_norm in query_norm:
            return 90

        query_tokens = cls._meaningful_tokens(query_norm)
        candidate_tokens = cls._meaningful_tokens(candidate_norm)
        if cls._tokens_overlap(query_tokens, candidate_tokens):
            return 75
        return 0

    @staticmethod
    def _norm(value):
        if value is None:
            return ""

        value = str(value).strip().lower()

        if value in {"nan", "none", "null"}:
            return ""

        return re.sub(r"\s+", " ", value)

    @classmethod
    def _norm_taxon(cls, value):
        """Like _norm, but also strips botanical-nomenclature tokens
        (the hybrid marker "×"/standalone "x", and infraspecific rank
        abbreviations subsp./ssp./var./f./cv./nothosubsp.) that a
        database's full taxonomic name carries but a person's everyday
        working name for the same plant usually won't. Used only for
        MATCHING a user-supplied plant name against the database — the
        database's actual full name is still what gets displayed and
        used everywhere else."""
        text = cls._norm(value)
        text = text.replace("×", " x ")
        text = re.sub(
            r"\b(x|subsp|ssp|nothosubsp|var|f|cv)\b\.?",
            " ",
            text,
        )
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _split_terms(value):
        if value is None:
            return []

        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = re.split(r"[,;|/]", str(value))

        clean_items = []

        for item in raw_items:
            item = str(item).strip()

            if item and item.lower() not in {"nan", "none", "null"}:
                clean_items.append(item)

        return clean_items

    @staticmethod
    def _split_compound_terms(value):
        """Like _split_terms, but for lists of COMPOUND NAMES
        specifically. Chemical nomenclature routinely uses a comma as
        part of a single compound's own name — "1,8-Cineole",
        "2,3-dihydrobenzofuran", "3,4-Dihydroxyphenylacetic acid" are all
        one compound each. _split_terms splitting on "," was fragmenting
        these into nonsense tokens (a bare "1" plus "8-Cineole" as two
        separate "compounds") every time a compound list got serialized
        and re-parsed. This splits only on ";" and "|" — real delimiters
        this codebase actually uses between distinct compounds in a
        list — never on "," or "/", for any compound name, not just the
        ones that happened to surface this."""
        if value is None:
            return []

        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = re.split(r"[;|]", str(value))

        clean_items = []

        for item in raw_items:
            item = str(item).strip()

            if item and item.lower() not in {"nan", "none", "null"}:
                clean_items.append(item)

        return clean_items

    @staticmethod
    def _pick(row, names):
        for name in names:
            try:
                value = row.get(name, "")
            except AttributeError:
                value = ""

            if (
                value is not None
                and str(value).strip()
                and str(value).lower() not in {"nan", "none", "null"}
            ):
                return str(value).strip()

        return ""

    # ------------------------------------------------------------------ #
    # Known inventory: what is already known for this problem, before any
    # alternative-plant discovery runs. Pure offline lookup against
    # seed_data (PLANT_COMPOUNDS / COMPOUND_TARGETS / TARGET_DISEASES).
    # ------------------------------------------------------------------ #

    def known_inventory_df(self, indication):
        # Step 4 scientific-knowledge contract.  Keep the original six
        # columns for backwards compatibility and append fields that already
        # exist in plant_compounds so the UI can truthfully show mechanisms,
        # safety, plant part, provenance and extraction context.
        columns = [
            "Known_Plant",
            "Known_Compound",
            "Chemical_Class",
            "Known_Target",
            "Evidence_Level",
            "Typical_Extraction",
            "Known_Plant_Part",
            "Known_Mechanism",
            "Extraction_Solvent",
            "Dosage_Form",
            "Bioavailability",
            "Toxicity",
            "Safety_Note",
            "Confidence_Score",
            "Reference_Title",
            "Reference_URL",
            "Evidence_Source",
            "Source_Year",
        ]

        indication_norm = self._norm(indication)

        if not indication_norm:
            return pd.DataFrame(columns=columns)

        if not self.plant_compounds_df.empty:
            supabase_result = self._known_inventory_from_supabase(
                indication_norm, columns
            )
            if not supabase_result.empty:
                return supabase_result

        return self._known_inventory_from_seed_data(indication_norm, columns)

    def _known_inventory_from_supabase(self, indication_norm, columns):
        """Build Step 3/4 inventory from evidence-selected plants.

        This avoids treating the broad ``plant_compounds.indication``
        compilation lists as authoritative plant-level indication tags.
        """
        refs = self._reference_plants_from_supabase(indication_norm, 200)
        if refs is None or refs.empty or "Scientific_Name" not in refs.columns:
            return pd.DataFrame(columns=columns)

        selected = refs["Scientific_Name"].dropna().astype(str).tolist()
        df = self.plant_compounds_df.copy()
        if df.empty or "scientific_name" not in df.columns:
            return pd.DataFrame(columns=columns)

        matched = df[df["scientific_name"].fillna("").astype(str).isin(selected)].copy()
        if matched.empty:
            return pd.DataFrame(columns=columns)

        score_map = dict(zip(refs["Scientific_Name"], refs.get("Retrieval_Score", 0)))
        rows = []
        for _, row in matched.iterrows():
            plant = str(row.get("scientific_name") or "").strip()
            compound = str(row.get("compound_name") or "").strip()
            if not plant or not compound:
                continue
            rows.append({
                "Known_Plant": plant,
                "Known_Compound": compound,
                "Chemical_Class": str(row.get("compound_class") or "").strip(),
                "Known_Target": str(row.get("target") or "").strip(),
                "Evidence_Level": str(row.get("evidence_level") or "").strip(),
                "Typical_Extraction": str(row.get("extraction_method") or "").strip(),
                "Known_Plant_Part": str(row.get("plant_part") or "").strip(),
                "Known_Mechanism": str(row.get("mechanism") or "").strip(),
                "Extraction_Solvent": str(row.get("solvent") or "").strip(),
                "Dosage_Form": str(row.get("dosage_form") or "").strip(),
                "Bioavailability": str(row.get("bioavailability") or "").strip(),
                "Toxicity": str(row.get("toxicity") or "").strip(),
                "Safety_Note": str(row.get("safety_note") or "").strip(),
                "Confidence_Score": row.get("confidence_score"),
                "Reference_Title": str(row.get("reference_title") or "").strip(),
                "Reference_URL": str(row.get("reference_url") or "").strip(),
                "Evidence_Source": str(row.get("source") or "").strip(),
                "Source_Year": str(row.get("source_year") or "").strip(),
                "_retrieval_score": score_map.get(plant, 0),
            })

        if not rows:
            return pd.DataFrame(columns=columns)

        result = (
            pd.DataFrame(rows)
            .drop_duplicates()
            .sort_values(
                ["_retrieval_score", "Known_Plant", "Known_Compound"],
                ascending=[False, True, True],
            )
            .drop(columns=["_retrieval_score"])
            .reset_index(drop=True)
        )
        return result.reindex(columns=columns)

    def _known_inventory_from_seed_data(self, indication_norm, columns):
        """Fallback path used only when Supabase data is unavailable:
        the small local seed_data.py dataset (~30 plants).
        """
        matched_diseases = [
            disease for disease in TARGET_DISEASES
            if indication_norm in self._norm(disease)
            or self._norm(disease) in indication_norm
        ]

        indication_tokens = self._meaningful_tokens(indication_norm)
        for disease in TARGET_DISEASES:
            if disease in matched_diseases:
                continue
            disease_tokens = self._meaningful_tokens(self._norm(disease))
            if self._tokens_overlap(indication_tokens, disease_tokens):
                matched_diseases.append(disease)

        relevant_targets = {}
        for disease in matched_diseases:
            for target, level in TARGET_DISEASES[disease].items():
                relevant_targets[self._norm(target)] = level

        if not relevant_targets:
            return pd.DataFrame(columns=columns)

        rows = []
        for plant, compounds in PLANT_COMPOUNDS.items():
            for compound_name, chem_class, extraction in compounds:
                for target in COMPOUND_TARGETS.get(compound_name, []):
                    if self._norm(target) in relevant_targets:
                        rows.append({
                            "Known_Plant": plant,
                            "Known_Compound": compound_name,
                            "Chemical_Class": chem_class,
                            "Known_Target": target,
                            "Evidence_Level": relevant_targets[self._norm(target)],
                            "Typical_Extraction": extraction,
                        })

        if not rows:
            return pd.DataFrame(columns=columns)

        result = (
            pd.DataFrame(rows)
            .drop_duplicates()
            .sort_values(["Known_Plant", "Known_Compound"])
            .reset_index(drop=True)
        )
        return result.reindex(columns=columns)

    # ------------------------------------------------------------------ #
    # Market landscape: EU regulatory status, patents, retail products.
    #
    # This answers the "what already exists in the market" question and is
    # intentionally a SEPARATE table from run()'s decision table, not extra
    # columns bolted onto it — the OUTPUT_COLUMNS contract stays as-is.
    # ------------------------------------------------------------------ #

    def _curated_evidence_for(self, plant):
        return _SLEEP_TEA_EVIDENCE_NORM_MAP.get(self._norm(plant))

    @staticmethod
    def _compact_ema_status(value):
        """Return a short, non-inflated EMA/HMPC label for tables and exports.

        The full source wording is preserved separately in EMA_HMPC_Detail.
        This function deliberately does not upgrade an inventory match into a
        monograph claim unless the source text explicitly says monograph.

        PHASE 2B FIX: this used to run its own ad hoc, order-sensitive
        substring checks, which had a real bug — the negative check
        only recognized "not found"/"not listed"/"no match", so the
        real connector's actual not-found text, "Not in HMPC inventory
        (as of 2021 snapshot)", never matched it and fell through to
        the "hmpc inventory" substring check instead, which DOES match
        (that text contains "hmpc inventory" as a substring) —
        producing "Listed in HMPC inventory" for a plant that was
        explicitly NOT found. That is the exact EMA_HMPC_Status vs
        EMA_HMPC_Detail contradiction observed for real plants in a
        live Market Analysis run. Fixed by delegating to
        classify_ema_hmpc_signal() (standard_evidence_builder.py) — the
        same shared, already-tested primitive _market_status() and
        build_regulatory_record() use — instead of maintaining a third,
        independently-ordered set of substring rules here.
        """
        if not value:
            return "Not verified"
        signal = classify_ema_hmpc_signal(value)
        return {
            "inventory_listed": "Listed in HMPC inventory",
            "monograph_exists": "HMPC monograph available",
            "traditional_use": "Traditional-use status",
            "searched_not_found": "Not found in HMPC inventory",
            "source_unavailable": "Source unavailable",
            "unknown": "Not verified",
        }[signal]

    def _eu_regulatory_status(self, plant):
        curated = self._curated_evidence_for(plant)
        if curated:
            ema_detail = curated.get("ema_status", "Not evaluated")
            source = "Curated (seed_data.SLEEP_TEA_EVIDENCE) — manually verified"
            return {
                "EMA_HMPC_Status": self._compact_ema_status(ema_detail),
                "EMA_HMPC_Detail": ema_detail,
                "EMA_Source": source,
                "EMA_HMPC_Match_Category": "manually_curated",
                "WHO_Status": curated.get("who_status", "Not independently verified"),
                "WHO_Source": source,
                "ESCOP_Status": curated.get("escop_status", "Not independently verified"),
                "ESCOP_Source": source,
                "Source": source,  # backwards compatibility
            }

        try:
            from ema_regulatory_connector import search_regulatory_sources_real
            records = search_regulatory_sources_real(plant)
            if records:
                r = records[0]
                ema_detail = r.get("EMA_Status", "Not yet verified")
                ema_source = r.get("Source_URL", "") or r.get("Notes", "")
                who_status = r.get("WHO_Status", "Not independently verified")
                escop_status = r.get("ESCOP_Status", "Not independently verified")
                return {
                    "EMA_HMPC_Status": self._compact_ema_status(ema_detail),
                    "EMA_HMPC_Detail": ema_detail,
                    "EMA_Source": ema_source,
                    "EMA_HMPC_Match_Category": r.get("Taxonomic_Match_Status", "unknown"),
                    "WHO_Status": who_status,
                    "WHO_Source": r.get("WHO_Source", "No independent WHO lookup configured"),
                    "ESCOP_Status": escop_status,
                    "ESCOP_Source": r.get("ESCOP_Source", "No independent ESCOP lookup configured"),
                    "Source": r.get("Notes", "") + f" ({r.get('Source_URL', '')})",
                }
        except Exception:
            pass

        source = (
            "No EMA HMPC bulk API exists (browse-only site) — needs manual "
            "lookup at ema.europa.eu and curation."
        )
        return {
            "EMA_HMPC_Status": "Not verified",
            "EMA_HMPC_Detail": "Not yet verified",
            "EMA_Source": source,
            "EMA_HMPC_Match_Category": "source_unavailable",
            "WHO_Status": "Not independently verified",
            "WHO_Source": "No independent WHO lookup configured",
            "ESCOP_Status": "Not independently verified",
            "ESCOP_Source": "No independent ESCOP lookup configured",
            "Source": source,  # backwards compatibility
        }

    def _search_patents(self, query, max_results=5):
        """
        EPO Open Patent Services (OPS) — real free API, needs registration:
        https://developers.epo.org/ (free account -> consumer key/secret).
        Set env vars EPO_OPS_KEY and EPO_OPS_SECRET to activate.
        """
        if not self.use_live_search:
            return [{"status": "Skipped", "canonical_status": "SEARCH_NOT_PERFORMED", "detail": "Live search disabled."}]

        key, secret = os.environ.get("EPO_OPS_KEY"), os.environ.get("EPO_OPS_SECRET")
        if not key or not secret:
            return [{
                "status": "Not configured",
                "canonical_status": "SOURCE_UNAVAILABLE",
                "source_type": "Patent database",
                "source": "EPO OPS",
                "detail": "Set EPO_OPS_KEY and EPO_OPS_SECRET (free registration "
                          "at https://developers.epo.org/) to enable patent search.",
            }]

        try:
            auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
            token_r = requests.post(
                "https://ops.epo.org/3.2/auth/accesstoken",
                headers={"Authorization": f"Basic {auth}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials"},
                timeout=20,
            )
            token_r.raise_for_status()
            access_token = token_r.json().get("access_token")

            search_r = requests.get(
                "https://ops.epo.org/3.2/rest-services/published-data/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": f'ctxt="{query}"', "Range": f"1-{max_results}"},
                timeout=20,
            )
            search_r.raise_for_status()
            retrieved_at = datetime.now(timezone.utc).isoformat()
            hits = []
            try:
                root = ET.fromstring(search_r.text)
                seen = set()
                for doc_id in root.iter():
                    if not str(doc_id.tag).endswith("document-id"):
                        continue
                    fields = {}
                    for child in list(doc_id):
                        tag = str(child.tag).split("}")[-1]
                        fields[tag] = (child.text or "").strip()
                    patent_id = "".join([fields.get("country", ""), fields.get("doc-number", ""), fields.get("kind", "")])
                    if not patent_id or patent_id in seen:
                        continue
                    seen.add(patent_id)
                    hits.append({
                        "Patent_ID": patent_id,
                        "Applicant": None,
                        "Jurisdiction": fields.get("country") or None,
                        "Status": "Unknown — publication-search result only",
                        "Filing_Date": None,
                        "Publication_Date": fields.get("date") or None,
                        "Claim_Relevance": "Query match only; patent claims not inspected",
                        "Ingredient_Preparation_Relevance": query,
                        "Source_URL_or_ID": patent_id,
                    })
                    if len(hits) >= max_results:
                        break
            except ET.ParseError:
                hits = []
            return [{
                "status": "OK",
                "canonical_status": "COMPLETED",
                "source_type": "Patent database",
                "source": "EPO OPS",
                "query": query,
                "retrieval_timestamp": retrieved_at,
                "patent_hits": hits,
                "raw_response": search_r.text if not hits else "",
            }]
        except Exception as e:
            return [{"status": "Error", "canonical_status": "SOURCE_UNAVAILABLE", "source_type": "Patent database", "source": "EPO OPS", "detail": str(e)}]

    def _search_retail_products(self, query):
        """
        Retail/brand product presence needs a paid web-search API (there is
        no free, structured, ToS-compliant source for 'which brands sell
        X'). Set SEARCH_API_KEY (+ optionally SEARCH_API_PROVIDER) to
        activate once you've picked a provider (Bing Web Search API,
        SerpAPI, etc.) — this function is the single place to wire it in.
        """
        if not self.use_live_search:
            return [{"status": "Skipped", "canonical_status": "SEARCH_NOT_PERFORMED", "detail": "Live search disabled."}]

        api_key = os.environ.get("SEARCH_API_KEY")
        if not api_key:
            return [{
                "status": "Not configured",
                "canonical_status": "SOURCE_UNAVAILABLE",
                "source_type": "Search engine proxy",
                "detail": "Set SEARCH_API_KEY to a paid web-search provider "
                          "(e.g. Bing Web Search API, SerpAPI) to enable "
                          "retail/brand product scanning. No free source "
                          "exists for this data.",
            }]
        return [{
            "status": "Not implemented",
            "canonical_status": "CONNECTOR_NOT_IMPLEMENTED",
            "source_type": "Search engine proxy",
            "detail": "SEARCH_API_KEY is set, but no provider call is wired "
                      "in yet. Implement the request for your chosen "
                      "provider inside _search_retail_products().",
        }]

    def market_landscape(self, plant):
        """Single-plant market snapshot with independent domains.

        Regulatory data stays under ``regulatory``. EPO patent hits are also
        projected into the canonical Phase-8 MarketEvidence shape so they can
        be traced without being mistaken for efficacy or approval evidence.
        Retail remains an explicit unavailable/not-implemented state until a
        real provider is wired.
        """
        patents = self._search_patents(plant)
        retail = self._search_retail_products(plant)
        market_evidence = []
        if patents and patents[0].get("canonical_status") == "COMPLETED":
            meta = patents[0]
            for hit in meta.get("patent_hits", []):
                market_evidence.append({
                    "source": meta.get("source", "EPO OPS"),
                    "source_type": "Patent database",
                    "query": meta.get("query", plant),
                    "country_market": hit.get("Jurisdiction") or "",
                    "product_name": "",
                    "brand": hit.get("Applicant") or "",
                    "plant_ingredient": plant,
                    "preparation": "",
                    "dosage_form": "",
                    "price": None,
                    "currency": "",
                    "availability": "",
                    "review_count": None,
                    "rating": None,
                    "seller_retailer": "",
                    "retrieval_timestamp": meta.get("retrieval_timestamp"),
                    "source_url_or_id": hit.get("Source_URL_or_ID") or hit.get("Patent_ID", ""),
                    "freshness": "FRESH",
                    "confidence": 0.9,
                    "reliability": 0.9,
                    "source_record_id": hit.get("Patent_ID", ""),
                    "evidence_kind": "patent",
                    "metadata": hit,
                })
        return {
            "plant": plant,
            "region": get_region(plant),
            "regulatory": self._eu_regulatory_status(plant),
            "patents": patents,
            "retail_products": retail,
            "market_evidence": market_evidence,
        }

    def market_landscape_df(self, plants):
        """Market landscape table: one row per plant."""
        rows = []
        for plant in plants:
            snap = self.market_landscape(plant)
            reg = snap["regulatory"]
            patents = snap["patents"]
            retail = snap["retail_products"]
            us_uk = get_us_uk_status(plant) or {}
            rows.append({
                "Plant": snap["plant"],
                "Region_of_Origin": snap["region"],
                "EMA_HMPC_Status": reg["EMA_HMPC_Status"],
                "EMA_HMPC_Detail": reg.get("EMA_HMPC_Detail", reg["EMA_HMPC_Status"]),
                "EMA_HMPC_Match_Category": reg.get("EMA_HMPC_Match_Category", "unknown"),
                "EMA_Source": reg.get("EMA_Source", reg.get("Source", "")),
                "WHO_Status": reg["WHO_Status"],
                "WHO_Source": reg.get("WHO_Source", ""),
                "ESCOP_Status": reg["ESCOP_Status"],
                "ESCOP_Source": reg.get("ESCOP_Source", ""),
                "Regulatory_Source": reg["Source"],
                "US_Status": us_uk.get(
                    "us_status", "Not yet catalogued for this plant"
                ),
                "UK_Status": us_uk.get(
                    "uk_status", "Not yet catalogued for this plant"
                ),
                "Patent_Search_Status": patents[0].get("status", "Unknown"),
                "Patent_Search_Canonical_Status": patents[0].get("canonical_status", "UNKNOWN"),
                "Patent_Hit_Count": len(patents[0].get("patent_hits", [])),
                "Patent_Detail": patents[0].get("detail", patents[0].get("raw_response", "")),
                "Retail_Products_Status": retail[0].get("status", "Unknown"),
                "Retail_Products_Canonical_Status": retail[0].get("canonical_status", "UNKNOWN"),
                "Retail_Products_Detail": retail[0].get("detail", ""),
            })
        return pd.DataFrame(rows)

    def enrich_candidates_with_market_landscape(self, result_df, max_plants=30):
        """OPT-IN post-processing: merges market_landscape_df()'s
        regulatory/patent/retail snapshot into a COPY of result_df, one
        lookup per UNIQUE Alternative_Plant (not once per row — a
        result can have many rows sharing the same alternative plant
        across different reference comparisons, and market_landscape()
        is the same cost regardless of how many rows ask about that
        plant).

        NOT called by run() itself. market_landscape() can trigger a
        real network call (patent search, when EPO_OPS_KEY/SECRET are
        configured) — baking that into every default run without
        review is exactly the unreviewed cost/latency change earlier
        passes (Gap 2's _market_status() work) deliberately avoided.
        This stays an explicit, separate call the caller opts into
        (see step_rd_candidates.py's "Enrich with market/patent
        landscape" button) once they've decided that cost is worth it.

        max_plants caps how many unique plants get looked up in one
        call (default 30) — a large result set could otherwise trigger
        dozens of sequential network calls from a single button click;
        the returned DataFrame's Market_Landscape_Checked column shows
        exactly which plants were actually included, so a truncated
        enrichment is visible, not silent.

        HONESTY ABOUT WHAT'S REAL VS STUB:
        - Regulatory (EMA/WHO/ESCOP) status is real — same
          _eu_regulatory_status() logic already used elsewhere.
        - Patent_Search_Status is real IF EPO_OPS_KEY/SECRET are set
          ("OK" or "Error"), otherwise honestly "Not configured".
        - Retail_Products_Status is currently always "Not implemented"
          — _search_retail_products() is a documented stub. This
          function does not hide that; it surfaces the real status
          string as-is rather than omitting the column.
        """
        if result_df is None or result_df.empty or "Alternative_Plant" not in result_df.columns:
            return result_df.copy() if result_df is not None else result_df

        unique_plants = [
            p for p in result_df["Alternative_Plant"].dropna().unique().tolist() if p
        ]
        checked_plants = unique_plants[:max_plants]
        truncated = len(unique_plants) > max_plants

        landscape_df = self.market_landscape_df(checked_plants)
        landscape_df = landscape_df.rename(columns={
            "Plant": "Alternative_Plant",
            "EMA_HMPC_Status": "Market_Landscape_EMA_HMPC_Status",
            "WHO_Status": "Market_Landscape_WHO_Status",
            "ESCOP_Status": "Market_Landscape_ESCOP_Status",
            "Regulatory_Source": "Market_Landscape_Regulatory_Source",
            "US_Status": "Market_Landscape_US_Status",
            "UK_Status": "Market_Landscape_UK_Status",
            "Patent_Search_Status": "Market_Landscape_Patent_Search_Status",
            "Patent_Search_Canonical_Status": "Market_Landscape_Patent_Search_Canonical_Status",
            "Patent_Hit_Count": "Market_Landscape_Patent_Hit_Count",
            "Patent_Detail": "Market_Landscape_Patent_Detail",
            "Retail_Products_Status": "Market_Landscape_Retail_Search_Status",
            "Retail_Products_Canonical_Status": "Market_Landscape_Retail_Search_Canonical_Status",
            "Retail_Products_Detail": "Market_Landscape_Retail_Detail",
        })

        enriched = result_df.merge(landscape_df, on="Alternative_Plant", how="left")
        enriched["Market_Landscape_Checked"] = enriched["Alternative_Plant"].isin(checked_plants)

        if truncated:
            enriched["Market_Landscape_Note"] = (
                f"Only the first {max_plants} of {len(unique_plants)} unique "
                f"alternative plants were checked this run — increase max_plants "
                f"or re-run to cover the rest."
            )
        else:
            enriched["Market_Landscape_Note"] = ""

        return enriched


def load_default_evidence():
    try:
        return pd.DataFrame(load_evidence_database())
    except Exception:
        return pd.DataFrame()
