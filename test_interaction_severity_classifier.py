"""
Unit tests for interaction_severity_classifier.py in isolation, no
engine/pandas involved. See test_structured_serious_interaction_gate_fix.py
for the end-to-end engine-level regression suite.
"""

from assertion_vocabulary import SeverityLevel
from severity_assignment_policy import HighRiskInteractionDrugClass
from interaction_severity_classifier import (
    classify_interaction_assertion,
    hard_hit_terms_for,
    informational_terms_for,
    InteractionSeverityTier,
    HARD_GATE_SIGNAL_TERM,
)


def test_empty_text_is_none_tier():
    result = classify_interaction_assertion("")
    assert result.tier == InteractionSeverityTier.NONE
    assert hard_hit_terms_for(result) == frozenset()
    assert informational_terms_for(result) == ()


def test_none_text_is_none_tier():
    result = classify_interaction_assertion(None)
    assert result.tier == InteractionSeverityTier.NONE


def test_serious_contraindication_with_multiple_drug_classes():
    text = (
        "Concomitant use with coumarin-type anticoagulants, cyclosporine, "
        "or protease inhibitors metabolised by CYP3A4 is contraindicated."
    )
    result = classify_interaction_assertion(text)
    assert result.tier == InteractionSeverityTier.SERIOUS_CONTRAINDICATION
    assert result.severity == SeverityLevel.SERIOUS
    assert HighRiskInteractionDrugClass.ANTICOAGULANT in result.drug_classes
    assert HighRiskInteractionDrugClass.TRANSPLANT_IMMUNOSUPPRESSANT in result.drug_classes
    assert HighRiskInteractionDrugClass.ANTIRETROVIRAL_THERAPY in result.drug_classes
    assert hard_hit_terms_for(result) == frozenset({HARD_GATE_SIGNAL_TERM})
    assert informational_terms_for(result)


def test_serious_high_risk_interaction_without_contraindication_wording():
    result = classify_interaction_assertion(
        "This extract may interact with anticoagulant medication and "
        "increase bleeding risk."
    )
    assert result.tier == InteractionSeverityTier.SERIOUS_HIGH_RISK_INTERACTION
    assert result.severity == SeverityLevel.SERIOUS
    assert hard_hit_terms_for(result) == frozenset({HARD_GATE_SIGNAL_TERM})


def test_moderate_interaction_no_high_risk_class():
    result = classify_interaction_assertion(
        "This extract may interact with common over-the-counter antacids."
    )
    assert result.tier == InteractionSeverityTier.MODERATE_INTERACTION
    assert result.severity == SeverityLevel.MODERATE
    assert hard_hit_terms_for(result) == frozenset()
    assert informational_terms_for(result)


def test_contraindication_wording_without_recognized_drug_class_is_moderate_not_serious():
    result = classify_interaction_assertion("Contraindicated in pregnancy.")
    assert result.tier == InteractionSeverityTier.MODERATE_INTERACTION
    assert result.tier != InteractionSeverityTier.SERIOUS_CONTRAINDICATION
    assert hard_hit_terms_for(result) == frozenset()


def test_precaution_only_language():
    result = classify_interaction_assertion(
        "Caution is advised when using this product with other medications."
    )
    assert result.tier == InteractionSeverityTier.PRECAUTION_CAUTION
    assert result.severity == SeverityLevel.MINOR
    assert hard_hit_terms_for(result) == frozenset()


def test_theoretical_mechanistic_only_language_does_not_raise_severity():
    result = classify_interaction_assertion(
        "The compound is a known inhibitor of CYP3A4 in vitro."
    )
    assert result.tier == InteractionSeverityTier.THEORETICAL_MECHANISTIC
    assert result.severity == SeverityLevel.NONE
    assert hard_hit_terms_for(result) == frozenset()


def test_mechanistic_mention_inside_a_serious_sentence_does_not_downgrade_it():
    # A CYP3A4 mention that is PART OF a serious contraindication
    # sentence must not be misread as merely "mechanistic-only" -- the
    # sentence-level classification already returns SERIOUS for this
    # unit because assertion language + drug class are both present.
    result = classify_interaction_assertion(
        "Concomitant use with cyclosporine, metabolised via CYP3A4, is "
        "contraindicated."
    )
    assert result.tier == InteractionSeverityTier.SERIOUS_CONTRAINDICATION


def test_no_known_interactions_reassurance_is_none():
    result = classify_interaction_assertion(
        "No known drug interactions have been reported for this extract."
    )
    assert result.tier == InteractionSeverityTier.NONE


def test_not_contraindicated_negation_is_none():
    result = classify_interaction_assertion(
        "This product is not contraindicated with anticoagulant therapy."
    )
    assert result.tier == InteractionSeverityTier.NONE


def test_did_not_interact_negation_is_none():
    result = classify_interaction_assertion(
        "The extract did not interact with warfarin in a controlled "
        "pharmacokinetic study."
    )
    assert result.tier == InteractionSeverityTier.NONE


def test_negated_mention_does_not_suppress_a_later_genuine_warning_in_the_same_text():
    # Two independent sentences: the first is reassurance about one
    # substance, the second is a genuine serious contraindication about
    # a different one. Sentence-level splitting means the negation in
    # sentence 1 must not suppress sentence 2.
    text = (
        "No known interaction with common antacids has been reported. "
        "Concomitant use with cyclosporine is contraindicated."
    )
    result = classify_interaction_assertion(text)
    assert result.tier == InteractionSeverityTier.SERIOUS_CONTRAINDICATION


def test_mixed_text_reports_the_most_severe_tier_found():
    text = (
        "The extract improved sleep quality in a small trial. "
        "Caution is advised in patients on other medications. "
        "Concurrent use with tacrolimus, a transplant immunosuppressant, "
        "should be avoided."
    )
    result = classify_interaction_assertion(text)
    assert result.tier == InteractionSeverityTier.SERIOUS_CONTRAINDICATION


def test_pure_function_is_deterministic():
    text = "Must not be co-administered with cyclosporine."
    r1 = classify_interaction_assertion(text)
    r2 = classify_interaction_assertion(text)
    assert r1 == r2


def test_hard_gate_signal_term_is_a_single_stable_constant():
    assert isinstance(HARD_GATE_SIGNAL_TERM, str)
    assert HARD_GATE_SIGNAL_TERM
    assert "hypericum" not in HARD_GATE_SIGNAL_TERM.lower()
    assert "st john" not in HARD_GATE_SIGNAL_TERM.lower()
