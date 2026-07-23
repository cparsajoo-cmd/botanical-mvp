"""Regression tests for product_development_concept.py."""

import pandas as pd

from product_development_concept import (
    build_development_concept_text,
    add_development_concept_column,
    NOT_TRACKED,
)


def _make_row(**overrides):
    base = {
        "Alternative_Plant": "Silybum marianum",
        "Alternative_Plant_Part": "Seed",
        "Extraction_Method": "Hydroethanolic extract",
        "indication": "Liver support",
        "Target_Market": "European Union",
        "Market_Status": "Regulatory monograph exists",
        "White_Space_Type": "",
        "Commercial_Regulatory_Rationale": "Market status: Regulatory monograph exists.",
    }
    base.update(overrides)
    return base


def test_development_concept_includes_plant_and_plant_part():
    text = build_development_concept_text(_make_row())
    assert "Silybum marianum" in text
    assert "Seed" in text


def test_development_concept_honestly_labels_untracked_fields():
    text = build_development_concept_text(_make_row())
    assert text.count(NOT_TRACKED) == 4  # chemotype, DER, standardization marker, dose
    assert "Chemotype" in text
    assert "DER" in text
    assert "Standardization marker" in text
    assert "Dose:" in text


def test_development_concept_uses_standardized_project_when_provided():
    standardized_project = {
        "dosage_form": "Capsule",
        "route": "Oral",
        "target_indication": "Liver Support",
        "target_population": "Elderly / older adults",
        "target_market": "European Union",
        "regulatory_focus": ["EU Regulatory Framework", "EMA-HMPC Monographs"],
    }
    text = build_development_concept_text(_make_row(), standardized_project)
    assert "Capsule" in text
    assert "Oral route" in text
    assert "Elderly / older adults" in text
    assert "EMA-HMPC Monographs" in text


def test_development_concept_falls_back_gracefully_with_no_standardized_project():
    text = build_development_concept_text(_make_row(), standardized_project=None)
    assert "Not specified" in text  # route falls back since no standardized_project given


def test_development_concept_shows_white_space_as_commercial_positioning_when_present():
    text = build_development_concept_text(_make_row(White_Space_Type="Industrial R&D White Space"))
    assert "Commercial positioning: Industrial R&D White Space" in text


def test_add_development_concept_column_adds_one_column_per_row():
    df = pd.DataFrame([_make_row(), _make_row(Alternative_Plant="Matricaria chamomilla")])
    enriched = add_development_concept_column(df)
    assert "Product_Development_Concept" in enriched.columns
    assert len(enriched) == 2
    assert "Silybum marianum" in enriched.iloc[0]["Product_Development_Concept"]
    assert "Matricaria chamomilla" in enriched.iloc[1]["Product_Development_Concept"]


def test_add_development_concept_column_does_not_mutate_input():
    df = pd.DataFrame([_make_row()])
    original_columns = list(df.columns)
    add_development_concept_column(df)
    assert list(df.columns) == original_columns


def test_add_development_concept_column_handles_empty_dataframe():
    result = add_development_concept_column(pd.DataFrame())
    assert result.empty


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
