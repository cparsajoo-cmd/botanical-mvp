import pandas as pd
from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from decision_holdout_v2 import load_reference, run_case


def test_structured_final_status_overrides_legacy_score_tier_text():
    row = {
        'Final_Decision_Status': 'GO',
        'Eligibility_Status': 'eligible',
        'Decision_Class': 'Low priority / insufficient data',
    }
    assert final_status_from_engine_row(row) == FinalDecisionStatus.GO


def test_legacy_fallback_still_works_without_structured_status():
    row = {'Eligibility_Status': 'eligible', 'Decision_Class': 'Low priority / insufficient data'}
    assert final_status_from_engine_row(row) == FinalDecisionStatus.INSUFFICIENT_EVIDENCE


def test_exposed_v2_supportive_cases_are_not_autonomously_go_when_semantic_gate_was_never_assessed():
    """These frozen v2 snapshots predate semantic-gate coverage and are now
    regression-only.  Their scientific direction can still be positive, but
    the current production contract must not turn an unassessed high-stakes
    record into an autonomous GO/GO WITH CAUTION.  Unit tests in
    test_evidence_interpretation_decision_remediation.py separately verify
    that a fully eligible supportive systematic review resolves to
    GO_WITH_CAUTION when the safety/regulatory precondition is satisfied.
    """
    refs = {c['case_id']: c for c in load_reference()['cases']}
    for cid in ('v2_001_lavender_anxiety', 'v2_002_boswellia_joint'):
        status, row = run_case(refs[cid])
        assert row['Evidence_Hierarchy_Detail'] == 'Systematic review / meta-analysis'
        assert row['Occurrence_Corroboration'].startswith('Single-source claim')
        assert row['Evidence_Direction'] == 'positive'
        assert row['Eligibility_Status'] == 'expert_review_required'
        assert row['Final_Decision_Status'] == 'EXPERT REVIEW REQUIRED'
        assert status == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED

def test_engine_exposes_structured_final_decision_status_column():
    refs = {c['case_id']: c for c in load_reference()['cases']}
    status, row = run_case(refs['v2_001_lavender_anxiety'])
    assert 'Final_Decision_Status' in row.index
    assert row['Final_Decision_Status'] == status.value
