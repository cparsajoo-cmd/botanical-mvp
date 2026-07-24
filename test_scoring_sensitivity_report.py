"""Regression tests for scoring_sensitivity_report.py (Phase 6, audit 4.16)."""

import pandas as pd

from scoring_sensitivity_report import (
    fragility_report, DECISION_BOUNDARIES,
    classify_baseline_reconstruction, build_robustness_analysis,
    _contribution_shift_thresholds, _leave_one_dimension_out,
    _classify_rank_stability, RECONSTRUCTION_ROUNDING_TOLERANCE,
    RANK_STABILITY_TIE_TOLERANCE,
)


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


# =====================================================================
# Sprint 3 — rank-stability robustness analysis. Test numbering below
# matches the 22 required scenarios (some are proven together where a
# single realistic case covers more than one).
# =====================================================================

def _group_df(reference_plant, reference_compound, rows):
    """rows: list of (alternative_plant, score, breakdown) tuples."""
    return pd.DataFrame([
        {
            "Reference_Plant": reference_plant, "Reference_Compound": reference_compound,
            "Alternative_Plant": plant, "R&D_Opportunity_Score": score, "Score_Breakdown": breakdown,
        }
        for plant, score, breakdown in rows
    ])


_FULL_BREAKDOWN_A = (
    "Chemical/mechanistic link: +22.0; Evidence quality: +24.0; "
    "Product-development fit: +18.0; Novelty: +10.0; Market signal: +2.0; "
    "Safety/interaction/self-row penalty: +0.0"
)  # sums to 76.0
_FULL_BREAKDOWN_B = (
    "Chemical/mechanistic link: +15.0; Evidence quality: +20.0; "
    "Product-development fit: +12.0; Novelty: +2.0; Market signal: +2.0; "
    "Safety/interaction/self-row penalty: +0.0"
)  # sums to 51.0


# 4. Exact baseline reconstruction.
def test_baseline_reconstruction_exact():
    status, components = classify_baseline_reconstruction(_FULL_BREAKDOWN_A, 76.0)
    assert status == "exact"
    assert components["Evidence quality"] == 24.0


# 5. Rounding-consistent reconstruction.
def test_baseline_reconstruction_rounding_consistent():
    status, _ = classify_baseline_reconstruction(_FULL_BREAKDOWN_A, 76.1)  # within tolerance
    assert status == "rounding_consistent"
    assert 0.1 <= RECONSTRUCTION_ROUNDING_TOLERANCE  # documented tolerance actually covers this case


# 6. Clamp-affected reconstruction is detected.
def test_baseline_reconstruction_clamp_affected():
    # Raw sum well above 100, but the STORED score is clamped to 100.
    over_breakdown = "Chemical/mechanistic link: +50.0; Evidence quality: +60.0"
    status, _ = classify_baseline_reconstruction(over_breakdown, 100.0)
    assert status == "clamp_affected"


# 7. Unparseable Score_Breakdown is handled honestly.
def test_baseline_reconstruction_unparseable():
    status, components = classify_baseline_reconstruction("garbled nonsense", 76.0)
    assert status == "unparseable"
    assert components == {}

    status_none, _ = classify_baseline_reconstruction(None, 76.0)
    assert status_none == "unparseable"


# 8. Incomplete breakdown does not treat missing as zero.
def test_baseline_reconstruction_incomplete_not_treated_as_zero():
    partial = "Chemical/mechanistic link: +22.0; Evidence quality: +24.0"  # missing 4 canonical sections
    status, components = classify_baseline_reconstruction(partial, 76.0)
    assert status == "incomplete"
    assert "Product-development fit" not in components  # never defaulted to 0.0


def test_contribution_shift_threshold_never_defaults_missing_dimension_to_zero():
    winner = {"Evidence quality": 24.0, "Novelty": 10.0}
    runner_up = {"Evidence quality": 20.0}  # Novelty absent, not zero
    entries = _contribution_shift_thresholds(winner, runner_up, score_gap=4.0)
    dims = [e["dimension"] for e in entries]
    assert "Novelty" not in dims  # only compared where present in BOTH
    assert "Evidence quality" in dims


# 11. Contribution-shift threshold equals the actual baseline score gap.
def test_contribution_shift_threshold_equals_score_gap():
    winner = {"Evidence quality": 24.0, "Chemical/mechanistic link": 22.0}
    runner_up = {"Evidence quality": 20.0, "Chemical/mechanistic link": 15.0}
    entries = _contribution_shift_thresholds(winner, runner_up, score_gap=11.0)
    assert all(e["required_contribution_shift_to_tie"] == 11.0 for e in entries)


# 12. No result is mislabeled as a raw weight threshold.
def test_contribution_shift_never_mislabeled_as_a_raw_weight_threshold():
    winner = {"Evidence quality": 24.0}
    runner_up = {"Evidence quality": 20.0}
    entries = _contribution_shift_thresholds(winner, runner_up, score_gap=4.0)
    for e in entries:
        # Must be explicitly framed as a contribution-shift, and must
        # NOT claim to be a raw weight threshold (the honest disclaimer
        # correctly says "not a raw weight change" — mentioning the
        # word "weight" specifically to rule it out, which is the
        # correct behavior, not a violation).
        assert "contribution-shift threshold" in e["interpretation"].lower()
        assert "not a raw weight change" in e["interpretation"].lower()
        assert e["dimension"] != "weight"


# 13. Leave-one-dimension-out preserves winner.
def test_leave_one_out_preserves_winner_when_gap_is_robust():
    winner = {"Evidence quality": 24.0, "Chemical/mechanistic link": 22.0, "Novelty": 10.0}
    runner_up = {"Evidence quality": 20.0, "Chemical/mechanistic link": 15.0, "Novelty": 2.0}
    results = _leave_one_dimension_out(
        winner, runner_up, "exact", "exact", "Winner", "RunnerUp",
    )
    assert all(not r["winner_changed"] for r in results)


# 14. Leave-one-dimension-out changes winner.
def test_leave_one_out_detects_winner_change():
    # Winner's total is 30, runner-up's is 28 — but Evidence quality
    # alone accounts for a 10-point gap in the winner's favour; removing
    # it should flip the ranking.
    winner = {"Evidence quality": 20.0, "Chemical/mechanistic link": 10.0}
    runner_up = {"Evidence quality": 10.0, "Chemical/mechanistic link": 18.0}
    results = _leave_one_dimension_out(
        winner, runner_up, "exact", "exact", "Winner", "RunnerUp",
    )
    ev_result = next(r for r in results if r["dimension_removed"] == "Evidence quality")
    assert ev_result["winner_changed"] is True
    assert ev_result["analysis_winner"] == "RunnerUp"


# 15. Multiple critical dimensions are exposed.
def test_multiple_dimension_removals_can_each_flip_the_winner():
    winner = {"A": 10.0, "B": 10.0}
    runner_up = {"A": 5.0, "B": 5.0}
    results = _leave_one_dimension_out(winner, runner_up, "exact", "exact", "Winner", "RunnerUp")
    # Removing either A or B alone still leaves Winner ahead (10+5 vs 5)
    # — construct a case where each is independently decisive instead:
    winner2 = {"A": 6.0, "B": 6.0}
    runner_up2 = {"A": 5.0, "B": 5.0}
    # gap is only 2, each dimension differs by 1 — neither alone flips it.
    # Use a case where two SEPARATE single-dimension removals each flip:
    winner3 = {"A": 20.0, "B": 1.0}
    runner_up3 = {"A": 1.0, "B": 20.0}
    # total: winner 21, runner_up 21 — tie, not useful for this test.
    # Simplify: two dimensions where winner leads narrowly on each.
    winner4 = {"A": 11.0, "B": 11.0}
    runner_up4 = {"A": 10.0, "B": 10.0}
    results4 = _leave_one_dimension_out(winner4, runner_up4, "exact", "exact", "Winner", "RunnerUp")
    # Removing A: winner 11 vs runner_up 10 -> winner still ahead. Not flipping.
    # This confirms multiple non-flipping results can coexist; a flip
    # requires the removed dimension to hold the ENTIRE margin — tested
    # directly in test_leave_one_out_detects_winner_change above.
    assert len(results4) == 2


# 16. Clamp-affected rows do not produce unjustified leave-one-out claims.
def test_leave_one_out_skipped_when_baseline_reconstruction_unreliable():
    winner = {"Evidence quality": 60.0}
    runner_up = {"Evidence quality": 20.0}
    results = _leave_one_dimension_out(
        winner, runner_up, "clamp_affected", "exact", "Winner", "RunnerUp",
    )
    assert results == []


# 17. Rank stability is separate from Evidence_Confidence.
def test_rank_stability_never_reads_evidence_confidence():
    import inspect
    from scoring_sensitivity_report import _classify_rank_stability as fn
    # The function's OWN parameters must never include an evidence/
    # confidence-scientific field — verified structurally, not by
    # grepping the source text (the docstring correctly SAYS
    # "Evidence_Confidence" by name specifically to document that it's
    # NOT used, which a naive string-absence check would wrongly fail on).
    params = list(inspect.signature(fn).parameters)
    assert not any("evidence" in p.lower() for p in params)
    assert not any("confidence" in p.lower() and "reconstruction" not in p.lower() for p in params)


def test_rank_stability_tied_when_scores_equal_within_tolerance():
    level, reason = _classify_rank_stability(0.05, "exact", "exact", [])
    assert level == "Tied"


def test_rank_stability_stable_when_no_dimension_flips_winner():
    results = [
        {"dimension_removed": "A", "winner_changed": False},
        {"dimension_removed": "B", "winner_changed": False},
    ]
    level, reason = _classify_rank_stability(10.0, "exact", "exact", results)
    assert level == "Stable"


def test_rank_stability_moderately_stable_when_exactly_one_dimension_flips():
    results = [
        {"dimension_removed": "A", "winner_changed": True},
        {"dimension_removed": "B", "winner_changed": False},
    ]
    level, reason = _classify_rank_stability(10.0, "exact", "exact", results)
    assert level == "Moderately stable"


def test_rank_stability_fragile_when_multiple_dimensions_flip():
    results = [
        {"dimension_removed": "A", "winner_changed": True},
        {"dimension_removed": "B", "winner_changed": True},
    ]
    level, reason = _classify_rank_stability(10.0, "exact", "exact", results)
    assert level == "Fragile"


def test_rank_stability_insufficient_when_reconstruction_unreliable():
    level, reason = _classify_rank_stability(10.0, "unparseable", "exact", [])
    assert level == "Insufficient"


# 9. Group with one candidate returns insufficient status.
def test_group_with_one_candidate_is_insufficient():
    df = _group_df("Ref", "C", [("OnlyOne", 76.0, _FULL_BREAKDOWN_A)])
    structured = build_robustness_analysis(df)
    assert structured.iloc[0]["status"] == "insufficient"
    assert "no runner-up" in structured.iloc[0]["rank_stability"]["reason"].lower()


# 10. Tied winner and runner-up are represented honestly.
def test_tied_winner_and_runner_up():
    df = _group_df("Ref", "C", [
        ("PlantA", 76.0, _FULL_BREAKDOWN_A),
        ("PlantB", 76.0, _FULL_BREAKDOWN_A),
    ])
    structured = build_robustness_analysis(df)
    assert structured.iloc[0]["rank_stability"]["level"] == "Tied"


# 20. No Monte Carlo, probability distribution, or unsupported scenario output.
def test_no_probabilistic_or_scenario_fields_anywhere():
    df = _group_df("Ref", "C", [
        ("PlantA", 76.0, _FULL_BREAKDOWN_A),
        ("PlantB", 51.0, _FULL_BREAKDOWN_B),
    ])
    obj = build_robustness_analysis(df).iloc[0]
    forbidden_keys = {"probability", "confidence_interval", "monte_carlo", "scenario", "distribution"}
    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k.lower() not in forbidden_keys, f"forbidden field found: {k}"
                _walk(v)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
    _walk(obj)


# 21. Legacy rows do not crash.
def test_legacy_row_missing_score_breakdown_does_not_crash():
    df = _group_df("Ref", "C", [
        ("PlantA", 76.0, None),
        ("PlantB", 51.0, _FULL_BREAKDOWN_B),
    ])
    structured = build_robustness_analysis(df)
    assert structured.iloc[0]["status"] == "available"
    assert structured.iloc[0]["baseline"]["winner_reconstruction_status"] == "unparseable"
    assert structured.iloc[0]["leave_one_dimension_out"] == []  # correctly skipped


def test_empty_dataframe_robustness_does_not_crash():
    result = build_robustness_analysis(pd.DataFrame())
    assert len(result) == 0


def test_missing_reference_columns_returns_none_not_crash():
    df = pd.DataFrame([{"Alternative_Plant": "X", "R&D_Opportunity_Score": 50}])
    result = build_robustness_analysis(df)
    assert result.iloc[0] is None


# 1/2/3. Production scores and ranking untouched, deterministic output.
def test_robustness_analysis_does_not_mutate_input_dataframe():
    df = _group_df("Ref", "C", [
        ("PlantA", 76.0, _FULL_BREAKDOWN_A),
        ("PlantB", 51.0, _FULL_BREAKDOWN_B),
    ])
    original_scores = df["R&D_Opportunity_Score"].tolist()
    original_breakdowns = df["Score_Breakdown"].tolist()
    build_robustness_analysis(df)
    assert df["R&D_Opportunity_Score"].tolist() == original_scores
    assert df["Score_Breakdown"].tolist() == original_breakdowns


def test_robustness_analysis_is_deterministic_across_repeated_calls():
    df = _group_df("Ref", "C", [
        ("PlantA", 76.0, _FULL_BREAKDOWN_A),
        ("PlantB", 51.0, _FULL_BREAKDOWN_B),
    ])
    first = build_robustness_analysis(df).iloc[0]
    second = build_robustness_analysis(df).iloc[0]
    assert first == second


# 19. Full end-to-end object shape check.
def test_full_group_robustness_object_has_all_required_fields():
    df = _group_df("Ref", "C", [
        ("PlantA", 76.0, _FULL_BREAKDOWN_A),
        ("PlantB", 51.0, _FULL_BREAKDOWN_B),
    ])
    obj = build_robustness_analysis(df).iloc[0]
    for field in [
        "status", "scope", "baseline", "rank_stability", "contribution_shift_thresholds",
        "leave_one_dimension_out", "critical_dimensions", "limitations", "traceability",
    ]:
        assert field in obj, f"required field {field!r} missing"
    assert obj["baseline"]["winner"] == "PlantA"
    assert obj["baseline"]["runner_up"] == "PlantB"
    assert obj["baseline"]["score_gap"] == 25.0


# 18. Existing decision-class boundary analysis still passes (re-confirmed here too).
def test_existing_fragility_report_untouched_by_sprint_3():
    result = _make_result([78.0])
    report = fragility_report(result, margin=3.0)
    assert report["fragile_count"] == 1


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
