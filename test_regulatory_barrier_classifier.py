"""Regression tests for regulatory_barrier_classifier.py (architecture audit Q8)."""

from regulatory_barrier_classifier import classify_regulatory_barriers


def test_banned_is_detected():
    result = classify_regulatory_barriers("This plant is banned for sale in the EU due to safety concerns.")
    assert result.has_barrier
    assert "Prohibited / banned" in result.barrier_types


def test_prescription_only_is_detected():
    result = classify_regulatory_barriers("This extract is available on a prescription only basis.")
    assert result.has_barrier
    assert "Restricted access (prescription/controlled)" in result.barrier_types


def test_novel_food_requirement_is_detected():
    result = classify_regulatory_barriers("This ingredient is classified as a novel food requiring authorization.")
    assert result.has_barrier
    assert "Novel food / pre-market approval required" in result.barrier_types


def test_import_restriction_is_detected():
    result = classify_regulatory_barriers("The species is CITES-listed and import restricted in most markets.")
    assert result.has_barrier
    assert "Import / export restriction" in result.barrier_types


def test_multiple_barrier_types_can_be_detected_at_once():
    result = classify_regulatory_barriers(
        "This is a controlled substance and is also banned for over-the-counter sale."
    )
    assert "Restricted access (prescription/controlled)" in result.barrier_types
    assert "Prohibited / banned" in result.barrier_types


def test_negated_mentions_are_not_flagged():
    result = classify_regulatory_barriers("This plant is not banned and has no import restriction in the EU.")
    assert not result.has_barrier


def test_positive_regulatory_recognition_alone_is_not_a_barrier():
    # A monograph existing is the OPPOSITE finding from a barrier — text
    # about regulatory recognition with no restriction language should
    # not be flagged.
    result = classify_regulatory_barriers("The EMA/HMPC monograph recognizes well-established use for this indication.")
    assert not result.has_barrier


def test_empty_or_none_text_has_no_barrier():
    assert classify_regulatory_barriers("").has_barrier is False
    assert classify_regulatory_barriers(None).has_barrier is False


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
