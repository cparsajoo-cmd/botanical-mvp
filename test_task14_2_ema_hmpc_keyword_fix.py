"""
Task 14.2 — Fix EMA/HMPC Keyword False Positives.

WHAT THIS COVERS
evidence_extractor.contains_ema_hmpc_reference() — the dedicated,
word-boundary-aware EMA/HMPC authority-mention matcher that replaces
the previous plain-substring check for this one keyword group only,
plus an extraction-level regression test proving the fix actually
changes extract_evidence_from_text()'s real output correctly (not just
the helper in isolation).

WHAT THIS DELIBERATELY DOES NOT COVER
WHO/ESCOP detection, Novel_Food_Status, Source_Type, Evidence_Level,
LLM standardization, the EMA connector, RegulatoryRecord, regulatory
gates, scoring, ranking, reports, persistence, Streamlit, or database
schema — none of these were touched by this task, and none are
exercised here as anything other than an unchanged-behavior check.

HOW TO RUN
    pytest -q test_task14_2_ema_hmpc_keyword_fix.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

from evidence_extractor import contains_ema_hmpc_reference, extract_evidence_from_text


# ---------------------------------------------------------------------
# Positive cases (1-9): genuine EMA/HMPC mentions.
# ---------------------------------------------------------------------

def test_bare_uppercase_ema():
    assert contains_ema_hmpc_reference("EMA") is True


def test_bare_lowercase_ema():
    assert contains_ema_hmpc_reference("ema") is True


def test_parenthesized_ema():
    assert contains_ema_hmpc_reference("(EMA)") is True


def test_ema_slash_hmpc():
    assert contains_ema_hmpc_reference("EMA/HMPC") is True


def test_ema_space_hmpc():
    assert contains_ema_hmpc_reference("EMA HMPC") is True


def test_bare_hmpc():
    assert contains_ema_hmpc_reference("HMPC") is True


def test_full_phrase_european_medicines_agency():
    assert contains_ema_hmpc_reference("European Medicines Agency") is True


def test_possessive_european_medicines_agencys_assessment():
    assert contains_ema_hmpc_reference("European Medicines Agency's assessment") is True


def test_sentence_containing_genuine_standalone_ema_reference():
    assert contains_ema_hmpc_reference(
        "The plant was formally reviewed by EMA in 2020 for possible monograph status."
    ) is True
    assert contains_ema_hmpc_reference("EMA,") is True
    assert contains_ema_hmpc_reference("See the EMA.") is True


# ---------------------------------------------------------------------
# Negative cases (10-16): confirmed false-positive words, ordinary
# text, and every missing-value shape.
# ---------------------------------------------------------------------

def test_schema_does_not_match():
    assert contains_ema_hmpc_reference("schema") is False


def test_enema_does_not_match():
    assert contains_ema_hmpc_reference("enema") is False


def test_cinema_does_not_match():
    assert contains_ema_hmpc_reference("cinema") is False


def test_schematic_does_not_match():
    assert contains_ema_hmpc_reference("schematic") is False


def test_hematoma_does_not_match():
    assert contains_ema_hmpc_reference("hematoma") is False


def test_ordinary_scientific_text_with_no_authority_reference_does_not_match():
    assert contains_ema_hmpc_reference(
        "A randomized controlled trial of valerian root extract for sleep latency "
        "in adults, following a strict dosing schema and enema-free protocol, "
        "shown at a local cinema health fair."
    ) is False


def test_none_nan_pdna_and_empty_strings_return_false():
    for missing_value in (None, float("nan"), pd.NA, "", "   ", "\t\n"):
        assert contains_ema_hmpc_reference(missing_value) is False, f"failed for {missing_value!r}"


def test_other_missing_like_string_tokens_return_false():
    for token in ("nan", "NaN", "None", "NULL", "<NA>", "NaT"):
        assert contains_ema_hmpc_reference(token) is False, f"failed for {token!r}"


# ---------------------------------------------------------------------
# Extraction-level regression test.
# ---------------------------------------------------------------------

def test_record_containing_schema_does_not_receive_ema_positive_status():
    record = extract_evidence_from_text(
        "A randomized trial following a strict dosing schema, with an "
        "enema-preparation protocol, tested in a cinema-adjacent clinic."
    )
    assert record["EMA_Status"] == ""
    assert record["Regulatory_Status"] == ""


def test_record_with_genuine_ema_hmpc_mention_still_receives_ema_positive_status():
    record = extract_evidence_from_text(
        "The European Medicines Agency (EMA) HMPC committee reviewed "
        "Valeriana officinalis for traditional-use monograph status."
    )
    assert record["EMA_Status"] == "Yes"
    assert record["Regulatory_Status"] == "EMA/HMPC evidence detected"


def test_who_and_escop_outputs_remain_unchanged():
    text_with_who = (
        "This substance is covered by a WHO monograph for traditional use, "
        "following a dosing schema unrelated to any other authority."
    )
    record = extract_evidence_from_text(text_with_who)
    assert record["WHO_Status"] == "Yes"
    assert record["EMA_Status"] == ""  # "schema" must not trip EMA

    text_with_escop = "ESCOP guidance supports traditional use in mild sleep disorders."
    record2 = extract_evidence_from_text(text_with_escop)
    assert record2["ESCOP_Status"] == "Yes"
    assert record2["EMA_Status"] == ""


def test_extract_evidence_from_text_input_not_mutated():
    original_text = "A study mentioning EMA and HMPC in a schema-driven trial design."
    text_copy = str(original_text)
    extract_evidence_from_text(original_text)
    assert original_text == text_copy


def test_both_who_and_ema_can_be_detected_independently_in_the_same_text():
    """Confirms the fix didn't accidentally couple EMA detection to
    WHO/ESCOP detection or vice versa."""
    text = (
        "European Medicines Agency review and a separate WHO monograph "
        "both support traditional use; ESCOP guidance concurs."
    )
    record = extract_evidence_from_text(text)
    assert record["EMA_Status"] == "Yes"
    assert record["WHO_Status"] == "Yes"
    assert record["ESCOP_Status"] == "Yes"
