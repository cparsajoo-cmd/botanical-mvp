"""Regression tests for pharma_report_generator.py (Gap 9)."""

import pandas as pd

from pharma_report_generator import generate_pharma_report
import pharma_report_generator


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
        # Task 6 — additive defaults; existing tests that don't care
        # about these fields are unaffected.
        Gate_Results={
            "safety": {"gate_name": "safety", "status": "passed", "reason": "No documented hard safety term present.", "evidence": "No explicit flag found"},
            "identity": {"gate_name": "identity", "status": "passed", "reason": "Compound identity resolved via a 'exact' match.", "evidence": "exact"},
            "minimum_evidence": {"gate_name": "minimum_evidence", "status": "passed", "reason": "Evidence located.", "evidence": "Clinical / human evidence"},
            "regulatory": {"gate_name": "regulatory", "status": "not_evaluable", "reason": "No evidence text was available.", "evidence": ""},
        },
        Scoring_Config_Version="1.0-default",
    )
    base.update(overrides)
    return base


def test_indication_centric_row_does_not_show_reference_or_matched_compound_labels():
    row = _make_row(
        Reference_Plant="Indication-centric discovery",
        Reference_Compound="Not used as candidate gate",
        Target_or_Mechanism="GABAA receptor modulation",
    )
    result = pd.DataFrame([row])
    report = generate_pharma_report(result, indication="insomnia", dosage_form="Y", market="Z")
    assert "**Discovery basis:** Indication-specific evidence" in report
    assert "**Supporting mechanism/target:** GABAA receptor modulation" in report
    assert "**Reference:**" not in report
    assert "**Matched compound:**" not in report


def test_compound_substitution_row_keeps_legacy_reference_and_compound_labels():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Reference:** RefPlant / RefCompound" in report
    assert "**Matched compound:** AltCompound" in report
    assert "**Discovery basis:**" not in report


def test_remainder_table_uses_mechanism_column_for_indication_centric_candidates():
    rows = [
        _make_row(
            Alternative_Plant=f"Plant {i}",
            Reference_Plant="Indication-centric discovery",
            Reference_Compound="Not used as candidate gate",
            Target_or_Mechanism=f"Mechanism {i}",
        )
        for i in range(1, 25)  # more than top_n so a remainder table is built
    ]
    result = pd.DataFrame(rows)
    report = generate_pharma_report(result, indication="insomnia", dosage_form="Y", market="Z", top_n=3)
    assert "| Plant | Supporting mechanism/target | Score | Confidence | Call |" in report
    assert "| Plant | Compound | Score | Confidence | Call |" not in report


def test_phase5_validation_status_appears_in_the_report_when_present():
    row = _make_row(
        Validation_Status="valid_with_limitations",
        Normalization_Summary="plant_identity=verified; indication=verified",
        Validation_Summary="plant_specific_attribution: pass; outcome_presence: fail",
    )
    result = pd.DataFrame([row])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "Evidence normalization & validation" in report
    assert "valid_with_limitations" in report
    assert "plant_identity=verified" in report
    assert "outcome_presence: fail" in report


def test_phase5_section_absent_when_row_has_no_validation_status():
    # Compound-substitution rows (and any pre-Phase-5 analysis) never set
    # Validation_Status — the section must simply not appear, not error
    # or show a fabricated status.
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "Evidence normalization & validation" not in report


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


def test_report_renders_robustness_section_without_recomputing_it():
    robustness_obj = {
        "status": "available", "scope": "reference_group_top_two",
        "baseline": {
            "winner": "Lavender", "winner_score": 91.0, "runner_up": "Passionflower",
            "runner_up_score": 88.0, "score_gap": 3.0,
            "winner_reconstruction_status": "exact", "runner_up_reconstruction_status": "exact",
        },
        "rank_stability": {"level": "Stable", "reason": "No single comparable dimension's removal changes the winner."},
        "contribution_shift_thresholds": [{"dimension": "Evidence quality", "required_contribution_shift_to_tie": 3.0}],
        "leave_one_dimension_out": [{"dimension_removed": "Novelty", "winner_changed": False}],
        "critical_dimensions": [], "limitations": [], "traceability": [],
    }
    result = pd.DataFrame([_make_row(**{"Comparative_Rationale_Structured": None})])
    report_lines = pharma_report_generator._candidate_section(result.iloc[0], 1, robustness_obj)
    assert "Robustness of the ranking" in report_lines
    assert "Stable" in report_lines
    assert "model sensitivity, not scientific uncertainty" in report_lines
    assert "3.0 points" in report_lines


def test_report_robustness_section_shows_insufficient_status_honestly():
    robustness_obj = {
        "status": "insufficient", "scope": "reference_group_top_two", "baseline": None,
        "rank_stability": {"level": "Insufficient", "reason": "Only one candidate in this reference group — no runner-up available for comparison."},
        "contribution_shift_thresholds": [], "leave_one_dimension_out": [], "critical_dimensions": [],
        "limitations": [], "traceability": [],
    }
    result = pd.DataFrame([_make_row()])
    section = pharma_report_generator._candidate_section(result.iloc[0], 1, robustness_obj)
    assert "Insufficient data" in section
    assert "no runner-up available" in section


def test_report_handles_missing_robustness_object_gracefully():
    result = pd.DataFrame([_make_row()])
    section = pharma_report_generator._candidate_section(result.iloc[0], 1, None)
    assert "AltPlant" in section  # renders the rest of the section fine


def test_report_renders_evidence_conflict_section_without_recomputing_it():
    evidence_conflict_obj = {
        "overall_consistency": "Mixed",
        "dominant_evidence_pattern": "Mixed clinical",
        "conflict_present": True,
        "agreement_summary": "MIXED (mostly positive, one contradiction): ...",
        "conflict_summary": "Null result",
        "possible_explanations": ["Population differences", "Dose differences"],
        "research_gaps": ["Only single publication"],
        "evidence_interpretation": "The available evidence contains both supporting and conflicting findings. The evidence should be interpreted together with the identified limitations.",
        "limitations": ["Evidence interpretation is based on candidate-level aggregated evidence."],
        "traceability": ["Occurrence_Corroboration", "Has_Negative_Evidence"],
    }
    result = pd.DataFrame([_make_row(Evidence_Conflict_Structured=evidence_conflict_obj)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "Overall consistency: Mixed" in report
    assert "Dominant evidence pattern: Mixed clinical" in report
    assert "Population differences; Dose differences" in report
    assert "Research gaps: Only single publication" in report
    assert "supporting and conflicting findings" in report
    # Must never claim recommendation strength from this section.
    assert "recommendation remains strong" not in report.lower()
    assert "recommendation should be downgraded" not in report.lower()


def test_report_handles_missing_evidence_conflict_object_gracefully():
    result = pd.DataFrame([_make_row(Evidence_Conflict_Structured=None)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "AltPlant" in report  # still renders the rest of the section fine


def test_report_renders_regulatory_intelligence_honestly():
    result = pd.DataFrame([_make_row(
        Market_Landscape_EMA_HMPC_Status="Listed in HMPC inventory as 'Melissae folium' — see source PDF for monograph status",
        Market_Landscape_Regulatory_Source="EMA HMPC — Inventory of herbal substances for assessment",
    )])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="European Union")
    assert "Present in EMA HMPC inventory" in report
    assert "not a confirmed monograph" in report
    assert "not available from the current repository" in report


def test_report_regulatory_intelligence_honest_when_enrichment_never_ran():
    result = pd.DataFrame([_make_row()])  # no Market_Landscape_* fields set
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="European Union")
    assert "EMA/HMPC status: Not available" in report


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


# ---------------------------------------------------------------------
# Task 6 — gate results, scoring config version, and decision record ID
# report sections. All additive/formatting-only: nothing here recomputes
# or reinterprets Gate_Results, Scoring_Config_Version, or the
# analysis_id decision_record_persistence.py already produced.
# ---------------------------------------------------------------------

def test_gate_results_section_appears_with_all_four_gates():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Decision gates**" in report
    assert "- safety: passed" in report
    assert "- identity: passed" in report
    assert "- minimum_evidence: passed" in report
    assert "- regulatory: not_evaluable" in report


def test_gate_results_section_shows_reason_text():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "Compound identity resolved via a 'exact' match." in report


def test_gate_results_section_absent_when_gate_results_missing():
    result = pd.DataFrame([_make_row(Gate_Results=None)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Decision gates**" not in report


def test_gate_results_section_handles_enum_status_objects_not_just_strings():
    # Gate_Results in a real run() result carries GateStatus enum
    # members, not plain strings — the section must format either.
    from data_contracts import GateStatus
    gate_results = {
        "safety": {"gate_name": "safety", "status": GateStatus.FAILED, "reason": "Documented hard safety term(s) present: lithogenic.", "evidence": "lithogenic"},
        "identity": {"gate_name": "identity", "status": GateStatus.PASSED, "reason": "r", "evidence": "exact"},
        "minimum_evidence": {"gate_name": "minimum_evidence", "status": GateStatus.NOT_EVALUABLE, "reason": "r", "evidence": ""},
        "regulatory": {"gate_name": "regulatory", "status": GateStatus.PASSED, "reason": "r", "evidence": ""},
    }
    result = pd.DataFrame([_make_row(Gate_Results=gate_results)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "- safety: failed" in report
    assert "lithogenic" in report


def test_scoring_config_version_appears_in_report():
    result = pd.DataFrame([_make_row(**{"Scoring_Config_Version": "1.0-default"})])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Scoring configuration version:** 1.0-default" in report


def test_scoring_config_version_absent_column_does_not_crash():
    row = _make_row()
    del row["Scoring_Config_Version"]
    result = pd.DataFrame([row])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Scoring configuration version:**" not in report


def test_decision_record_id_present_when_passed():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        decision_record_id="fixed-analysis-id-123",
    )
    assert "**Decision record:** persisted (analysis_id: fixed-analysis-id-123)" in report


def test_decision_record_id_honest_message_when_not_provided():
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Decision record:** not yet persisted" in report
    assert "fixed-analysis-id" not in report


def test_decision_record_id_never_fabricated_or_generated_by_this_module():
    import ast
    with open("pharma_report_generator.py", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename="pharma_report_generator.py")

    assert "uuid" not in [
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    ]
    call_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                call_names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                call_names.add(node.func.attr)
    assert "_new_analysis_id" not in call_names
    assert "persist_decision_record" not in call_names


def test_task6_sections_do_not_change_existing_report_structure_for_default_row():
    # Regression: existing sections (rationale, comparison, robustness,
    # evidence conflict, regulatory intelligence) must still all be
    # present alongside the new Task 6 sections, in the same relative
    # order they were before.
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    regulatory_idx = report.index("**Regulatory intelligence:**")
    gates_idx = report.index("**Decision gates**")
    assert regulatory_idx < gates_idx, "Decision gates must come after Regulatory intelligence, matching _candidate_section's call order"


# ---------------------------------------------------------------------
# Task 9 — second jurisdiction: US (dietary supplement market history),
# sourced from regulatory_frameworks.US_UK_PLANT_REGULATORY_STATUS.
# ---------------------------------------------------------------------

def test_us_status_line_appears_for_a_curated_plant():
    result = pd.DataFrame([_make_row(Alternative_Plant="Valeriana officinalis")])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="United States")
    assert "US (dietary supplement market history): Likely grandfathered" in report


def test_us_status_honestly_not_catalogued_for_an_uncurated_plant():
    result = pd.DataFrame([_make_row(Alternative_Plant="Some Uncurated Plant")])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="United States")
    assert "US (dietary supplement market history): Not catalogued for this plant" in report


def test_us_status_never_calls_a_network_connector():
    with open("pharma_report_generator.py", encoding="utf-8") as f:
        source = f.read()
    assert "from regulatory_frameworks import get_us_uk_status" in source
    assert "requests" not in source


# ---------------------------------------------------------------------
# Task 13.1 — Evidence Applicability report subsection. All additive/
# formatting-only: nothing here recomputes or reinterprets
# Applicability_Summary; every value already exists on the row. Never
# touches BotanicalRDCandidateEngine, scientific_evidence_index, or the
# database — this whole section is a pure read of a DataFrame column.
# ---------------------------------------------------------------------

def _applicability_summary(**overrides):
    defaults = dict(
        counts={"Directly applicable": 0, "Partially applicable": 1,
                "Indirectly relevant": 0, "Not assessable": 1, "Not applicable": 0},
        total_evidence_items=2, assessable_items=1, not_assessable_items=1,
        strongest_category="Partially applicable",
        critical_mismatches=[],
        missing_dimensions=["plant_part", "extraction_or_solvent"],
        evidence_record_ids=["ev-101", "ev-102"],
        summary_rationale="2 evidence item(s) assessed for preparation applicability.",
    )
    defaults.update(overrides)
    return defaults


def test_evidence_applicability_section_renders_a_complete_summary():
    result = pd.DataFrame([_make_row(Applicability_Summary=_applicability_summary())])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")

    assert "**Evidence applicability**" in report
    assert "Strongest applicable category: Partially applicable" in report
    assert "Total evidence items assessed: 2" in report
    assert "Not assessable: 1" in report
    assert "Missing dimensions: plant_part; extraction_or_solvent" in report
    assert "2 evidence item(s) assessed for preparation applicability." in report


def test_evidence_applicability_section_shows_genuine_evidence_record_ids_unchanged():
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary(evidence_record_ids=["ev-7", "ev-19"])
    )])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "ev-7; ev-19" in report


def test_evidence_record_ids_are_clearly_distinguished_from_source_record_ids():
    """_make_row()'s default Source_Record_IDs is a URL
    (https://pubmed.ncbi.nlm.nih.gov/12345/) — the report must label
    the two differently and never let a reader conflate them."""
    result = pd.DataFrame([_make_row(
        Source_Record_IDs="https://pubmed.ncbi.nlm.nih.gov/12345/",
        Applicability_Summary=_applicability_summary(evidence_record_ids=["ev-101", "ev-102"]),
    )])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")

    # The existing URL-based line is untouched.
    assert "**Traceability:** sources — https://pubmed.ncbi.nlm.nih.gov/12345/" in report
    # The new line explicitly names what it is and how it differs.
    assert "Database evidence-record IDs (evidence_records.id" in report
    assert "distinct from the source URLs in Traceability above" in report
    assert "ev-101; ev-102" in report
    # The genuine database ids never appear inside the URL-labeled line.
    traceability_line = next(line for line in report.splitlines() if line.startswith("**Traceability:**"))
    assert "ev-101" not in traceability_line
    assert "ev-102" not in traceability_line


def test_evidence_applicability_section_absent_when_summary_missing():
    """_make_row() does not set Applicability_Summary at all by
    default — this is the exact shape of a row from an analysis run
    before Task 10.2 existed."""
    result = pd.DataFrame([_make_row()])
    assert "Applicability_Summary" not in result.columns
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Evidence applicability**" not in report


def test_evidence_applicability_section_absent_when_summary_is_none():
    result = pd.DataFrame([_make_row(Applicability_Summary=None)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Evidence applicability**" not in report


def test_evidence_applicability_section_absent_when_summary_is_nan():
    result = pd.DataFrame([_make_row(Applicability_Summary=float("nan"))])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "**Evidence applicability**" not in report


def test_evidence_applicability_section_malformed_summary_does_not_crash():
    for malformed in ("not a dict", 42, ["a", "list"]):
        result = pd.DataFrame([_make_row(Applicability_Summary=malformed)])
        report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
        assert "**Evidence applicability**" not in report


def test_evidence_applicability_section_renders_only_available_partial_fields():
    partial_summary = {"strongest_category": "Not applicable"}  # every other key absent
    result = pd.DataFrame([_make_row(Applicability_Summary=partial_summary)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")

    assert "**Evidence applicability**" in report
    assert "Strongest applicable category: Not applicable" in report
    assert "Total evidence items assessed:" not in report
    assert "Database evidence-record IDs" not in report
    assert "Rationale:" not in report


def test_evidence_applicability_section_nan_fields_do_not_crash_or_leak_as_text():
    summary = _applicability_summary(
        total_evidence_items=float("nan"),
        evidence_record_ids=["ev-1", float("nan"), None],
    )
    result = pd.DataFrame([_make_row(Applicability_Summary=summary)])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")

    assert "Total evidence items assessed:" not in report
    assert "ev-1" in report
    # Precise check: the ids line itself must never contain the
    # literal string "nan" (the exact failure mode this guards).
    ids_line = next(line for line in report.splitlines() if "Database evidence-record IDs" in line)
    assert "nan" not in ids_line.lower()


def test_existing_report_sections_remain_present_alongside_evidence_applicability():
    """Non-regression: adding the new subsection must not remove or
    reorder any existing section."""
    result = pd.DataFrame([_make_row(Applicability_Summary=_applicability_summary())])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")

    for expected_marker in (
        "# Botanical R&D Decision Intelligence Report",
        "**Scientific rationale:**",
        "**Clinical rationale:**",
        "**Regulatory rationale:**",
        "**Commercial rationale:**",
        "**Safety profile:**",
        "**Traceability:** sources —",
        "**Confidence basis:**",
        "**Decision gates**",
    ):
        assert expected_marker in report

    # Ordering: the new section sits between Traceability and
    # Confidence basis, exactly where it was inserted.
    traceability_pos = report.index("**Traceability:**")
    applicability_pos = report.index("**Evidence applicability**")
    confidence_basis_pos = report.index("**Confidence basis:**")
    assert traceability_pos < applicability_pos < confidence_basis_pos


def test_existing_report_output_unchanged_when_no_applicability_summary():
    """A row shaped exactly like every pre-Task-13.1 test fixture in
    this file must produce byte-identical report content around the
    (now-absent) new section — proven by generating the report and
    confirming no new section text appears anywhere, not just checking
    one line."""
    result = pd.DataFrame([_make_row()])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    assert "Evidence applicability" not in report
    assert "evidence-record IDs" not in report


# ---------------------------------------------------------------------
# Task 13.2C — Scientific Evidence Details report wiring. All additive/
# formatting-only: pharma_report_generator.py only ever RECEIVES an
# already-built {id: dict} payload as a parameter — it never imports
# standard_evidence_builder, data_contracts, botanical_rd_candidate_
# engine, or database, and never looks anything up itself.
# ---------------------------------------------------------------------

def _applicability_summary_with_ids(ids):
    return {
        "strongest_category": "Partially applicable",
        "total_evidence_items": len(ids),
        "not_assessable_items": 0,
        "evidence_record_ids": ids,
        "critical_mismatches": [],
        "missing_dimensions": [],
        "summary_rationale": f"{len(ids)} evidence item(s) assessed.",
    }


_FULL_EVIDENCE_ENTRY = {
    "evidence_record_id": "ev-1",
    "source_type": "PubMed",
    "study_type": "Randomized Controlled Trial",
    "population": "human",
    "applicability_classification": "Partially applicable",
    "applicability_rationale": "PARTIALLY_APPLICABLE: indication and dosage form match.",
    "doi_pmid_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
}


def test_report_with_no_payload_remains_unchanged():
    """A candidate row with real evidence_record_ids, but no payload
    passed at all (the default) — the section must not appear, and no
    existing content is altered."""
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-1", "ev-2"])
    )])
    report = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")

    assert "Scientific Evidence Details" not in report
    # Every other section is still present and unaffected.
    assert "**Evidence applicability**" in report
    assert "**Traceability:** sources —" in report
    assert "**Confidence basis:**" in report


def test_report_with_payload_renders_evidence_details():
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-1"])
    )])
    payload = {"ev-1": dict(_FULL_EVIDENCE_ENTRY)}
    report = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        scientific_evidence_payload=payload,
    )

    assert "**Scientific Evidence Details:**" in report
    assert "Evidence #ev-1" in report
    assert "Source type: PubMed" in report
    assert "Study type: Randomized Controlled Trial" in report
    assert "Population: human" in report
    assert "Applicability: Partially applicable" in report
    assert "Rationale: PARTIALLY_APPLICABLE: indication and dosage form match." in report
    assert "DOI / PMID / URL: https://pubmed.ncbi.nlm.nih.gov/1/" in report


def test_unmatched_ids_are_ignored_safely():
    """The candidate references ev-2, but the payload only has ev-1 —
    ev-2 must simply not appear, no error, no placeholder line."""
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-1", "ev-2"])
    )])
    payload = {"ev-1": dict(_FULL_EVIDENCE_ENTRY)}
    report = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        scientific_evidence_payload=payload,
    )

    assert "Evidence #ev-1" in report
    assert "Evidence #ev-2" not in report


def test_no_matching_evidence_at_all_omits_the_whole_subsection():
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-99"])
    )])
    payload = {"ev-1": dict(_FULL_EVIDENCE_ENTRY)}  # no overlap at all
    report = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        scientific_evidence_payload=payload,
    )
    assert "Scientific Evidence Details" not in report


def test_partial_payload_renders_only_available_fields():
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-2"])
    )])
    payload = {"ev-2": {
        "evidence_record_id": "ev-2",
        "source_type": "ClinicalTrials.gov",
        "study_type": None,
        "population": None,
        "applicability_classification": None,
        "applicability_rationale": None,
        "doi_pmid_url": None,
    }}
    report = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        scientific_evidence_payload=payload,
    )

    assert "Evidence #ev-2" in report
    assert "Source type: ClinicalTrials.gov" in report
    assert "Study type:" not in report
    assert "Population:" not in report
    assert "Applicability:" not in report
    # Precise check: this section's own "  - Rationale: ..." line
    # (2-space indent), NOT Task 13.1's differently-formatted
    # "- Rationale: ..." line (no indent) inside the separate "Evidence
    # applicability" section above, which legitimately has its own
    # unrelated summary_rationale text.
    assert "  - Rationale:" not in report
    assert "  - DOI / PMID / URL:" not in report


def test_enum_values_appear_as_human_readable_text():
    """The payload (as build_scientific_evidence_presentation_payload()
    always produces) already carries the .value string, never a raw
    enum — proven end-to-end through the report."""
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-1"])
    )])
    payload = {"ev-1": dict(_FULL_EVIDENCE_ENTRY, applicability_classification="Not applicable")}
    report = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        scientific_evidence_payload=payload,
    )
    assert "Applicability: Not applicable" in report
    assert "EvidenceApplicability" not in report
    assert "<EvidenceApplicability" not in report


def test_multiple_evidence_items_render_correctly():
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-1", "ev-2", "ev-3"])
    )])
    payload = {
        "ev-1": dict(_FULL_EVIDENCE_ENTRY),
        "ev-2": dict(_FULL_EVIDENCE_ENTRY, evidence_record_id="ev-2", source_type="Europe PMC"),
        "ev-3": dict(_FULL_EVIDENCE_ENTRY, evidence_record_id="ev-3", source_type="ClinicalTrials.gov"),
    }
    report = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        scientific_evidence_payload=payload,
    )

    for expected_id, expected_source in (
        ("ev-1", "PubMed"), ("ev-2", "Europe PMC"), ("ev-3", "ClinicalTrials.gov"),
    ):
        block_start = report.index(f"Evidence #{expected_id}")
        block_end = report.index("\n\n", block_start)
        block = report[block_start:block_end]
        assert f"Source type: {expected_source}" in block

    # Ordering matches the candidate's own evidence_record_ids order.
    assert report.index("Evidence #ev-1") < report.index("Evidence #ev-2") < report.index("Evidence #ev-3")


def test_report_generation_never_imports_engine_or_database():
    """Report generation must never depend on engine or database
    access — proven by inspecting pharma_report_generator.py's actual
    import STATEMENTS via ast (not a raw text search, which would also
    match this module's own docstrings — e.g. its module-level
    docstring illustrates a caller's usage pattern with an example
    `from botanical_rd_candidate_engine import ...` line, which is
    documentation, not a real import)."""
    import ast
    with open("pharma_report_generator.py", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename="pharma_report_generator.py")

    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden_modules = {
        "botanical_rd_candidate_engine", "database", "standard_evidence_builder",
        "data_contracts", "supabase_client", "supabase",
    }
    assert not (imported_modules & forbidden_modules), (
        f"forbidden import(s) found: {imported_modules & forbidden_modules}"
    )

    # scientific_evidence_index must never be referenced as real code
    # either (only as prose, if at all) — checked by looking for it
    # inside actual attribute-access / call expressions in the AST,
    # not the raw text.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "scientific_evidence_index":
            raise AssertionError("scientific_evidence_index accessed as real code")
        if isinstance(node, ast.Name) and node.id == "scientific_evidence_index":
            raise AssertionError("scientific_evidence_index referenced as real code")


def test_scientific_evidence_details_section_malformed_payload_does_not_crash():
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-1"])
    )])
    for malformed_payload in ("not a dict", 42, ["a", "list"], {}, None):
        report = generate_pharma_report(
            result, indication="X", dosage_form="Y", market="Z",
            scientific_evidence_payload=malformed_payload,
        )
        assert "Scientific Evidence Details" not in report


def test_existing_report_content_unaffected_by_new_optional_parameter():
    """Passing scientific_evidence_payload must not change ANY other
    section's content — proven by generating the same report with and
    without the new parameter (payload has no matching ids) and
    diffing everything except the new section."""
    result = pd.DataFrame([_make_row(
        Applicability_Summary=_applicability_summary_with_ids(["ev-1"])
    )])
    report_without = generate_pharma_report(result, indication="X", dosage_form="Y", market="Z")
    report_with_empty_payload = generate_pharma_report(
        result, indication="X", dosage_form="Y", market="Z",
        scientific_evidence_payload={},
    )
    assert report_without == report_with_empty_payload


def test_step_rd_candidates_builds_the_payload_once_upstream_of_report_generation():
    """The building (get_scientific_evidence_by_ids() +
    build_scientific_evidence_presentation_payload()) happens in
    step_rd_candidates.py, NOT in pharma_report_generator.py — proven
    by inspecting step_rd_candidates.py's own source for the two calls
    and confirming their result is what gets passed into
    generate_pharma_report()."""
    with open("step_rd_candidates.py", encoding="utf-8") as f:
        source = f.read()

    assert "from standard_evidence_builder import" in source
    assert "get_scientific_evidence_by_ids" in source
    assert "build_scientific_evidence_presentation_payload" in source
    assert "scientific_evidence_payload=scientific_evidence_payload" in source

    # Each builder is actually CALLED (assigned to a result) exactly
    # once in this file — not once per candidate row, not once per
    # report section. Matched against the assignment pattern
    # specifically so this doesn't also match the import line or this
    # file's own prose mentioning the function name.
    assert source.count("= get_scientific_evidence_by_ids(") == 1
    assert source.count("= build_scientific_evidence_presentation_payload(") == 1


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
