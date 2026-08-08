from evidence_interpretation import (
    classify_evidence_direction,
    DIRECTION_POSITIVE,
    DIRECTION_NULL,
)


def direction(text: str) -> str:
    return classify_evidence_direction(text)[0]


def test_significant_anxiolytic_effect_is_positive():
    assert direction("Meta-analysis demonstrates that treatment exerts significant anxiolytic effects in adults with anxiety.") == DIRECTION_POSITIVE


def test_indication_adjective_before_symptoms_is_positive():
    assert direction("The enriched extract improved osteoarthritis symptoms compared with placebo.") == DIRECTION_POSITIVE


def test_present_tense_significantly_reduces_is_positive():
    assert direction("Meta-analysis concluded that treatment significantly reduces transaminase levels.") == DIRECTION_POSITIVE


def test_hedged_beneficial_language_is_at_least_supportive_direction():
    assert direction("The systematic review suggests treatment may be beneficial for improving blood pressure.") == DIRECTION_POSITIVE


def test_substantially_reduced_symptoms_is_positive():
    assert direction("Meta-analysis found supplementation substantially reduced upper respiratory symptoms.") == DIRECTION_POSITIVE


def test_significant_adverse_effects_are_not_positive():
    assert direction("The treatment produced significant adverse effects in the intervention group.") != DIRECTION_POSITIVE


def test_no_significant_benefit_is_not_positive():
    assert direction("The trial found no significant benefit compared with placebo.") != DIRECTION_POSITIVE


def test_no_significant_difference_remains_null():
    assert direction("There was no significant difference from placebo.") == DIRECTION_NULL
