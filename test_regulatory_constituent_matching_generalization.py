
from regulatory_scope_assessment import detect_dose_threshold_violation


def test_constituent_before_limit_phrase_is_matched():
    f=detect_dose_threshold_violation(
        "Compound-X shall not exceed 800 mg per daily portion.",
        "Daily portion provides 900 mg Compound-X.",
    )
    assert f is not None
    assert f.constituent == "compound-x"
    assert f.actual_value == 900
    assert f.violates is True


def test_amount_of_constituent_before_limit_phrase_is_matched():
    f=detect_dose_threshold_violation(
        "The amount of Compound-X shall not exceed 50 mg per day.",
        "60 mg Compound-X per day.",
    )
    assert f is not None
    assert f.constituent == "compound-x"
    assert f.actual_value == 60
    assert f.violates is True


def test_parenthetical_abbreviation_is_a_generic_alias():
    f=detect_dose_threshold_violation(
        "Less than 800 mg of Long-Compound-Name (LCN) per daily portion is required.",
        "The daily portion provides 900 mg LCN.",
    )
    assert f is not None
    assert f.constituent == "long-compound-name"
    assert f.actual_value == 900
    assert f.violates is True


def test_unrelated_first_quantity_is_not_used():
    f=detect_dose_threshold_violation(
        "Less than 800 mg Compound-X per daily portion is required.",
        "100 mg vitamin C and 900 mg Compound-X per daily portion.",
    )
    assert f is not None
    assert f.actual_value == 900
    assert f.violates is True


def test_larger_unrelated_quantity_does_not_create_false_violation():
    f=detect_dose_threshold_violation(
        "Less than 800 mg Compound-X per daily portion is required.",
        "900 mg vitamin C and 500 mg Compound-X per daily portion.",
    )
    assert f is not None
    assert f.actual_value == 500
    assert f.violates is False


def test_strict_less_than_boundary_remains_exclusive():
    f=detect_dose_threshold_violation(
        "Less than 800 mg Compound-X per daily portion is required.",
        "800 mg Compound-X per daily portion.",
    )
    assert f is not None and f.violates is True


def test_no_more_than_boundary_remains_inclusive():
    f=detect_dose_threshold_violation(
        "No more than 800 mg Compound-X per daily portion is permitted.",
        "800 mg Compound-X per daily portion.",
    )
    assert f is not None and f.violates is False
