"""Regression tests for comparative_rationale.py (architecture audit Q2)."""

import pandas as pd

from comparative_rationale import (
    build_comparative_rationale, _parse_score_breakdown,
    build_comparative_rationale_structured,
)


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


def test_global_rank_is_stated_alongside_local_comparison():
    df = pd.DataFrame([
        _row("Ref", "C", "AltHigh", 90, "Evidence quality: +24.0"),
        _row("Ref", "C", "AltLow", 40, "Evidence quality: +7.0"),
    ])
    rationale = build_comparative_rationale(df)
    assert "Global rank" in rationale.iloc[0]
    assert "Global rank" in rationale.iloc[1]


def test_local_top_pick_can_still_rank_low_globally():
    # AltWinner is top-ranked WITHIN its own tiny reference group, but
    # the global result set has several stronger candidates from a
    # DIFFERENT reference — the report must say both things, not just
    # the locally-flattering one.
    df = pd.DataFrame([
        _row("RefA", "CA", "AltWinner", 30, "Evidence quality: +7.0"),  # wins its own group...
        _row("RefB", "CB", "Strong1", 95, "Evidence quality: +24.0"),
        _row("RefB", "CB", "Strong2", 90, "Evidence quality: +22.0"),
        _row("RefB", "CB", "Strong3", 85, "Evidence quality: +20.0"),
    ])
    rationale = build_comparative_rationale(df)
    winner_text = rationale.iloc[0]
    assert "Top-ranked candidate for this reference" in winner_text
    # ...but globally ranks last (4th of 4) — both facts must be visible.
    assert "Global rank: 4 of 4" in winner_text


def test_global_rank_numbering_matches_actual_score_order():
    df = pd.DataFrame([
        _row("Ref", "C", "First", 100, "Evidence quality: +24.0"),
        _row("Ref", "C", "Second", 50, "Evidence quality: +12.0"),
        _row("Ref2", "C2", "Third", 10, "Evidence quality: +2.0"),
    ])
    rationale = build_comparative_rationale(df)
    assert "Global rank: 1 of 3" in rationale.iloc[0]
    assert "Global rank: 2 of 3" in rationale.iloc[1]
    assert "Global rank: 3 of 3" in rationale.iloc[2]


def test_empty_dataframe_does_not_crash():
    result = build_comparative_rationale(pd.DataFrame())
    assert len(result) == 0


def test_missing_reference_columns_returns_not_applicable_instead_of_crashing():
    df = pd.DataFrame([{"Alternative_Plant": "X", "R&D_Opportunity_Score": 50}])
    result = build_comparative_rationale(df)
    assert (result == "Not applicable").all()


# =====================================================================
# Sprint 2 — Comparative Decision Intelligence: structured comparison
# object. Test numbering below matches the 15 required scenarios.
# =====================================================================

def _row(ref_plant, ref_compound, alt_plant, score, breakdown):
    return {
        "Reference_Plant": ref_plant, "Reference_Compound": ref_compound,
        "Alternative_Plant": alt_plant, "R&D_Opportunity_Score": score,
        "Score_Breakdown": breakdown,
    }


# 1. Winner has a clear group-winner structured status.
def test_winner_has_clear_group_winner_status():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0; Chemical/mechanistic link: +22.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0; Chemical/mechanistic link: +22.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    winner_obj = structured.iloc[0]
    assert winner_obj["status"] == "group_winner"
    assert winner_obj["candidate"] is None
    assert winner_obj["score_gap"] is None
    assert winner_obj["winner_advantages"] == []
    assert winner_obj["candidate_advantages"] == []


# 2. Losing candidate receives winner and candidate metadata.
def test_losing_candidate_receives_winner_and_candidate_metadata():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0; Chemical/mechanistic link: +22.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0; Chemical/mechanistic link: +22.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert obj["status"] == "compared"
    assert obj["winner"]["candidate_name"] == "Lavender"
    assert obj["candidate"]["candidate_name"] == "Passionflower"
    assert obj["winner"]["score"] == 91.0
    assert obj["candidate"]["score"] == 88.0


# 3. Score gap matches the existing scores.
def test_score_gap_matches_existing_scores():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    assert structured.iloc[1]["score_gap"] == 3.0


# 4. Largest winner-favouring component becomes primary reason.
def test_largest_winner_favouring_component_is_primary_reason():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0; Chemical/mechanistic link: +22.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +12.0; Chemical/mechanistic link: +21.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    # Evidence quality differs by 12, Chemical link by only 1 — Evidence
    # quality must be named, not chemical link.
    assert "Evidence quality" in obj["primary_reason"]
    assert obj["winner_advantages"][0]["dimension"] == "Evidence quality"


def test_no_dominant_component_message_when_no_winner_advantage_exists():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +10.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +15.0"),  # candidate stronger on the only component
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert obj["primary_reason"] == "No dominant score-component difference could be identified from the available breakdown."


# 5. Candidate-favouring components are retained and exposed — the
#    exact "data currently discarded" bug the audit identified.
def test_candidate_favouring_components_are_retained_not_discarded():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0; Novelty: +2.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +10.0; Novelty: +10.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert len(obj["candidate_advantages"]) == 1
    assert obj["candidate_advantages"][0]["dimension"] == "Novelty"
    assert obj["candidate_advantages"][0]["favours"] == "candidate"
    assert obj["candidate_advantages"][0]["difference"] == -8.0


# 6. Equal components are represented safely.
def test_equal_components_represented_safely_as_ties():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0; Novelty: +5.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +21.0; Novelty: +5.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert len(obj["ties"]) == 1
    assert obj["ties"][0]["dimension"] == "Novelty"
    assert obj["ties"][0]["favours"] == "tie"


# 7. Missing Score_Breakdown does not crash.
def test_missing_score_breakdown_does_not_crash():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, None),
        _row("Ref", "C", "Passionflower", 88, None),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert obj["dimension_comparison"] == []
    assert obj["comparison_confidence"]["level"] == "Insufficient"


# 8. Unparseable Score_Breakdown produces an honest limitation.
def test_unparseable_score_breakdown_produces_honest_limitation():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "garbled nonsense text"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert any("missing or unparseable" in lim for lim in obj["limitations"])


# 9. Component present for one candidate only is marked incomplete.
def test_component_present_for_one_candidate_only_marked_unavailable():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0; Novelty: +5.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    novelty_entry = next(e for e in obj["dimension_comparison"] if e["dimension"] == "Novelty")
    assert novelty_entry["favours"] == "unavailable"
    assert novelty_entry["candidate_value"] is None  # never defaulted to zero
    assert any("present for only one candidate" in lim for lim in obj["limitations"])


# 10. Comparative_Rationale string remains backward compatible.
def test_comparative_rationale_string_output_unchanged_by_sprint_2():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0"),
    ])
    string_result = build_comparative_rationale(df)
    assert isinstance(string_result.iloc[0], str)
    assert isinstance(string_result.iloc[1], str)
    assert "Top-ranked candidate" in string_result.iloc[0]
    assert "points below" in string_result.iloc[1]


# 11. Structured object does not alter ranking or scores.
def test_structured_object_does_not_alter_ranking_or_scores():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0"),
    ])
    original_scores = df["R&D_Opportunity_Score"].tolist()
    build_comparative_rationale_structured(df)
    assert df["R&D_Opportunity_Score"].tolist() == original_scores  # untouched


# 14. No fabricated regulatory contribution where none exists.
def test_no_fabricated_regulatory_score_contribution():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Market signal: +3.0; Evidence quality: +24.0"),
        _row("Ref", "C", "Passionflower", 88, "Market signal: +2.0; Evidence quality: +20.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert any("No independent regulatory score contribution" in lim for lim in obj["limitations"])
    market_entry = next(e for e in obj["dimension_comparison"] if e["dimension"] == "Market signal")
    assert market_entry["dimension"] != "Regulatory"  # never relabeled as a regulatory score


# 15. Legacy rows remain supported.
def test_legacy_row_missing_alternative_plant_does_not_crash():
    df = pd.DataFrame([
        _row("Ref", "C", None, 91, "Evidence quality: +24.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert obj["winner"]["candidate_name"] == "Unknown"
    assert any("Legacy row" in lim for lim in obj["limitations"])


def test_global_rank_is_populated_in_structured_object():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0"),
        _row("Ref2", "C2", "Chamomile", 95, "Evidence quality: +30.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    obj = structured.iloc[1]
    assert obj["candidate"]["global_rank"] == 3  # lowest of the three
    assert obj["winner"]["global_rank"] == 2


def test_comparison_confidence_high_when_full_overlap():
    df = pd.DataFrame([
        _row("Ref", "C", "Lavender", 91, "Evidence quality: +24.0; Chemical/mechanistic link: +22.0"),
        _row("Ref", "C", "Passionflower", 88, "Evidence quality: +20.0; Chemical/mechanistic link: +21.0"),
    ])
    structured = build_comparative_rationale_structured(df)
    assert structured.iloc[1]["comparison_confidence"]["level"] == "High"


def test_empty_dataframe_structured_does_not_crash():
    result = build_comparative_rationale_structured(pd.DataFrame())
    assert len(result) == 0


def test_missing_reference_columns_returns_none_not_crash_for_structured():
    df = pd.DataFrame([{"Alternative_Plant": "X", "R&D_Opportunity_Score": 50}])
    result = build_comparative_rationale_structured(df)
    assert result.iloc[0] is None


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
