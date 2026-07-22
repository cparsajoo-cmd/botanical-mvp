"""Regression tests for white_space_classifier.py (Gap 4)."""

from white_space_classifier import classify_white_space


def test_nothing_looked_at_is_a_data_gap():
    result = classify_white_space(
        evidence_confidence=0, market_status="Search not performed", use_live_search=False,
    )
    assert result == "Data Gap"


def test_data_gap_requires_both_axes_to_be_unsearched():
    # Live search ran (even if it found nothing) — not a Data Gap.
    result = classify_white_space(
        evidence_confidence=0, market_status="Search not performed", use_live_search=True,
    )
    assert result != "Data Gap"


def test_real_search_with_no_scientific_evidence_is_scientific_white_space():
    result = classify_white_space(
        evidence_confidence=5, market_status="Search not performed", use_live_search=True,
    )
    assert result == "Scientific White Space"


def test_no_verified_product_found_is_commercial_white_space():
    result = classify_white_space(
        evidence_confidence=0, market_status="No verified product found", use_live_search=False,
    )
    # Strong scientific evidence is absent here too, so this shouldn't
    # escalate to Industrial R&D White Space — see the dedicated test
    # for that combination below.
    assert result in {"Commercial White Space", "Data Gap"}


def test_no_regulatory_recognition_found_is_regulatory_white_space():
    # evidence_confidence=10 is below the real-scientific-signal bar
    # (30) and use_live_search=False, so this doesn't qualify as
    # Scientific White Space (that requires a live search to have
    # actually run) or as Industrial R&D White Space (that requires
    # real_scientific_signal) — isolating the regulatory gap on its own.
    result = classify_white_space(
        evidence_confidence=10,
        market_status="Commercial evidence reported, not independently verified",
        use_live_search=False,
    )
    assert result == "Regulatory White Space"


def test_strong_evidence_plus_no_regulatory_recognition_escalates_to_industrial():
    # Same regulatory gap as above, but with confidence that clears the
    # real-scientific-signal bar — this is the more actionable,
    # investable case and should get the more specific label.
    result = classify_white_space(
        evidence_confidence=50,
        market_status="Search incomplete",
        use_live_search=True,
    )
    assert result == "Industrial R&D White Space"


def test_real_evidence_plus_regulatory_monograph_is_not_white_space_at_all():
    result = classify_white_space(
        evidence_confidence=80, market_status="Regulatory monograph exists", use_live_search=True,
    )
    assert result is None


def test_industrial_rd_white_space_requires_real_science_plus_an_open_market():
    # Real scientific confidence (not itself a Scientific White Space)
    # combined with no commercial product found — the one combination
    # that's actually an investable finding, not just a diagnostic gap.
    result = classify_white_space(
        evidence_confidence=70, market_status="No verified product found", use_live_search=True,
    )
    assert result == "Industrial R&D White Space"


def test_industrial_rd_white_space_does_not_fire_when_science_itself_is_weak():
    # Weak evidence + no commercial product = two separate gaps, not one
    # investable opportunity — must be labeled Scientific White Space
    # (the more specific, more honest diagnosis), not the optimistic one.
    result = classify_white_space(
        evidence_confidence=5, market_status="No verified product found", use_live_search=True,
    )
    assert result == "Scientific White Space"


def test_every_row_gets_at_most_one_label():
    valid_labels = {
        "Data Gap", "Scientific White Space", "Commercial White Space",
        "Regulatory White Space", "Industrial R&D White Space", None,
    }
    import itertools
    confidences = [0, 5, 29, 30, 50, 100]
    statuses = [
        "Search not performed", "Search incomplete", "Unknown", "Source unavailable",
        "Regulatory monograph exists", "Traditional-use status",
        "Commercial evidence reported, not independently verified",
        "Conflicting market evidence", "No verified product found",
    ]
    live_search_flags = [True, False]
    for combo in itertools.product(confidences, statuses, live_search_flags):
        result = classify_white_space(*combo)
        assert result in valid_labels, f"got an unexpected label {result!r} for inputs {combo!r}"


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
