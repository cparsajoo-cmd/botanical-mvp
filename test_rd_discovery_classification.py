"""Regression tests for the additive R&D Discovery Lane layer.

Two levels are covered:

1. Pure unit tests directly against rd_discovery_classification.py's
   functions -- no DataFrame, no candidate_shortlisting.py involved.
2. Integration tests against build_plant_candidate_shortlist() itself,
   confirming (a) every existing Scientific_Triage_Status/Overall_Score
   behavior is unchanged (these mirror fixtures already exercised in
   test_candidate_shortlisting.py) and (b) the new RD_Discovery_Lane /
   Discovery_Potential_Score / Evidence_Maturity_Score columns carry the
   expected additive values on top.
"""
import pandas as pd

from candidate_shortlisting import (
    build_plant_candidate_shortlist,
    merge_authoritative_scores,
    build_rd_discovery_hypothesis_view,
)
from rd_discovery_classification import (
    classify_discovery_lane,
    discovery_potential_score,
    evidence_maturity_score,
    DISCOVERY_LANE_EVIDENCE_BACKED,
    DISCOVERY_LANE_HYPOTHESIS,
    DISCOVERY_LANE_REGULATORY_STOP,
    DISCOVERY_LANE_SAFETY_STOP,
    DISCOVERY_LANE_INSUFFICIENT,
    DISCOVERY_LANE_EVIDENCE_GAP,
)


# --------------------------------------------------------------------------
# Pure unit tests
# --------------------------------------------------------------------------

def test_shortlist_status_is_always_evidence_backed():
    lane = classify_discovery_lane(
        plant_status="Shortlist",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=False,
        indication_points=30.0,
        dosage_mismatch=False,
    )
    assert lane == DISCOVERY_LANE_EVIDENCE_BACKED


def test_exploratory_status_is_always_discovery_hypothesis():
    lane = classify_discovery_lane(
        plant_status="Exploratory",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=False,
        indication_points=5.0,
        dosage_mismatch=False,
    )
    assert lane == DISCOVERY_LANE_HYPOTHESIS


def test_excluded_hard_stop_with_regulatory_text_is_regulatory_prohibition():
    lane = classify_discovery_lane(
        plant_status="Excluded",
        plant_hard_stop=True,
        regulatory_prohibition_present=True,
        explicit_mechanistic_rationale=False,
        indication_points=10.0,
        dosage_mismatch=False,
    )
    assert lane == DISCOVERY_LANE_REGULATORY_STOP


def test_excluded_hard_stop_without_regulatory_text_is_safety_not_developable():
    lane = classify_discovery_lane(
        plant_status="Excluded",
        plant_hard_stop=True,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=False,
        indication_points=10.0,
        dosage_mismatch=False,
    )
    assert lane == DISCOVERY_LANE_SAFETY_STOP


def test_excluded_no_evidence_no_mechanism_is_insufficient_signal():
    lane = classify_discovery_lane(
        plant_status="Excluded",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=False,
        indication_points=0.0,
        dosage_mismatch=False,
    )
    assert lane == DISCOVERY_LANE_INSUFFICIENT


def test_excluded_dosage_mismatch_is_insufficient_signal_even_with_mechanism():
    # A preparation mismatch is a formulation problem, not a scientific
    # dead end -- but it is also not a validated R&D hypothesis yet, so it
    # stays out of the "Evidence-Backed" and "Discovery Hypothesis" lanes.
    lane = classify_discovery_lane(
        plant_status="Excluded",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=True,
        indication_points=25.0,
        dosage_mismatch=True,
    )
    assert lane == DISCOVERY_LANE_INSUFFICIENT


def test_excluded_with_explicit_mechanistic_rationale_becomes_discovery_hypothesis():
    # The core fix: a plant excluded purely for lacking direct evidence,
    # but WITH an explicit mechanistic rationale, must not disappear --
    # it belongs in the discovery lane, not "Insufficient Signal".
    lane = classify_discovery_lane(
        plant_status="Excluded",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=True,
        indication_points=0.0,
        dosage_mismatch=False,
    )
    assert lane == DISCOVERY_LANE_HYPOTHESIS


def test_discovery_potential_score_is_zero_with_no_mechanistic_signal():
    score = discovery_potential_score(
        mech_points=0.0, target_count=0,
        mechanistic_evidence_count=0, novelty_points=0.0,
    )
    assert score == 0.0


def test_discovery_potential_score_rewards_mechanism_without_clinical_evidence():
    # Strong mechanistic rationale, zero clinical evidence -- must score
    # HIGH here (this is the entire point of splitting the axis away
    # from evidence_maturity_score).
    score = discovery_potential_score(
        mech_points=10.0, target_count=3,
        mechanistic_evidence_count=4, novelty_points=5.0,
    )
    assert score > 60.0
    assert score <= 100.0


def test_discovery_potential_score_zeros_novelty_when_market_unassessed():
    # External review, second pass (2026-09-08): the neutral 2.5-point
    # "not assessed" prior from _novelty_market() must not read as
    # evidence of novelty.
    unassessed = discovery_potential_score(
        mech_points=0.0, target_count=0,
        mechanistic_evidence_count=0, novelty_points=2.5,
        novelty_tier="Commercial novelty not assessed",
    )
    assert unassessed == 0.0


def test_discovery_potential_score_still_rewards_real_novelty_signal():
    # A genuinely assessed, low-market-presence tier must still count.
    white_space = discovery_potential_score(
        mech_points=0.0, target_count=0,
        mechanistic_evidence_count=0, novelty_points=5.0,
        novelty_tier="Commercial white-space",
    )
    assert white_space == 15.0


def test_discovery_potential_score_backward_compatible_without_tier_arg():
    # A caller that never learned about novelty_tier (pre-existing unit
    # tests, older callers) keeps the original, unmodified behavior.
    score = discovery_potential_score(
        mech_points=0.0, target_count=0,
        mechanistic_evidence_count=0, novelty_points=2.5,
    )
    assert score == 7.5


def test_discovery_potential_score_is_bounded():
    score = discovery_potential_score(
        mech_points=999.0, target_count=999,
        mechanistic_evidence_count=999, novelty_points=999.0,
    )
    assert score == 100.0


def test_evidence_maturity_score_is_bounded():
    score = evidence_maturity_score(
        evq_points=999.0, direct_evidence_count=999,
        outcome_specific_human_evidence_count=999, indication_points=999.0,
    )
    assert score == 100.0


def test_evidence_maturity_score_zero_when_no_evidence():
    score = evidence_maturity_score(
        evq_points=0.0, direct_evidence_count=0,
        outcome_specific_human_evidence_count=0, indication_points=0.0,
    )
    assert score == 0.0


# --------------------------------------------------------------------------
# Integration tests against build_plant_candidate_shortlist()
# --------------------------------------------------------------------------

def _row(**overrides):
    row = {
        "Reference_Plant": "Reference plant",
        "Alternative_Plant": "Candidate plant",
        "Shared_or_Similar_Compound": "specific alkaloid",
        "Novelty_Status": "Rare / differentiating",
        "Target_or_Mechanism": "AMPK",
        "Target_Provenance": "Supported by source record",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human clinical evidence",
        "Candidate_Evidence_Strength_Tier": "Direct evidence",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": "PMID:123",
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "Regulatory_Barriers": "None identified",
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "Investigate",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "R&D_Opportunity_Score": 70,
    }
    row.update(overrides)
    return row


def _assert_common_shape(result):
    assert "RD_Discovery_Lane" in result.index
    assert "Discovery_Potential_Score" in result.index
    assert "Evidence_Maturity_Score" in result.index
    assert 0.0 <= float(result["Discovery_Potential_Score"]) <= 100.0
    assert 0.0 <= float(result["Evidence_Maturity_Score"]) <= 100.0


def test_new_columns_never_change_scientific_triage_status_or_overall_score():
    # Same fixture as test_candidate_shortlisting.py::
    # test_direct_human_evidence_can_shortlist_with_one_traceable_source --
    # confirms this additive layer does not perturb the pre-existing gate.
    row = _row(
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:101",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Shortlist"
    assert result["RD_Discovery_Lane"] == DISCOVERY_LANE_EVIDENCE_BACKED
    _assert_common_shape(result)


def test_mechanistic_inference_only_lands_in_discovery_hypothesis_lane():
    # Same fixture as test_candidate_shortlisting.py::
    # test_mechanism_only_inferred_link_cannot_enter_shortlist -- confirms
    # this candidate, capped at "Exploratory" by the existing gate,
    # now ALSO carries an explicit "R&D Discovery Hypothesis" lane instead
    # of only the ambiguous "Exploratory" status.
    row = _row(
        Target_or_Mechanism="Aldose-Reductase-Inhibitor; AMPK",
        Scientific_Rationale=(
            "Shares a validated biological target with the reference compound "
            "(seed_data.COMPOUND_TARGETS hardcoded knowledge base, not a specific study)."
        ),
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:999",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Exploratory"
    assert result["RD_Discovery_Lane"] == DISCOVERY_LANE_HYPOTHESIS
    assert float(result["Discovery_Potential_Score"]) > 0.0
    _assert_common_shape(result)


def test_safety_hard_stop_without_regulatory_text_is_not_currently_developable():
    # Same fixture as test_candidate_shortlisting.py::
    # test_hard_stop_overrides_high_scientific_scores -- Regulatory_Barriers
    # is "None identified", so the additive lane must read this as a safety
    # stop, not a regulatory prohibition.
    row = _row(
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:102",
        Decision_Class="No-Go / safety concern",
        Go_Investigate_Hold_NoGo="No-Go",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Excluded"
    assert result["RD_Discovery_Lane"] == DISCOVERY_LANE_SAFETY_STOP
    _assert_common_shape(result)


def test_regulatory_prohibition_text_is_labeled_regulatory_not_safety():
    row = _row(
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:103",
        Regulatory_Barriers="Prohibited for oral use in the EU",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Excluded"
    assert result["RD_Discovery_Lane"] == DISCOVERY_LANE_REGULATORY_STOP
    _assert_common_shape(result)


def test_no_relevance_no_mechanism_is_insufficient_signal_not_hypothesis():
    row = _row(
        Target_or_Mechanism="Not clearly extracted",
        Target_Provenance="Not applicable (no shared-target claim for this match type)",
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:404",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="An indication with no matching evidence at all",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Excluded"
    assert result["RD_Discovery_Lane"] == DISCOVERY_LANE_INSUFFICIENT
    _assert_common_shape(result)


def test_known_established_catalogue_plant_becomes_evidence_gap():
    lane = classify_discovery_lane(
        plant_status="Exploratory",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=True,
        indication_points=5.0,
        dosage_mismatch=False,
        already_in_catalogue=True,
        novelty_tier="Established / commercially active",
    )
    assert lane == DISCOVERY_LANE_EVIDENCE_GAP


def test_saturated_market_catalogue_plant_also_becomes_evidence_gap():
    lane = classify_discovery_lane(
        plant_status="Exploratory",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=True,
        indication_points=5.0,
        dosage_mismatch=False,
        already_in_catalogue=True,
        novelty_tier="Competitive / saturated market",
    )
    assert lane == DISCOVERY_LANE_EVIDENCE_GAP


def test_unknown_catalogue_status_falls_back_to_discovery_hypothesis():
    # already_in_catalogue=None (unknown) must never be treated as
    # "known established" -- it must fall back to the original, broader
    # behavior rather than invent novelty it cannot confirm.
    lane = classify_discovery_lane(
        plant_status="Exploratory",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=True,
        indication_points=5.0,
        dosage_mismatch=False,
        already_in_catalogue=None,
        novelty_tier="Established / commercially active",
    )
    assert lane == DISCOVERY_LANE_HYPOTHESIS


def test_genuinely_novel_candidate_with_thin_market_stays_discovery_hypothesis():
    lane = classify_discovery_lane(
        plant_status="Exploratory",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=True,
        indication_points=5.0,
        dosage_mismatch=False,
        already_in_catalogue=False,
        novelty_tier="Commercial white-space",
    )
    assert lane == DISCOVERY_LANE_HYPOTHESIS


def test_established_catalogue_plant_but_thin_market_for_this_use_stays_hypothesis():
    # already_in_catalogue=True alone is not sufficient -- an established
    # plant with a genuine commercial white-space/repurposing opportunity
    # for THIS indication is still a real discovery lead, not merely an
    # "evidence gap" on a saturated product.
    lane = classify_discovery_lane(
        plant_status="Exploratory",
        plant_hard_stop=False,
        regulatory_prohibition_present=False,
        explicit_mechanistic_rationale=True,
        indication_points=5.0,
        dosage_mismatch=False,
        already_in_catalogue=True,
        novelty_tier="Indication-repurposing opportunity",
    )
    assert lane == DISCOVERY_LANE_HYPOTHESIS


def test_shortlisting_integration_routes_established_catalogue_plant_to_evidence_gap():
    row = _row(
        Target_or_Mechanism="Aldose-Reductase-Inhibitor; AMPK",
        Scientific_Rationale=(
            "Shares a validated biological target with the reference compound "
            "(seed_data.COMPOUND_TARGETS hardcoded knowledge base, not a specific study)."
        ),
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:999",
        Already_In_Internal_Catalogue=True,
        Commercial_Novelty_Status="established commercial use",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Exploratory"
    assert result["RD_Discovery_Lane"] == "Established Plant — Evidence Gap for This Indication"
    _assert_common_shape(result)


def test_shortlisting_integration_routes_unmarked_candidate_to_discovery_hypothesis():
    # Same fixture as above, minus the catalogue/market tags -- confirms
    # the default behavior (no origin signal available) is unchanged.
    row = _row(
        Target_or_Mechanism="Aldose-Reductase-Inhibitor; AMPK",
        Scientific_Rationale=(
            "Shares a validated biological target with the reference compound "
            "(seed_data.COMPOUND_TARGETS hardcoded knowledge base, not a specific study)."
        ),
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:998",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Exploratory"
    assert result["RD_Discovery_Lane"] == DISCOVERY_LANE_HYPOTHESIS


# --------------------------------------------------------------------------
# merge_authoritative_scores() integration -- confirmed-bug regression
# (external review, 2026-09-08: RD_Discovery_Lane / Discovery_Potential_
# Score / Evidence_Maturity_Score were computed onto plant_summary but
# silently dropped by merge_authoritative_scores(), the function that
# actually produces rd_report_ready_df -- the frame step_rd_candidates.py
# renders/exports. Verified directly before writing this fix.)
# --------------------------------------------------------------------------

def test_rd_discovery_lane_fields_survive_merge_authoritative_scores():
    row = _row(
        Target_or_Mechanism="Aldose-Reductase-Inhibitor; AMPK",
        Scientific_Rationale=(
            "Shares a validated biological target with the reference compound "
            "(seed_data.COMPOUND_TARGETS hardcoded knowledge base, not a specific study)."
        ),
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:999",
    )
    df = pd.DataFrame([row])
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion",
    )
    merged = merge_authoritative_scores(df, summary)
    assert "RD_Discovery_Lane" in merged.columns
    assert "Discovery_Potential_Score" in merged.columns
    assert "Evidence_Maturity_Score" in merged.columns
    assert merged.iloc[0]["RD_Discovery_Lane"] == summary.iloc[0]["RD_Discovery_Lane"]
    assert merged.iloc[0]["Discovery_Potential_Score"] == summary.iloc[0]["Discovery_Potential_Score"]
    assert merged.iloc[0]["Evidence_Maturity_Score"] == summary.iloc[0]["Evidence_Maturity_Score"]


# --------------------------------------------------------------------------
# build_rd_discovery_hypothesis_view() -- independent second ranking axis
# (external review, 2026-09-08: Discovery_Potential_Score existed but
# nothing sorted or filtered by it -- the primary table still sorts by
# Scientific_Triage_Status/Overall_Score only.)
# --------------------------------------------------------------------------

def test_discovery_hypothesis_view_ranks_by_discovery_potential_not_overall_score():
    # Plant A: catalogue-safe evidence-backed candidate, high Overall_Score,
    # not a discovery hypothesis at all -- must be excluded from this view.
    plant_a = _row(
        Alternative_Plant="Plant A",
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:501",
    )
    # Plant B: weak mechanistic hypothesis, low Discovery_Potential.
    plant_b = _row(
        Alternative_Plant="Plant B",
        Target_or_Mechanism="AMPK",
        Scientific_Rationale=(
            "Shares a validated biological target with the reference compound "
            "(seed_data.COMPOUND_TARGETS hardcoded knowledge base, not a specific study)."
        ),
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:502",
    )
    # Plant C: strong mechanistic hypothesis (multiple targets), high
    # Discovery_Potential -- must rank ABOVE Plant B in this view even
    # though both are Exploratory / R&D Discovery Hypothesis.
    plant_c = _row(
        Alternative_Plant="Plant C",
        Target_or_Mechanism="Aldose-Reductase-Inhibitor; AMPK; GLUT4; PPAR-gamma",
        Scientific_Rationale=(
            "Shares multiple validated biological targets with the reference "
            "compound (seed_data.COMPOUND_TARGETS hardcoded knowledge base, "
            "not a specific study)."
        ),
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:503",
    )
    df = pd.DataFrame([plant_a, plant_b, plant_c])
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion",
    )
    merged = merge_authoritative_scores(df, summary)
    view = build_rd_discovery_hypothesis_view(merged)

    assert "Plant A" not in set(view["Alternative_Plant"])
    assert list(view["Alternative_Plant"]) == ["Plant C", "Plant B"]
    assert (
        view.iloc[0]["Discovery_Potential_Score"]
        >= view.iloc[1]["Discovery_Potential_Score"]
    )


def test_discovery_hypothesis_view_empty_when_no_lane_column():
    view = build_rd_discovery_hypothesis_view(pd.DataFrame([{"Alternative_Plant": "X"}]))
    assert view.empty


def test_discovery_hypothesis_view_empty_on_empty_input():
    assert build_rd_discovery_hypothesis_view(pd.DataFrame()).empty
    assert build_rd_discovery_hypothesis_view(None).empty


def test_discovery_hypothesis_view_excludes_regulatory_prohibition_always():
    row = _row(
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:601",
        Regulatory_Barriers="Prohibited for oral use in the EU",
    )
    df = pd.DataFrame([row])
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion",
    )
    merged = merge_authoritative_scores(df, summary)
    view = build_rd_discovery_hypothesis_view(merged, include_not_currently_developable=True)
    assert view.empty
