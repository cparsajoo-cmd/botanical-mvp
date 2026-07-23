"""Regression tests for free_text_question_parser.py (real Question Understanding)."""

from free_text_question_parser import parse_free_text_question


def test_the_exact_example_question_from_the_external_reviews():
    # "یک محصول خوراکی گیاهی برای اختلال شناختی خفیف، مناسب سالمندان، با
    # حداقل خطر تداخل CYP و بازار هدف اروپا" — repeated verbatim across
    # all three review rounds as the benchmark question the system
    # supposedly couldn't understand. English equivalent used here since
    # the vocabulary tables are English (matching step_inputs.py's own
    # selectbox labels).
    question = (
        "A botanical oral product for mild cognitive impairment, "
        "suitable for the elderly, with low CYP interaction risk, "
        "for the European Union market."
    )
    result = parse_free_text_question(question)

    assert result.indication == "Cognitive decline / Alzheimer's support"
    assert result.route == "Oral"
    assert result.market == "European Union"
    assert "Elderly / older adults" in result.target_population
    assert "Low CYP interaction risk" in result.safety_constraints


def test_indication_matching_prefers_the_longer_more_specific_phrase():
    # "mild cognitive impairment" should win over any shorter,
    # coincidentally-overlapping term.
    result = parse_free_text_question("A product for mild cognitive impairment.")
    assert result.indication == "Cognitive decline / Alzheimer's support"
    assert result.indication_matched_phrase == "mild cognitive impairment"


def test_dosage_form_matching_and_route_inference():
    result = parse_free_text_question("I want to develop a capsule for joint pain.")
    assert result.dosage_form == "Capsule"
    assert result.route == "Oral"
    assert result.indication == "Joint & muscle comfort"


def test_topical_route_inferred_from_cream():
    result = parse_free_text_question("A cream for skin inflammation.")
    assert result.dosage_form == "Cream"
    assert result.route == "Topical"


def test_market_synonym_matching():
    result = parse_free_text_question("Targeting the US market with a sleep product.")
    assert result.market == "United States"
    assert result.indication == "Sleep and relaxation"


def test_multiple_target_populations_and_safety_constraints_all_captured():
    result = parse_free_text_question(
        "A product for elderly and pregnant patients, non-sedating and pregnancy-safe."
    )
    assert "Elderly / older adults" in result.target_population
    assert "Pregnant / lactating" in result.target_population
    assert "Non-sedating / low sedation" in result.safety_constraints
    assert "Pregnancy-safe" in result.safety_constraints


def test_empty_text_returns_all_none_not_a_guess():
    result = parse_free_text_question("")
    assert result.indication is None
    assert result.dosage_form is None
    assert result.market is None
    assert result.target_population == []
    assert result.safety_constraints == []


def test_none_text_does_not_crash():
    result = parse_free_text_question(None)
    assert result.indication is None


def test_unmatched_field_stays_none_never_defaults_to_something_wrong():
    # A question with a real dosage form but no recognizable indication
    # must leave indication as None, not guess one.
    result = parse_free_text_question("I want to make a capsule product.")
    assert result.dosage_form == "Capsule"
    assert result.indication is None


def test_matched_phrase_is_reported_for_traceability():
    result = parse_free_text_question("A tea for insomnia.")
    assert result.dosage_form_matched_phrase == "tea"
    assert result.indication_matched_phrase == "insomnia"


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
