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
