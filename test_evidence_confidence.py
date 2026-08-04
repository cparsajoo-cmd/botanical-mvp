"""Regression tests for evidence_confidence.py (Phase 6, audit 4.16)."""

from evidence_confidence import (
    compute_evidence_confidence,
    confidence_adjusted_framing_note,
    _detect_sample_size_modifier,
    _detect_blinding_modifier,
    _detect_placebo_control_modifier,
    _methodological_quality_modifier,
    MAX_METHODOLOGICAL_MODIFIER_TOTAL,
    SAMPLE_SIZE_CONFIDENCE_MODIFIERS,
    BLINDING_CONFIDENCE_MODIFIERS,
    PLACEBO_CONTROL_CONFIDENCE_MODIFIER,
)


def test_systematic_review_scores_highest():
    conf = compute_evidence_confidence(
        evidence_hierarchy_detail="Systematic review / meta-analysis",
        evidence_level="Clinical / human evidence",
        has_negative_evidence=False,
    )
    assert conf == 100.0


def test_hierarchy_tiers_rank_in_the_expected_order():
    tiers_strongest_first = [
        "Systematic review / meta-analysis",
        "Clinical trial",
        "Observational human evidence",
        "Validated ex vivo / in vivo",
        "In vitro / mechanistic",
        "Traditional-use / regulatory monograph",
        "Occurrence / analytical chemistry only",
    ]
    scores = [
        compute_evidence_confidence(tier, "General literature signal", False)
        for tier in tiers_strongest_first
    ]
    assert scores == sorted(scores, reverse=True), (
        f"confidence scores are not monotonically decreasing by tier: {scores}"
    )


def test_falls_back_to_evidence_level_when_no_hierarchy_tier_classified():
    conf = compute_evidence_confidence(
        evidence_hierarchy_detail=None,
        evidence_level="Regulatory / monograph evidence",
        has_negative_evidence=False,
    )
    assert conf == 40.0


def test_no_evidence_at_all_scores_zero():
    conf = compute_evidence_confidence(
        evidence_hierarchy_detail=None,
        evidence_level="No direct evidence",
        has_negative_evidence=False,
    )
    assert conf == 0.0


def test_negative_evidence_substantially_reduces_but_does_not_zero_confidence():
    without_negative = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", has_negative_evidence=False,
    )
    with_negative = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", has_negative_evidence=True,
    )
    assert with_negative < without_negative
    assert with_negative > 0, (
        "a negative finding should substantially undercut confidence, not "
        "necessarily zero it — a single negative result can coexist with "
        "other positive evidence about the same candidate"
    )


def test_confidence_never_exceeds_100_or_drops_below_0():
    conf = compute_evidence_confidence("Systematic review / meta-analysis", "Clinical / human evidence", False)
    assert 0 <= conf <= 100


def test_high_opportunity_low_confidence_triggers_exploratory_note():
    note = confidence_adjusted_framing_note(rd_opportunity_score=85.0, evidence_confidence=15.0)
    assert note is not None
    assert "Exploratory" in note


def test_high_opportunity_high_confidence_does_not_trigger_note():
    note = confidence_adjusted_framing_note(rd_opportunity_score=85.0, evidence_confidence=90.0)
    assert note is None


def test_low_opportunity_low_confidence_does_not_trigger_the_exploratory_note():
    # Low opportunity is already appropriately deprioritized on its own
    # merits — the note exists specifically for the MISMATCH case, not
    # for "everything about this candidate is weak."
    note = confidence_adjusted_framing_note(rd_opportunity_score=20.0, evidence_confidence=10.0)
    assert note is None


def test_missing_scores_do_not_crash_the_note_function():
    assert confidence_adjusted_framing_note(None, 50.0) is None
    assert confidence_adjusted_framing_note(50.0, None) is None
    assert confidence_adjusted_framing_note(None, None) is None


# ---------------------------------------------------------------------
# Task 10.1 — sample-size modifier
# ---------------------------------------------------------------------

def test_sample_size_modifier_detects_n_equals_notation():
    assert _detect_sample_size_modifier("A trial with n = 250 patients.") == 6


def test_sample_size_modifier_detects_patients_phrasing():
    assert _detect_sample_size_modifier("A study enrolling 150 patients.") == 4


def test_sample_size_modifier_detects_sample_size_of_phrasing():
    assert _detect_sample_size_modifier("With a sample size of 45 participants.") == 2


def test_sample_size_modifier_zero_below_smallest_band():
    assert _detect_sample_size_modifier("A study with 12 subjects.") == 0


def test_sample_size_modifier_zero_when_no_number_present():
    assert _detect_sample_size_modifier("A study with no reported sample size.") == 0


def test_sample_size_modifier_zero_on_empty_or_none_text():
    assert _detect_sample_size_modifier("") == 0
    assert _detect_sample_size_modifier(None) == 0


def test_sample_size_modifier_uses_the_largest_number_found():
    # If more than one number is mentioned (e.g. an enrollment number
    # and an unrelated dosage number), the largest match wins — this
    # is a plain-text heuristic, not a structured extraction, so it
    # errs toward the strongest plausible signal.
    assert _detect_sample_size_modifier("Dosed at 5mg, n = 300 patients enrolled.") == 6


def test_sample_size_modifier_thresholds_match_documented_bands():
    assert SAMPLE_SIZE_CONFIDENCE_MODIFIERS == [(200, 6), (100, 4), (30, 2)]


# ---------------------------------------------------------------------
# Task 10.1 — blinding modifier
# ---------------------------------------------------------------------

def test_blinding_modifier_detects_double_blind():
    assert _detect_blinding_modifier("A double-blind study.") == 5


def test_blinding_modifier_detects_double_blind_no_hyphen():
    assert _detect_blinding_modifier("A double blind trial.") == 5


def test_blinding_modifier_detects_triple_blind():
    assert _detect_blinding_modifier("A triple-blind design.") == 5


def test_blinding_modifier_detects_single_blind():
    assert _detect_blinding_modifier("A single-blind study.") == 3


def test_blinding_modifier_prefers_double_over_single_when_both_mentioned():
    text = "One arm was single-blind, another was double-blind."
    assert _detect_blinding_modifier(text) == 5


def test_blinding_modifier_zero_when_not_mentioned():
    assert _detect_blinding_modifier("An open-label study.") == 0


def test_blinding_modifier_zero_on_empty_or_none_text():
    assert _detect_blinding_modifier("") == 0
    assert _detect_blinding_modifier(None) == 0


def test_blinding_modifier_values_match_documented_constants():
    assert BLINDING_CONFIDENCE_MODIFIERS == {
        "double_or_triple_blind": 5,
        "single_blind": 3,
    }


# ---------------------------------------------------------------------
# Task 10.1 — placebo-control modifier
# ---------------------------------------------------------------------

def test_placebo_modifier_detects_placebo_controlled():
    assert _detect_placebo_control_modifier("A placebo-controlled trial.") == PLACEBO_CONTROL_CONFIDENCE_MODIFIER


def test_placebo_modifier_detects_vs_placebo_phrasing():
    assert _detect_placebo_control_modifier("Active treatment vs placebo.") == PLACEBO_CONTROL_CONFIDENCE_MODIFIER


def test_placebo_modifier_zero_when_not_mentioned():
    assert _detect_placebo_control_modifier("An uncontrolled observational study.") == 0


def test_placebo_modifier_zero_on_empty_or_none_text():
    assert _detect_placebo_control_modifier("") == 0
    assert _detect_placebo_control_modifier(None) == 0


def test_placebo_modifier_constant_value():
    assert PLACEBO_CONTROL_CONFIDENCE_MODIFIER == 4


# ---------------------------------------------------------------------
# Task 10.1 — combined modifier (capped total)
# ---------------------------------------------------------------------

def test_combined_modifier_sums_all_three():
    text = "A double-blind, placebo-controlled trial with n = 250 patients."
    # 6 (sample size) + 5 (blinding) + 4 (placebo) = 15
    assert _methodological_quality_modifier(text) == 15


def test_combined_modifier_is_capped_at_documented_maximum():
    text = "A double-blind, placebo-controlled trial with n = 500 patients."
    assert _methodological_quality_modifier(text) <= MAX_METHODOLOGICAL_MODIFIER_TOTAL
    assert _methodological_quality_modifier(text) == MAX_METHODOLOGICAL_MODIFIER_TOTAL


def test_combined_modifier_zero_for_plain_text():
    assert _methodological_quality_modifier("A general discussion of the plant's traditional uses.") == 0


# ---------------------------------------------------------------------
# Task 10.1 — wiring into compute_evidence_confidence()
# ---------------------------------------------------------------------

def test_compute_evidence_confidence_backward_compatible_without_evidence_text():
    # Every pre-Task-10.1 call site/test that doesn't pass evidence_text
    # must produce byte-identical results to before this task.
    conf = compute_evidence_confidence(
        evidence_hierarchy_detail="Clinical trial",
        evidence_level="Clinical / human evidence",
        has_negative_evidence=False,
    )
    assert conf == 85.0


def test_compute_evidence_confidence_applies_modifiers_when_text_provided():
    conf = compute_evidence_confidence(
        evidence_hierarchy_detail="Clinical trial",
        evidence_level="Clinical / human evidence",
        has_negative_evidence=False,
        evidence_text="A double-blind, placebo-controlled trial with n = 250 patients.",
    )
    # 85 (Clinical trial tier) + 15 (capped combined modifier) = 100
    assert conf == 100.0


def test_compute_evidence_confidence_never_decreases_from_evidence_text():
    # The core backward-compatibility guarantee: adding evidence_text
    # can only raise or leave unchanged a confidence score relative to
    # not passing it — modifiers are purely additive and only applied
    # when a real tier was already found.
    without_text = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
    )
    with_unhelpful_text = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_text="A general discussion with no methodology details.",
    )
    with_helpful_text = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_text="A double-blind, placebo-controlled trial with n = 300 patients.",
    )
    assert with_unhelpful_text >= without_text
    assert with_helpful_text >= with_unhelpful_text


def test_compute_evidence_confidence_modifiers_not_applied_when_no_real_tier():
    # No evidence at all (base = 0) must stay 0 even if the text
    # somehow contains methodology keywords (e.g. leftover boilerplate
    # text) — modifiers must never manufacture confidence out of
    # nothing.
    conf = compute_evidence_confidence(
        evidence_hierarchy_detail=None,
        evidence_level="No direct evidence",
        has_negative_evidence=False,
        evidence_text="double-blind placebo-controlled n = 500 patients",
    )
    assert conf == 0.0


def test_compute_evidence_confidence_modifiers_applied_before_negative_multiplier():
    # A well-blinded, placebo-controlled, large trial that FAILED
    # (negative finding) still earns the methodological-quality
    # modifiers — they describe study design, not outcome — and is
    # then downweighted overall for the negative result, same as
    # before this task.
    text = "A double-blind, placebo-controlled trial with n = 250 patients found no significant effect."
    conf = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", has_negative_evidence=True,
        evidence_text=text,
    )
    # (85 + 15) * 0.4 = 40.0
    assert conf == 40.0


def test_compute_evidence_confidence_still_clamped_to_100():
    conf = compute_evidence_confidence(
        "Systematic review / meta-analysis", "Clinical / human evidence", False,
        evidence_text="A double-blind, placebo-controlled trial with n = 500 patients.",
    )
    assert conf == 100.0


def test_compute_evidence_confidence_default_evidence_text_is_none():
    import inspect
    sig = inspect.signature(compute_evidence_confidence)
    assert sig.parameters["evidence_text"].default is None


# ---------------------------------------------------------------------
# Phase 1 follow-up (evidence_interpretation.py awareness) — Study_Design /
# Evidence_Direction / Evidence_Applicability / is_completed_study must
# now be able to influence Evidence_Confidence, on top of the existing
# Evidence_Level/hierarchy-tier logic above (which stays completely
# unchanged for any caller that doesn't pass the new keywords — see the
# backward-compatibility tests already above this section).
# ---------------------------------------------------------------------
from evidence_interpretation import interpret_evidence


def _confidence_from_text(
    text,
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="Clinical trial",
    has_negative_evidence=False,
):
    """Runs the real interpret_evidence() -> compute_evidence_confidence()
    path, exactly as botanical_rd_candidate_engine.py now wires them
    together, rather than hand-picking direction/applicability values."""
    interp = interpret_evidence(text)
    confidence = compute_evidence_confidence(
        evidence_hierarchy_detail=evidence_hierarchy_detail,
        evidence_level=evidence_level,
        has_negative_evidence=has_negative_evidence,
        evidence_text=text,
        evidence_direction=interp.evidence_direction,
        evidence_applicability=interp.evidence_applicability,
        is_completed_study=interp.is_completed_study,
        study_design=interp.study_design,
    )
    return confidence, interp


def test_evidence_confidence_decreases_for_protocol():
    baseline, _ = _confidence_from_text(
        "A randomized controlled trial demonstrated significant improvement."
    )
    protocol_confidence, interp = _confidence_from_text(
        "Protocol for a randomized controlled trial."
    )
    assert interp.study_design == "clinical_trial_protocol"
    assert interp.is_completed_study is False
    assert protocol_confidence < baseline
    assert protocol_confidence <= 10.0


def test_evidence_confidence_decreases_for_future_trial():
    baseline, _ = _confidence_from_text(
        "A randomized controlled trial demonstrated significant improvement."
    )
    future_confidence, interp = _confidence_from_text(
        "A clinical trial is needed to evaluate efficacy."
    )
    assert interp.evidence_applicability == "contextual_or_future"
    assert future_confidence < baseline
    assert future_confidence <= 10.0


def test_evidence_confidence_decreases_for_null_rct():
    positive_confidence, _ = _confidence_from_text(
        "A randomized controlled trial demonstrated significant improvement."
    )
    null_confidence, interp = _confidence_from_text(
        "A randomized controlled trial found no significant difference from placebo."
    )
    assert interp.evidence_direction == "null"
    assert null_confidence < positive_confidence


def test_evidence_confidence_decreases_for_negative_rct():
    positive_confidence, _ = _confidence_from_text(
        "A randomized controlled trial demonstrated significant improvement."
    )
    negative_confidence, interp = _confidence_from_text(
        "A clinical trial failed to demonstrate efficacy."
    )
    assert interp.evidence_direction == "negative"
    assert negative_confidence < positive_confidence


def test_evidence_confidence_not_inflated_by_bare_clinical_trial_phrase_when_direction_unclear():
    # "Clinical trial protocol suggests..." contains the phrase
    # "clinical trial" but is neither a completed study nor a positive
    # finding — confidence must not reach anywhere near the 85-point
    # "Clinical trial" tier baseline.
    confidence, interp = _confidence_from_text("Clinical trial protocol suggests a benefit.")
    assert interp.study_design == "clinical_trial_protocol"
    assert confidence <= 10.0


def test_evidence_confidence_positive_rct_is_unaffected_by_new_signals():
    # A genuinely positive, completed RCT must still score at the full
    # "Clinical trial" tier baseline (85) — the new signals must never
    # penalize a real, positive, completed study.
    confidence, interp = _confidence_from_text(
        "A randomized controlled trial demonstrated significant improvement."
    )
    assert interp.evidence_direction == "positive"
    assert interp.is_completed_study is True
    assert confidence == 85.0


def test_compute_evidence_confidence_backward_compatible_without_new_kwargs():
    # No evidence_direction/evidence_applicability/is_completed_study/
    # study_design supplied at all -> identical to the function's
    # behavior before this section existed.
    confidence = compute_evidence_confidence(
        evidence_hierarchy_detail="Clinical trial",
        evidence_level="Clinical / human evidence",
        has_negative_evidence=False,
    )
    assert confidence == 85.0


if __name__ == "__main__":
    import sys

    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        this_module = sys.modules[__name__]
        test_fns = [
            getattr(this_module, name)
            for name in dir(this_module)
            if name.startswith("test_") and callable(getattr(this_module, name))
        ]
        passed, failed = [], []
        for fn in test_fns:
            try:
                fn()
            except AssertionError as exc:
                failed.append((fn.__name__, str(exc) or "assertion failed"))
            except Exception as exc:  # noqa: BLE001
                failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            else:
                passed.append(fn.__name__)
        print(f"\n{len(passed) + len(failed)} test(s) run.\n")
        for name in passed:
            print(f"  \u2705 {name}")
        if failed:
            print()
            for name, reason in failed:
                print(f"  \u274c {name}\n     -> {reason}")
            print(f"\n{len(failed)} FAILED, {len(passed)} passed.\n")
            sys.exit(1)
        print(f"\nALL TESTS PASSED ({len(passed)}/{len(passed)}).\n")
        sys.exit(0)


# ---------------------------------------------------------------------
# Phase 1 follow-up — direct Evidence_Quality modifier
# ---------------------------------------------------------------------
def test_evidence_quality_high_keeps_confidence_unchanged():
    baseline = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False
    )
    with_high = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_quality="high",
    )
    assert with_high == baseline


def test_evidence_quality_moderate_slightly_reduces_confidence():
    baseline = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False
    )
    with_moderate = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_quality="moderate",
    )
    assert with_moderate == round(baseline * 0.95, 1)
    assert with_moderate < baseline


def test_evidence_quality_low_reduces_confidence():
    baseline = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False
    )
    with_low = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_quality="low",
    )
    assert with_low == round(baseline * 0.85, 1)
    assert with_low < baseline


def test_evidence_quality_unknown_preserves_backward_compatibility():
    baseline = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False
    )
    with_unknown = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_quality="unknown",
    )
    assert with_unknown == baseline


def test_omitting_evidence_quality_preserves_previous_behaviour_exactly():
    omitted = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_text="A double-blind, placebo-controlled trial with n = 250 patients.",
        evidence_direction="positive",
        evidence_applicability="direct_reported",
        is_completed_study=True,
        study_design="randomized_controlled_trial",
    )
    explicit_none = compute_evidence_confidence(
        "Clinical trial", "Clinical / human evidence", False,
        evidence_text="A double-blind, placebo-controlled trial with n = 250 patients.",
        evidence_direction="positive",
        evidence_applicability="direct_reported",
        is_completed_study=True,
        study_design="randomized_controlled_trial",
        evidence_quality=None,
    )
    assert omitted == explicit_none == 100.0
