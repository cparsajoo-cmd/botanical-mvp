"""Regression tests for pharma_report_generator.py (Gap 9 + Sprint 1)."""

import pandas as pd

from pharma_report_generator import generate_pharma_report, build_recommendation_card


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
        Score_Breakdown="Evidence quality: +24.0; Chemical/mechanistic link: +15.0; Market signal: +2.0; Safety/interaction/self-row penalty: -14.0",
        Evidence_Confidence=70.0,
        Decision_Class="Promising candidate; verify safety and standardization",
        Decision_Class_AH="C — Alternative-source R&D candidate",
        White_Space_Type="", Confidence_Note="",
        Go_Investigate_Hold_NoGo="Investigate",
        Scientific_Rationale="Shares a validated biological target.",
        Commercial_Regulatory_Rationale="Market status: Regulatory monograph exists.",
        Regulatory_Rationale="A regulatory monograph exists for this application. No regulatory barrier was identified in the available evidence text.",
        Commercial_Rationale="Market status: Regulatory monograph exists.",
        Safety_Rationale="No explicit safety flag or drug-interaction concern was identified in the available evidence text.",
        Clinical_Rationale="Clinical-grade evidence exists: Clinical trial (Evidence_Confidence 70.0).",
        Evidence_Strengths="High evidence confidence (70)",
        Evidence_Weaknesses="Single-source claim — not independently corroborated",
        Next_Experiment_Suggestion="Quantify compound concentration in AltPlant.",
        Evidence_Conflict_Reasoning="POSITIVE BUT INSUFFICIENT: 1 source found, no contradiction on record, but too little independent corroboration to be conclusive on its own.",
        Recommendation_Confidence_Statement="This INVESTIGATE recommendation reflects real uncertainty: Partial Evidence. Treat as a lead worth pursuing, not a validated conclusion.",
        Competitive_Positioning="Competitive position: scientifically developing (solid, multi-source evidence); regulatorily established (monograph recognition).",
        Rationale="Full narrative rationale text.",
    )
    base.update(overrides)
    return base


def test_cso_reasoning_statements_appear_in_the_writeup():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "This INVESTIGATE recommendation reflects real uncertainty" in report
    assert "Competitive position: scientifically developing" in report
    assert "POSITIVE BUT INSUFFICIENT" in report


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


def test_recommendation_card_answers_why_selected():
    card = build_recommendation_card(_make_row())
    assert card["scientific_rationale"] == "Shares a validated biological target."


def test_recommendation_card_identifies_top_scientific_contributor():
    card = build_recommendation_card(_make_row())
    # Chemical/mechanistic link (+15.0) is the only Scientific-mapped
    # component present in the fixture's Score_Breakdown.
    assert "Chemical/mechanistic link" in card["top_scientific_contributor"]
    assert "+15.0" in card["top_scientific_contributor"]


def test_recommendation_card_identifies_top_clinical_contributor():
    card = build_recommendation_card(_make_row())
    assert "Evidence quality" in card["top_clinical_contributor"]
    assert "+24.0" in card["top_clinical_contributor"]


def test_recommendation_card_reports_no_regulatory_factor_honestly_when_absent():
    # The fixture's Score_Breakdown has no component mapped purely to
    # Regulatory on its own (Market signal covers both Commercial and
    # Regulatory) — but since Market signal IS present, it should show up.
    card = build_recommendation_card(_make_row())
    assert "Market signal" in card["top_regulatory_contributor"]


def test_recommendation_card_reports_no_factor_honestly_when_dimension_truly_absent():
    row = _make_row(Score_Breakdown="Chemical/mechanistic link: +15.0")
    card = build_recommendation_card(row)
    assert "No safety factor identified" in card["top_safety_factor"]


def test_recommendation_card_identifies_score_reducing_factors():
    card = build_recommendation_card(_make_row())
    assert "Safety/interaction/self-row penalty" in card["score_reducing_factors"]
    assert card["score_reducing_factors"]["Safety/interaction/self-row penalty"] == -14.0


def test_recommendation_card_reports_none_reducing_when_no_negative_component():
    row = _make_row(Score_Breakdown="Chemical/mechanistic link: +15.0; Evidence quality: +24.0")
    card = build_recommendation_card(row)
    assert card["score_reducing_factors"] == "None — no component reduced the score."


def test_recommendation_card_includes_all_five_decision_dimensions():
    card = build_recommendation_card(_make_row())
    assert card["scientific_rationale"]
    assert card["clinical_rationale"]
    assert card["regulatory_rationale"]
    assert card["commercial_rationale"]
    assert card["safety_profile"]
    assert card["mechanism_of_action"] == "Hepatoprotective"
    assert card["final_recommendation"] == "Investigate"
    assert card["confidence_level"] == 70.0


def test_recommendation_card_uses_only_existing_row_data_no_new_computation_needed():
    # Sanity check on the "do not invent new data" requirement — every
    # value on the card must trace to a key already present on the row
    # (or be derived purely from Score_Breakdown, which is also already
    # on the row).
    row = _make_row()
    card = build_recommendation_card(row)
    assert card["botanical"] == row["Alternative_Plant"]
    assert card["evidence_conflict_reasoning"] == row["Evidence_Conflict_Reasoning"]


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
