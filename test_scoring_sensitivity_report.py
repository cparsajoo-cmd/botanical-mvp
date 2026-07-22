"""Regression tests for scoring_sensitivity_report.py (Phase 6, audit 4.16)."""

import pandas as pd

from scoring_sensitivity_report import fragility_report, DECISION_BOUNDARIES


def _make_result(scores):
    return pd.DataFrame({
        "Alternative_Plant": [f"Plant{i}" for i in range(len(scores))],
        "R&D_Opportunity_Score": scores,
    })


def test_a_score_right_at_a_boundary_is_flagged_fragile():
    result = _make_result([78.0])  # exactly on the Strong boundary
    report = fragility_report(result, margin=3.0)
    assert report["fragile_count"] == 1


def test_a_score_far_from_any_boundary_is_not_flagged():
    result = _make_result([100.0])  # far from 78
    report = fragility_report(result, margin=3.0)
    assert report["fragile_count"] == 0


def test_distance_is_measured_to_the_nearest_boundary_not_a_fixed_one():
    result = _make_result([46.0])  # 1 away from 45, 16 away from 62
    report = fragility_report(result, margin=3.0)
    row = report["fragile_rows"].iloc[0]
    assert row["Nearest_Boundary"] == 45
    assert row["Distance_To_Boundary"] == 1.0


def test_margin_is_configurable_and_respected():
    result = _make_result([50.0])  # 5 away from 45
    tight = fragility_report(result, margin=3.0)
    loose = fragility_report(result, margin=6.0)
    assert tight["fragile_count"] == 0
    assert loose["fragile_count"] == 1


def test_mixed_batch_only_flags_the_boundary_close_rows():
    result = _make_result([10.0, 44.0, 79.0, 95.0])
    report = fragility_report(result, margin=2.0)
    assert report["fragile_count"] == 2  # 44 (near 45) and 79 (near 78)
    assert report["total_count"] == 4


def test_empty_result_does_not_crash():
    report = fragility_report(pd.DataFrame())
    assert report["fragile_count"] == 0
    assert report["total_count"] == 0


def test_summary_mentions_the_actual_boundaries():
    result = _make_result([78.0])
    report = fragility_report(result)
    for boundary in DECISION_BOUNDARIES:
        assert str(boundary) in report["summary"]


def test_fragile_rows_are_sorted_closest_first():
    result = _make_result([44.0, 78.5, 46.5])
    report = fragility_report(result, margin=5.0)
    distances = report["fragile_rows"]["Distance_To_Boundary"].tolist()
    assert distances == sorted(distances)


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
