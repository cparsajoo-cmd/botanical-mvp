"""Unit tests for scientific_phrase_matcher.py.

Per the scoped bug-fix instructions, these are written BEFORE wiring the
four call sites and must all pass before that wiring happens.
"""

import pytest

from scientific_phrase_matcher import (
    find_phrase_matches,
    has_phrase_match,
    phrase_present,
)

# Phrase families named in the bug report, mapped to the actual phrase
# string already used by one or more of the four call sites.
PHRASE_FAMILIES = {
    "clinical_trial": "clinical trial",
    "systematic_review": "systematic review",
    "cohort_study": "cohort study",
    "animal_model": "animal model",
    "monograph": "monograph",
    "controlled_substance": "controlled substance",
    "novel_food": "novel food",
}


def _plural_of(term: str) -> str:
    # Minimal, explicit per-family plural map for constructing test
    # sentences (deliberately NOT reusing the module's own pluralizer,
    # so the test doesn't just check the implementation against itself).
    explicit = {
        "clinical trial": "clinical trials",
        "systematic review": "systematic reviews",
        "cohort study": "cohort studies",
        "animal model": "animal models",
        "monograph": "monographs",
        "controlled substance": "controlled substances",
        "novel food": "novel foods",
    }
    return explicit[term]


@pytest.mark.parametrize("family, term", list(PHRASE_FAMILIES.items()))
def test_singular_matches(family, term):
    text = f"a {term} demonstrated efficacy.".lower()
    assert phrase_present(text, term), f"{family}: singular form should match"


@pytest.mark.parametrize("family, term", list(PHRASE_FAMILIES.items()))
def test_plural_matches(family, term):
    plural = _plural_of(term)
    text = f"several {plural} demonstrated efficacy.".lower()
    assert phrase_present(text, term), f"{family}: plural form should match"
    assert has_phrase_match(text, [term]), f"{family}: plural form should match via find/has"


@pytest.mark.parametrize("family, term", list(PHRASE_FAMILIES.items()))
def test_negated_does_not_match(family, term):
    plural = _plural_of(term)
    text = f"no {plural} have been conducted.".lower()
    assert not has_phrase_match(text, [term], negation_aware=True), (
        f"{family}: negated mention should not count as a positive match"
    )


@pytest.mark.parametrize("family, term", list(PHRASE_FAMILIES.items()))
def test_forward_negated_does_not_match(family, term):
    plural = _plural_of(term)
    text = f"further {plural} are needed to confirm this.".lower()
    assert not has_phrase_match(text, [term], negation_aware=True), (
        f"{family}: 'further X are needed' should not count as a positive match"
    )


def test_unrelated_prefix_does_not_match_clinical_trial():
    text = "this is a preclinical / mechanistic evidence finding.".lower()
    assert not phrase_present(text, "clinical trial")
    assert not has_phrase_match(text, ["clinical trial"])


def test_unrelated_word_does_not_match_clinical_trial_specifically():
    text = "the product is intended for clinical use.".lower()
    assert not phrase_present(text, "clinical trial")
    assert not has_phrase_match(text, ["clinical trial"])


# --- Behavior of the shared primitives themselves -------------------------

def test_phrase_present_is_word_boundary_aware_for_single_words():
    # The exact false positive fixed in candidate_shortlisting.py:
    # "clinical" must not match inside "preclinical".
    assert not phrase_present("preclinical / mechanistic evidence", "clinical")
    assert phrase_present("a clinical study was performed", "clinical")


def test_phrase_present_handles_irregular_y_plural():
    assert phrase_present("a cohort study was run", "cohort study")
    assert phrase_present("several cohort studies were run", "cohort study")
    assert not phrase_present("cohort studying is different", "cohort study")


def test_find_phrase_matches_returns_each_term_at_most_once_in_order():
    text = "a clinical trial and another clinical trial and a monograph"
    matches = find_phrase_matches(text, ["clinical trial", "monograph", "animal model"])
    assert matches == ["clinical trial", "monograph"]


def test_find_phrase_matches_negation_aware_false_preserves_old_substring_style_behavior():
    # candidate_shortlisting.py's original _evidence_points() had no
    # negation handling at all; negation_aware=False preserves that.
    text = "no clinical trials have been conducted"
    assert has_phrase_match(text, ["clinical trial"], negation_aware=False)


def test_empty_text_never_matches():
    assert not phrase_present("", "clinical trial")
    assert not has_phrase_match("", ["clinical trial", "monograph"])
    assert find_phrase_matches("", ["clinical trial"]) == []
