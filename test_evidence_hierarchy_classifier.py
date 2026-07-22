"""Regression tests for evidence_hierarchy_classifier.py (Phase 4, audit 4.14)."""

from evidence_hierarchy_classifier import classify_evidence_hierarchy


def test_systematic_review_outranks_everything_else_mentioned():
    text = (
        "A systematic review and meta-analysis of in vitro studies "
        "found consistent hepatoprotective effects."
    )
    assert classify_evidence_hierarchy(text) == "Systematic review / meta-analysis"


def test_rct_is_distinguished_from_a_plain_observational_study():
    rct_text = "A double-blind, placebo-controlled randomized controlled trial in 120 patients."
    cohort_text = "A prospective cohort study followed 300 patients over 2 years."

    assert classify_evidence_hierarchy(rct_text) == "Clinical trial"
    assert classify_evidence_hierarchy(cohort_text) == "Observational human evidence"
    assert classify_evidence_hierarchy(rct_text) != classify_evidence_hierarchy(cohort_text), (
        "an RCT and a cohort study used to be lumped into the same "
        "'Clinical / human evidence' bucket — they must now be distinct tiers"
    )


def test_ex_vivo_in_vivo_outranks_bare_in_vitro():
    animal_text = "Effects were confirmed in a mouse model of hepatic injury."
    in_vitro_text = "The compound showed enzyme inhibition in a cell-free in vitro assay."

    assert classify_evidence_hierarchy(animal_text) == "Validated ex vivo / in vivo"
    assert classify_evidence_hierarchy(in_vitro_text) == "In vitro / mechanistic"


def test_regulatory_monograph_terms_classify_correctly():
    text = "The EMA/HMPC monograph recognizes well-established use for this indication."
    assert classify_evidence_hierarchy(text) == "Traditional-use / regulatory monograph"


def test_analytical_chemistry_only_is_the_weakest_named_tier():
    text = "HPLC analysis confirmed the compound was present; concentration determined by GC-MS."
    assert classify_evidence_hierarchy(text) == "Occurrence / analytical chemistry only"


def test_negated_mentions_do_not_count():
    text = "No clinical trials have been conducted and human data remain absent."
    assert classify_evidence_hierarchy(text) is None, (
        "a negated mention of 'clinical trial' must not classify as Clinical trial evidence"
    )


def test_no_matching_terms_returns_none_not_a_fallback_string():
    assert classify_evidence_hierarchy("The plant has been used for centuries.") is None
    assert classify_evidence_hierarchy("") is None
    assert classify_evidence_hierarchy(None) is None


def test_strongest_tier_present_wins_when_multiple_are_mentioned():
    text = (
        "Earlier in vitro work suggested a mechanism, later confirmed by a "
        "randomized controlled trial and ultimately summarized in a "
        "systematic review and meta-analysis."
    )
    assert classify_evidence_hierarchy(text) == "Systematic review / meta-analysis"


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
