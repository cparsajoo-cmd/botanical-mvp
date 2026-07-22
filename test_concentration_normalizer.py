"""Regression tests for concentration_normalizer.py (Phase 4, audit 4.10)."""

from concentration_normalizer import (
    parse_concentration,
    are_comparable,
    format_concentration_info,
)


def test_explicit_dry_weight_basis_is_detected():
    parsed = parse_concentration("The extract contained 3.5 mg/g dry weight of silymarin.")
    assert len(parsed) == 1
    assert parsed[0].value == 3.5
    assert parsed[0].basis == "mg/g dry weight"
    assert parsed[0].basis_is_explicit


def test_extract_basis_and_percent_extract_are_detected():
    parsed = parse_concentration("Standardized to 80% total extract, equivalent to 12 mg/g extract.")
    bases = {p.basis for p in parsed}
    assert "% total extract" in bases
    assert "mg/g extract" in bases


def test_bare_mg_per_g_with_no_basis_is_kept_separate_and_flagged_unstated():
    parsed = parse_concentration("Contains 5 mg/g of the active compound.")
    assert len(parsed) == 1
    assert parsed[0].basis == "mg/g"
    assert not parsed[0].basis_is_explicit, (
        "an mg/g mention with no dry/fresh/extract qualifier must NOT be "
        "silently treated as an explicit basis"
    )


def test_same_explicit_basis_values_are_comparable():
    a = parse_concentration("2 mg/g dry weight")[0]
    b = parse_concentration("5 mg/g dry weight")[0]
    assert are_comparable(a, b)


def test_different_bases_are_never_comparable():
    a = parse_concentration("2 mg/g dry weight")[0]
    b = parse_concentration("2 mg/g extract")[0]
    assert not are_comparable(a, b)

    c = parse_concentration("0.5%")[0]
    d = parse_concentration("3 mg/g extract")[0]
    assert not are_comparable(c, d)


def test_two_unstated_basis_mg_per_g_values_are_not_assumed_comparable():
    # This is the core 4.10 requirement: "unstated" must never be
    # treated as "the same as another unstated" just because the unit
    # token matches — that's exactly the silent assumption that made
    # "Plant Y is richer" claims unreliable.
    a = parse_concentration("4 mg/g")[0]
    b = parse_concentration("9 mg/g")[0]
    assert not are_comparable(a, b), (
        "two mg/g values with no stated basis must not be treated as comparable"
    )


def test_format_concentration_info_flags_mixed_bases():
    text = "0.5 mg/g dry weight and separately 3% total extract were reported."
    parsed = parse_concentration(text)
    formatted = format_concentration_info(parsed)
    assert formatted.startswith("Not directly comparable"), formatted


def test_format_concentration_info_does_not_flag_single_basis():
    text = "Two batches measured 2 mg/g dry weight and 4 mg/g dry weight respectively."
    parsed = parse_concentration(text)
    formatted = format_concentration_info(parsed)
    assert "Not directly comparable" not in formatted, formatted


def test_format_concentration_info_handles_no_matches():
    assert format_concentration_info([]) == "Not clearly reported"
    assert format_concentration_info(parse_concentration("")) == "Not clearly reported"
    assert format_concentration_info(parse_concentration("no numbers here at all")) == "Not clearly reported"


def test_mg_per_capsule_is_its_own_basis_not_confused_with_mg_per_g():
    parsed = parse_concentration("Each dose provides 250 mg per capsule.")
    assert len(parsed) == 1
    assert parsed[0].basis == "mg per capsule"
    assert parsed[0].basis_is_explicit


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
