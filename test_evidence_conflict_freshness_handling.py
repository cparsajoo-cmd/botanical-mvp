from final_decision_policy import (
    resolve_scientific_evidence,
    ScientificEvidenceSignal,
)


def rec(text, source_type='SYSTEMATIC_REVIEW', year=None, study_design=''):
    return {
        'assertion_text': text,
        'source_type': source_type,
        'source_year': year,
        'study_design': study_design,
    }


def test_explicit_debate_in_governing_review_requires_expert_conflict():
    result = resolve_scientific_evidence([
        rec('Systematic review found significant benefit for the target outcome.', year=2024),
        rec('Whether the intervention is truly efficacious remains a matter of debate and the available evidence was not definitive.', year=2000),
    ])
    assert result.signal == ScientificEvidenceSignal.CONFLICT


def test_newer_direct_null_trial_can_challenge_older_positive_review():
    result = resolve_scientific_evidence([
        rec('Review reported significant benefit and improved symptoms.', year=2009),
        rec('Randomized controlled study found trivial-to-small effects on the target outcome.', source_type='CLINICAL_TRIAL', year=2025, study_design='Randomized Controlled Trial'),
    ])
    assert result.signal == ScientificEvidenceSignal.CONFLICT


def test_older_direct_null_trial_does_not_override_newer_positive_review():
    result = resolve_scientific_evidence([
        rec('Review reported significant benefit and improved symptoms.', year=2025),
        rec('Randomized controlled study found trivial-to-small effects on the target outcome.', source_type='CLINICAL_TRIAL', year=2020, study_design='Randomized Controlled Trial'),
    ])
    assert result.signal == ScientificEvidenceSignal.SUPPORTIVE


def test_missing_year_does_not_invent_freshness_conflict():
    result = resolve_scientific_evidence([
        rec('Review reported significant benefit and improved symptoms.', year=None),
        rec('Randomized controlled study found trivial-to-small effects on the target outcome.', source_type='CLINICAL_TRIAL', year=2025, study_design='Randomized Controlled Trial'),
    ])
    assert result.signal == ScientificEvidenceSignal.SUPPORTIVE


def test_plain_positive_review_stays_supportive():
    result = resolve_scientific_evidence([
        rec('Systematic review found significant benefit and improved symptoms.', year=2024),
    ])
    assert result.signal == ScientificEvidenceSignal.SUPPORTIVE
