"""Regression tests for comparative_rationale.py (architecture audit Q2)."""

import pandas as pd

from comparative_rationale import build_comparative_rationale, _parse_score_breakdown


def _row(ref_plant, ref_compound, alt_plant, score, breakdown):
    return {
        "Reference_Plant": ref_plant, "Reference_Compound": ref_compound,
        "Alternative_Plant": alt_plant, "R&D_Opportunity_Score": score,
        "Score_Breakdown": breakdown,
    }


def test_parse_score_breakdown_round_trips_the_engines_own_format():
    parsed = _parse_score_breakdown("Evidence quality: +24.0; Chemical/mechanistic link: +22.0; Market signal: -2.0")
    assert parsed == {"Evidence quality": 24.0, "Chemical/mechanistic link": 22.0, "Market signal": -2.0}


def test_parse_score_breakdown_tolerates_the_merge_bonus_suffix():
    parsed = _parse_score_breakdown("Evidence quality: +24.0; Multi-compound match bonus: +10.0")
    assert parsed["Multi-compound match bonus"] == 10.0


def test_parse_score_breakdown_handles_missing_or_placeholder_gracefully():
    assert _parse_score_breakdown("") == {}
    assert _parse_score_breakdown("No breakdown available") == {}


def test_top_candidate_in_a_group_gets_a_top_ranked_label():
    df = pd.DataFrame([
        _row("Ref", "C", "AltHigh", 90, "Evidence quality: +24.0"),
        _row("Ref", "C", "AltLow", 40, "Evidence quality: +7.0"),
    ])
    rationale = build_comparative_rationale(df)
    assert "Top-ranked candidate" in rationale.iloc[0]


def test_non_top_candidate_explains_the_gap_and_names_the_winner():
    df = pd.DataFrame([
        _row("Ref", "C", "AltHigh", 90, "Evidence quality: +24.0"),
        _row("Ref", "C", "AltLow", 40, "Evidence quality: +7.0"),
    ])
    rationale = build_comparative_rationale(df)
    explanation = rationale.iloc[1]
    assert "50.0 points below AltHigh" in explanation
    assert "Evidence quality" in explanation  # the actual largest contributing difference


def test_comparison_is_scoped_per_reference_group_not_global():
    # Two completely separate reference groups — a candidate should
    # only ever be compared against others sharing ITS OWN reference,
    # never against a different reference's candidates.
    df = pd.DataFrame([
        _row("RefA", "CA", "Alt1", 90, "Evidence quality: +24.0"),
        _row("RefA", "CA", "Alt2", 80, "Evidence quality: +20.0"),
        _row("RefB", "CB", "Alt3", 10, "Evidence quality: +2.0"),  # lowest score overall, but alone in its group
    ])
    rationale = build_comparative_rationale(df)
    # Alt3 is the ONLY candidate for RefB/CB, so it must be top-ranked
    # for its own group despite having the lowest score in the WHOLE df.
    assert "Top-ranked candidate" in rationale.iloc[2]


def test_identifies_the_correct_dominant_component_even_when_multiple_differ():
    df = pd.DataFrame([
        _row("Ref", "C", "AltHigh", 90,
             "Evidence quality: +24.0; Chemical/mechanistic link: +22.0; Market signal: +2.0"),
        _row("Ref", "C", "AltLow", 55,
             "Evidence quality: +7.0; Chemical/mechanistic link: +20.0; Market signal: +2.0"),
    ])
    rationale = build_comparative_rationale(df)
    explanation = rationale.iloc[1]
    # Evidence quality differs by 17, Chemical link by only 2 — Evidence
    # quality must be named as the dominant reason, not chemical link.
    assert "Evidence quality" in explanation
    assert "+17.0" in explanation


def test_a_component_where_the_loser_scored_higher_is_not_blamed_for_the_loss():
    df = pd.DataFrame([
        _row("Ref", "C", "AltHigh", 90, "Evidence quality: +30.0; Novelty: +0.0"),
        # AltLow scored HIGHER on Novelty, but still lost overall —
        # Novelty must not be cited as a reason it was rejected.
        _row("Ref", "C", "AltLow", 60, "Evidence quality: +0.0; Novelty: +10.0"),
    ])
    rationale = build_comparative_rationale(df)
    explanation = rationale.iloc[1]
    assert "Evidence quality" in explanation
    assert "Novelty" not in explanation


def test_empty_dataframe_does_not_crash():
    result = build_comparative_rationale(pd.DataFrame())
    assert len(result) == 0


def test_missing_reference_columns_returns_not_applicable_instead_of_crashing():
    df = pd.DataFrame([{"Alternative_Plant": "X", "R&D_Opportunity_Score": 50}])
    result = build_comparative_rationale(df)
    assert (result == "Not applicable").all()


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
