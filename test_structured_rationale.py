"""Regression tests for structured_rationale.py (Gap 6 + Gap 8)."""

from structured_rationale import (
    go_investigate_hold_no_go,
    scientific_rationale,
    commercial_regulatory_rationale,
    evidence_strengths,
    evidence_weaknesses,
    next_experiment_suggestion,
    evidence_conflict_reasoning,
    recommendation_confidence_statement,
    competitive_positioning_statement,
    regulatory_rationale,
    commercial_rationale,
    safety_rationale,
    clinical_rationale,
    build_recommendation_card,
    build_confidence_basis,
    build_missing_information,
    build_not_searched,
    NO_REGULATORY_SCORE_CONTRIBUTION_MESSAGE,
    classify_evidence_consistency,
    classify_dominant_evidence_pattern,
    build_possible_explanations,
    detect_research_gaps,
    build_evidence_interpretation,
    build_evidence_conflict_structured,
    SUPPORTED_EXPLANATION_CATEGORIES,
    REJECTED_EXPLANATION_CATEGORIES,
    build_regulatory_intelligence,
    build_development_considerations,
    SUPPORTED_REGULATORY_AUTHORITIES,
    UNAVAILABLE_REGULATORY_AUTHORITIES,
)


# ---------------------------------------------------------------------
# evidence_conflict_reasoning
# ---------------------------------------------------------------------
def test_evidence_conflict_reasoning_multi_source_no_conflict_is_consistent():
    result = evidence_conflict_reasoning(
        occurrence_corroboration="Corroborated by 5 independent sources",
        has_negative_evidence=False, negative_evidence_types="", evidence_confidence=80,
    )
    assert "POSITIVE, CONSISTENT" in result
    assert "5 independent sources" in result


def test_evidence_conflict_reasoning_single_source_no_conflict_is_insufficient_not_consistent():
    result = evidence_conflict_reasoning(
        occurrence_corroboration="Single-source claim — not independently corroborated",
        has_negative_evidence=False, negative_evidence_types="", evidence_confidence=40,
    )
    assert "POSITIVE BUT INSUFFICIENT" in result


def test_evidence_conflict_reasoning_zero_evidence_is_a_distinct_conclusion_from_thin_evidence():
    # Audit Task 5's exact requirement: "no evidence exists" and
    # "evidence exists but is insufficient" must never read as the same
    # conclusion — this is the real bug this session fixed (an earlier
    # version produced the identical "thin" message for both).
    zero_evidence = evidence_conflict_reasoning(
        occurrence_corroboration="No independent source identified — not corroborated",
        has_negative_evidence=False, negative_evidence_types="", evidence_confidence=0,
    )
    thin_evidence = evidence_conflict_reasoning(
        occurrence_corroboration="Single-source claim — not independently corroborated",
        has_negative_evidence=False, negative_evidence_types="", evidence_confidence=20,
    )
    assert "NO EVIDENCE FOUND" in zero_evidence
    assert "data gap" in zero_evidence.lower()
    assert "POSITIVE BUT INSUFFICIENT" in thin_evidence
    assert zero_evidence != thin_evidence
    assert "NO EVIDENCE FOUND" not in thin_evidence
    assert "POSITIVE BUT INSUFFICIENT" not in zero_evidence


def test_evidence_conflict_reasoning_many_sources_plus_contradiction_is_mixed_mostly_positive():
    # A contradiction alongside 3+ corroborating sources should read as
    # a specific limitation, not full-blown conflict.
    result = evidence_conflict_reasoning(
        occurrence_corroboration="Corroborated by 4 independent sources",
        has_negative_evidence=True, negative_evidence_types="Null result", evidence_confidence=60,
    )
    assert "MIXED (mostly positive" in result
    assert "Null result" in result


def test_evidence_conflict_reasoning_single_source_plus_contradiction_is_genuinely_conflicting():
    result = evidence_conflict_reasoning(
        occurrence_corroboration="Single-source claim — not independently corroborated",
        has_negative_evidence=True, negative_evidence_types="Failed trial", evidence_confidence=20,
    )
    assert "NEGATIVE, GENUINELY CONFLICTING" in result
    assert "must be resolved" in result


def test_evidence_conflict_reasoning_negative_evidence_with_zero_corroboration_is_negative_only():
    result = evidence_conflict_reasoning(
        occurrence_corroboration="No independent source identified — not corroborated",
        has_negative_evidence=True, negative_evidence_types="Toxicity finding", evidence_confidence=5,
    )
    assert "NEGATIVE ONLY" in result
    assert "should not be recommended without further investigation" in result


def test_evidence_conflict_reasoning_gives_an_honest_why_hint_when_the_text_supports_it():
    result = evidence_conflict_reasoning(
        occurrence_corroboration="Corroborated by 4 independent sources",
        has_negative_evidence=True, negative_evidence_types="Null result", evidence_confidence=60,
        raw_evidence_text="The null result was observed in an elderly population using a different dose than the earlier trials.",
    )
    assert "Possible reason for the conflict" in result
    assert "Population differences" in result
    assert "Dose differences" in result


def test_evidence_conflict_reasoning_never_fabricates_a_why_hint_when_text_doesnt_support_one():
    result = evidence_conflict_reasoning(
        occurrence_corroboration="Corroborated by 4 independent sources",
        has_negative_evidence=True, negative_evidence_types="Null result", evidence_confidence=60,
        raw_evidence_text="A study reported a null result with no further detail provided.",
    )
    assert "not determinable from the available evidence text" in result
    assert "Possible reason for the conflict:" not in result


# ---------------------------------------------------------------------
# recommendation_confidence_statement
# ---------------------------------------------------------------------
def test_recommendation_confidence_go_with_strong_tier_is_well_supported():
    result = recommendation_confidence_statement(
        go_call="Go", candidate_evidence_strength_tier="Broad Evidence",
        evidence_confidence=85, has_negative_evidence=False,
    )
    assert "well-supported" in result


def test_recommendation_confidence_go_with_weak_tier_urges_review():
    result = recommendation_confidence_statement(
        go_call="Go", candidate_evidence_strength_tier="Preliminary",
        evidence_confidence=20, has_negative_evidence=False,
    )
    assert "review the underlying evidence" in result


def test_recommendation_confidence_investigate_reads_as_a_lead_not_a_conclusion():
    result = recommendation_confidence_statement(
        go_call="Investigate", candidate_evidence_strength_tier="Partial Evidence",
        evidence_confidence=40, has_negative_evidence=False,
    )
    assert "lead worth pursuing, not a validated conclusion" in result


def test_recommendation_confidence_no_go_always_demands_safety_review():
    result = recommendation_confidence_statement(
        go_call="No-Go", candidate_evidence_strength_tier="Broad Evidence",
        evidence_confidence=90, has_negative_evidence=False,
    )
    assert "safety" in result.lower()


def test_recommendation_confidence_notes_contradiction_when_present():
    result = recommendation_confidence_statement(
        go_call="Go", candidate_evidence_strength_tier="Broad Evidence",
        evidence_confidence=85, has_negative_evidence=True,
    )
    assert "contradictory finding is on record" in result


# ---------------------------------------------------------------------
# competitive_positioning_statement
# ---------------------------------------------------------------------
def test_competitive_positioning_synthesizes_all_three_maturity_dimensions():
    result = competitive_positioning_statement(
        market_status="Regulatory monograph exists",
        candidate_evidence_strength_tier="Broad Evidence",
        regulatory_barriers=None, white_space_type="",
    )
    assert "scientifically developing" in result
    assert "regulatorily established" in result


def test_competitive_positioning_highlights_industrial_rd_white_space_as_strongest():
    result = competitive_positioning_statement(
        market_status="No verified product found",
        candidate_evidence_strength_tier="High-priority evidence tier",
        regulatory_barriers=None, white_space_type="Industrial R&D White Space",
    )
    assert "strongest competitive position" in result


def test_competitive_positioning_flags_data_gap_as_unassessable():
    result = competitive_positioning_statement(
        market_status="Search not performed", candidate_evidence_strength_tier="Preliminary",
        regulatory_barriers=None, white_space_type="Data Gap",
    )
    assert "cannot yet be assessed" in result


def test_competitive_positioning_includes_regulatory_barrier_when_present():
    result = competitive_positioning_statement(
        market_status="Commercial evidence reported, not independently verified",
        candidate_evidence_strength_tier="Partial Evidence",
        regulatory_barriers="Prescription-only", white_space_type="",
    )
    assert "Prescription-only" in result


# ---------------------------------------------------------------------
# Decision card dimensions (Task 1): regulatory_rationale,
# commercial_rationale, safety_rationale, clinical_rationale — split
# out as distinct dimensions, not the pre-existing combined
# commercial_regulatory_rationale().
# ---------------------------------------------------------------------
def test_regulatory_rationale_states_barrier_with_honesty_caveat():
    result = regulatory_rationale("Regulatory monograph exists", "Prescription-only")
    assert "monograph exists" in result
    assert "screening signal, not a verified legal determination" in result
    assert "Prescription-only" in result


def test_regulatory_rationale_no_barrier_says_so_explicitly():
    result = regulatory_rationale("Regulatory monograph exists", None)
    assert "No regulatory barrier was identified" in result


def test_commercial_rationale_is_distinct_from_regulatory_rationale():
    commercial = commercial_rationale("No verified product found", "Commercial White Space")
    regulatory = regulatory_rationale("No verified product found", None)
    assert "market gap" in commercial
    assert commercial != regulatory


def test_commercial_rationale_data_gap_says_not_assessed():
    result = commercial_rationale("Search not performed", "Data Gap")
    assert "cannot yet be assessed" in result


def test_safety_rationale_no_flags_says_so_explicitly():
    result = safety_rationale("No explicit flag found", "No explicit flag found")
    assert "No explicit safety flag or drug-interaction concern was identified" in result


def test_safety_rationale_lists_real_flags_with_screening_caveat():
    result = safety_rationale("lithogenic", "No explicit flag found")
    assert "lithogenic" in result
    assert "not a completed toxicological review" in result


def test_clinical_rationale_distinguishes_clinical_grade_from_preclinical():
    clinical = clinical_rationale("Clinical trial", 85, False)
    preclinical = clinical_rationale("In vitro / mechanistic", 30, False)
    assert "Clinical-grade evidence exists" in clinical
    assert "No clinical-grade evidence was found" in preclinical


def test_clinical_rationale_notes_negative_finding_when_present():
    result = clinical_rationale("Clinical trial", 85, True)
    assert "negative/contradictory clinical finding is also on record" in result


# ---------------------------------------------------------------------
# go_investigate_hold_no_go
# ---------------------------------------------------------------------
def test_go_investigate_hold_no_go_covers_all_eight_classes():
    cases = {
        "A — Verified commercial route": "Go",
        "B — Established scientific candidate": "Go",
        "C — Alternative-source R&D candidate": "Investigate",
        "D — Mechanism-based R&D candidate": "Investigate",
        "E — White-space opportunity": "Investigate",
        "G — Hold / insufficient evidence": "Hold",
        "H — No-go / safety concern": "No-Go",
    }
    for decision_class_ah, expected in cases.items():
        assert go_investigate_hold_no_go(decision_class_ah) == expected


def test_go_investigate_hold_no_go_f_class_is_a_cautious_investigate():
    result = go_investigate_hold_no_go("F — Exploratory hypothesis")
    assert result.startswith("Investigate")
    assert result != "Go"


def test_go_investigate_hold_no_go_defaults_safely_on_unrecognized_input():
    assert go_investigate_hold_no_go("") == "Hold"
    assert go_investigate_hold_no_go("nonsense") == "Hold"


# ---------------------------------------------------------------------
# scientific_rationale
# ---------------------------------------------------------------------
def test_scientific_rationale_states_exact_match_plainly():
    result = scientific_rationale(
        match_quality="exact", target_provenance="Not applicable",
        evidence_hierarchy_detail=None, occurrence_corroboration="",
        has_negative_evidence=False,
    )
    assert "exact reference compound" in result.lower()


def test_scientific_rationale_includes_target_provenance_for_target_verified():
    result = scientific_rationale(
        match_quality="target_verified",
        target_provenance="seed_data.COMPOUND_TARGETS (hardcoded knowledge base, not a specific study/database record)",
        evidence_hierarchy_detail=None, occurrence_corroboration="",
        has_negative_evidence=False,
    )
    assert "seed_data.COMPOUND_TARGETS" in result


def test_scientific_rationale_flags_negative_evidence():
    result = scientific_rationale(
        match_quality="exact", target_provenance="",
        evidence_hierarchy_detail="Clinical trial",
        occurrence_corroboration="Corroborated by 2 independent sources",
        has_negative_evidence=True,
    )
    assert "negative" in result.lower() or "contradictory" in result.lower()


def test_scientific_rationale_class_only_reads_as_a_hypothesis_not_evidence():
    result = scientific_rationale(
        match_quality="class_only", target_provenance="",
        evidence_hierarchy_detail=None, occurrence_corroboration="",
        has_negative_evidence=False,
    )
    assert "hypothesis" in result.lower()


# ---------------------------------------------------------------------
# commercial_regulatory_rationale
# ---------------------------------------------------------------------
def test_commercial_rationale_highlights_industrial_rd_white_space():
    result = commercial_regulatory_rationale(
        market_status="No verified product found", white_space_type="Industrial R&D White Space",
    )
    assert "investment" in result.lower()


def test_commercial_rationale_data_gap_is_explicitly_not_a_finding():
    result = commercial_regulatory_rationale(market_status="Search not performed", white_space_type="Data Gap")
    assert "not a finding" in result.lower()


# ---------------------------------------------------------------------
# evidence_strengths / evidence_weaknesses
# ---------------------------------------------------------------------
def test_evidence_strengths_lists_only_signals_actually_present():
    strengths = evidence_strengths(
        match_quality="exact", evidence_confidence=80,
        occurrence_corroboration="Corroborated by 3 independent sources",
        market_status="Regulatory monograph exists",
    )
    assert len(strengths) == 4  # exact match, high confidence, corroboration, regulatory


def test_evidence_strengths_is_empty_when_nothing_qualifies():
    strengths = evidence_strengths(
        match_quality="class_only", evidence_confidence=10,
        occurrence_corroboration="Single-source claim — not independently corroborated",
        market_status="Search not performed",
    )
    assert strengths == []


def test_evidence_weaknesses_flags_negative_evidence_with_its_types():
    weaknesses = evidence_weaknesses(
        evidence_confidence=50, occurrence_corroboration="Corroborated by 2 independent sources",
        has_negative_evidence=True, negative_evidence_types="Null result",
        safety_flags="No explicit flag found", market_status="Regulatory monograph exists",
    )
    assert any("Null result" in w for w in weaknesses)


def test_evidence_weaknesses_flags_safety_and_conflicting_market():
    weaknesses = evidence_weaknesses(
        evidence_confidence=50, occurrence_corroboration="Corroborated by 2 independent sources",
        has_negative_evidence=False, negative_evidence_types="",
        safety_flags="lithogenic", market_status="Conflicting market evidence",
    )
    assert any("lithogenic" in w.lower() for w in weaknesses)
    assert any("conflict" in w.lower() for w in weaknesses)


# ---------------------------------------------------------------------
# next_experiment_suggestion
# ---------------------------------------------------------------------
def test_next_experiment_no_go_demands_safety_review_first():
    result = next_experiment_suggestion(
        decision_class_ah="H — No-go / safety concern", evidence_weaknesses_list=[], alt_plant="TestPlant",
    )
    assert "safety" in result.lower() or "toxicolog" in result.lower()


def test_next_experiment_single_source_asks_for_corroboration_before_anything_else():
    # Even for an otherwise-strong class, a single-source weakness
    # should be surfaced as the actual next step, since it's the
    # cheapest, most important gap to close first.
    result = next_experiment_suggestion(
        decision_class_ah="C — Alternative-source R&D candidate",
        evidence_weaknesses_list=["Single-source claim — not independently corroborated"],
        alt_plant="TestPlant",
    )
    assert "independent" in result.lower()


def test_next_experiment_mechanism_based_suggests_target_validation():
    result = next_experiment_suggestion(
        decision_class_ah="D — Mechanism-based R&D candidate", evidence_weaknesses_list=[], alt_plant="TestPlant",
    )
    assert "target" in result.lower() or "mechanism" in result.lower()


def test_next_experiment_always_mentions_the_specific_plant():
    result = next_experiment_suggestion(
        decision_class_ah="C — Alternative-source R&D candidate", evidence_weaknesses_list=[], alt_plant="Silybum marianum",
    )
    assert "Silybum marianum" in result


# =====================================================================
# Sprint 1 (post-review corrections) — the Explainable Recommendation
# Card. Realistic row fixtures matching the ACTUAL current
# OUTPUT_COLUMNS shape (verified against botanical_rd_candidate_engine.py),
# not simplified stand-ins.
# =====================================================================

def _full_row(**overrides):
    """A complete, realistic run() output row — every field a real
    candidate would have. Individual tests override only what they
    need to isolate."""
    base = dict(
        Alternative_Plant="AltPlant", Reference_Plant="RefPlant",
        Target_or_Mechanism="Hepatoprotective",
        Scientific_Rationale="Shares a validated biological target.",
        Clinical_Rationale="Clinical-grade evidence exists: Clinical trial (Evidence_Confidence 70.0).",
        Regulatory_Rationale="A regulatory monograph exists for this application. No regulatory barrier was identified in the available evidence text.",
        Commercial_Rationale="Market status: Regulatory monograph exists.",
        Safety_Rationale="No explicit safety flag or drug-interaction concern was identified in the available evidence text.",
        Safety_Flags="No explicit flag found", Interaction_Flags="No explicit flag found",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Market_Status="Regulatory monograph exists",
        Occurrence_Corroboration="Corroborated by 3 independent sources",
        Concentration_Info="2 mg/g dry weight", Extraction_Method="Aqueous",
        Source_Record_IDs="https://pubmed.ncbi.nlm.nih.gov/1/",
        Candidate_Evidence_Strength_Tier="Broad Evidence",
        Evidence_Confidence=70.0,
        Score_Breakdown="Chemical/mechanistic link: +15.0; Evidence quality: +24.0; Market signal: +2.0; Safety/interaction/self-row penalty: -14.0",
        Evidence_Weaknesses="None identified",
        Next_Experiment_Suggestion="Quantify compound concentration in AltPlant.",
        Go_Investigate_Hold_NoGo="Investigate",
        Evidence_Conflict_Reasoning="POSITIVE, CONSISTENT: 3 independent sources were found and none contradicts the finding.",
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------
# 1. No independent regulatory score component (review point 2's core fix)
# ---------------------------------------------------------------------
def test_no_independent_regulatory_score_component():
    card = build_recommendation_card(_full_row())
    assert card["top_regulatory_contributor"] == NO_REGULATORY_SCORE_CONTRIBUTION_MESSAGE
    assert "not available" in card["top_regulatory_contributor"].lower() or \
           "no independent regulatory score contribution" in card["top_regulatory_contributor"].lower()


def test_market_signal_never_attributed_to_regulatory_even_when_present():
    row = _full_row(Score_Breakdown="Market signal: +6.0")
    card = build_recommendation_card(row)
    # Market signal must count toward Commercial only.
    assert "Market signal" in card["top_commercial_contributor"]
    assert card["top_regulatory_contributor"] == NO_REGULATORY_SCORE_CONTRIBUTION_MESSAGE


# ---------------------------------------------------------------------
# 2. Market search not performed
# ---------------------------------------------------------------------
def test_market_search_not_performed_is_distinguished():
    row = _full_row(Market_Status="Search not performed")
    card = build_recommendation_card(row)
    assert any("Market/regulatory picture not established" in m for m in card["missing_information"])
    assert any("Commercial/regulatory market search" in n for n in card["not_searched"])
    assert build_confidence_basis(row)["regulatory_data_availability"] == "not searched"


# ---------------------------------------------------------------------
# 3. Regulatory/patent connector unavailable
# ---------------------------------------------------------------------
def test_patent_connector_unavailable_when_enrichment_never_ran():
    # A standard (non-enriched) row has no Market_Landscape_* columns at all.
    card = build_recommendation_card(_full_row())
    assert "connector unavailable" in card["connector_unavailable"]["patent_connector"]
    assert "connector unavailable" in card["connector_unavailable"]["retail_connector"]
    assert any("Patent search" in n for n in card["not_searched"])


def test_connector_status_read_honestly_when_enrichment_did_run():
    row = _full_row(
        Market_Landscape_Patent_Search_Status="Not configured",
        Market_Landscape_Retail_Search_Status="Skipped",
    )
    card = build_recommendation_card(row)
    assert card["connector_unavailable"]["patent_connector"] == "Not configured"
    assert card["connector_unavailable"]["retail_connector"] == "Skipped"


# ---------------------------------------------------------------------
# 4. Safety data unavailable
# ---------------------------------------------------------------------
def test_safety_data_unavailable_when_no_evidence_text_existed():
    row = _full_row(Evidence_Level="No direct evidence", Safety_Flags="No explicit flag found")
    basis = build_confidence_basis(row)
    assert basis["safety_data_availability"] == "not searched"


def test_safety_data_searched_but_not_found_when_evidence_existed_but_no_flag():
    row = _full_row(Evidence_Level="Clinical / human evidence", Safety_Flags="No explicit flag found")
    basis = build_confidence_basis(row)
    assert basis["safety_data_availability"] == "searched but not found"


def test_safety_data_available_when_a_real_flag_exists():
    row = _full_row(Evidence_Level="Clinical / human evidence", Safety_Flags="lithogenic")
    basis = build_confidence_basis(row)
    assert basis["safety_data_availability"] == "available"


# ---------------------------------------------------------------------
# 5. Empty value versus searched-but-not-found
# ---------------------------------------------------------------------
def test_empty_string_is_not_silently_read_as_no_evidence():
    # A missing/empty Evidence_Level (e.g. a malformed row) must be
    # "unknown / legacy state", NOT silently treated as "not searched"
    # or "no evidence" — those are different, stronger claims than
    # "we don't know."
    row = _full_row(Evidence_Level="", Market_Status="")
    basis = build_confidence_basis(row)
    assert basis["regulatory_data_availability"] == "unknown / legacy state"


def test_searched_but_not_found_is_distinct_from_not_searched():
    searched_empty = _human_evidence_helper_row(Evidence_Hierarchy_Detail="In vitro / mechanistic")
    not_searched = _human_evidence_helper_row(Evidence_Hierarchy_Detail=None)
    basis_searched = build_confidence_basis(searched_empty)
    basis_not_searched = build_confidence_basis(not_searched)
    assert basis_searched["human_evidence_availability"] == "searched but not found"
    assert basis_not_searched["human_evidence_availability"] == "unknown / legacy state"
    assert basis_searched["human_evidence_availability"] != basis_not_searched["human_evidence_availability"]


def _human_evidence_helper_row(**overrides):
    return _full_row(**overrides)


# ---------------------------------------------------------------------
# 6. Legacy rows without the new explainability fields
# ---------------------------------------------------------------------
def test_legacy_row_without_new_fields_does_not_crash():
    # A minimal, old-shaped row missing every new column this card
    # reads — must degrade gracefully, not raise.
    legacy_row = {"Alternative_Plant": "OldPlant"}
    card = build_recommendation_card(legacy_row)
    assert card["botanical"] == "OldPlant"
    assert card["scientific_rationale"] == ""
    assert card["confidence_basis"]["regulatory_data_availability"] == "unknown / legacy state"
    assert card["confidence_basis"]["human_evidence_availability"] == "unknown / legacy state"
    assert card["confidence_basis"]["safety_data_availability"] == "unknown / legacy state"


# ---------------------------------------------------------------------
# 7. Incomplete Score_Breakdown
# ---------------------------------------------------------------------
def test_incomplete_score_breakdown_does_not_crash_and_reports_honestly():
    row = _full_row(Score_Breakdown="Chemical/mechanistic link: +15.0")  # only one component
    card = build_recommendation_card(row)
    assert "Chemical/mechanistic link" in card["top_scientific_contributor"]
    assert "No clinical factor identified" in card["top_clinical_contributor"]
    assert "No safety factor identified" in card["top_safety_factor"]
    assert card["negative_drivers"] == "None — no component reduced the score."


def test_missing_score_breakdown_entirely_does_not_crash():
    row = _full_row(Score_Breakdown=None)
    card = build_recommendation_card(row)
    assert card["positive_drivers"] == "None — no component increased the score."
    assert card["negative_drivers"] == "None — no component reduced the score."


# ---------------------------------------------------------------------
# 8. No fabricated positive claim from missing data
# ---------------------------------------------------------------------
def test_no_fabricated_positive_claim_when_data_is_missing():
    row = _full_row(
        Evidence_Level="No direct evidence", Market_Status="Search not performed",
        Occurrence_Corroboration="No independent source identified — not corroborated",
        Concentration_Info="Not clearly reported", Extraction_Method="Not clearly reported",
        Score_Breakdown=None,
    )
    card = build_recommendation_card(row)
    # Every "missing" signal must show up as missing, not as a positive finding.
    assert len(card["missing_information"]) >= 4
    assert card["positive_drivers"] == "None — no component increased the score."
    basis = card["confidence_basis"]
    assert basis["regulatory_data_availability"] == "not searched"
    assert basis["safety_data_availability"] == "not searched"


# ---------------------------------------------------------------------
# 9. Score contribution consistency with the original score
# ---------------------------------------------------------------------
def test_score_contributions_sum_consistently_with_positive_and_negative_split():
    row = _full_row(
        Score_Breakdown="Chemical/mechanistic link: +15.0; Evidence quality: +24.0; "
                        "Market signal: +2.0; Safety/interaction/self-row penalty: -14.0"
    )
    card = build_recommendation_card(row)
    positive_sum = sum(card["positive_drivers"].values())
    negative_sum = sum(card["negative_drivers"].values())
    assert positive_sum == 41.0  # 15 + 24 + 2
    assert negative_sum == -14.0
    # Every component from the raw breakdown must appear in exactly one bucket.
    all_components = {**card["positive_drivers"], **card["negative_drivers"]}
    assert set(all_components) == {
        "Chemical/mechanistic link", "Evidence quality", "Market signal",
        "Safety/interaction/self-row penalty",
    }


# ---------------------------------------------------------------------
# General card correctness
# ---------------------------------------------------------------------
def test_recommendation_card_includes_every_reviewer_required_field():
    card = build_recommendation_card(_full_row())
    for field in [
        "positive_drivers", "negative_drivers", "limitations", "missing_information",
        "not_searched", "connector_unavailable", "recommended_next_step",
        "traceability", "confidence_basis",
    ]:
        assert field in card, f"required field {field!r} missing from the recommendation card"


def test_confidence_basis_includes_every_reviewer_required_dimension():
    basis = build_confidence_basis(_full_row())
    for field in [
        "confidence_level", "confidence_tier", "evidence_completeness",
        "human_evidence_availability", "regulatory_data_availability",
        "safety_data_availability", "critical_missing_information",
        "fallback_or_default_values_used",
    ]:
        assert field in basis, f"required confidence-basis field {field!r} missing"


def test_traceability_includes_sources_and_corroboration():
    card = build_recommendation_card(_full_row())
    assert "pubmed.ncbi.nlm.nih.gov" in card["traceability"]["source_record_ids"]
    assert "3 independent sources" in card["traceability"]["corroboration"]


def test_fallback_detected_from_go_call_language():
    row = _full_row(Go_Investigate_Hold_NoGo="Investigate — data source reliability could not be confirmed this run")
    basis = build_confidence_basis(row)
    assert basis["fallback_or_default_values_used"].startswith("YES")


def test_fallback_not_detected_on_normal_go_call():
    row = _full_row(Go_Investigate_Hold_NoGo="Go")
    basis = build_confidence_basis(row)
    assert basis["fallback_or_default_values_used"].startswith("Not detected")


# =====================================================================
# Sprint 4 — Evidence Conflict & Consistency Intelligence
# =====================================================================

# ---------------------------------------------------------------------
# Five consistency categories
# ---------------------------------------------------------------------
def test_consistency_insufficient_information_when_nothing_found():
    result = classify_evidence_consistency("No independent source identified — not corroborated", False)
    assert result == "Insufficient information"


def test_consistency_mostly_consistent_single_source_no_conflict():
    result = classify_evidence_consistency("Single-source claim — not independently corroborated", False)
    assert result == "Mostly consistent"


def test_consistency_consistent_multi_source_no_conflict():
    result = classify_evidence_consistency("Corroborated by 3 independent sources", False)
    assert result == "Consistent"


def test_consistency_mixed_when_mostly_positive_with_contradiction():
    result = classify_evidence_consistency("Corroborated by 4 independent sources", True)
    assert result == "Mixed"


def test_consistency_conflicting_when_thin_with_contradiction():
    result = classify_evidence_consistency("Single-source claim — not independently corroborated", True)
    assert result == "Conflicting"


def test_consistency_returns_only_the_five_allowed_categories():
    allowed = {"Consistent", "Mostly consistent", "Mixed", "Conflicting", "Insufficient information"}
    cases = [
        ("No independent source identified — not corroborated", False),
        ("Single-source claim — not independently corroborated", False),
        ("Corroborated by 2 independent sources", False),
        ("Corroborated by 5 independent sources", True),
        ("Single-source claim — not independently corroborated", True),
    ]
    for corroboration, has_negative in cases:
        result = classify_evidence_consistency(corroboration, has_negative)
        assert result in allowed


# ---------------------------------------------------------------------
# dominant_evidence_pattern
# ---------------------------------------------------------------------
def test_dominant_pattern_sparse_evidence_for_thin_corroboration():
    result = classify_dominant_evidence_pattern("Clinical trial", False, "Single-source claim — not independently corroborated")
    assert result == "Sparse evidence"


def test_dominant_pattern_negative_dominated():
    result = classify_dominant_evidence_pattern("Clinical trial", True, "Corroborated by 2 independent sources")
    assert result == "Negative dominated"


def test_dominant_pattern_clinical_supported():
    result = classify_dominant_evidence_pattern("Clinical trial", False, "Corroborated by 3 independent sources")
    assert result == "Clinical-supported"


def test_dominant_pattern_mixed_clinical():
    result = classify_dominant_evidence_pattern("Clinical trial", True, "Corroborated by 4 independent sources")
    assert result == "Mixed clinical"


def test_dominant_pattern_mostly_preclinical():
    result = classify_dominant_evidence_pattern("Validated ex vivo / in vivo", False, "Corroborated by 3 independent sources")
    assert result == "Mostly preclinical"


def test_dominant_pattern_mostly_mechanistic():
    result = classify_dominant_evidence_pattern("In vitro / mechanistic", False, "Corroborated by 3 independent sources")
    assert result == "Mostly mechanistic"


def test_dominant_pattern_mostly_positive_fallback():
    result = classify_dominant_evidence_pattern("Traditional-use / regulatory monograph", False, "Corroborated by 2 independent sources")
    assert result == "Mostly positive"


# ---------------------------------------------------------------------
# possible_explanations — supported vs rejected categories
# ---------------------------------------------------------------------
def test_possible_explanations_empty_when_no_conflict():
    result = build_possible_explanations("A study reported a null result in an elderly population.", has_negative_evidence=False)
    assert result == []


def test_possible_explanations_detects_supported_categories():
    text = "The null result was observed in an elderly population using a different dose than earlier trials."
    result = build_possible_explanations(text, has_negative_evidence=True)
    assert "Population differences" in result
    assert "Dose differences" in result


def test_possible_explanations_never_includes_rejected_categories():
    # Even with text that might superficially suggest species/target/
    # mechanism differences, only SUPPORTED categories may ever appear.
    text = "Different species were used and a different molecular target was implicated, with conflicting mechanism data."
    result = build_possible_explanations(text, has_negative_evidence=True)
    for rejected in REJECTED_EXPLANATION_CATEGORIES:
        assert rejected not in result
    for item in result:
        assert item in SUPPORTED_EXPLANATION_CATEGORIES


def test_possible_explanations_detects_study_quality_differences():
    text = "One study had a high risk of bias while another was well-controlled."
    result = build_possible_explanations(text, has_negative_evidence=True)
    assert "Study quality differences" in result


def test_possible_explanations_detects_evidence_level_span():
    text = "A systematic review found positive effects, while in vitro mechanism of action studies were inconclusive."
    result = build_possible_explanations(text, has_negative_evidence=True)
    assert "Evidence level differences" in result


def test_possible_explanations_honestly_empty_when_text_does_not_support_any():
    text = "A study reported a null result with no further detail provided."
    result = build_possible_explanations(text, has_negative_evidence=True)
    assert result == []  # no fabricated explanation when the text doesn't support one


def test_possible_explanations_empty_when_no_text_available():
    result = build_possible_explanations(None, has_negative_evidence=True)
    assert result == []


# ---------------------------------------------------------------------
# Research gap detection — only the 7 supported gap types
# ---------------------------------------------------------------------
_UNSUPPORTED_GAPS = {"No long-term evidence", "No formulation consistency"}
_SUPPORTED_GAPS = {
    "Few human studies", "Mostly in vitro evidence", "No clinical confirmation",
    "No safety studies", "Only single publication", "Only preclinical evidence",
    "Only mechanistic evidence", "Only market evidence",
}


def test_research_gaps_never_includes_unsupported_gap_types():
    result = detect_research_gaps(
        evidence_hierarchy_detail="In vitro / mechanistic",
        occurrence_corroboration="Single-source claim — not independently corroborated",
        evidence_level="No direct evidence", safety_flags=None, market_status=None,
    )
    for gap in result:
        assert gap not in _UNSUPPORTED_GAPS
        assert gap in _SUPPORTED_GAPS


def test_research_gaps_detects_in_vitro_only():
    result = detect_research_gaps(
        evidence_hierarchy_detail="In vitro / mechanistic",
        occurrence_corroboration="Corroborated by 3 independent sources",
        evidence_level="Preclinical / mechanistic evidence", safety_flags="No explicit flag found",
        market_status="Search not performed",
    )
    assert "Mostly in vitro evidence" in result
    assert "Only mechanistic evidence" in result
    assert "No clinical confirmation" in result


def test_research_gaps_detects_no_safety_studies_only_when_no_evidence_text_existed():
    with_text = detect_research_gaps(
        evidence_hierarchy_detail="Clinical trial", occurrence_corroboration="Corroborated by 2 independent sources",
        evidence_level="Clinical / human evidence", safety_flags="No explicit flag found", market_status=None,
    )
    without_text = detect_research_gaps(
        evidence_hierarchy_detail=None, occurrence_corroboration="No independent source identified — not corroborated",
        evidence_level="No direct evidence", safety_flags="No explicit flag found", market_status=None,
    )
    assert "No safety studies" not in with_text  # evidence text existed, safety extraction ran
    assert "No safety studies" in without_text


def test_research_gaps_detects_only_single_publication():
    result = detect_research_gaps(
        evidence_hierarchy_detail="Clinical trial", occurrence_corroboration="Single-source claim — not independently corroborated",
        evidence_level="Clinical / human evidence", safety_flags=None, market_status=None,
    )
    assert "Only single publication" in result


def test_research_gaps_detects_only_market_evidence():
    result = detect_research_gaps(
        evidence_hierarchy_detail=None, occurrence_corroboration="No independent source identified — not corroborated",
        evidence_level="No direct evidence", safety_flags=None,
        market_status="Regulatory monograph exists",
    )
    assert "Only market evidence" in result


def test_research_gaps_no_market_evidence_gap_when_market_also_not_searched():
    result = detect_research_gaps(
        evidence_hierarchy_detail=None, occurrence_corroboration="No independent source identified — not corroborated",
        evidence_level="No direct evidence", safety_flags=None, market_status="Search not performed",
    )
    assert "Only market evidence" not in result


# ---------------------------------------------------------------------
# Evidence Interpretation — never evaluates recommendation strength
# ---------------------------------------------------------------------
def test_evidence_interpretation_insufficient():
    result = build_evidence_interpretation("Insufficient information", False)
    assert "Insufficient evidence" in result


def test_evidence_interpretation_consistent_no_conflict():
    result = build_evidence_interpretation("Consistent", False)
    assert "consistent" in result.lower()


def test_evidence_interpretation_conflict_present():
    result = build_evidence_interpretation("Mixed", True)
    assert "supporting and conflicting findings" in result
    assert "identified limitations" in result


def test_evidence_interpretation_never_evaluates_recommendation_strength():
    forbidden = ["recommendation remains strong", "recommendation should be downgraded", "recommendation is strong", "recommendation is weak"]
    for consistency, conflict in [
        ("Insufficient information", False), ("Consistent", False), ("Mixed", True), ("Conflicting", True),
    ]:
        result = build_evidence_interpretation(consistency, conflict).lower()
        for phrase in forbidden:
            assert phrase not in result


# ---------------------------------------------------------------------
# Full structured object
# ---------------------------------------------------------------------
def test_evidence_conflict_structured_includes_all_required_fields():
    obj = build_evidence_conflict_structured(
        occurrence_corroboration="Corroborated by 3 independent sources",
        has_negative_evidence=True, negative_evidence_types="Null result",
        evidence_hierarchy_detail="Clinical trial", evidence_level="Clinical / human evidence",
        safety_flags="No explicit flag found", market_status="Regulatory monograph exists",
        evidence_conflict_reasoning_text="MIXED (mostly positive, one contradiction): ...",
        raw_evidence_text="The null result was observed in an elderly population.",
    )
    for field in [
        "overall_consistency", "dominant_evidence_pattern", "conflict_present",
        "agreement_summary", "conflict_summary", "possible_explanations",
        "research_gaps", "evidence_interpretation", "limitations", "traceability",
    ]:
        assert field in obj, f"required field {field!r} missing"


def test_evidence_conflict_structured_always_includes_the_limitation_disclaimer():
    obj = build_evidence_conflict_structured(
        occurrence_corroboration="Corroborated by 2 independent sources", has_negative_evidence=False,
        negative_evidence_types="", evidence_hierarchy_detail="Clinical trial",
        evidence_level="Clinical / human evidence", safety_flags="No explicit flag found",
        market_status="Regulatory monograph exists", evidence_conflict_reasoning_text="POSITIVE, CONSISTENT: ...",
    )
    assert any("candidate-level aggregated evidence" in lim for lim in obj["limitations"])
    assert any("Study-level attribution is not available" in lim for lim in obj["limitations"])


def test_evidence_conflict_structured_deterministic():
    kwargs = dict(
        occurrence_corroboration="Corroborated by 4 independent sources", has_negative_evidence=True,
        negative_evidence_types="Null result", evidence_hierarchy_detail="Clinical trial",
        evidence_level="Clinical / human evidence", safety_flags="No explicit flag found",
        market_status="Regulatory monograph exists", evidence_conflict_reasoning_text="MIXED: ...",
        raw_evidence_text="Different populations and different doses were used across studies.",
    )
    result1 = build_evidence_conflict_structured(**kwargs)
    result2 = build_evidence_conflict_structured(**kwargs)
    assert result1 == result2


def test_evidence_conflict_structured_never_touches_scoring_fields():
    # Confirms the structured object contains no key resembling a
    # score, rank, or confidence value that could be mistaken for one.
    obj = build_evidence_conflict_structured(
        occurrence_corroboration="Corroborated by 2 independent sources", has_negative_evidence=False,
        negative_evidence_types="", evidence_hierarchy_detail="Clinical trial",
        evidence_level="Clinical / human evidence", safety_flags="No explicit flag found",
        market_status="Regulatory monograph exists", evidence_conflict_reasoning_text="POSITIVE, CONSISTENT: ...",
    )
    forbidden_keys = {"score", "rank", "r&d_opportunity_score", "evidence_confidence", "decision_class"}
    assert not (set(k.lower() for k in obj.keys()) & forbidden_keys)


# =====================================================================
# Sprint 5, Phase B — Regulatory Intelligence
# =====================================================================

def test_regulatory_intelligence_includes_all_required_fields():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'Melissae folium' — see source PDF for monograph status",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status="Regulatory monograph exists", market="European Union",
    )
    for field in [
        "overall_regulatory_landscape", "regulatory_maturity", "regulatory_data_quality",
        "authority_coverage", "ema_status", "traditional_use_status",
        "major_regulatory_flags", "development_considerations", "limitations", "traceability",
    ]:
        assert field in obj, f"required field {field!r} missing"


def test_only_ema_hmpc_is_ever_a_populated_authority():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    for authority in SUPPORTED_REGULATORY_AUTHORITIES:
        assert authority in obj["authority_coverage"]
        assert "Not available" not in obj["authority_coverage"][authority]
    for authority in UNAVAILABLE_REGULATORY_AUTHORITIES:
        assert authority in obj["authority_coverage"]
        assert "not " in obj["authority_coverage"][authority].lower()


def test_unavailable_authorities_never_report_a_fabricated_status():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market=None,
    )
    for authority_key in ["WHO", "ESCOP", "FDA (botanical regulatory status)", "Health Canada", "Novel Food"]:
        status = obj["authority_coverage"][authority_key]
        assert status not in {"Yes", "No", "Approved", "Recognized"}


def test_ema_status_present_in_inventory():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'Valerianae radix' — see source PDF for monograph status",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    assert "Present in EMA HMPC inventory" in obj["ema_status"]
    assert "not a confirmed monograph" in obj["ema_status"]


def test_ema_status_not_found():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Not in HMPC inventory (as of 2021 snapshot)",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    assert obj["ema_status"] == "Not found in EMA HMPC inventory"


def test_ema_status_not_available_when_enrichment_never_ran():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status=None, market_landscape_regulatory_source=None,
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    assert obj["ema_status"] == "Not available"
    assert obj["regulatory_maturity"] == "Insufficient information"
    assert "Unavailable" in obj["regulatory_data_quality"]


def test_regulatory_data_quality_distinguishes_verified_connector_from_static_reference():
    connector_result = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    curated_result = build_regulatory_intelligence(
        market_landscape_ema_status="Yes",
        market_landscape_regulatory_source="Curated (seed_data.SLEEP_TEA_EVIDENCE) — manually verified",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    assert "Verified connector" in connector_result["regulatory_data_quality"]
    assert "Static regulatory reference" in curated_result["regulatory_data_quality"]
    assert connector_result["regulatory_data_quality"] != curated_result["regulatory_data_quality"]


def test_regulatory_maturity_is_not_defined_as_ema_status_itself():
    # Both a "listed" and a "not listed" EMA answer are equally RESOLVED
    # (Verified) — maturity is about how resolved the LOOKUP is, not
    # whether the plant happens to be in the inventory.
    listed = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    not_listed = build_regulatory_intelligence(
        market_landscape_ema_status="Not in HMPC inventory (as of 2021 snapshot)",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    assert listed["regulatory_maturity"] == "Verified"
    assert not_listed["regulatory_maturity"] == "Verified"


def test_traditional_use_status_detected_from_market_status():
    detected = build_regulatory_intelligence(
        market_landscape_ema_status=None, market_landscape_regulatory_source=None,
        regulatory_barriers=None, market_status="Traditional-use status", market=None,
    )
    not_detected = build_regulatory_intelligence(
        market_landscape_ema_status=None, market_landscape_regulatory_source=None,
        regulatory_barriers=None, market_status="Search not performed", market=None,
    )
    assert "Detected" in detected["traditional_use_status"]
    assert "not independently verified" in detected["traditional_use_status"]
    assert "Not detected" in not_detected["traditional_use_status"]


def test_major_regulatory_flags_reuses_existing_regulatory_barriers():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status=None, market_landscape_regulatory_source=None,
        regulatory_barriers="Prohibited / banned", market_status=None, market=None,
    )
    assert obj["major_regulatory_flags"] == "Prohibited / banned"


def test_development_considerations_reuses_regulatory_frameworks_and_is_labeled_market_level():
    considerations = build_development_considerations("European Union")
    assert len(considerations) > 0
    for item in considerations:
        assert "market-level pathway" in item
        assert "not a claim this botanical qualifies" in item


def test_development_considerations_honest_when_market_unknown():
    considerations = build_development_considerations("Nonexistent Market")
    assert considerations == ["Regulatory pathway information not available for this market."]


def test_regulatory_intelligence_limitations_always_present():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    assert any("NOT that a monograph has been" in lim for lim in obj["limitations"])
    assert any("not supported by the current repository" in lim for lim in obj["limitations"])


def test_regulatory_intelligence_deterministic():
    kwargs = dict(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers="None identified", market_status="Regulatory monograph exists", market="European Union",
    )
    assert build_regulatory_intelligence(**kwargs) == build_regulatory_intelligence(**kwargs)


def test_regulatory_intelligence_never_touches_scoring_fields():
    obj = build_regulatory_intelligence(
        market_landscape_ema_status="Listed in HMPC inventory as 'X'",
        market_landscape_regulatory_source="EMA HMPC — Inventory of herbal substances for assessment",
        regulatory_barriers=None, market_status=None, market="European Union",
    )
    forbidden = {"score", "rank", "r&d_opportunity_score", "evidence_confidence", "regulatory_score", "regulatory_risk_score"}
    assert not (set(k.lower() for k in obj.keys()) & forbidden)


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
