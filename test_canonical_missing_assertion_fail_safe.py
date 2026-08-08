
from canonical_scientific_assertion import (
    resolve_record_direction, CANONICAL_UNCLEAR
)

def test_missing_structured_direction_abstains_even_if_raw_text_sounds_positive():
    r=resolve_record_direction(
        {"assertion_text":"The intervention was more effective than placebo."},
        fallback_fn=lambda _: "positive",
    )
    assert r.direction == CANONICAL_UNCLEAR
    assert r.provenance == "missing_structured_direction"

def test_missing_structured_direction_abstains_even_if_raw_text_sounds_null():
    r=resolve_record_direction(
        {"assertion_text":"The intervention did not improve symptoms."},
        fallback_fn=lambda _: "null",
    )
    assert r.direction == CANONICAL_UNCLEAR
