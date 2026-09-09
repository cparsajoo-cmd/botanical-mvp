import pandas as pd

import post_discovery_investor_view as piv
from evidence_source_resolver import attach_human_evidence_source_traceability
from rd_discovery_classification import DISCOVERY_LANE_HYPOTHESIS, DISCOVERY_LANE_SAFETY_STOP


def _row(**overrides):
    row = {
        "Alternative_Plant": "Plant X",
        "RD_Discovery_Lane": DISCOVERY_LANE_HYPOTHESIS,
        "Safety_Concern_Level": "NONE",
        "Safety_Assertion_Status": "NO_SAFETY_EVIDENCE_RETRIEVED",
        "Commercial_Status_Overall": "UNKNOWN",
        "Commercial_Status_For_Indication": "UNKNOWN",
        "Commercial_Opportunity_Class": None,
    }
    row.update(overrides)
    return row


def test_ai_zero_vs_positive_ids_is_flagged():
    status, issues = piv.validate_candidate_evidence_consistency(_row(
        AI_Direct_Human_Outcome_Evidence_Count=0,
        Direct_Human_Outcome_Evidence_IDs="E1;E2",
    ))
    assert status == piv.CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION
    assert issues


def test_ai_positive_vs_zero_ids_is_flagged():
    status, _ = piv.validate_candidate_evidence_consistency(_row(
        AI_Direct_Human_Outcome_Evidence_Count=2,
        Direct_Human_Outcome_Evidence_IDs="()",
    ))
    assert status == piv.CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION


def test_ids_zero_vs_positive_outcome_count_is_flagged():
    status, _ = piv.validate_candidate_evidence_consistency(_row(
        Direct_Human_Outcome_Evidence_IDs="()",
        Outcome_Specific_Human_Evidence_Count=2,
    ))
    assert status == piv.CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION


def test_ids_positive_vs_zero_outcome_count_is_flagged():
    status, _ = piv.validate_candidate_evidence_consistency(_row(
        Direct_Human_Outcome_Evidence_IDs="E1;E2",
        Outcome_Specific_Human_Evidence_Count=0,
    ))
    assert status == piv.CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION


def test_positive_strength_with_every_explicit_count_zero_is_flagged():
    status, issues = piv.validate_candidate_evidence_consistency(_row(
        AI_Direct_Human_Outcome_Evidence_Count=0,
        Direct_Human_Outcome_Evidence_IDs="()",
        Outcome_Specific_Human_Evidence_Count=0,
        Human_Evidence_Strength="MODERATE",
    ))
    assert status == piv.CONSISTENCY_HUMAN_EVIDENCE_CONTRADICTION
    assert any("strength" in issue.lower() for issue in issues)


def test_safety_stop_with_no_safety_evidence_is_flagged_and_step_is_safety_first():
    row = _row(
        RD_Discovery_Lane=DISCOVERY_LANE_SAFETY_STOP,
        Safety_Concern_Level="NONE",
        Safety_Assertion_Status="NO_SAFETY_EVIDENCE_RETRIEVED",
    )
    status, issues = piv.validate_candidate_evidence_consistency(row)
    assert status == piv.CONSISTENCY_SAFETY_CONTRADICTION
    assert issues
    assert piv.next_rd_step(row) == "Resolve toxicology/interaction risk before efficacy development."
    assert piv.key_evidence_gap(row) == "Safety characterization insufficient"


def test_positive_expected_human_count_with_no_ids_becomes_source_linkage_incomplete_after_attachment():
    report = pd.DataFrame([_row(
        AI_Direct_Human_Outcome_Evidence_Count=2,
        Direct_Human_Outcome_Evidence_IDs="()",
    )])
    enriched = attach_human_evidence_source_traceability(report, pd.DataFrame())
    status, issues = piv.validate_candidate_evidence_consistency(enriched.iloc[0])
    assert status == piv.CONSISTENCY_MULTIPLE  # count/ID contradiction + source-linkage gap
    assert any("source linkage" in issue.lower() for issue in issues)


def test_consistent_human_evidence_with_resolved_source_remains_coherent():
    evidence_df = pd.DataFrame([{
        "Evidence_Record_ID": "E1",
        "Source_Title": "Trial",
        "Source_URL": "https://example.org/e1",
        "Study_Type": "Randomized controlled trial",
        "Population": "human",
    }])
    report = pd.DataFrame([_row(
        AI_Direct_Human_Outcome_Evidence_Count=1,
        Direct_Human_Outcome_Evidence_IDs="E1",
        Outcome_Specific_Human_Evidence_Count=1,
        Human_Evidence_Strength="MODERATE",
    )])
    enriched = attach_human_evidence_source_traceability(report, evidence_df)
    status, issues = piv.validate_candidate_evidence_consistency(enriched.iloc[0])
    assert status == piv.CONSISTENCY_COHERENT
    assert issues == []
