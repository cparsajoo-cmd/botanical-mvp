from evidence_interpretation import (
    classify_evidence_direction,
    DIRECTION_POSITIVE,
    DIRECTION_NULL,
    DIRECTION_NEGATIVE,
    DIRECTION_MIXED,
)

def test_calibrated_generic_positive_language():
    assert classify_evidence_direction(
        "Treatment significantly reduced symptom severity and produced greater improvement than placebo."
    )[0] == DIRECTION_POSITIVE

def test_calibrated_generic_null_language():
    assert classify_evidence_direction(
        "There were no statistically significant effects between treatment and placebo."
    )[0] == DIRECTION_NULL

def test_calibrated_generic_negative_language():
    assert classify_evidence_direction(
        "Treatment did not improve symptoms and was no more effective than placebo."
    )[0] == DIRECTION_NEGATIVE

def test_calibrated_generic_mixed_language():
    assert classify_evidence_direction(
        "Treatment significantly improved symptoms, but there was no significant effect on the secondary outcome."
    )[0] == DIRECTION_MIXED

def test_no_plant_or_case_specific_vocabulary_is_required():
    text = "Intervention was clinically effective, but had no significant effect on one secondary outcome."
    assert classify_evidence_direction(text)[0] == DIRECTION_MIXED
