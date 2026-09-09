import math

import pytest

from evidence_id_parsing import normalize_evidence_ids, count_evidence_ids


# --- Section 34: mandatory empty-collection tests --------------------------

@pytest.mark.parametrize("value", [
    None, "", [], (), set(), {}, "[]", "()", "{}", "None", "nan",
    "NaN", "NULL", "N/A", "n/a", "  ", "set()",
])
def test_all_empty_representations_count_as_zero(value):
    assert normalize_evidence_ids(value) == []
    assert count_evidence_ids(value) == 0


def test_float_nan_counts_as_zero():
    assert normalize_evidence_ids(float("nan")) == []


# --- Section 34: mandatory content-parsing tests ----------------------------

def test_actual_list_parses_correctly():
    assert normalize_evidence_ids(["E1", "E2"]) == ["E1", "E2"]


def test_actual_tuple_parses_correctly():
    assert normalize_evidence_ids(("E1", "E2")) == ["E1", "E2"]


def test_semicolon_separated_string_parses_correctly():
    assert normalize_evidence_ids("E1;E2") == ["E1", "E2"]


def test_comma_separated_string_parses_correctly():
    assert normalize_evidence_ids("E1,E2") == ["E1", "E2"]


def test_json_array_string_parses_correctly():
    assert normalize_evidence_ids('["E1","E2"]') == ["E1", "E2"]


def test_python_repr_tuple_string_parses_correctly():
    assert normalize_evidence_ids("('E1', 'E2')") == ["E1", "E2"]


def test_python_repr_set_string_parses_correctly():
    result = normalize_evidence_ids("{'E1', 'E2'}")
    assert set(result) == {"E1", "E2"}
    assert len(result) == 2


def test_single_bare_id_string_parses_as_one():
    assert normalize_evidence_ids("E1") == ["E1"]


def test_single_element_json_array_parses_as_one():
    assert normalize_evidence_ids('["E1"]') == ["E1"]
    assert count_evidence_ids('["E1"]') == 1


# --- The exact production bug scenario --------------------------------------

def test_empty_tuple_repr_string_never_counts_as_one():
    """The exact reported production bug: Direct_Human_Outcome_Evidence_IDs
    round-tripped to the literal string "()" must count as 0, not 1.
    """
    assert count_evidence_ids("()") == 0
    assert normalize_evidence_ids("()") == []


def test_empty_list_repr_string_never_counts_as_one():
    assert count_evidence_ids("[]") == 0


def test_naive_semicolon_split_would_have_been_wrong_but_this_is_not():
    """Documents exactly why a naive `str(value).split(';')` is wrong:
    it would produce ["()"], a list of length 1. This function must not.
    """
    naive_wrong_result = [p for p in str("()").split(";") if p.strip()]
    assert naive_wrong_result == ["()"]  # the bug, reproduced in isolation
    assert normalize_evidence_ids("()") != naive_wrong_result
    assert normalize_evidence_ids("()") == []


# --- Deduplication -----------------------------------------------------------

def test_duplicate_ids_are_deduplicated_preserving_first_occurrence_order():
    assert normalize_evidence_ids(["E1", "E2", "E1", "E3", "e1"]) == ["E1", "E2", "E3"]


def test_whitespace_and_quote_padded_tokens_are_cleaned():
    assert normalize_evidence_ids("  E1 ; E2  ") == ["E1", "E2"]


# --- Never raises -------------------------------------------------------------

def test_never_raises_on_unusual_input():
    for value in [123, 1.5, True, {"a": "b"}, object()]:
        # Must not raise -- degrade to a best-effort or empty result.
        normalize_evidence_ids(value)
