"""Regression tests for evidence_confidence.py (Phase 6, audit 4.16)."""

from evidence_confidence import (
    compute_evidence_confidence,
    confidence_adjusted_framing_note,
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
