"""Regression tests for question_understanding_engine.py.

This module existed in the repo with no test file at all — flagged
across multiple external reviews as "designed but never wired in."
Now that it's actually called from step_inputs.py, it needs real
coverage; the first bug these tests would have caught (see
test_normalize_functions_dont_mangle_already_formatted_values) was
found by actually running the wiring end-to-end, not by inspection.
"""

from question_understanding_engine import (
    normalize_market,
    normalize_dosage_form,
    normalize_indication,
    infer_route,
    infer_product_type,
    infer_regulatory_focus,
    infer_evidence_requirements,
    standardize_project_definition,
)


def test_normalize_functions_dont_mangle_already_formatted_values():
    # The exact bug: .title() applied blindly to a value that was
    # ALREADY correctly formatted (e.g. coming from
    # free_text_question_parser.py's own canonical vocabulary) mangled
    # apostrophes and acronyms. Only surfaced once this module was
    # actually wired into a live path for the first time.
    assert normalize_indication("Cognitive decline / Alzheimer's support") == "Cognitive decline / Alzheimer's support"
    assert normalize_market("Middle East / GCC") == "Middle East / GCC"


def test_normalize_functions_still_title_case_raw_lowercase_input():
    # The ORIGINAL intended use case (a person typing lowercase free
    # text) must still work.
    assert normalize_indication("sleep") == "Sleep Support"
    assert normalize_market("eu") == "European Union"
    assert normalize_dosage_form("tea") == "Herbal Infusion"


def test_normalize_indication_unknown_lowercase_value_gets_title_cased():
    assert normalize_indication("some new indication") == "Some New Indication"


def test_infer_route_from_dosage_form():
    assert infer_route("Herbal Infusion") == "Oral"
    assert infer_route("Nasal Spray") == "Intranasal"
    assert infer_route("Cream") == "Topical"
    assert infer_route("something unrecognized") == "Not specified"


def test_infer_product_type_distinguishes_food_from_supplement_from_medicinal():
    assert infer_product_type("Herbal Infusion", "Sleep Support") == "Botanical Food Product"
    assert infer_product_type("Capsule", "Sleep Support") == "Botanical Food Supplement"
    assert infer_product_type("Nasal Spray", "Allergic Rhinitis") == "Botanical Medicinal Product Candidate"


def test_infer_regulatory_focus_includes_eu_specific_items_for_eu_market():
    focus = infer_regulatory_focus("eu", "Capsule", "Sleep Support")
    assert "EU Regulatory Framework" in focus
    assert "EMA-HMPC Monographs" in focus


def test_infer_evidence_requirements_always_includes_the_baseline_set():
    reqs = infer_evidence_requirements("Capsule", "Sleep Support")
    assert "EMA-HMPC" in reqs
    assert "Clinical Evidence" in reqs
    assert "Safety Evidence" in reqs


def test_infer_evidence_requirements_adds_cns_requirement_for_sleep_indication():
    reqs = infer_evidence_requirements("Capsule", "insomnia")
    assert "Human Clinical Evidence for CNS-Related Claims" in reqs


def test_standardize_project_definition_end_to_end():
    result = standardize_project_definition({
        "product": "Cognitive decline / Alzheimer's support",
        "dosage_form": "Capsule",
        "indication": "Cognitive decline / Alzheimer's support",
        "market": "European Union",
        "population": "Elderly / older adults",
        "constraints": ["Low CYP interaction risk"],
    })
    assert result["route"] == "Oral"
    assert result["target_market"] == "European Union"
    assert result["target_population"] == "Elderly / older adults"
    assert result["constraints"] == ["Low CYP interaction risk"]
    assert "regulatory_focus" in result
    assert "evidence_requirements" in result


def test_standardize_project_definition_defaults_population_to_adults():
    result = standardize_project_definition({
        "dosage_form": "Capsule", "indication": "Sleep Support", "market": "EU",
    })
    assert result["target_population"] == "Adults"


def test_standardize_project_definition_handles_empty_input_gracefully():
    result = standardize_project_definition({})
    assert result["product"] == "Not specified"
    assert result["dosage_form"] == "Not specified"


if __name__ == "__main__":
    import sys

    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        this_module = sys.modules[__name__]
        test_fns = [
            getattr(this_module, name)
            for name in dir(this_module)
            if name.startswith("test_") and callable(getattr(this_module, name))
        ]
        passed, failed = [], []
        for fn in test_fns:
            try:
                fn()
            except AssertionError as exc:
                failed.append((fn.__name__, str(exc) or "assertion failed"))
            except Exception as exc:  # noqa: BLE001
                failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            else:
                passed.append(fn.__name__)
        print(f"\n{len(passed) + len(failed)} test(s) run.\n")
        for name in passed:
            print(f"  \u2705 {name}")
        if failed:
            print()
            for name, reason in failed:
                print(f"  \u274c {name}\n     -> {reason}")
            print(f"\n{len(failed)} FAILED, {len(passed)} passed.\n")
            sys.exit(1)
        print(f"\nALL TESTS PASSED ({len(passed)}/{len(passed)}).\n")
        sys.exit(0)
