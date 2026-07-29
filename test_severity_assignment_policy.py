"""
Tests for severity_assignment_policy.py — independent of any single
GoldCase. Covers assign_contraindication_severity() as a pure function
against its own controlled vocabulary (HighRiskInteractionDrugClass),
never against Case 006's specific claim content.
"""

from assertion_vocabulary import AssertionType, SeverityLevel
from severity_assignment_policy import (
    HighRiskInteractionDrugClass, assign_contraindication_severity,
)

_ALL_RECOGNIZED_CLASSES = tuple(HighRiskInteractionDrugClass)


def test_each_recognized_class_individually_returns_serious():
    """Each individual HighRiskInteractionDrugClass value, alone, maps
    to SeverityLevel.SERIOUS for a CONTRAINDICATION claim."""
    for drug_class in _ALL_RECOGNIZED_CLASSES:
        result = assign_contraindication_severity(
            assertion_type=AssertionType.CONTRAINDICATION,
            drug_classes=frozenset({drug_class}),
        )
        assert result == SeverityLevel.SERIOUS, f"{drug_class!r} did not map to SERIOUS"


def test_each_recognized_class_individually_returns_serious_for_interaction():
    """Same as above, for AssertionType.INTERACTION — the policy
    explicitly covers both assertion types (module docstring)."""
    for drug_class in _ALL_RECOGNIZED_CLASSES:
        result = assign_contraindication_severity(
            assertion_type=AssertionType.INTERACTION,
            drug_classes=frozenset({drug_class}),
        )
        assert result == SeverityLevel.SERIOUS, f"{drug_class!r} did not map to SERIOUS for INTERACTION"


def test_multiple_recognized_classes_together_return_serious():
    """A claim naming several recognized classes at once (Case 006's
    own real shape: transplant immunosuppressants + anticoagulants +
    antiretrovirals + cytotoxics) still resolves to exactly SERIOUS —
    not a higher or different value; SERIOUS is the ceiling this
    policy defines."""
    result = assign_contraindication_severity(
        assertion_type=AssertionType.CONTRAINDICATION,
        drug_classes=frozenset({
            HighRiskInteractionDrugClass.TRANSPLANT_IMMUNOSUPPRESSANT,
            HighRiskInteractionDrugClass.ANTICOAGULANT,
            HighRiskInteractionDrugClass.ANTIRETROVIRAL_THERAPY,
            HighRiskInteractionDrugClass.CYTOTOXIC_AGENT,
        }),
    )
    assert result == SeverityLevel.SERIOUS


def test_empty_class_set_returns_none():
    """No drug classes supplied at all -> no rule applies -> None,
    never a guessed severity."""
    result = assign_contraindication_severity(
        assertion_type=AssertionType.CONTRAINDICATION,
        drug_classes=frozenset(),
    )
    assert result is None


def test_unsupported_assertion_type_returns_none():
    """An assertion_type this policy does not cover (e.g.
    SUPPORTS_INDICATION) returns None regardless of drug_classes —
    this policy is scoped to CONTRAINDICATION/INTERACTION only."""
    result = assign_contraindication_severity(
        assertion_type=AssertionType.SUPPORTS_INDICATION,
        drug_classes=frozenset({HighRiskInteractionDrugClass.ANTICOAGULANT}),
    )
    assert result is None


def test_unrecognized_class_outside_vocabulary_returns_none():
    """A caller passing something outside the controlled vocabulary
    (simulated here via a plain string masquerading as a class,
    passed inside the frozenset) gets no assignment — never a
    partial/best-effort SERIOUS computed from the recognized subset
    it happens to also contain."""
    result = assign_contraindication_severity(
        assertion_type=AssertionType.CONTRAINDICATION,
        drug_classes=frozenset({"NOT_A_REAL_DRUG_CLASS"}),
    )
    assert result is None


def test_mixed_recognized_and_unrecognized_classes_fails_closed_to_none():
    """A set containing ONE recognized HighRiskInteractionDrugClass
    together with ONE unrecognized/invalid value must NOT silently
    assign SERIOUS from the recognized member while ignoring the
    invalid one — assign_contraindication_severity()'s own
    `issubset(set(HighRiskInteractionDrugClass))` check (severity_
    assignment_policy.py) requires the ENTIRE input set to be within
    the controlled vocabulary, so any invalid member fails the whole
    call closed to None. This is the policy's documented validation
    contract (module docstring: 'a caller passing something outside
    the controlled vocabulary gets no assignment, never a partial/
    best-effort one silently computed from the recognized subset'),
    exercised here specifically for a MIXED set (one valid + one
    invalid), not just an all-invalid set as in the test above."""
    result = assign_contraindication_severity(
        assertion_type=AssertionType.CONTRAINDICATION,
        drug_classes=frozenset({
            HighRiskInteractionDrugClass.ANTICOAGULANT,  # recognized
            "NOT_A_REAL_DRUG_CLASS",                      # unrecognized
        }),
    )
    assert result is None, (
        "expected fail-closed None for a mixed valid+invalid input set — "
        f"got {result!r} instead, which would mean SERIOUS was silently "
        "assigned from the recognized subset while ignoring invalid input"
    )

    # Same check for AssertionType.INTERACTION, the policy's other
    # covered assertion type — the fail-closed contract must not be
    # assertion-type-specific.
    result_interaction = assign_contraindication_severity(
        assertion_type=AssertionType.INTERACTION,
        drug_classes=frozenset({
            HighRiskInteractionDrugClass.TRANSPLANT_IMMUNOSUPPRESSANT,
            "ALSO_NOT_A_REAL_DRUG_CLASS",
        }),
    )
    assert result_interaction is None


def test_no_accidental_moderate_or_minor_assignment():
    """This policy currently formalizes only the SERIOUS case (module
    docstring: 'WHAT THIS RULE DELIBERATELY DOES NOT COVER'). No input
    combination should ever produce MODERATE or MINOR — only SERIOUS
    or None."""
    possible_results = set()
    # Every non-empty subset of the recognized classes, both assertion types.
    from itertools import combinations
    for assertion_type in (AssertionType.CONTRAINDICATION, AssertionType.INTERACTION, AssertionType.SUPPORTS_INDICATION):
        for r in range(0, len(_ALL_RECOGNIZED_CLASSES) + 1):
            for combo in combinations(_ALL_RECOGNIZED_CLASSES, r):
                possible_results.add(
                    assign_contraindication_severity(
                        assertion_type=assertion_type,
                        drug_classes=frozenset(combo),
                    )
                )
    assert possible_results <= {SeverityLevel.SERIOUS, None}
    assert SeverityLevel.MODERATE not in possible_results
    assert SeverityLevel.MINOR not in possible_results


if __name__ == "__main__":
    import sys
    import traceback

    tests = [
        test_each_recognized_class_individually_returns_serious,
        test_each_recognized_class_individually_returns_serious_for_interaction,
        test_multiple_recognized_classes_together_return_serious,
        test_empty_class_set_returns_none,
        test_unsupported_assertion_type_returns_none,
        test_unrecognized_class_outside_vocabulary_returns_none,
        test_mixed_recognized_and_unrecognized_classes_fails_closed_to_none,
        test_no_accidental_moderate_or_minor_assignment,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {test.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    sys.exit(1 if failures else 0)
