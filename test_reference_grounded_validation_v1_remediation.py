"""Regression tests for the Reference-Grounded Validation v1 remediation.

These are deliberately SYNTHETIC examples using generic/invented plant
and compound names — never the 24-case holdout's own botanicals,
wording, or PMIDs (see the holdout integrity rule in
gold_corpus/scientific_validity/final_holdout_v1/FINAL_REFERENCE_GROUNDED_VALIDATION_REPORT.md).
Each test proves a GENERALIZABLE root-cause fix, not a memorized case.
"""

import pandas as pd

from scientific_phrase_matcher import find_verb_aware_phrase_matches
from regulatory_barrier_classifier import classify_regulatory_barriers
from regulatory_scope_assessment import (
    assess_regulatory_scope,
    detect_dose_threshold_violation,
)
from safety_assertion_engine import classify_safety_assertions
from eligibility_gate import (
    classify_safety_finding,
    classify_regulatory_finding,
    evaluate_eligibility,
    EligibilityStatus,
    RegulatoryDataStatus,
)
from evidence_interpretation import classify_evidence_direction, DIRECTION_POSITIVE, DIRECTION_NULL
from final_decision_policy import _final_decision_direction


# ----------------------------------------------------------------------
# Problem C.1 — verb-conjugation-aware regulatory phrase matching
# ----------------------------------------------------------------------

def test_verb_aware_matcher_catches_present_tense_prohibition():
    hits = find_verb_aware_phrase_matches(
        "regulators in this market prohibit the sale of this ingredient.",
        ["prohibit", "ban"],
    )
    assert hits == ["prohibit"]


def test_verb_aware_matcher_respects_negation():
    hits = find_verb_aware_phrase_matches(
        "this ingredient is not banned in any jurisdiction.",
        ["ban"],
    )
    assert hits == []


def test_regulatory_barrier_classifier_matches_present_tense_verbs():
    result = classify_regulatory_barriers(
        "national law prohibits the use of this plant extract in food products."
    )
    assert result.has_barrier
    assert "Prohibited / banned" in result.barrier_types


# ----------------------------------------------------------------------
# Problem C.2/C.3 — regulatory scope defaulting and dose thresholds
# ----------------------------------------------------------------------

def test_unqualified_regulatory_prohibition_defaults_to_species_wide():
    assessment = assess_regulatory_scope(
        "this genus is entirely prohibited from use in food supplements.",
        candidate_context_text="use as a food supplement ingredient",
    )
    assert assessment.scope == "species_wide"
    assert assessment.relevant is True


def test_qualified_regulatory_prohibition_matches_declared_candidate_context():
    assessment = assess_regulatory_scope(
        "root preparations containing xanthotoxin are prohibited due to phototoxicity concerns.",
        candidate_context_text="root extract containing xanthotoxin for oral use",
    )
    assert assessment.scope == "constituent_specific"
    assert assessment.relevant is True


def test_qualified_regulatory_prohibition_unconfirmed_stays_unresolved():
    assessment = assess_regulatory_scope(
        "root preparations containing xanthotoxin are prohibited due to phototoxicity concerns.",
        candidate_context_text="leaf tea with no stated constituent profile",
    )
    assert assessment.relevant is not True


def test_dose_threshold_violation_detected():
    finding = detect_dose_threshold_violation(
        "regulation requires that daily portions provide less than 200 mg of this alkaloid.",
        candidate_context_text="daily portion providing 350 mg of this alkaloid",
    )
    assert finding is not None
    assert finding.violates is True


def test_dose_threshold_compliant_amount_is_not_a_violation():
    finding = detect_dose_threshold_violation(
        "regulation requires that daily portions provide less than 200 mg of this alkaloid.",
        candidate_context_text="daily portion providing 50 mg of this alkaloid",
    )
    assert finding is not None
    assert finding.violates is False


def test_classify_regulatory_finding_end_to_end_unqualified_prohibition_is_no_go():
    barrier_result = classify_regulatory_barriers(
        "this botanical is banned entirely from the food supplement market."
    )
    finding = classify_regulatory_finding(
        barrier_types=frozenset(barrier_result.barrier_types),
        has_evidence_text=True,
        same_plant=True,
        finding_text="this botanical is banned entirely from the food supplement market.",
        candidate_context_text="use as a food supplement ingredient",
    )
    regulatory_decision = evaluate_eligibility(
        classify_safety_finding(hit_terms=frozenset(), flagged_terms=frozenset(), has_evidence_text=True, same_plant=True),
        finding,
    )
    assert regulatory_decision.status == EligibilityStatus.NO_GO_REGULATORY


def test_classify_regulatory_finding_end_to_end_dose_violation_is_no_go():
    finding = classify_regulatory_finding(
        barrier_types=frozenset(),
        has_evidence_text=True,
        same_plant=True,
        finding_text="regulation requires daily portions to provide less than 100 mg of this compound.",
        candidate_context_text="daily portion providing 250 mg of this compound",
    )
    regulatory_decision = evaluate_eligibility(
        classify_safety_finding(hit_terms=frozenset(), flagged_terms=frozenset(), has_evidence_text=True, same_plant=True),
        finding,
    )
    assert regulatory_decision.status == EligibilityStatus.NO_GO_REGULATORY


# ---------------------------------------------------------------------
# Root-cause regression (2026-08-10, RGV v2 rerun against
# rgv2_022_cbd_eu_food and rgv2_023_acmella_eu_food). Both real evidence
# texts are correctly recognized by regulatory_barrier_classifier as
# "Novel food / pre-market approval required" (a product with no
# granted market authorization), but classify_regulatory_finding's
# is_prohibited check only ever looked for "Prohibited / banned" --
# a novel-food requirement with no authorization was RESTRICTED, not
# PROHIBITED, so real cases resolved to GO WITH CAUTION instead of
# NO GO REGULATORY. same_plant=True (as in both real cases, where the
# candidate pool is only the plant itself) on purpose, matching how the
# real validation harness calls the engine for a self-lookup.
# ---------------------------------------------------------------------
def test_classify_regulatory_finding_end_to_end_novel_food_no_authorization_is_no_go():
    text = (
        "CBD-rich Cannabis sativa extracts are treated as novel foods in the EU "
        "and cannot be placed on the market as food supplements without Union authorization."
    )
    barrier_result = classify_regulatory_barriers(text)
    assert barrier_result.barrier_types == ["Novel food / pre-market approval required"]
    finding = classify_regulatory_finding(
        barrier_types=frozenset(barrier_result.barrier_types),
        has_evidence_text=True,
        same_plant=True,
        finding_text=text,
        # Real candidate context text (rgv2_022_cbd_eu_food's own
        # indication) restates "extract", the same qualifier the
        # finding text uses -- this is what lets scope resolve to
        # RELEVANT instead of staying UNKNOWN.
        candidate_context_text="CBD-rich extract as an EU food supplement ingredient",
    )
    assert finding.status == RegulatoryDataStatus.PROHIBITED
    regulatory_decision = evaluate_eligibility(
        classify_safety_finding(hit_terms=frozenset(), flagged_terms=frozenset(), has_evidence_text=True, same_plant=True),
        finding,
    )
    assert regulatory_decision.status == EligibilityStatus.NO_GO_REGULATORY


def test_classify_regulatory_finding_end_to_end_terminated_novel_food_procedure_is_no_go():
    text = (
        "The EU authorisation procedure for Acmella oleracea extract was terminated "
        "without addition to the Union list of authorised novel foods."
    )
    barrier_result = classify_regulatory_barriers(text)
    assert "Novel food / pre-market approval required" in barrier_result.barrier_types
    finding = classify_regulatory_finding(
        barrier_types=frozenset(barrier_result.barrier_types),
        has_evidence_text=True,
        same_plant=True,
        finding_text=text,
        # Real candidate context text (rgv2_023_acmella_eu_food's own
        # indication), same reasoning as above.
        candidate_context_text="Acmella oleracea extract as an EU food supplement ingredient",
    )
    assert finding.status == RegulatoryDataStatus.PROHIBITED
    regulatory_decision = evaluate_eligibility(
        classify_safety_finding(hit_terms=frozenset(), flagged_terms=frozenset(), has_evidence_text=True, same_plant=True),
        finding,
    )
    assert regulatory_decision.status == EligibilityStatus.NO_GO_REGULATORY


# ----------------------------------------------------------------------
# Problem B — safety-assertion vocabulary generalization
# ----------------------------------------------------------------------

def test_organ_toxicity_matches_plural_injury_form():
    assertions = classify_safety_assertions(
        "this plant has caused multiple documented cases of hepatocellular liver injuries."
    )
    assert any(a.assertion_type.value == "organ_toxicity" and a.severity.value == "SERIOUS" for a in assertions)


def test_fatal_adverse_event_matches_fatalities_noun_form():
    assertions = classify_safety_assertions(
        "several fatalities have been reported following ingestion of this preparation."
    )
    assert any(a.assertion_type.value == "fatal_adverse_event" for a in assertions)


def test_fatal_adverse_event_matches_present_tense_cause_with_list_of_outcomes():
    assertions = classify_safety_assertions(
        "acute poisoning can cause seizures, coma, respiratory failure, multiorgan failure and death."
    )
    kinds = {a.assertion_type.value for a in assertions}
    assert "fatal_adverse_event" in kinds
    assert "organ_toxicity" in kinds


def test_classify_safety_finding_end_to_end_serious_assertion_is_no_go():
    assertions = classify_safety_assertions(
        "this herb has caused several cases of acute hepatic necrosis and reported fatalities."
    )
    finding = classify_safety_finding(
        hit_terms=frozenset(), flagged_terms=frozenset(),
        has_evidence_text=True, same_plant=True, assertions=tuple(assertions),
    )
    decision = evaluate_eligibility(
        finding,
        classify_regulatory_finding(barrier_types=frozenset(), has_evidence_text=True, same_plant=True),
    )
    assert decision.status == EligibilityStatus.NO_GO_SAFETY


# ----------------------------------------------------------------------
# Problem A — evidence direction: negation scope and vocabulary
# ----------------------------------------------------------------------

def test_negation_scope_reaches_across_a_full_clause():
    direction, *_ = classify_evidence_direction(
        "the review found no convincing evidence that this preparation was effective for the condition."
    )
    assert direction == DIRECTION_NULL


def test_negation_scope_does_not_cross_a_contrastive_conjunction():
    direction, *_ = classify_evidence_direction(
        "the primary endpoint was not significant, although secondary outcomes improved."
    )
    # A later, contrastively-introduced positive clause must not be
    # cancelled by an earlier, unrelated negation in the same sentence.
    assert direction in ("mixed", "positive")


def test_comparative_better_than_placebo_is_positive():
    direction, *_ = classify_evidence_direction(
        "this preparation was better than placebo for symptom relief, though larger trials are needed."
    )
    assert direction == DIRECTION_POSITIVE


def test_reduced_duration_and_incidence_is_positive():
    direction, *_ = classify_evidence_direction(
        "the trial found this preparation reduced episode duration and recurrence."
    )
    assert direction == DIRECTION_POSITIVE


def test_final_decision_direction_recognizes_insufficient_evidence_to_recommend():
    assert _final_decision_direction(
        "the systematic review found insufficient evidence to recommend this preparation for the condition."
    ) == "null"


def test_final_decision_direction_recognizes_did_not_demonstrate_effect():
    assert _final_decision_direction(
        "the trial did not demonstrate an effect of this preparation on the primary outcome."
    ) == "negative"
