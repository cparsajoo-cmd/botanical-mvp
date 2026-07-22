"""Regression tests for negative_evidence_classifier.py (Phase 4, audit 4.15)."""

from negative_evidence_classifier import classify_negative_evidence


def test_failed_trial_is_detected():
    result = classify_negative_evidence(
        "The randomized controlled trial failed to demonstrate efficacy "
        "compared to placebo."
    )
    assert result.is_negative
    assert "Failed trial" in result.finding_types


def test_null_result_is_detected():
    result = classify_negative_evidence(
        "There was no significant difference between the treatment and "
        "placebo groups at 12 weeks."
    )
    assert result.is_negative
    assert "Null result" in result.finding_types


def test_retraction_is_detected():
    result = classify_negative_evidence("This article was retracted in 2021 due to data integrity concerns.")
    assert result.is_negative
    assert "Retraction" in result.finding_types


def test_contradictory_study_is_detected():
    result = classify_negative_evidence(
        "These findings contradict earlier reports of hepatoprotective activity."
    )
    assert result.is_negative
    assert "Contradictory study" in result.finding_types


def test_poor_quality_study_is_detected():
    result = classify_negative_evidence(
        "The study had a high risk of bias and an underpowered study design."
    )
    assert result.is_negative
    assert "Poor-quality study" in result.finding_types


def test_a_study_can_match_more_than_one_category():
    result = classify_negative_evidence(
        "This article was retracted after the trial failed to demonstrate "
        "efficacy and showed no significant difference from placebo."
    )
    assert "Retraction" in result.finding_types
    assert "Failed trial" in result.finding_types
    assert "Null result" in result.finding_types
    assert len(result.finding_types) == 3


def test_positive_evidence_is_not_flagged_negative():
    result = classify_negative_evidence(
        "The randomized controlled trial demonstrated a significant "
        "improvement in symptoms compared to placebo."
    )
    assert not result.is_negative
    assert result.finding_types == []


def test_negated_negative_phrasing_does_not_false_flag():
    result = classify_negative_evidence(
        "No retraction has been issued and there is no evidence of a null result."
    )
    assert not result.is_negative, (
        "double-negated phrasing ('no retraction', 'no evidence of a null "
        "result') must not itself be flagged as a negative finding"
    )


def test_empty_or_none_text_is_not_negative():
    assert classify_negative_evidence("").is_negative is False
    assert classify_negative_evidence(None).is_negative is False


def test_matched_phrases_are_returned_for_traceability():
    result = classify_negative_evidence("The trial failed to demonstrate efficacy.")
    assert result.matched_phrases, "a positive match should record which phrase triggered it"
    assert any("fail" in phrase for phrase in result.matched_phrases)


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
