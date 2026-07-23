"""Regression tests for decision_class_ah.py (Phase 6, audit 4.7)."""

from decision_class_ah import classify_decision_ah


def test_safety_concern_always_maps_to_h_regardless_of_other_signals():
    result = classify_decision_ah(
        existing_decision_class="Safety concern — not suitable without expert review",
        evidence_confidence=95, rd_opportunity_score=95,
        market_status="Verified marketed product", match_quality="exact", same_plant=False,
    )
    assert result == "H — No-go / safety concern", (
        "a hard safety exclusion must override every other signal, even a "
        "high score or verified market status"
    )


def test_verified_marketed_product_maps_to_a():
    result = classify_decision_ah(
        existing_decision_class="Strong R&D candidate",
        evidence_confidence=80, rd_opportunity_score=80,
        market_status="Verified marketed product", match_quality="exact", same_plant=False,
    )
    assert result == "A — Verified commercial route"


def test_same_plant_with_real_evidence_maps_to_b():
    result = classify_decision_ah(
        existing_decision_class="Strong R&D candidate",
        evidence_confidence=50, rd_opportunity_score=70,
        market_status="Search not performed", match_quality="exact", same_plant=True,
    )
    assert result == "B — Established scientific candidate"


def test_alternative_plant_exact_match_with_real_evidence_maps_to_c():
    result = classify_decision_ah(
        existing_decision_class="Promising candidate; verify safety and standardization",
        evidence_confidence=45, rd_opportunity_score=70,
        market_status="Search not performed", match_quality="exact", same_plant=False,
    )
    assert result == "C — Alternative-source R&D candidate"


def test_target_verified_match_with_weak_evidence_but_real_opportunity_maps_to_d():
    result = classify_decision_ah(
        existing_decision_class="Early-stage candidate; more evidence needed",
        evidence_confidence=10, rd_opportunity_score=50,
        market_status="Search not performed", match_quality="target_verified", same_plant=False,
    )
    assert result == "D — Mechanism-based R&D candidate"


def test_high_opportunity_low_confidence_maps_to_f_exploratory():
    # The exact mismatch this whole phase exists to catch.
    result = classify_decision_ah(
        existing_decision_class="Strong R&D candidate",
        evidence_confidence=5, rd_opportunity_score=90,
        market_status="Search not performed", match_quality="exact", same_plant=False,
    )
    assert result == "F — Exploratory hypothesis"


def test_no_verified_product_found_with_real_evidence_maps_to_e():
    result = classify_decision_ah(
        existing_decision_class="Early-stage candidate; more evidence needed",
        evidence_confidence=40, rd_opportunity_score=50,
        market_status="No verified product found", match_quality="class_only", same_plant=False,
    )
    assert result == "E — White-space opportunity"


def test_weak_everything_falls_back_to_g_hold():
    result = classify_decision_ah(
        existing_decision_class="Low priority / insufficient data",
        evidence_confidence=5, rd_opportunity_score=20,
        market_status="Search not performed", match_quality="class_only", same_plant=False,
    )
    assert result == "G — Hold / insufficient evidence"


def test_target_verified_match_with_strong_evidence_maps_to_c_not_hold():
    # The exact bug found via an end-to-end smoke test: a
    # target_verified match with confidence high enough to clear the
    # "real evidence" bar (>= MODEST_CONFIDENCE_THRESHOLD) used to match
    # neither C (which required match_quality == "exact" only) nor D
    # (which requires LOW confidence) — it fell through every rule and
    # wrongly landed in G/Hold, misclassifying a genuinely strong
    # candidate as "insufficient evidence."
    result = classify_decision_ah(
        existing_decision_class="Promising candidate; verify safety and standardization",
        evidence_confidence=85, rd_opportunity_score=72,
        market_status="Commercial evidence reported, not independently verified",
        match_quality="target_verified", same_plant=False,
    )
    assert result == "C — Alternative-source R&D candidate", (
        f"a target_verified match with strong evidence (85) wrongly fell through to {result!r}"
    )


def test_every_candidate_gets_exactly_one_of_the_eight_classes():
    valid_classes = {
        "A — Verified commercial route",
        "B — Established scientific candidate",
        "C — Alternative-source R&D candidate",
        "D — Mechanism-based R&D candidate",
        "E — White-space opportunity",
        "F — Exploratory hypothesis",
        "G — Hold / insufficient evidence",
        "H — No-go / safety concern",
    }
    import itertools
    decisions = ["Strong R&D candidate", "Low priority / insufficient data", "Safety concern — not suitable without expert review"]
    confidences = [0, 20, 50, 90]
    opportunities = [10, 50, 80]
    markets = ["Search not performed", "No verified product found", "Verified marketed product"]
    qualities = ["exact", "target_verified", "class_only"]
    same_plants = [True, False]

    for combo in itertools.product(decisions, confidences, opportunities, markets, qualities, same_plants):
        result = classify_decision_ah(*combo)
        assert result in valid_classes, f"got an invalid class {result!r} for inputs {combo!r}"


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
