"""Regression suite for the 2026-08-08 audit fix: interpret_evidence()'s
new `contributing_records` parameter.

BACKGROUND — what this closes

canonical_scientific_assertion.resolve_record_direction() already existed
and already implements the correct precedence (structured source
assertion > LLM extraction > legacy reported direction > per-record text
fallback), and the Reference-Grounded Validation decision path
(evidence_body_assessment.py / final_decision_policy.py) already used it
correctly. But botanical_rd_candidate_engine.py's own scoring path —
_collect_raw_evidence() -> interpret_evidence() — never called it at all:
it always re-guessed direction from classify_evidence_direction() run on
ONE pooled, multi-source text blob, even for records that already had a
structured Result_Direction (e.g. from backfill_canonical_assertions.py).

This suite proves three things against the real functions, not mocks of
them:

1. Backward compatibility: interpret_evidence() with no
   `contributing_records` (every existing caller/test) is byte-identical
   to before.
2. Structured direction now wins over pooled-text re-guessing when it's
   available, per record.
3. Even for records with NO structured direction, per-record text
   fallback (classifying each record's own text individually) behaves
   differently from — and is expected to be more accurate than —
   classifying one pooled blob, because pooling can dilute or bury the
   signal from a single record among unrelated text from others. This is
   the mechanism named in the Reference-Grounded Validation v2 root-cause
   sanity check, independent of any single phrase-table gap.
"""
import pytest

from evidence_interpretation import (
    interpret_evidence,
    classify_evidence_direction,
    DIRECTION_POSITIVE,
    DIRECTION_NEGATIVE,
    DIRECTION_NULL,
    DIRECTION_MIXED,
    DIRECTION_UNCLEAR,
    DIRECTION_CONTRIBUTION_RATIO,
    DEFAULT_CLINICAL_WEIGHT,
    _resolve_pooled_direction,
)


POSITIVE_TEXT = "The trial showed significant improvement versus placebo."
NEGATIVE_TEXT = "The trial failed to demonstrate efficacy over placebo."
NULL_TEXT = "There was no significant difference from placebo."
UNCLEAR_TEXT = "A trial is planned to evaluate this botanical."
# Deliberately distinct from UNCLEAR_TEXT: this text trips no
# positive/null/negative phrase AND no future/planned/ongoing-without-
# result phrase, so classify_evidence_applicability() resolves it to
# APPLICABILITY_DIRECT rather than APPLICABILITY_CONTEXTUAL_OR_FUTURE.
# Needed to isolate "direction resolved from structured data" from
# "applicability zeroed the contribution anyway for an unrelated reason"
# in the contribution-value assertion below.
NEUTRAL_COMPLETED_TEXT = (
    "This report was published in a peer-reviewed journal covering "
    "botanical safety topics."
)


def _record(*, text="", source_result_direction=None, llm_result_direction=None,
            reported_direction=None, assertion_text=None):
    return {
        "text": text,
        "assertion_text": assertion_text if assertion_text is not None else text,
        "source_result_direction": source_result_direction,
        "llm_result_direction": llm_result_direction,
        "reported_direction": reported_direction,
    }


# ---------------------------------------------------------------------
# 1. Backward compatibility.
# ---------------------------------------------------------------------
def test_no_contributing_records_is_byte_identical_to_before():
    """Default (omitted) argument: behavior must match the pre-fix
    function exactly -- every existing caller relies on this."""
    pooled_text = POSITIVE_TEXT + " " + NULL_TEXT  # would classify as MIXED
    baseline = interpret_evidence(pooled_text, clinical_weight=24.0)
    with_none = interpret_evidence(pooled_text, clinical_weight=24.0, contributing_records=None)
    with_empty = interpret_evidence(pooled_text, clinical_weight=24.0, contributing_records=[])

    for result in (with_none, with_empty):
        assert result.evidence_direction == baseline.evidence_direction
        assert result.study_design == baseline.study_design
        assert result.evidence_quality == baseline.evidence_quality
        assert result.evidence_applicability == baseline.evidence_applicability
        assert result.contribution == baseline.contribution
        assert result.direction_provenance == []


def test_other_fields_unaffected_when_contributing_records_supplied():
    """study_design/quality/applicability stay derived from the pooled
    text even when contributing_records changes evidence_direction --
    out of scope for this pass, must not silently change."""
    pooled_text = "Randomized, double-blind, placebo-controlled trial. " + UNCLEAR_TEXT
    records = [_record(source_result_direction="Positive", text=pooled_text)]

    without = interpret_evidence(pooled_text, clinical_weight=24.0)
    with_records = interpret_evidence(pooled_text, clinical_weight=24.0, contributing_records=records)

    assert with_records.study_design == without.study_design
    assert with_records.evidence_quality == without.evidence_quality
    assert with_records.evidence_applicability == without.evidence_applicability
    assert with_records.evidence_direction != without.evidence_direction  # this DID change


# ---------------------------------------------------------------------
# 2. Structured direction wins over pooled-text re-guessing.
# ---------------------------------------------------------------------
def test_structured_positive_direction_overrides_unclear_pooled_text():
    """The exact production scenario this fix targets: a record has a
    real backfilled Result_Direction, but its own prose (or the blob it
    was pooled into) doesn't trip any phrase-table entry."""
    records = [_record(source_result_direction="Positive", text=NEUTRAL_COMPLETED_TEXT)]
    result = interpret_evidence(
        NEUTRAL_COMPLETED_TEXT, clinical_weight=24.0, contributing_records=records
    )

    assert result.evidence_direction == DIRECTION_POSITIVE
    assert result.direction_provenance == ["source_result_direction"]
    assert result.contribution == pytest.approx(
        24.0 * DIRECTION_CONTRIBUTION_RATIO[DIRECTION_POSITIVE]
    )


def test_llm_result_direction_used_when_source_direction_absent():
    records = [_record(llm_result_direction="Negative", text=UNCLEAR_TEXT)]
    result = interpret_evidence(UNCLEAR_TEXT, clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_NEGATIVE
    assert result.direction_provenance == ["llm_result_direction"]


def test_source_direction_takes_precedence_over_llm_direction():
    records = [_record(source_result_direction="Positive", llm_result_direction="Negative")]
    result = interpret_evidence("", clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_POSITIVE
    assert result.direction_provenance == ["source_result_direction"]


def test_explicit_unclear_structured_value_is_not_promoted_by_text_fallback():
    """resolve_record_direction()'s own rule: an EXPLICIT 'Unknown' from
    the source/LLM is meaningful and must not be overridden by whatever
    the text classifier happens to find elsewhere in the record."""
    records = [_record(source_result_direction="Unknown", text=POSITIVE_TEXT)]
    result = interpret_evidence(POSITIVE_TEXT, clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_UNCLEAR
    assert result.direction_provenance == ["source_result_direction"]


# ---------------------------------------------------------------------
# 3. Per-record text fallback vs. pooled-blob dilution.
# ---------------------------------------------------------------------
def test_per_record_fallback_finds_signal_pooling_would_dilute():
    """Reference-Grounded Validation v2's own root-cause mechanism: one
    genuinely positive record's signal can survive per-record
    classification even where it would have been just one clause inside
    a much longer, unrelated pooled blob. Here we prove the narrower,
    directly testable half of that claim: per-record resolution correctly
    identifies EACH record's own direction independently, rather than
    forcing every contributing record through a single pooled verdict."""
    positive_record = _record(text=POSITIVE_TEXT)
    unrelated_record = _record(text="This document discusses unrelated regulatory history.")
    records = [positive_record, unrelated_record]

    pooled_text = POSITIVE_TEXT + " " + unrelated_record["text"]
    result = interpret_evidence(pooled_text, clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_POSITIVE
    assert result.direction_provenance == ["text_fallback", "text_fallback"]


def test_no_structured_direction_and_no_recoverable_text_is_unclear():
    records = [_record(text=""), _record(text="")]
    result = interpret_evidence("", clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_UNCLEAR
    assert result.contribution == 0.0


def test_disagreeing_records_aggregate_to_mixed():
    records = [
        _record(source_result_direction="Positive"),
        _record(source_result_direction="Negative"),
    ]
    result = interpret_evidence("", clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_MIXED
    assert result.direction_provenance == ["source_result_direction", "source_result_direction"]


def test_agreeing_records_do_not_become_mixed():
    records = [
        _record(source_result_direction="Positive"),
        _record(text=POSITIVE_TEXT),  # resolves via text_fallback to the same direction
    ]
    result = interpret_evidence(POSITIVE_TEXT, clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_POSITIVE


def test_one_structured_one_uninformative_record_is_not_forced_to_mixed():
    """An uninformative ('unclear') record must not drag a genuinely
    single-direction body of evidence into 'mixed' -- only a real
    disagreement between two INFORMATIVE directions should."""
    records = [
        _record(source_result_direction="Positive"),
        _record(text=""),  # resolves to unclear -- carries no information
    ]
    result = interpret_evidence("", clinical_weight=24.0, contributing_records=records)

    assert result.evidence_direction == DIRECTION_POSITIVE


# ---------------------------------------------------------------------
# _resolve_pooled_direction() unit-level coverage (the aggregation rule
# in isolation, independent of interpret_evidence()'s other fields).
# ---------------------------------------------------------------------
def test_resolve_pooled_direction_empty_list_is_unclear():
    direction, provenance, supporting = _resolve_pooled_direction([])
    assert direction == DIRECTION_UNCLEAR
    assert provenance == []
    assert supporting == []


def test_resolve_pooled_direction_null_and_negative_still_aggregate_to_mixed():
    records = [_record(text=NULL_TEXT), _record(text=NEGATIVE_TEXT)]
    direction, provenance, supporting = _resolve_pooled_direction(records)
    assert direction == DIRECTION_MIXED
    assert provenance == ["text_fallback", "text_fallback"]
    # Both "null" (no significant difference) and "negative" are
    # informative (non-"unclear") directions, so both records support
    # the "mixed" outcome.
    assert supporting == records


# ---------------------------------------------------------------------
# Root-cause regression (2026-08-11, external audit point 5): the
# strongest source authority among ALL pooled records used to represent
# the whole bucket, even records with nothing to do with the resolved
# direction. supporting_records must be exactly the records whose own
# direction equals the aggregate, so a weak-authority positive finding
# cannot borrow a strong-authority but off-topic/unclear record's clout.
# ---------------------------------------------------------------------
def test_resolve_pooled_direction_supporting_records_excludes_unclear_and_off_direction():
    positive_rec = _record(text=POSITIVE_TEXT)
    unclear_rec = _record(text="")
    negative_rec = _record(text=NEGATIVE_TEXT)
    direction, _, supporting = _resolve_pooled_direction([positive_rec, unclear_rec])
    assert direction == DIRECTION_POSITIVE
    assert supporting == [positive_rec]

    direction2, _, supporting2 = _resolve_pooled_direction([positive_rec, negative_rec])
    assert direction2 == DIRECTION_MIXED
    assert supporting2 == [positive_rec, negative_rec]
