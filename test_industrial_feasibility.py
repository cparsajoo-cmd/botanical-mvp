"""Regression tests for industrial_feasibility.py (architecture audit Q9)."""

from industrial_feasibility import classify_industrial_feasibility


def test_no_extraction_method_is_not_assessed():
    result = classify_industrial_feasibility(extraction_fit_score=3, has_concentration_data=False)
    assert result.startswith("Not assessed")


def test_low_score_is_low_feasibility():
    result = classify_industrial_feasibility(extraction_fit_score=8, has_concentration_data=True)
    assert result.startswith("Low feasibility")


def test_moderate_score_is_moderate_feasibility():
    result = classify_industrial_feasibility(extraction_fit_score=16, has_concentration_data=True)
    assert result.startswith("Moderate feasibility")


def test_high_score_is_high_feasibility():
    result = classify_industrial_feasibility(extraction_fit_score=26, has_concentration_data=True)
    assert result.startswith("High feasibility")


def test_missing_concentration_data_is_noted_even_with_a_good_extraction_match():
    result = classify_industrial_feasibility(extraction_fit_score=26, has_concentration_data=False)
    assert "concentration not quantified" in result


def test_present_concentration_data_does_not_trigger_the_caveat():
    result = classify_industrial_feasibility(extraction_fit_score=26, has_concentration_data=True)
    assert "concentration not quantified" not in result


def test_thresholds_are_monotonic_as_score_increases():
    scores = [3, 8, 14, 20, 30]
    labels = [classify_industrial_feasibility(s, True) for s in scores]
    tiers = []
    for label in labels:
        if label.startswith("Not assessed"):
            tiers.append(0)
        elif label.startswith("Low"):
            tiers.append(1)
        elif label.startswith("Moderate"):
            tiers.append(2)
        else:
            tiers.append(3)
    assert tiers == sorted(tiers), f"feasibility tiers are not monotonic: {tiers}"


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
