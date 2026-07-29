"""Tests for subject_normalization.py (v4 correction #5)."""

from subject_normalization import normalize_subject, SUBJECT_NORMALIZATION_RULE_VERSION


def test_pregnancy_variants_normalize_to_same_subject():
    assert normalize_subject("pregnancy") == normalize_subject("pregnant women")
    assert normalize_subject("pregnancy") == normalize_subject("use in pregnancy")
    assert normalize_subject("pregnancy") == normalize_subject("during pregnancy")


def test_normalization_is_case_insensitive():
    assert normalize_subject("Pregnancy") == normalize_subject("pregnancy")
    assert normalize_subject("PREGNANT WOMEN") == normalize_subject("pregnant women")


def test_normalization_collapses_whitespace():
    assert normalize_subject("  pregnancy  ") == normalize_subject("pregnancy")
    assert normalize_subject("pregnant   women") == normalize_subject("pregnant women")


def test_unrelated_subjects_do_not_collide():
    assert normalize_subject("pregnancy") != normalize_subject("hepatic impairment")
    assert normalize_subject("pregnancy") != normalize_subject("lactation")


def test_lactation_variants_normalize_together():
    assert normalize_subject("lactation") == normalize_subject("breastfeeding")
    assert normalize_subject("lactation") == normalize_subject("nursing mothers")


def test_pediatric_variants_normalize_together():
    assert normalize_subject("pediatric") == normalize_subject("children")
    assert normalize_subject("pediatric") == normalize_subject("paediatric")


def test_unrecognized_subject_normalizes_to_its_own_collapsed_form():
    result = normalize_subject("  Some Unusual Subject  ")
    assert result == "some unusual subject"


def test_unrecognized_subject_never_raises():
    normalize_subject("")
    normalize_subject("")


def test_rule_version_is_a_non_empty_string():
    assert isinstance(SUBJECT_NORMALIZATION_RULE_VERSION, str)
    assert len(SUBJECT_NORMALIZATION_RULE_VERSION) > 0


def test_normalization_is_deterministic():
    assert normalize_subject("pregnant women") == normalize_subject("pregnant women")
