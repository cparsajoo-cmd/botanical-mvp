"""PROBLEM 5 regression tests -- cross-formulation/route evidence
misattribution.

Verified, outcome-specific HUMAN evidence for a botanical must not
automatically count as DIRECT evidence for the user's REQUESTED
preparation/dosage form when the underlying study used a different,
incompatible preparation or route. This file tests the sequential gate
added on top of Problem 2's evidence-sufficiency gate:

    candidate attribution -> outcome specificity -> human evidence
        -> formulation/route compatibility -> actionable product-form decision

All botanicals and indications used below are fictional. Indication
strings are kept fully lowercase throughout (including inside rationale
text) because the underlying phrase matcher
(scientific_phrase_matcher.phrase_present) is case-sensitive for a raw,
non-curated indication string -- this is a fixture-construction detail
of these tests, not part of what Problem 5 changes.
"""
from __future__ import annotations

import pandas as pd
import pytest

from candidate_shortlisting import (
    build_plant_candidate_shortlist,
    _dimension_status_formulation_compatible,
    _row_formulation_compatible,
)
from step_rd_candidates import (
    _reconcile_final_decision_status,
    _pre_gate_final_decision_status,
    _verified_outcome_specific_human_evidence_count,
    _verified_formulation_compatible_outcome_specific_human_evidence_count,
    _evidence_sufficiency_gate_triggered,
    _formulation_compatibility_gate_triggered,
    _merge_and_sync_final_decision_status,
)
from evidence_adjudication_engine import build_final_rationale


NON_ACTIONABLE_STATUSES = {
    "EXPERT REVIEW REQUIRED",
    "NO GO SAFETY",
    "NO GO REGULATORY",
    "INSUFFICIENT EVIDENCE",
}


# ---------------------------------------------------------------------
# Full-pipeline fixtures (fictional botanicals/indications only)
# ---------------------------------------------------------------------

def _row(
    plant="Fictional botanical Alpha",
    source="PMID:900001",
    indication="fictional sleep-support indication",
    preparation="",
    route="",
    prep_category="",
    result_direction="positive",
    candidate_attribution_verified=True,
    extra_scientific_rationale_suffix="",
):
    rationale = (
        f"human clinical trial reported improved outcome for {indication}"
        f"{extra_scientific_rationale_suffix}"
    )
    return {
        "Reference_Plant": "Reference plant",
        "Alternative_Plant": plant,
        "Shared_or_Similar_Compound": "fictionoside",
        "Novelty_Status": "Rare / differentiating",
        "Target_or_Mechanism": "FICR1",
        "Target_Provenance": "Supported by source record",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human clinical evidence",
        "Candidate_Evidence_Strength_Tier": "Direct evidence",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": source,
        "Extraction_Method": preparation,
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "Well tolerated; no serious adverse events",
        "Interaction_Flags": "No explicit flag found",
        "Regulatory_Barriers": "None identified",
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "Investigate",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "Result_Direction": result_direction,
        "R&D_Opportunity_Score": 70,
        "Candidate_Attribution_Verified": candidate_attribution_verified,
        "Indication_Match_Type": "exact_indication",
        "Indication_Match_Terms": indication,
        "Scientific_Rationale": rationale,
        "Clinical_Rationale": rationale,
        "Evidence_Preparation": preparation,
        "Evidence_Route": route,
        "Evidence_Preparation_Category": prep_category,
    }


def _target_context(indication, dosage_form, prep_category="", route="oral"):
    ctx = {"Target_Indication": indication, "Target_Preparation": dosage_form, "Target_Route": route}
    if prep_category:
        ctx["Target_Preparation_Category"] = prep_category
    return ctx


def _summary_row(df, plant, indication, dosage_form, target_context):
    summary, _ = build_plant_candidate_shortlist(
        df, indication=indication, dosage_form=dosage_form, target_context=target_context
    )
    return summary.set_index("Alternative_Plant").loc[plant]


# ---------------------------------------------------------------------
# Core predicate unit tests -- _dimension_status_formulation_compatible
# ---------------------------------------------------------------------

def test_dimension_status_match_prep_and_route_is_compatible():
    assert _dimension_status_formulation_compatible(
        {"preparation": "MATCH", "route": "MATCH"}
    ) is True


def test_dimension_status_partial_preparation_is_not_compatible():
    assert _dimension_status_formulation_compatible(
        {"preparation": "PARTIAL", "route": "MATCH"}
    ) is False


def test_dimension_status_mismatch_preparation_is_not_compatible():
    assert _dimension_status_formulation_compatible(
        {"preparation": "MISMATCH", "route": "MATCH"}
    ) is False


def test_dimension_status_unknown_preparation_never_silently_becomes_match():
    assert _dimension_status_formulation_compatible(
        {"preparation": "UNKNOWN", "route": "MATCH"}
    ) is False


def test_dimension_status_prep_match_but_route_mismatch_fails_overall():
    # Case 18 -- a preparation match must not hide a route mismatch.
    assert _dimension_status_formulation_compatible(
        {"preparation": "MATCH", "route": "MISMATCH"}
    ) is False


def test_dimension_status_prep_match_route_unknown_fails_closed():
    assert _dimension_status_formulation_compatible(
        {"preparation": "MATCH", "route": "UNKNOWN"}
    ) is False


def test_dimension_status_route_not_applicable_or_unspecified_does_not_fail():
    # The target itself never asked about route -- nothing to mismatch.
    assert _dimension_status_formulation_compatible(
        {"preparation": "MATCH", "route": "NOT_APPLICABLE"}
    ) is True
    assert _dimension_status_formulation_compatible(
        {"preparation": "MATCH", "route": "TARGET_UNSPECIFIED"}
    ) is True


def test_dimension_status_missing_mapping_fails_closed():
    assert _dimension_status_formulation_compatible(None) is False
    assert _dimension_status_formulation_compatible({}) is False


def test_row_formulation_compatible_noop_when_no_dosage_form_requested():
    assert _row_formulation_compatible({}, "") is True


# ---------------------------------------------------------------------
# Required regression cases 1-6, 18 -- direct preparation/route
# compatibility via the real pipeline.
# ---------------------------------------------------------------------

def test_case_1_requested_infusion_plus_human_infusion_study_is_direct_compatible():
    indication = "fictional calm-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="infusion", route="oral", prep_category="aqueous",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 1


def test_case_2_requested_infusion_plus_capsule_extract_study_not_direct():
    indication = "fictional clarity-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="standardized extract capsule",
        route="oral", prep_category="solid_oral",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


def test_case_3_requested_infusion_plus_essential_oil_inhalation_not_direct():
    indication = "fictional breathe-ease indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="essential oil", route="inhalation",
        prep_category="essential_oil",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


def test_case_4_requested_oral_capsule_plus_oral_capsule_study_compatible():
    indication = "fictional appetite-support indication"
    tc = _target_context(indication, "Capsule", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="capsule", route="oral",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Capsule", tc)
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 1


def test_case_5_requested_topical_plus_oral_study_incompatible():
    indication = "fictional skin-comfort indication"
    tc = _target_context(indication, "Topical cream", prep_category="topical", route="topical")
    df = pd.DataFrame([_row(
        indication=indication, preparation="capsule", route="oral", prep_category="solid_oral",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Topical cream", tc)
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


def test_case_6_requested_oral_plus_inhalation_study_incompatible():
    indication = "fictional airway-support indication"
    tc = _target_context(indication, "Extract", prep_category="extract", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="extract", route="inhalation", prep_category="extract",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Extract", tc)
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


def test_case_18_preparation_match_but_route_mismatch_fails_overall():
    indication = "fictional focus-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="infusion", route="topical", prep_category="aqueous",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    assert row["Dimension_Status"]["preparation"] == "MATCH"
    assert row["Dimension_Status"]["route"] == "MISMATCH"
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


# ---------------------------------------------------------------------
# Required regression case 7 -- UNKNOWN preparation must never silently
# count as a match.
# ---------------------------------------------------------------------

def test_case_7_unknown_preparation_does_not_count_as_direct():
    indication = "fictional mood-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="", route="", prep_category="",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    assert row["Dimension_Status"]["preparation"] == "UNKNOWN"
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


# ---------------------------------------------------------------------
# Required regression case 8 -- PARTIAL compatibility must not
# independently establish direct evidence.
# ---------------------------------------------------------------------

def test_case_8_partial_preparation_does_not_independently_establish_direct():
    indication = "fictional digestive-comfort indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="decoction", route="oral", prep_category="aqueous",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    assert row["Dimension_Status"]["preparation"] == "PARTIAL"
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


# ---------------------------------------------------------------------
# Required regression case 9 -- multiple verified human studies, all
# mismatched, cannot yield an actionable positive recommendation.
# ---------------------------------------------------------------------

def test_case_9_multiple_mismatched_studies_block_actionable_recommendation():
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 3,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
    }
    pre_gate = _pre_gate_final_decision_status(row)
    assert pre_gate in {"GO", "GO WITH CAUTION"}, "fixture must reach an actionable pre-gate status"
    status = _reconcile_final_decision_status(row)
    assert status not in {"GO", "GO WITH CAUTION"}
    assert status in NON_ACTIONABLE_STATUSES
    assert status == "EXPERT REVIEW REQUIRED"


# ---------------------------------------------------------------------
# Required regression case 10 -- one compatible + several mismatched
# studies: compatible evidence survives; mismatched studies do not
# inflate the direct formulation count.
# ---------------------------------------------------------------------

def test_case_10_one_compatible_plus_several_mismatched_studies():
    indication = "fictional joint-comfort indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([
        _row(source="PMID:1", indication=indication, preparation="infusion", route="oral", prep_category="aqueous"),
        _row(source="PMID:2", indication=indication, preparation="standardized extract capsule", route="oral", prep_category="solid_oral"),
        _row(source="PMID:3", indication=indication, preparation="tincture", route="oral", prep_category="alcoholic"),
    ])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 3
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 1


# ---------------------------------------------------------------------
# Required regression case 11 -- zero compatible human studies + strong
# mechanistic evidence: still no actionable formulation-specific
# positive recommendation.
# ---------------------------------------------------------------------

def test_case_11_strong_mechanistic_evidence_does_not_bypass_the_gate():
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
        "Mechanistic_Evidence_Count": 30,
    }
    status = _reconcile_final_decision_status(row)
    assert status == "EXPERT REVIEW REQUIRED"


# ---------------------------------------------------------------------
# Required regression case 12 -- zero compatible human studies + AI
# Human_Evidence_Strength=STRONG: no bypass.
# ---------------------------------------------------------------------

def test_case_12_ai_strong_human_evidence_strength_does_not_bypass_the_gate():
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
        "Human_Evidence_Strength": "STRONG",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "HIGH",
        "Direct_Indication_Evidence_Count": 3,
        "Evidence_Adjudication_Evidence_Count": 3,
        "Direct_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
        "Direct_Human_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
    }
    status = _reconcile_final_decision_status(row)
    assert status == "EXPERT REVIEW REQUIRED"


# ---------------------------------------------------------------------
# Required regression case 13 -- zero compatible studies + AI positive
# adjudication: no bypass.
# ---------------------------------------------------------------------

def test_case_13_positive_ai_adjudication_does_not_bypass_the_gate():
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "MODERATE",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "HIGH",
        "Direct_Indication_Evidence_Count": 3,
        "Evidence_Adjudication_Evidence_Count": 3,
        "Direct_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
        "Direct_Human_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
    }
    status = _reconcile_final_decision_status(row)
    assert status == "EXPERT REVIEW REQUIRED"


# ---------------------------------------------------------------------
# Required regression case 14 -- a mismatched human study remains
# visible as indirect/transferability-limited evidence; it is never
# discarded from Outcome_Specific_Human_Evidence_Count.
# ---------------------------------------------------------------------

def test_case_14_mismatched_study_remains_visible_not_discarded():
    indication = "fictional recovery-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    df = pd.DataFrame([_row(
        indication=indication, preparation="tincture", route="oral", prep_category="alcoholic",
    )])
    row = _summary_row(df, "Fictional botanical Alpha", indication, "Infusion", tc)
    # The mismatched study is NOT discarded -- it still counts toward the
    # botanical-level verified human evidence count.
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0


# ---------------------------------------------------------------------
# Required regression case 15 -- a genuine safety NO-GO with a
# preparation mismatch present must keep the safety NO-GO authoritative
# (never "improved" or replaced by the formulation-compatibility gate).
# ---------------------------------------------------------------------

def test_case_15_genuine_safety_no_go_remains_authoritative_despite_mismatch():
    row = {
        "Decision_Class_AH": "H — No-go / safety concern",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "incompatible",
        "Outcome_Specific_Human_Evidence_Count": 2,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
    }
    assert _pre_gate_final_decision_status(row) == "NO GO SAFETY"
    assert _reconcile_final_decision_status(row) == "NO GO SAFETY"

    # Also verify the pass-through-from-upstream NO GO SAFETY path.
    upstream_row = {
        "Final_Decision_Status": "NO GO SAFETY",
        "Outcome_Specific_Human_Evidence_Count": 2,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
    }
    assert _reconcile_final_decision_status(upstream_row) == "NO GO SAFETY"


# ---------------------------------------------------------------------
# Required regression case 16 -- the Problem-2 zero-human-evidence case
# still behaves exactly as Problem 2 requires (Problem 5's gate is
# sequential and never fires when Problem 2's gate already has).
# ---------------------------------------------------------------------

def test_case_16_problem_2_zero_human_evidence_case_unaffected():
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "STRONG",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "HIGH",
        "Direct_Indication_Evidence_Count": 3,
        "Evidence_Adjudication_Evidence_Count": 3,
        "Direct_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
        "Direct_Human_Outcome_Evidence_IDs": ["e1", "e2", "e3"],
    }
    assert _evidence_sufficiency_gate_triggered(_pre_gate_final_decision_status(row), row) is True
    # Problem 5's gate is a no-op here -- Problem 2's own gate already owns
    # (and triggers on) this case.
    assert _formulation_compatibility_gate_triggered(_pre_gate_final_decision_status(row), row) is False
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


# ---------------------------------------------------------------------
# Required regression case 17 -- missing compatibility metadata fails
# closed for a direct formulation claim.
# ---------------------------------------------------------------------

def test_case_17_missing_compatibility_metadata_fails_closed():
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 1,
        # Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count
        # is entirely absent from this row -- missing metadata.
    }
    assert _verified_formulation_compatible_outcome_specific_human_evidence_count(row) == 0
    status = _reconcile_final_decision_status(row)
    assert status == "EXPERT REVIEW REQUIRED"

    # Also exercise the same fail-closed behavior for blank/NaN/garbage
    # values, mirroring Problem 2's own fail-closed parsing contract.
    for bad_value in ("", float("nan"), "not-a-number", -1):
        bad_row = dict(row, Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count=bad_value)
        assert _verified_formulation_compatible_outcome_specific_human_evidence_count(bad_row) == 0


# ---------------------------------------------------------------------
# Adversarial tests (15+) -- attempts to bypass formulation compatibility
# using combinations of strong signals, alternate schemas, and missing
# metadata. Expected values decided before running: every one of these
# must remain non-actionable (EXPERT REVIEW REQUIRED), because verified
# outcome-specific human evidence exists but none of it is formulation-
# compatible.
# ---------------------------------------------------------------------

def _bypass_attempt_row(**overrides):
    row = {
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
    }
    row.update(overrides)
    return row


def test_adversarial_1_high_ai_direct_outcome_count_does_not_bypass():
    row = _bypass_attempt_row(
        Evidence_Adjudication_Status="AI_ADJUDICATION_OK",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
        Human_Evidence_Strength="STRONG",
        Evidence_Conflict_Level="NONE",
        Scientific_Evidence_Confidence="HIGH",
        Direct_Indication_Evidence_Count=12,
        Evidence_Adjudication_Evidence_Count=12,
        Direct_Outcome_Evidence_IDs=[f"e{i}" for i in range(12)],
        Direct_Human_Outcome_Evidence_IDs=[f"e{i}" for i in range(12)],
    )
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_2_high_mechanistic_evidence_count_does_not_bypass():
    row = _bypass_attempt_row(Mechanistic_Evidence_Count=50)
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_3_positive_adjudication_plus_direct_human_mode_does_not_bypass():
    row = _bypass_attempt_row(
        Evidence_Adjudication_Status="AI_ADJUDICATION_OK",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
        Human_Evidence_Strength="MODERATE",
        Evidence_Conflict_Level="NONE",
        Scientific_Evidence_Confidence="MODERATE",
        Direct_Indication_Evidence_Count=3,
        Evidence_Adjudication_Evidence_Count=3,
        Direct_Outcome_Evidence_IDs=["e1", "e2", "e3"],
        Direct_Human_Outcome_Evidence_IDs=["e1", "e2", "e3"],
    )
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_4_same_route_different_preparation_does_not_bypass():
    # Same underlying (oral) route, but the requested vs. studied
    # preparation differ -- preparation MISMATCH must independently block,
    # even with route MATCH.
    assert _dimension_status_formulation_compatible(
        {"preparation": "MISMATCH", "route": "MATCH"}
    ) is False
    row = _bypass_attempt_row()
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_5_same_preparation_label_different_route_does_not_bypass():
    # A "compatible_but_indirect"-style legacy label on Preparation_
    # Applicability_Class must not stand in for the strict per-record
    # formulation-compatible count.
    row = _bypass_attempt_row(Preparation_Applicability_Class="compatible_but_indirect")
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_6_missing_preparation_metadata_does_not_bypass():
    row = _bypass_attempt_row()
    del row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_7_missing_route_metadata_does_not_bypass():
    # A record with preparation MATCH but no route signal at all --
    # candidate_shortlisting._row_formulation_compatible() already fails
    # this closed (tested directly); confirm the decision-layer gate
    # agrees when it is fed that same zero count.
    assert _dimension_status_formulation_compatible({"preparation": "MATCH"}) is False
    row = _bypass_attempt_row()
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_8_partial_match_alone_does_not_bypass():
    assert _dimension_status_formulation_compatible(
        {"preparation": "PARTIAL", "route": "MATCH"}
    ) is False
    row = _bypass_attempt_row()
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_9_conflicting_applicability_fields_does_not_bypass():
    # Preparation_Applicability_Class says direct_match (a coarser,
    # primary-tier-wide field) while the strict compatible count is
    # genuinely zero -- the strict count must win, not the coarser label.
    row = _bypass_attempt_row(Preparation_Applicability_Class="direct_match")
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_10_legacy_dosage_compatible_field_alone_does_not_bypass():
    # A legacy plant-level "Dosage_Form_Compatibility": "Compatible" flag
    # (the coarser, any-row-compatible-wins aggregate) sitting alongside a
    # genuinely zero strict compatible count must not resurrect Go.
    row = _bypass_attempt_row(Dosage_Form_Compatibility="Compatible")
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_11_mechanistic_support_alone_does_not_bypass():
    row = _bypass_attempt_row(
        Mechanistic_Evidence_Count=8,
        Supported_Targets_or_Mechanisms="FICR9; FICR10",
    )
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_12_go_with_caution_pre_gate_also_blocked():
    row = _bypass_attempt_row(Decision_Class_AH="C — Alternative-source R&D candidate")
    pre_gate = _pre_gate_final_decision_status(row)
    assert pre_gate == "GO WITH CAUTION"
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_13_high_evidence_adjudication_count_alone_does_not_bypass():
    row = _bypass_attempt_row(Evidence_Adjudication_Evidence_Count=40)
    assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_14_fractional_or_negative_compatible_count_fails_closed():
    for bad_value in (0.5, -3, "1.5"):
        row = _bypass_attempt_row(
            Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count=bad_value
        )
        assert _verified_formulation_compatible_outcome_specific_human_evidence_count(row) == 0
        assert _reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"


def test_adversarial_15_never_escalated_to_no_go_safety():
    # The formulation-compatibility gate is an evidence-sufficiency-style
    # gate, not a safety gate -- it must land on EXPERT REVIEW REQUIRED,
    # never NO GO SAFETY/REGULATORY, and must not be confused for a
    # statement that the botanical is unsafe or ineffective.
    row = _bypass_attempt_row()
    status = _reconcile_final_decision_status(row)
    assert status == "EXPERT REVIEW REQUIRED"
    assert status not in {"NO GO SAFETY", "NO GO REGULATORY"}


# ---------------------------------------------------------------------
# Rationale policy -- three states must not collapse into the same
# sentence: (A) no verified human evidence, (B) verified human evidence
# exists but is formulation-incompatible, (C) verified compatible human
# evidence exists.
# ---------------------------------------------------------------------

def test_rationale_case_a_no_verified_human_evidence():
    row = pd.Series({
        "Evidence_Sufficiency_Gate_Triggered": True,
        "Formulation_Compatibility_Gate_Triggered": False,
        "Outcome_Specific_Human_Evidence_Count": 0,
    })
    rationale = build_final_rationale(row)
    assert "no verified outcome-specific human evidence" in rationale.lower()


def test_rationale_case_b_verified_but_formulation_mismatched():
    row = pd.Series({
        "Evidence_Sufficiency_Gate_Triggered": False,
        "Formulation_Compatibility_Gate_Triggered": True,
        "Outcome_Specific_Human_Evidence_Count": 2,
    })
    rationale = build_final_rationale(row)
    lower = rationale.lower()
    # Must not claim human evidence supports the requested formulation...
    assert "supports the requested" not in lower
    # ...and must not claim no human evidence exists at all.
    assert "no verified outcome-specific human evidence" not in lower
    assert "verified human evidence" in lower
    assert "does not directly match" in lower or "does not match" in lower


def test_rationale_case_c_verified_compatible_human_evidence():
    row = pd.Series({
        "Evidence_Sufficiency_Gate_Triggered": False,
        "Formulation_Compatibility_Gate_Triggered": False,
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Final_Canonical_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Final_Canonical_Evidence_Direction_Source": "VERIFIED",
    })
    rationale = build_final_rationale(row)
    lower = rationale.lower()
    assert "no verified outcome-specific human evidence" not in lower
    assert "does not directly match" not in lower
    assert "one verified outcome-specific human study" in lower


def test_rationale_three_states_are_textually_distinct():
    a = build_final_rationale(pd.Series({
        "Evidence_Sufficiency_Gate_Triggered": True,
        "Formulation_Compatibility_Gate_Triggered": False,
        "Outcome_Specific_Human_Evidence_Count": 0,
    }))
    b = build_final_rationale(pd.Series({
        "Evidence_Sufficiency_Gate_Triggered": False,
        "Formulation_Compatibility_Gate_Triggered": True,
        "Outcome_Specific_Human_Evidence_Count": 1,
    }))
    c = build_final_rationale(pd.Series({
        "Evidence_Sufficiency_Gate_Triggered": False,
        "Formulation_Compatibility_Gate_Triggered": False,
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Final_Canonical_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Final_Canonical_Evidence_Direction_Source": "VERIFIED",
    }))
    assert len({a, b, c}) == 3


# ---------------------------------------------------------------------
# End-to-end tests (A/B/C), chaining real evidence records through
# build_plant_candidate_shortlist -> _merge_and_sync_final_decision_status
# -> build_final_rationale.
# ---------------------------------------------------------------------

def test_end_to_end_a_direct_match_survives_through_to_rationale():
    indication = "fictional endurance-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    raw_df = pd.DataFrame([_row(
        plant="Fictional botanical Endtoend A",
        indication=indication, preparation="infusion", route="oral", prep_category="aqueous",
    )])
    plant_summary, _ = build_plant_candidate_shortlist(
        raw_df, indication=indication, dosage_form="Infusion", target_context=tc
    )
    report_ready_df = _merge_and_sync_final_decision_status(raw_df, plant_summary)
    row = report_ready_df.set_index("Alternative_Plant").loc["Fictional botanical Endtoend A"]

    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 1
    assert bool(row["Evidence_Sufficiency_Gate_Triggered"]) is False
    assert bool(row["Formulation_Compatibility_Gate_Triggered"]) is False

    rationale = build_final_rationale(row)
    assert "does not directly match" not in rationale.lower()


def test_end_to_end_b_clear_mismatch_blocks_actionable_recommendation():
    indication = "fictional vitality-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    raw_df = pd.DataFrame([_row(
        plant="Fictional botanical Endtoend B",
        indication=indication, preparation="standardized extract capsule",
        route="oral", prep_category="solid_oral",
    )])
    plant_summary, _ = build_plant_candidate_shortlist(
        raw_df, indication=indication, dosage_form="Infusion", target_context=tc
    )
    row = plant_summary.set_index("Alternative_Plant").loc["Fictional botanical Endtoend B"]

    # Botanical-level evidence remains: verified human evidence exists...
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 1
    # ...but formulation-specific direct count/support is zero.
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 0

    # Feed a controlled, otherwise-actionable report-ready row (isolating
    # the decision-authority layer from this candidate's own, unrelated
    # pre-gate/AI-adjudication scoring path) to confirm the requested
    # formulation is blocked from an unqualified actionable recommendation.
    decision_row = {
        "Alternative_Plant": "Fictional botanical Endtoend B",
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": int(row["Outcome_Specific_Human_Evidence_Count"]),
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": int(
            row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]
        ),
    }
    status = _reconcile_final_decision_status(decision_row)
    assert status not in {"GO", "GO WITH CAUTION"}
    assert status == "EXPERT REVIEW REQUIRED"

    rationale = build_final_rationale(pd.Series({
        "Evidence_Sufficiency_Gate_Triggered": False,
        "Formulation_Compatibility_Gate_Triggered": True,
        "Outcome_Specific_Human_Evidence_Count": decision_row["Outcome_Specific_Human_Evidence_Count"],
    }))
    lower = rationale.lower()
    assert "no verified outcome-specific human evidence" not in lower
    assert "supports the requested" not in lower
    assert "verified human evidence" in lower


def test_end_to_end_c_mixed_evidence_only_compatible_study_counts():
    indication = "fictional resilience-support indication"
    tc = _target_context(indication, "Infusion", prep_category="aqueous", route="oral")
    raw_df = pd.DataFrame([
        _row(plant="Fictional botanical Endtoend C", source="PMID:c1",
             indication=indication, preparation="infusion", route="oral", prep_category="aqueous"),
        _row(plant="Fictional botanical Endtoend C", source="PMID:c2",
             indication=indication, preparation="essential oil", route="inhalation", prep_category="essential_oil"),
        _row(plant="Fictional botanical Endtoend C", source="PMID:c3",
             indication=indication, preparation="tincture", route="oral", prep_category="alcoholic"),
    ])
    plant_summary, _ = build_plant_candidate_shortlist(
        raw_df, indication=indication, dosage_form="Infusion", target_context=tc
    )
    report_ready_df = _merge_and_sync_final_decision_status(raw_df, plant_summary)
    row = report_ready_df.set_index("Alternative_Plant").loc["Fictional botanical Endtoend C"]

    # Direct formulation evidence reflects ONLY the compatible study.
    assert int(row["Outcome_Specific_Human_Evidence_Count"]) == 3
    assert int(row["Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count"]) == 1
    # The compatible-evidence count being >= 1 means Problem 5's gate does
    # not itself block this candidate (necessary, not sufficient).
    assert bool(row["Formulation_Compatibility_Gate_Triggered"]) is False


# ---------------------------------------------------------------------
# Independent post-Claude verification cases (added during final audit)
# ---------------------------------------------------------------------

def test_independent_hard_plant_part_mismatch_blocks_direct_formulation_support():
    assert _dimension_status_formulation_compatible({
        "preparation": "MATCH", "route": "MATCH", "plant_part": "MISMATCH"
    }) is False


def test_independent_legacy_fallback_explicit_route_mismatch_fails_closed():
    row = {
        "Evidence_Preparation": "infusion",
        "Evidence_Route": "inhalation",
        "Extraction_Method": "infusion",
    }
    assert _row_formulation_compatible(
        row, "Infusion", target_route="oral"
    ) is False


def test_independent_rationale_reports_mismatch_even_if_other_gate_already_nonactionable():
    rationale = build_final_rationale({
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 0,
        "Formulation_Compatibility_Gate_Triggered": False,
        "Final_Decision_Status": "EXPERT REVIEW REQUIRED",
    })
    lower = rationale.lower()
    assert "verified human evidence was identified" in lower
    assert "does not directly match" in lower
    assert "no verified outcome-specific human evidence" not in lower


def test_independent_rationale_quantifies_mixed_transferability_without_inflating_direct_support():
    rationale = build_final_rationale({
        "Outcome_Specific_Human_Evidence_Count": 3,
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 1,
        "Final_Canonical_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Final_Canonical_Evidence_Direction_Source": "VERIFIED",
    })
    lower = rationale.lower()
    assert "1 of 3 verified outcome-specific human study" in lower
    assert "remaining verified human evidence is transferability-limited" in lower
