"""
Phase 1 regression suite — "اصلاح موتور شواهد علمی": Study_Design vs
Evidence_Direction separation.

WHAT THIS PROVES
Before this fix, a negative, null, future-planned, or protocol-only
"clinical trial" mention scored IDENTICALLY to a genuinely positive,
completed RCT — see evidence_interpretation.py's module docstring and
this suite's own direct-execution tests below for proof against the
real code path.

HOW TO RUN
    pytest -q test_phase1_evidence_direction.py
"""

import pandas as pd
import pytest

import botanical_rd_candidate_engine as eng
from evidence_interpretation import (
    interpret_evidence,
    classify_study_design,
    classify_evidence_direction,
    DIRECTION_POSITIVE,
    DIRECTION_NEGATIVE,
    DIRECTION_NULL,
    DIRECTION_MIXED,
    DIRECTION_UNCLEAR,
    APPLICABILITY_CONTEXTUAL_OR_FUTURE,
    APPLICABILITY_DIRECT,
    STUDY_DESIGN_RCT,
    STUDY_DESIGN_CLINICAL_TRIAL,
    STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL,
    STUDY_DESIGN_REVIEW,
    STUDY_DESIGN_ANIMAL_STUDY,
    STUDY_DESIGN_IN_VITRO_STUDY,
    DIRECTION_CONTRIBUTION_RATIO,
    DEFAULT_CLINICAL_WEIGHT,
)


# ---------------------------------------------------------------------
# Shared engine fixture — mirrors make_engine() in
# test_botanical_rd_candidate_engine.py so this file uses the project's
# real import path and real engine construction, not a stub.
# ---------------------------------------------------------------------
def make_engine():
    background = [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    df = pd.DataFrame(background)
    return eng.BotanicalRDCandidateEngine(
        plant_compounds_df=df,
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        use_live_search=False,
    )


def _score_with_evidence(engine, evidence_text):
    """Runs the exact real code path: _evidence_level() +
    interpret_evidence() -> _score_candidate(), returning
    (evidence_level, evidence_direction, evidence_quality_contribution,
    total_score)."""
    evidence_level = engine._evidence_level(evidence_text)
    interp = interpret_evidence(
        evidence_text, clinical_weight=engine.scoring_config.evidence_clinical
    )
    score, components = engine._score_candidate(
        same_plant=False,
        matched_compound="C",
        reference_compound="C",
        match_quality="exact",
        concentration="2 mg/g dry weight",
        extraction="aqueous infusion",
        dosage_form="Infusion",
        co_compounds="",
        safety_flags="",
        interaction_flags="",
        market_status="Regulatory monograph exists",
        novelty_status="Alternative cross-region candidate",
        target="Target",
        evidence=evidence_text,
        evidence_level=evidence_level,
        compound_plant_count=0,
        target_specificity=None,
        evidence_direction_contribution=interp.contribution,
    )
    return evidence_level, interp.evidence_direction, components["Evidence quality"], score


# ---------------------------------------------------------------------
# 1) Positive RCT
# ---------------------------------------------------------------------
def test_positive_rct():
    text = "A randomized controlled trial demonstrated significant improvement."
    assert classify_study_design(text) == STUDY_DESIGN_RCT
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_POSITIVE
    interp = interpret_evidence(text)
    assert interp.contribution == pytest.approx(24.0)


# ---------------------------------------------------------------------
# 2) Negative RCT
# ---------------------------------------------------------------------
def test_negative_rct():
    text = "A randomized controlled trial failed to demonstrate efficacy."
    assert classify_study_design(text) == STUDY_DESIGN_RCT
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_NEGATIVE
    interp = interpret_evidence(text)
    assert interp.contribution == pytest.approx(-12.0)
    assert interp.contribution < 0


# ---------------------------------------------------------------------
# 3) Null RCT
# ---------------------------------------------------------------------
def test_null_rct():
    text = "A randomized controlled trial found no significant difference from placebo."
    assert classify_study_design(text) == STUDY_DESIGN_RCT
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_NULL
    interp = interpret_evidence(text)
    assert interp.contribution == 0


# ---------------------------------------------------------------------
# 4) Mixed RCT
# ---------------------------------------------------------------------
def test_mixed_rct():
    text = (
        "A randomized controlled trial found the primary endpoint was "
        "not significant, although some secondary outcomes improved."
    )
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_MIXED
    interp = interpret_evidence(text)
    assert interp.contribution == pytest.approx(6.0)


# ---------------------------------------------------------------------
# 5) Future clinical trial mention — must NOT be completed clinical
#    evidence.
# ---------------------------------------------------------------------
def test_future_clinical_trial_mention():
    text = "A clinical trial is needed to evaluate efficacy."
    interp = interpret_evidence(text)
    assert interp.evidence_applicability == APPLICABILITY_CONTEXTUAL_OR_FUTURE
    assert interp.is_completed_study is False
    assert interp.contribution == 0


# ---------------------------------------------------------------------
# 6) Clinical trial protocol
# ---------------------------------------------------------------------
def test_clinical_trial_protocol():
    text = "This is a clinical trial protocol for evaluating chamomile."
    assert classify_study_design(text) == STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL
    interp = interpret_evidence(text)
    assert interp.evidence_applicability == APPLICABILITY_CONTEXTUAL_OR_FUTURE
    assert interp.contribution == 0


# ---------------------------------------------------------------------
# 7) Review mentioning another trial — the REVIEW itself must not be
#    auto-classified as the RCT it discusses.
# ---------------------------------------------------------------------
def test_review_mentioning_another_trial_is_not_reclassified_as_rct():
    text = "This review discusses a randomized trial that reported improvement."
    assert classify_study_design(text) == STUDY_DESIGN_REVIEW
    assert classify_study_design(text) != STUDY_DESIGN_RCT


# ---------------------------------------------------------------------
# 8) Negated efficacy statement must not become positive
# ---------------------------------------------------------------------
def test_negated_efficacy_statement_is_not_positive():
    text = "The treatment did not demonstrate significant improvement over placebo."
    direction, *_ = classify_evidence_direction(text)
    assert direction != DIRECTION_POSITIVE
    interp = interpret_evidence(text)
    assert interp.contribution <= 0


# ---------------------------------------------------------------------
# 9) Animal study
# ---------------------------------------------------------------------
def test_animal_study_design():
    text = "An animal model study in mice showed reduced inflammation."
    assert classify_study_design(text) == STUDY_DESIGN_ANIMAL_STUDY


# ---------------------------------------------------------------------
# 10) In-vitro study
# ---------------------------------------------------------------------
def test_in_vitro_study_design():
    text = "An in vitro study showed enzyme inhibition."
    assert classify_study_design(text) == STUDY_DESIGN_IN_VITRO_STUDY


# ---------------------------------------------------------------------
# 11) No-evidence sentence containing the word "clinical"
# ---------------------------------------------------------------------
def test_no_evidence_sentence_with_word_clinical_is_not_completed_evidence():
    text = "Clinical evidence is currently insufficient to support this use."
    interp = interpret_evidence(text)
    assert interp.evidence_applicability == APPLICABILITY_CONTEXTUAL_OR_FUTURE
    assert interp.contribution == 0


# ---------------------------------------------------------------------
# 12) Conflicting positive and negative statements
# ---------------------------------------------------------------------
def test_conflicting_positive_and_negative_statements():
    text = (
        "One trial found the treatment significantly improved symptoms, "
        "while another trial reported the treatment worsened outcomes."
    )
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_MIXED


# ---------------------------------------------------------------------
# 13) Study_Design must be independent of Evidence_Direction: same
#     design, different direction; same direction, different design.
# ---------------------------------------------------------------------
def test_study_design_is_independent_of_evidence_direction():
    positive_rct = interpret_evidence(
        "A randomized controlled trial demonstrated significant improvement."
    )
    negative_rct = interpret_evidence(
        "A randomized controlled trial failed to demonstrate efficacy."
    )
    # Same Study_Design, different Evidence_Direction.
    assert positive_rct.study_design == negative_rct.study_design == STUDY_DESIGN_RCT
    assert positive_rct.evidence_direction != negative_rct.evidence_direction

    positive_generic_trial = interpret_evidence(
        "The clinical trial demonstrated significant improvement."
    )
    # Same Evidence_Direction, different Study_Design.
    assert positive_generic_trial.evidence_direction == positive_rct.evidence_direction
    assert positive_generic_trial.study_design != positive_rct.study_design


# ---------------------------------------------------------------------
# 14) Real effect of Evidence_Direction on R&D_Opportunity_Score,
#     through the actual engine (_score_candidate), not just the
#     standalone module.
# ---------------------------------------------------------------------
def test_evidence_direction_has_real_effect_on_score():
    engine = make_engine()

    _, dir_pos, contrib_pos, score_pos = _score_with_evidence(
        engine, "A randomized controlled trial demonstrated significant improvement."
    )
    _, dir_mixed, contrib_mixed, score_mixed = _score_with_evidence(
        engine,
        "A randomized controlled trial found the primary endpoint was "
        "not significant, although some secondary outcomes improved.",
    )
    _, dir_null, contrib_null, score_null = _score_with_evidence(
        engine, "A randomized controlled trial found no significant difference from placebo."
    )
    _, dir_negative, contrib_negative, score_negative = _score_with_evidence(
        engine, "A clinical trial failed to demonstrate efficacy."
    )
    _, dir_future, contrib_future, score_future = _score_with_evidence(
        engine, "A future randomized controlled trial is planned to evaluate this herb."
    )
    _, dir_protocol, contrib_protocol, score_protocol = _score_with_evidence(
        engine, "This is a clinical trial protocol for evaluating chamomile."
    )

    assert dir_pos == DIRECTION_POSITIVE
    assert dir_mixed == DIRECTION_MIXED
    assert dir_null == DIRECTION_NULL
    assert dir_negative == DIRECTION_NEGATIVE
    assert dir_future == DIRECTION_UNCLEAR
    assert dir_protocol == DIRECTION_UNCLEAR

    # Required orderings (audit's explicit required test table).
    assert score_pos > score_mixed
    assert score_mixed > score_null

    # Required exact contribution values.
    assert contrib_null == 0
    assert contrib_negative < 0
    assert contrib_future == 0
    assert contrib_protocol == 0

    # A negative RCT must score strictly lower than a null RCT (a
    # documented negative finding is worse than "no effect detected").
    assert score_negative < score_null

    # Before this fix, ALL SIX of these scored identically (same flat
    # +24 "Clinical / human evidence" weight applied regardless of
    # outcome) — this is the direct proof the bug is fixed.
    scores = [score_pos, score_mixed, score_null, score_negative, score_future, score_protocol]
    assert len(set(scores)) > 1


# ---------------------------------------------------------------------
# Backward compatibility: when evidence_direction_contribution is not
# supplied (the parameter's default, None), _score_candidate() must
# behave EXACTLY as it did before this Phase 1 change — this protects
# every pre-existing caller/test of _score_candidate() that doesn't
# know about evidence_interpretation.py at all.
# ---------------------------------------------------------------------
def test_score_candidate_unchanged_when_direction_contribution_not_supplied():
    engine = make_engine()
    score, components = engine._score_candidate(
        same_plant=False,
        matched_compound="C",
        reference_compound="C",
        match_quality="exact",
        concentration="2 mg/g dry weight",
        extraction="aqueous infusion",
        dosage_form="Infusion",
        co_compounds="X; Y",
        safety_flags="",
        interaction_flags="",
        market_status="Regulatory monograph exists",
        novelty_status="Alternative cross-region candidate",
        target="Hepatoprotective",
        evidence="some evidence",
        evidence_level="Clinical / human evidence",
        compound_plant_count=0,
        target_specificity=None,
    )
    assert components["Evidence quality"] == engine.scoring_config.evidence_clinical


# ---------------------------------------------------------------------
# Contribution table sanity: the reference weights the audit asked to
# be preserved (positive=+24, mixed=+6, null=0, unclear=0, negative=-12
# at the default/current Clinical weight of 24), defined in exactly one
# place (evidence_interpretation.DIRECTION_CONTRIBUTION_RATIO).
# ---------------------------------------------------------------------
def test_direction_contribution_ratio_matches_required_reference_table():
    assert DEFAULT_CLINICAL_WEIGHT == 24
    assert DIRECTION_CONTRIBUTION_RATIO[DIRECTION_POSITIVE] * DEFAULT_CLINICAL_WEIGHT == 24
    assert DIRECTION_CONTRIBUTION_RATIO[DIRECTION_MIXED] * DEFAULT_CLINICAL_WEIGHT == 6
    assert DIRECTION_CONTRIBUTION_RATIO[DIRECTION_NULL] * DEFAULT_CLINICAL_WEIGHT == 0
    assert DIRECTION_CONTRIBUTION_RATIO[DIRECTION_UNCLEAR] * DEFAULT_CLINICAL_WEIGHT == 0
    assert DIRECTION_CONTRIBUTION_RATIO[DIRECTION_NEGATIVE] * DEFAULT_CLINICAL_WEIGHT == -12


# ---------------------------------------------------------------------
# Evidence_Direction allowed-values contract.
# ---------------------------------------------------------------------
def test_evidence_direction_allowed_values_only():
    allowed = {
        DIRECTION_POSITIVE, DIRECTION_NEGATIVE, DIRECTION_NULL,
        DIRECTION_MIXED, DIRECTION_UNCLEAR,
    }
    samples = [
        "A randomized controlled trial demonstrated significant improvement.",
        "A randomized controlled trial failed to demonstrate efficacy.",
        "A randomized controlled trial found no significant difference from placebo.",
        "The primary endpoint was not significant, although secondary outcomes improved.",
        "",
        "An in vitro study showed enzyme inhibition.",
    ]
    for text in samples:
        direction, *_ = classify_evidence_direction(text)
        assert direction in allowed


# ---------------------------------------------------------------------
# Study_Design / Evidence_Direction columns are actually stored on the
# engine's output row (not just computed and discarded).
# ---------------------------------------------------------------------
def test_study_design_and_evidence_direction_are_output_columns():
    assert "Study_Design" in eng.OUTPUT_COLUMNS
    assert "Evidence_Direction" in eng.OUTPUT_COLUMNS


# ---------------------------------------------------------------------
# Follow-up audit — defect #4: Evidence_Quality / Evidence_Applicability
# must also be stored as their own output columns, not just left inside
# the internal EvidenceInterpretation object.
# ---------------------------------------------------------------------
def test_evidence_quality_and_applicability_are_output_columns():
    assert "Evidence_Quality" in eng.OUTPUT_COLUMNS
    assert "Evidence_Applicability" in eng.OUTPUT_COLUMNS


# ---------------------------------------------------------------------
# Follow-up audit — defect #1: a clinical trial PROTOCOL must never be
# treated as a completed study, regardless of which trial design it's
# a protocol FOR.
# ---------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Protocol for a randomized controlled trial.",
    "Protocol for an RCT.",
    "Registered clinical trial protocol.",
    "Clinical trial protocol",
    "Study protocol",
    "Protocol paper",
    "Protocol article",
    "Registered protocol",
    "Trial registration",
    "Study registration",
    "Protocol for a randomized trial",
])
def test_protocol_variants_are_never_completed_clinical_evidence(text):
    interp = interpret_evidence(text)
    assert interp.study_design == STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL
    assert interp.evidence_applicability == APPLICABILITY_CONTEXTUAL_OR_FUTURE
    assert interp.is_completed_study is False
    assert interp.evidence_direction == DIRECTION_UNCLEAR
    assert interp.contribution == 0


def test_protocol_for_an_rct_specifically():
    interp = interpret_evidence("Protocol for an RCT.")
    assert interp.study_design == STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL
    assert interp.is_completed_study is False
    assert interp.contribution == 0


def test_registered_clinical_trial_protocol_specifically():
    interp = interpret_evidence("Registered clinical trial protocol.")
    assert interp.study_design == STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL
    assert interp.evidence_applicability == APPLICABILITY_CONTEXTUAL_OR_FUTURE
    assert interp.is_completed_study is False


# ---------------------------------------------------------------------
# Follow-up audit — defect #2: expanded RCT phrasing must classify as
# STUDY_DESIGN_RCT, but a review merely discussing an RCT must not.
# ---------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "randomized trial",
    "randomised trial",
    "randomized placebo-controlled trial",
    "randomised placebo-controlled trial",
    "randomized double-blind trial",
    "randomised double-blind trial",
    "double blind randomized trial",
    "double blind randomised trial",
    "double-blind randomized clinical trial",
    "double-blind randomised clinical trial",
])
def test_expanded_rct_phrasing_is_classified_as_rct(text):
    assert classify_study_design(text) == STUDY_DESIGN_RCT


def test_bare_randomized_trial_design():
    assert classify_study_design("randomized trial") == STUDY_DESIGN_RCT


def test_randomized_placebo_controlled_trial_design():
    assert classify_study_design("randomized placebo-controlled trial") == STUDY_DESIGN_RCT


def test_double_blind_randomized_clinical_trial_design():
    assert classify_study_design("double-blind randomized clinical trial") == STUDY_DESIGN_RCT


def test_review_discussing_a_randomized_trial_stays_review_after_rct_expansion():
    # Same case as the earlier review test, re-verified after widening
    # the RCT phrase list — review priority must still win.
    text = "This review discusses a randomized trial that reported improvement."
    assert classify_study_design(text) == STUDY_DESIGN_REVIEW
    assert classify_study_design(text) != STUDY_DESIGN_RCT


# ---------------------------------------------------------------------
# Follow-up audit — defect #3: Evidence_Confidence must consult the new
# Study_Design/Evidence_Direction/Evidence_Applicability/
# is_completed_study fields, end to end through the real engine.
# ---------------------------------------------------------------------
def test_evidence_confidence_uses_new_fields_end_to_end():
    from evidence_confidence import compute_evidence_confidence

    def confidence_for(text):
        interp = interpret_evidence(text)
        return compute_evidence_confidence(
            evidence_hierarchy_detail="Clinical trial",
            evidence_level="Clinical / human evidence",
            has_negative_evidence=False,
            evidence_text=text,
            evidence_direction=interp.evidence_direction,
            evidence_applicability=interp.evidence_applicability,
            is_completed_study=interp.is_completed_study,
            study_design=interp.study_design,
        )

    positive_confidence = confidence_for(
        "A randomized controlled trial demonstrated significant improvement."
    )
    null_confidence = confidence_for(
        "A randomized controlled trial found no significant difference from placebo."
    )
    negative_confidence = confidence_for("A clinical trial failed to demonstrate efficacy.")
    future_confidence = confidence_for("Clinical trial is needed.")
    protocol_confidence = confidence_for("Clinical trial protocol suggests a benefit.")

    assert positive_confidence == 85.0
    assert null_confidence < positive_confidence
    assert negative_confidence < positive_confidence
    assert future_confidence <= 10.0
    assert protocol_confidence <= 10.0


def test_no_significant_difference_from_placebo_in_a_randomized_trial():
    interp = interpret_evidence("No significant difference from placebo in a randomized trial.")
    assert interp.evidence_direction == DIRECTION_NULL


def test_trial_failed_to_demonstrate_efficacy():
    interp = interpret_evidence("Trial failed to demonstrate efficacy.")
    assert interp.evidence_direction == DIRECTION_NEGATIVE


# ---------------------------------------------------------------------
# Regression — every core Phase 1 behavior must still hold after the
# protocol/RCT-detection expansion above.
# ---------------------------------------------------------------------
def test_regression_positive_rct_still_positive():
    text = "A randomized controlled trial demonstrated significant improvement."
    assert classify_study_design(text) == STUDY_DESIGN_RCT
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_POSITIVE
    assert interpret_evidence(text).contribution == pytest.approx(24.0)


def test_regression_negative_rct_still_negative():
    text = "A randomized controlled trial failed to demonstrate efficacy."
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_NEGATIVE
    assert interpret_evidence(text).contribution == pytest.approx(-12.0)


def test_regression_null_rct_still_null():
    text = "A randomized controlled trial found no significant difference from placebo."
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_NULL
    assert interpret_evidence(text).contribution == 0


def test_regression_mixed_rct_still_mixed():
    text = (
        "A randomized controlled trial found the primary endpoint was "
        "not significant, although some secondary outcomes improved."
    )
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_MIXED
    assert interpret_evidence(text).contribution == pytest.approx(6.0)


def test_regression_animal_study_still_animal_study():
    assert classify_study_design(
        "An animal model study in mice showed reduced inflammation."
    ) == STUDY_DESIGN_ANIMAL_STUDY


def test_regression_in_vitro_still_in_vitro():
    assert classify_study_design(
        "An in vitro study showed enzyme inhibition."
    ) == STUDY_DESIGN_IN_VITRO_STUDY


def test_regression_future_mention_still_contextual():
    interp = interpret_evidence("A clinical trial is needed to evaluate efficacy.")
    assert interp.evidence_applicability == APPLICABILITY_CONTEXTUAL_OR_FUTURE
    assert interp.contribution == 0


def test_regression_protocol_still_contextual():
    interp = interpret_evidence("This is a clinical trial protocol for evaluating chamomile.")
    assert interp.study_design == STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL
    assert interp.evidence_applicability == APPLICABILITY_CONTEXTUAL_OR_FUTURE
    assert interp.contribution == 0


def test_regression_review_still_review():
    text = "This review discusses a randomized trial that reported improvement."
    assert classify_study_design(text) == STUDY_DESIGN_REVIEW


def test_regression_conflicting_evidence_still_mixed():
    text = (
        "One trial found the treatment significantly improved symptoms, "
        "while another trial reported the treatment worsened outcomes."
    )
    direction, *_ = classify_evidence_direction(text)
    assert direction == DIRECTION_MIXED
