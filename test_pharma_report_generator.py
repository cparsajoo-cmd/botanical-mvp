"""Regression tests for pharma_report_generator.py (Gap 9)."""

import pandas as pd

from pharma_report_generator import generate_pharma_report


def _make_row(**overrides):
    base = dict(
        Reference_Plant="RefPlant", Reference_Compound="RefCompound",
        Alternative_Plant="AltPlant", Shared_or_Similar_Compound="AltCompound",
        Target_or_Mechanism="Hepatoprotective", Target_Provenance="Not applicable",
        Concentration_Info="2 mg/g dry weight", Extraction_Method="Aqueous",
        Co_Compounds="CompoundX", Safety_Flags="No explicit flag found",
        Interaction_Flags="No explicit flag found",
        Evidence_Source="Live-collected evidence (PubMed/Europe PMC/Supabase)",
        Source_Record_IDs="https://pubmed.ncbi.nlm.nih.gov/12345/",
        Occurrence_Corroboration="Single-source claim — not independently corroborated",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Has_Negative_Evidence=False, Negative_Evidence_Types="",
        Market_Status="Regulatory monograph exists", Novelty_Status="Alternative cross-region candidate",
        **{"R&D_Opportunity_Score": 75.0},
        Evidence_Confidence=70.0,
        Decision_Class="Promising candidate; verify safety and standardization",
        Decision_Class_AH="C — Alternative-source R&D candidate",
        White_Space_Type="", Confidence_Note="",
        Go_Investigate_Hold_NoGo="Investigate",
        Scientific_Rationale="Shares a validated biological target.",
        Commercial_Regulatory_Rationale="Market status: Regulatory monograph exists.",
        Evidence_Strengths="High evidence confidence (70)",
        Evidence_Weaknesses="Single-source claim — not independently corroborated",
        Next_Experiment_Suggestion="Quantify compound concentration in AltPlant.",
        Rationale="Full narrative rationale text.",
    )
    base.update(overrides)
    return base


def test_standardized_project_section_appears_when_provided():
    result = pd.DataFrame([_make_row()])
    standardized_project = {
        "product_type": "Botanical Food Supplement",
        "route": "Oral",
        "target_population": "Elderly / older adults",
        "target_market": "European Union",
        "constraints": ["Low CYP interaction risk"],
        "regulatory_focus": ["EU Regulatory Framework", "EMA-HMPC Monographs"],
        "evidence_requirements": ["Clinical Evidence", "Safety Evidence"],
    }
    report = generate_pharma_report(
        result, indication="Liver support", dosage_form="Infusion", market="EU",
        standardized_project=standardized_project,
    )
    assert "## Project Definition" in report
    assert "Botanical Food Supplement" in report
    assert "Elderly / older adults" in report
    assert "Low CYP interaction risk" in report
    assert "EMA-HMPC Monographs" in report


def test_no_project_definition_section_when_not_provided():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "## Project Definition" not in report


def test_report_has_title_and_question():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="Liver support", dosage_form="Infusion", market="EU")
    assert "Botanical R&D Decision Intelligence Report" in report
    assert "Liver support" in report
    assert "Infusion" in report
    assert "EU" in report


def test_empty_result_produces_an_explicit_no_candidates_report_not_an_exception():
    report = generate_pharma_report(pd.DataFrame(), indication="X", dosage_form="Y", market="Z")
    assert "No candidates were evaluated" in report


def test_executive_summary_counts_go_calls_correctly():
    result = pd.DataFrame([
        _make_row(Go_Investigate_Hold_NoGo="Go"),
        _make_row(Go_Investigate_Hold_NoGo="Go"),
        _make_row(Go_Investigate_Hold_NoGo="Hold"),
    ])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "| Go | 2 |" in report
    assert "| Hold | 1 |" in report


def test_top_candidates_are_ranked_by_score_descending():
    result = pd.DataFrame([
        _make_row(Alternative_Plant="LowScorer", **{"R&D_Opportunity_Score": 20.0}),
        _make_row(Alternative_Plant="HighScorer", **{"R&D_Opportunity_Score": 90.0}),
    ])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z", top_n=20)
    assert report.index("HighScorer") < report.index("LowScorer")


def test_top_n_limits_full_writeups_and_puts_the_rest_in_a_summary_table():
    result = pd.DataFrame([
        _make_row(Alternative_Plant=f"Plant{i}", **{"R&D_Opportunity_Score": float(100 - i)})
        for i in range(5)
    ])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z", top_n=2)
    assert "Top Candidates (top 2 of 5" in report
    assert "Remaining Candidates (3)" in report
    # Plant0/Plant1 (highest scores) get full write-ups (### headers);
    # Plant2-4 should only appear in the compact table.
    assert "### 1. Plant0" in report
    assert "### 2. Plant1" in report
    assert "### 3. Plant2" not in report


def test_safety_flags_and_next_experiment_appear_in_the_writeup():
    result = pd.DataFrame([_make_row(Safety_Flags="lithogenic", Next_Experiment_Suggestion="Do a toxicology review.")])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "lithogenic" in report
    assert "Do a toxicology review." in report


def test_confidence_note_renders_as_a_visible_warning_when_present():
    result = pd.DataFrame([_make_row(Confidence_Note="Exploratory — high opportunity, low confidence.")])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "Exploratory — high opportunity, low confidence." in report


def test_sources_are_included_for_traceability():
    result = pd.DataFrame([_make_row(Source_Record_IDs="https://pubmed.ncbi.nlm.nih.gov/99999/")])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "https://pubmed.ncbi.nlm.nih.gov/99999/" in report


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
