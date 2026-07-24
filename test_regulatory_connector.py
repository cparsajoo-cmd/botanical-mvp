"""Regression tests for regulatory_connector.py (Sprint 5, Phase A, Issue 2).

This module had zero test coverage before Sprint 5 — the audit found
it was still reachable in production with fabricated data. These
tests lock in that Phase A's fix actually holds.
"""

import unittest.mock as mock

import regulatory_connector as rc


def test_legacy_stub_is_disabled_by_default():
    assert rc._LEGACY_STUB_ENABLED is False


def test_legacy_stub_dict_still_exists_as_historical_reference_not_deleted():
    # Per the explicit instruction not to simply delete files — the
    # dict remains, just disconnected from execution.
    assert "Valeriana officinalis" in rc.REGULATORY_DB
    assert rc.REGULATORY_DB["Valeriana officinalis"]["EMA_Status"] == "Yes"


def test_fabricated_data_never_reaches_output_even_for_a_covered_plant():
    # THE regression this file exists to prevent: before the fix, any
    # of these 4 plants would silently get fabricated "Yes"/"No"
    # values instead of the real connector's answer.
    with mock.patch(
        "ema_regulatory_connector.search_regulatory_sources_real",
        return_value=[{
            "Scientific_Name": "Valeriana officinalis",
            "EMA_Status": "Not in HMPC inventory (as of 2021 snapshot)",
            "WHO_Status": "Not yet verified",
            "ESCOP_Status": "Not yet verified",
            "Regulatory_Status": "Not found in EMA HMPC's assessment inventory.",
        }],
    ) as mocked_real_connector:
        result = rc.search_regulatory_sources("Valeriana officinalis", "sleep")
        mocked_real_connector.assert_called_once()
        assert result[0]["EMA_Status"] == "Not in HMPC inventory (as of 2021 snapshot)"
        assert result[0]["EMA_Status"] != "Yes"


def test_real_connector_is_called_for_every_plant_including_legacy_covered_ones():
    covered_plants = ["Valeriana officinalis", "Passiflora incarnata", "Melissa officinalis", "Lavandula angustifolia"]
    for plant in covered_plants:
        with mock.patch(
            "ema_regulatory_connector.search_regulatory_sources_real",
            return_value=[{"EMA_Status": "Not yet verified"}],
        ) as mocked:
            rc.search_regulatory_sources(plant, "sleep")
            mocked.assert_called_once()


def test_real_connector_is_used_for_uncovered_plants_too():
    with mock.patch(
        "ema_regulatory_connector.search_regulatory_sources_real",
        return_value=[{"EMA_Status": "Not yet verified"}],
    ) as mocked:
        rc.search_regulatory_sources("Withania somnifera", "stress")
        mocked.assert_called_once()


def test_connector_failure_degrades_honestly_not_silently():
    with mock.patch(
        "ema_regulatory_connector.search_regulatory_sources_real",
        side_effect=ConnectionError("simulated network failure"),
    ):
        result = rc.search_regulatory_sources("Valeriana officinalis", "sleep")
        assert result[0]["EMA_Status"] == "Not yet verified"
        assert "Lookup failed" in result[0]["Regulatory_Status"] or "lookup" in result[0]["Notes"].lower()


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
