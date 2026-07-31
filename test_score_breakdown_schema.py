"""Tests for score_breakdown_schema.py (IMPLEMENTATION_PLAN.md Phase 1)."""

from score_breakdown_schema import (
    CANONICAL_SECTIONS,
    INDICATION_CANONICAL_SECTIONS,
    COMPONENT_TO_DIMENSIONS,
    parse_score_breakdown,
)

_LEGACY_BREAKDOWN = (
    "Chemical/mechanistic link: +22.0; Evidence quality: +24.0; "
    "Product-development fit: +18.0; Novelty: +10.0; Market signal: +2.0; "
    "Safety/interaction/self-row penalty: +0.0"
)

_INDICATION_BREAKDOWN = {
    "Direct indication evidence": 35,
    "Traceability": 10,
    "Mechanistic plausibility": 10,
    "Preparation applicability": 8,
    "Compound support (non-gating; max 5)": 5,
    "Baseline development potential": 10,
}


def test_parses_legacy_formatted_string():
    parsed = parse_score_breakdown(_LEGACY_BREAKDOWN)
    assert parsed["Evidence quality"] == 24.0
    assert set(parsed.keys()) == CANONICAL_SECTIONS


def test_parses_indication_centric_dict():
    parsed = parse_score_breakdown(_INDICATION_BREAKDOWN)
    assert parsed["Direct indication evidence"] == 35.0
    assert set(parsed.keys()) == INDICATION_CANONICAL_SECTIONS


def test_empty_and_placeholder_return_empty_dict():
    assert parse_score_breakdown("") == {}
    assert parse_score_breakdown(None) == {}
    assert parse_score_breakdown("No breakdown available") == {}
    assert parse_score_breakdown({}) == {}


def test_tolerates_multi_compound_match_bonus_suffix():
    parsed = parse_score_breakdown("Evidence quality: +24.0; Multi-compound match bonus: +10.0")
    assert parsed["Multi-compound match bonus"] == 10.0


def test_dict_form_skips_non_numeric_values_without_raising():
    parsed = parse_score_breakdown({"Direct indication evidence": 35, "Notes": "not a number"})
    assert parsed == {"Direct indication evidence": 35.0}


def test_string_form_skips_unparseable_parts_without_raising():
    parsed = parse_score_breakdown("Evidence quality: +24.0; malformed part with no colon")
    assert parsed == {"Evidence quality": 24.0}


def test_current_indication_key_is_present_in_both_canonical_set_and_dimension_map():
    # The exact regression this module exists to prevent: the compound-support
    # key name drifted once already (indication_candidate_discovery.py).
    # Both the canonical set and the dimension map must use the live key.
    live_key = "Compound support (non-gating; max 5)"
    assert live_key in INDICATION_CANONICAL_SECTIONS
    assert live_key in COMPONENT_TO_DIMENSIONS


def test_every_canonical_section_has_a_dimension_mapping():
    for section in CANONICAL_SECTIONS | INDICATION_CANONICAL_SECTIONS:
        assert section in COMPONENT_TO_DIMENSIONS, f"{section!r} has no dimension mapping"


def test_regulatory_is_never_a_mapped_dimension():
    for dims in COMPONENT_TO_DIMENSIONS.values():
        assert "Regulatory" not in dims
