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
        Evidence_Conflict_Reasoning="Evidence is UNCONTESTED but thin: no contradictory finding, but also no independent corroboration yet to rule one out.",
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
    assert "Evidence is UNCONTESTED but thin" in report


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


def test_report_uses_the_shared_canonical_recommendation_card():
    # Confirms pharma_report_generator imports the SAME function
    # structured_rationale.py defines, not a local duplicate.
    import pharma_report_generator
    import structured_rationale
    assert pharma_report_generator.build_recommendation_card is structured_rationale.build_recommendation_card


def test_no_duplicate_dimension_mapping_exists_in_the_report_module():
    # There must be no second _COMPONENT_TO_DIMENSIONS-style mapping or
    # local score-breakdown parser left in this file.
    import pharma_report_generator
    assert not hasattr(pharma_report_generator, "_COMPONENT_TO_DIMENSIONS")
    assert not hasattr(pharma_report_generator, "_local_parse_score_breakdown")
    assert not hasattr(pharma_report_generator, "_top_contributor_for_dimension")


def test_report_shows_the_honest_regulatory_message_not_a_fabricated_score():
    result = pd.DataFrame([_make_row(Score_Breakdown="Market signal: +6.0")])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "No independent regulatory score contribution is available" in report
    # And Market signal must show up under Commercial, not Regulatory.
    idx = report.find("Top commercial contributor")
    assert "Market signal" in report[idx:idx + 100]


def test_report_does_not_crash_on_a_legacy_row_missing_new_fields():
    legacy_row = {"Alternative_Plant": "OldPlant"}
    result = pd.DataFrame([legacy_row])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "OldPlant" in report


def test_report_does_not_fabricate_a_positive_claim_from_missing_data():
    result = pd.DataFrame([_make_row(
        Evidence_Level="No direct evidence", Market_Status="Search not performed",
        Occurrence_Corroboration="No independent source identified — not corroborated",
        Score_Breakdown=None,
    )])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    idx = report.find("Missing information")
    assert idx != -1
    assert "Positive drivers:** None" in report


def test_report_renders_head_to_head_comparison_without_recomputing_it():
    comparison_obj = {
        "status": "compared",
        "winner": {"candidate_name": "Lavender", "score": 91.0, "local_rank": 1, "global_rank": 1},
        "candidate": {"candidate_name": "Passionflower", "score": 88.0, "local_rank": 2, "global_rank": 2},
        "score_gap": 3.0,
        "primary_reason": "Evidence quality favours the winner by 4.0 points (+24.0 vs +20.0).",
        "winner_advantages": [{"dimension": "Evidence quality", "winner_value": 24.0, "candidate_value": 20.0, "difference": 4.0, "favours": "winner", "explanation": "..."}],
        "candidate_advantages": [{"dimension": "Novelty", "winner_value": 2.0, "candidate_value": 8.0, "difference": -6.0, "favours": "candidate", "explanation": "..."}],
        "ties": [],
        "dimension_comparison": [],
        "comparison_confidence": {"level": "High", "reason": "2 of 2 score components are directly comparable (100% overlap)."},
        "limitations": ["This comparison is based on scoring components, not raw scientific records."],
        "traceability": ["Score_Breakdown (winner)", "Score_Breakdown (candidate)"],
    }
    result = pd.DataFrame([_make_row(Comparative_Rationale_Structured=comparison_obj)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "Passionflower vs. Lavender" in report
    assert "score gap: +3.0" in report
    assert "Evidence quality favours the winner" in report
    assert "Winner ahead on: Evidence quality" in report
    assert "Candidate ahead on: Novelty" in report
    assert "Comparison confidence: High" in report
    # The raw dict must never appear literally in the report text.
    assert "'status': 'compared'" not in report
    assert "{'candidate_name'" not in report


def test_report_shows_group_winner_status_concisely():
    result = pd.DataFrame([_make_row(
        Comparative_Rationale_Structured={"status": "group_winner", "candidate": None},
    )])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "top-ranked candidate for its reference group" in report


def test_report_handles_missing_comparison_object_gracefully():
    result = pd.DataFrame([_make_row(Comparative_Rationale_Structured=None)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "AltPlant" in report  # still renders the rest of the section


def test_report_introduces_no_business_objective_simulation_language():
    comparison_obj = {
        "status": "compared",
        "winner": {"candidate_name": "Lavender", "score": 91.0, "local_rank": 1, "global_rank": 1},
        "candidate": {"candidate_name": "Passionflower", "score": 88.0, "local_rank": 2, "global_rank": 2},
        "score_gap": 3.0, "primary_reason": "Evidence quality favours the winner by 4.0 points.",
        "winner_advantages": [], "candidate_advantages": [], "ties": [], "dimension_comparison": [],
        "comparison_confidence": {"level": "High", "reason": "..."}, "limitations": [], "traceability": [],
    }
    result = pd.DataFrame([_make_row(Comparative_Rationale_Structured=comparison_obj)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    forbidden_terms = ["business objective", "alternative weighting", "if we prioritized", "under a different objective"]
    for term in forbidden_terms:
        assert term.lower() not in report.lower()


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
    result = pd.DataFrame([_make_row(
        Safety_Flags="lithogenic",
        Safety_Rationale="Safety flag(s) identified: lithogenic. These are screening signals extracted from evidence text, not a completed toxicological review.",
        Next_Experiment_Suggestion="Do a toxicology review.",
    )])
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
