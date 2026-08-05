"""Phase 3 — integration tests for the LIVE scoring path:
candidate_shortlisting._evidence_quality(), the function that actually
produces Evidence_Quality_Score (capped at 30.0) feeding Overall_Score.
"""
import pandas as pd

from candidate_shortlisting import (
    _evidence_quality,
    build_plant_candidate_shortlist,
)
import evidence_authority as ea


def _row(**overrides):
    row = {
        "Reference_Plant": "Reference plant",
        "Alternative_Plant": "Candidate plant",
        "Shared_or_Similar_Compound": "specific alkaloid",
        "Novelty_Status": "Rare / differentiating",
        "Target_or_Mechanism": "AMPK",
        "Target_Provenance": "Supported by source record",
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Human clinical evidence",
        "Candidate_Evidence_Strength_Tier": "Direct evidence",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": "PMID:123",
        "Applicability_Summary": '{"critical_mismatches":[],"evidence_items":[]}',
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "Regulatory_Barriers": "None identified",
        "Decision_Class": "Promising candidate; verify safety and standardization",
        "Decision_Class_AH": "Investigate",
        "Go_Investigate_Hold_NoGo": "Investigate",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "R&D_Opportunity_Score": 70,
    }
    row.update(overrides)
    return row


def _evq(rows):
    df = pd.DataFrame(rows)
    sources = list({r.get("Source_Record_IDs", "") for r in rows})
    references = list({r.get("Reference_Plant", "") for r in rows})
    return _evidence_quality(df, sources, references)


# ---------------------------------------------------------------------
# 15-19: authority/direction interaction scenarios
# ---------------------------------------------------------------------

def test_negative_rct_with_high_authority_scores_high_hierarchy_but_negative_direction_in_explain():
    total, tier, explain = _evq([
        _row(
            Evidence_Hierarchy_Detail="randomized controlled trial",
            Source_Record_IDs="PMID:100",
            Clinical_Rationale="worsened outcomes compared to placebo, increased adverse outcomes",
            Has_Negative_Evidence=True,
        )
    ])
    # Still classified into the RCT hierarchy tier (quality is design-based,
    # not outcome-based) — total > 0 and not silently zeroed by the
    # negative outcome.
    assert total > 0
    assert explain["quality_design_distribution"].get("rct") == 1
    # But the explainability layer must show a real negative-signed
    # contribution, not a positive one, for this record.
    assert explain["negative_weighted_contribution"] < 0
    assert explain["top_contradicting_evidence"]


def test_positive_rct_scores_higher_hierarchy_than_positive_animal_study():
    rct_total, _, _ = _evq([_row(Evidence_Hierarchy_Detail="randomized controlled trial")])
    animal_total, _, _ = _evq([_row(
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="animal study, rat model",
    )])
    assert rct_total > animal_total


def test_negative_rct_versus_positive_animal_study_signs_are_correct():
    """Direction sign correctness matters here, not aggregate-total
    ordering: aggregate totals also pass through the pre-existing,
    unmodified `outcome_multiplier` step (candidate-level consistency
    penalty), which Phase 3 explicitly does not redesign ("Ranking Logic
    = بدون بازطراحی"). What Phase 3 must guarantee is that the negative
    RCT's own signed contribution is negative and the positive animal
    study's is positive — never inverted by hierarchy or authority.
    """
    _, _, negative_rct_explain = _evq([_row(
        Evidence_Hierarchy_Detail="randomized controlled trial",
        Clinical_Rationale="worsened outcomes, increased adverse outcomes",
        Has_Negative_Evidence=True,
    )])
    _, _, positive_animal_explain = _evq([_row(
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="animal study, rat model",
        Scientific_Rationale="significant improvement, beneficial effect",
        Has_Negative_Evidence=False,
    )])
    assert negative_rct_explain["negative_weighted_contribution"] < 0
    assert negative_rct_explain["positive_weighted_contribution"] == 0
    assert positive_animal_explain["positive_weighted_contribution"] > 0
    assert positive_animal_explain["negative_weighted_contribution"] == 0


def test_mixed_evidence_with_different_authorities_preserves_both_signals():
    total, tier, explain = _evq([
        _row(
            Source_Record_IDs="PMID:1",
            Evidence_Hierarchy_Detail="randomized controlled trial",
            Scientific_Rationale="significant improvement, beneficial effect",
            Has_Negative_Evidence=False,
        ),
        _row(
            Source_Record_IDs="PMID:2",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="animal study",
            Clinical_Rationale="worsened outcomes, increased adverse outcomes",
            Has_Negative_Evidence=True,
        ),
    ])
    assert total > 0
    # Both a positive and a negative weighted contribution should be
    # visible — they must not collapse into one another before authority/
    # quality is applied.
    assert explain["positive_weighted_contribution"] > 0
    assert explain["negative_weighted_contribution"] < 0


def test_duplicate_copy_of_same_high_authority_source_not_double_counted():
    single_total, _, _ = _evq([
        _row(Source_Record_IDs="PMID:999", Evidence_Hierarchy_Detail="randomized controlled trial"),
    ])
    duplicate_total, _, _ = _evq([
        _row(Source_Record_IDs="PMID:999", Evidence_Hierarchy_Detail="randomized controlled trial"),
        _row(Source_Record_IDs="PMID:999", Evidence_Hierarchy_Detail="randomized controlled trial"),
    ])
    assert duplicate_total == single_total


# ---------------------------------------------------------------------
# 20-21
# ---------------------------------------------------------------------

def test_protocol_registry_record_without_results_earns_no_efficacy_points():
    total, tier, explain = _evq([
        _row(
            Evidence_Hierarchy_Detail="registry record without reported results",
            Evidence_Level="registry / protocol only",
        )
    ])
    assert total == 0.0
    assert tier == "None"


def test_unknown_authority_backward_compatible_fallback_does_not_zero_score():
    """A record with no organizational metadata at all (the common,
    pre-Phase-3 case) must still score — Unknown Source's conservative
    factor must not act like a hard exclusion."""
    total, tier, _ = _evq([_row()])
    assert total > 0
    assert tier != "None"


# ---------------------------------------------------------------------
# 25-27: cap / reconstruction / direction preservation
# ---------------------------------------------------------------------

def test_existing_evidence_quality_cap_still_respected():
    total, tier, _ = _evq([
        _row(Source_Record_IDs=f"PMID:{i}", Evidence_Hierarchy_Detail="systematic review meta-analysis")
        for i in range(12)
    ])
    assert total <= 30.0


def test_overall_score_remains_bounded_and_reconstructible_from_breakdown():
    from score_breakdown_schema import parse_score_breakdown, AUTHORITATIVE_CANONICAL_SECTIONS
    df = pd.DataFrame([_row(
        Scientific_Rationale="supports wound healing via collagen synthesis",
        Applicability_Summary='{"critical_mismatches":[],"evidence_items":[]}',
    )])
    summary, _ = build_plant_candidate_shortlist(df, indication="wound healing", dosage_form="Infusion")
    row = summary.iloc[0]
    assert 0 <= row["Overall_Score"] <= 100
    assert isinstance(row["Score_Breakdown"], dict)
    components = parse_score_breakdown(row["Score_Breakdown"])
    assert set(components.keys()) == AUTHORITATIVE_CANONICAL_SECTIONS
    assert round(sum(components.values()), 1) == row["Overall_Score"]


def test_direction_unchanged_after_authority_classification():
    """Classifying Source Authority for a record must never change its
    Has_Negative_Evidence / direction signal — direction is read
    independently, before and after authority classification, from the
    same unmodified row."""
    row = _row(Has_Negative_Evidence=True, Evidence_Hierarchy_Detail="randomized controlled trial")
    authority_before = ea.classify_source_authority_from_row(row)
    assert row["Has_Negative_Evidence"] is True
    authority_after = ea.classify_source_authority_from_row(row)
    assert authority_before.label == authority_after.label
    assert row["Has_Negative_Evidence"] is True


# ---------------------------------------------------------------------
# 28-29: negative outcome does not lower / positive does not raise
# study-quality classification.
# ---------------------------------------------------------------------

def test_negative_outcome_does_not_lower_hierarchy_classification():
    positive_total, _, positive_explain = _evq([
        _row(Evidence_Hierarchy_Detail="randomized controlled trial", Has_Negative_Evidence=False)
    ])
    negative_total, _, negative_explain = _evq([
        _row(Evidence_Hierarchy_Detail="randomized controlled trial", Has_Negative_Evidence=True)
    ])
    assert positive_explain["quality_design_distribution"] == negative_explain["quality_design_distribution"]


def test_positive_wording_does_not_raise_study_quality_in_evidence_quality_engine():
    from evidence_quality_engine import assess_evidence_quality
    positive = assess_evidence_quality({
        "Source_Title": "A randomized controlled trial",
        "Notes": "The treatment was effective and showed significant improvement",
    })
    neutral = assess_evidence_quality({
        "Source_Title": "A randomized controlled trial",
        "Notes": "",
    })
    assert positive["Evidence_Quality_Score"] == neutral["Evidence_Quality_Score"]


def test_negative_outcome_does_not_lower_study_quality_in_evidence_quality_engine():
    from evidence_quality_engine import assess_evidence_quality
    negative = assess_evidence_quality({
        "Source_Title": "A randomized controlled trial",
        "Notes": "the result was not effective and was negative overall",
    })
    neutral = assess_evidence_quality({
        "Source_Title": "A randomized controlled trial",
        "Notes": "",
    })
    assert negative["Evidence_Quality_Score"] == neutral["Evidence_Quality_Score"]


# ---------------------------------------------------------------------
# 30-33: PHASE 3, problem 2 fix — outcome_multiplier removal. The
# Evidence_Quality_Score total (`_evidence_quality`'s capped 0-30
# total, the number that actually feeds Overall_Score/
# R&D_Opportunity_Score) must no longer scale with Evidence_Direction.
# ---------------------------------------------------------------------

def test_evidence_quality_total_no_longer_scaled_by_outcome_multiplier():
    """A pool of otherwise-identical RCT evidence must score the SAME
    Evidence_Quality_Score total whether every record is positive,
    every record is negative, or the pool is null-only — the previous
    outcome_multiplier (0.55 for null/negative-only, 0.80 for
    mixed-with-positive) has been removed from this total."""
    positive_total, _, _ = _evq([
        _row(
            Source_Record_IDs="PMID:1",
            Evidence_Hierarchy_Detail="randomized controlled trial",
            Has_Negative_Evidence=False,
        )
    ])
    negative_total, _, _ = _evq([
        _row(
            Source_Record_IDs="PMID:1",
            Evidence_Hierarchy_Detail="randomized controlled trial",
            Has_Negative_Evidence=True,
        )
    ])
    assert positive_total == negative_total


def test_evidence_quality_total_unchanged_for_mixed_pool_versus_all_positive_pool():
    """Same guarantee as above, but for a multi-record pool: a pool
    with one positive + one negative RCT must score the SAME
    Evidence_Quality_Score total as two positive RCTs of identical
    design/authority — the negative record still shows up as a
    negative signed contribution in `explain`, it just no longer
    drags down the unsigned total via outcome_multiplier."""
    all_positive_total, _, _ = _evq([
        _row(Source_Record_IDs="PMID:1", Evidence_Hierarchy_Detail="randomized controlled trial"),
        _row(Source_Record_IDs="PMID:2", Evidence_Hierarchy_Detail="randomized controlled trial"),
    ])
    mixed_total, _, mixed_explain = _evq([
        _row(Source_Record_IDs="PMID:1", Evidence_Hierarchy_Detail="randomized controlled trial"),
        _row(
            Source_Record_IDs="PMID:2",
            Evidence_Hierarchy_Detail="randomized controlled trial",
            Clinical_Rationale="worsened outcomes, increased adverse outcomes",
            Has_Negative_Evidence=True,
        ),
    ])
    assert mixed_total == all_positive_total
    # Direction is still visible via the explain dict, just not via the total.
    assert mixed_explain["negative_weighted_contribution"] < 0


def test_positive_animal_versus_negative_rct_magnitude_comparison():
    """Comparable authority/applicability: the magnitude of a negative
    RCT's signed contribution must exceed a positive animal study's —
    a stronger study design produces a stronger contribution
    regardless of sign."""
    _, _, negative_rct_explain = _evq([_row(
        Evidence_Hierarchy_Detail="randomized controlled trial",
        Clinical_Rationale="worsened outcomes, increased adverse outcomes",
        Has_Negative_Evidence=True,
    )])
    _, _, positive_animal_explain = _evq([_row(
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="animal study, rat model",
        Scientific_Rationale="significant improvement, beneficial effect",
        Has_Negative_Evidence=False,
    )])
    negative_rct_contribution = negative_rct_explain["top_contradicting_evidence"][0]["signed_contribution"]
    positive_animal_contribution = positive_animal_explain["top_supporting_evidence"][0]["signed_contribution"]
    assert abs(negative_rct_contribution) > positive_animal_contribution


def test_mixed_evidence_scores_same_as_identical_composition_all_positive_pool():
    """One positive animal study + one negative high-authority RCT
    preserves both the positive and the negative signed contribution
    separately (never collapsed into one net number) -- but the SCORED
    Evidence_Quality_Score total must be IDENTICAL to a pool with the
    exact same composition (same designs, same authorities, same record
    count) where every record happens to be positive instead. hierarchy/
    depth/diversity CAN legitimately grow with a second independent
    record of a different design -- that is real, direction-agnostic
    architecture Phase 3 does not redesign -- but growth must come only
    from adding a record, never from that record disagreeing in
    direction. (Renamed/refixed from an earlier, looser version of this
    test that only asserted `mixed_total >= rct_alone_total` against a
    DIFFERENT, smaller composition -- too weak to catch a real remaining
    direction-dependence bug. See
    test_changing_only_direction_does_not_change_evidence_quality_score
    below for the general-case version of this guarantee.)"""
    all_positive_total, _, _ = _evq([
        _row(Source_Record_IDs="PMID:1", Evidence_Hierarchy_Detail="randomized controlled trial"),
        _row(
            Source_Record_IDs="PMID:2",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="animal study, rat model",
            Scientific_Rationale="significant improvement, beneficial effect",
        ),
    ])
    mixed_total, _, mixed_explain = _evq([
        _row(
            Source_Record_IDs="PMID:1",
            Evidence_Hierarchy_Detail="randomized controlled trial",
            Clinical_Rationale="worsened outcomes, increased adverse outcomes",
            Has_Negative_Evidence=True,
        ),
        _row(
            Source_Record_IDs="PMID:2",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="animal study, rat model",
            Scientific_Rationale="significant improvement, beneficial effect",
            Has_Negative_Evidence=False,
        ),
    ])
    # Both signals stay visible and separate...
    assert mixed_explain["positive_weighted_contribution"] > 0
    assert mixed_explain["negative_weighted_contribution"] < 0
    # ...but the scored total exactly matches the same-composition,
    # all-positive pool. Direction never changes Evidence_Quality_Score.
    assert mixed_total == all_positive_total
    # Diagnostics-only signal: this pool visibly disagrees, but that
    # information lives outside the scored total.
    assert mixed_explain["evidence_conflict"] is True


# ---------------------------------------------------------------------
# 35-41: PHASE 3 FOLLOW-UP -- `consistency_points` (derived from
# `negative_count`/Has_Negative_Evidence) was a SECOND, previously-missed
# route by which Evidence_Direction reached the scored
# Evidence_Quality_Score total, after the already-removed
# outcome_multiplier. All comparisons below hold every metadata field
# (design, authority, record count) fixed and change ONLY direction.
# ---------------------------------------------------------------------

def _rct(record_id, negative=False):
    if negative:
        return _row(
            Source_Record_IDs=record_id,
            Evidence_Hierarchy_Detail="randomized controlled trial",
            Clinical_Rationale="worsened outcomes, increased adverse outcomes",
            Has_Negative_Evidence=True,
        )
    return _row(
        Source_Record_IDs=record_id,
        Evidence_Hierarchy_Detail="randomized controlled trial",
        Scientific_Rationale="significant improvement, beneficial effect",
        Has_Negative_Evidence=False,
    )


def _null_rct(record_id):
    return _row(
        Source_Record_IDs=record_id,
        Evidence_Hierarchy_Detail="randomized controlled trial",
        Scientific_Rationale="no significant effect observed, no improvement",
        Has_Negative_Evidence=False,
    )


def test_one_positive_rct_equals_one_negative_rct():
    positive_total, _, _ = _evq([_rct("PMID:1", negative=False)])
    negative_total, _, _ = _evq([_rct("PMID:1", negative=True)])
    assert positive_total == negative_total


def test_three_positive_rcts_equals_two_positive_plus_one_negative_rct():
    all_positive_total, _, _ = _evq([
        _rct("PMID:1"), _rct("PMID:2"), _rct("PMID:3"),
    ])
    two_positive_one_negative_total, _, explain = _evq([
        _rct("PMID:1"), _rct("PMID:2"), _rct("PMID:3", negative=True),
    ])
    assert two_positive_one_negative_total == all_positive_total
    assert explain["negative_weighted_contribution"] < 0


def test_three_positive_rcts_equals_three_negative_rcts():
    all_positive_total, _, _ = _evq([
        _rct("PMID:1"), _rct("PMID:2"), _rct("PMID:3"),
    ])
    all_negative_total, _, explain = _evq([
        _rct("PMID:1", negative=True), _rct("PMID:2", negative=True), _rct("PMID:3", negative=True),
    ])
    assert all_negative_total == all_positive_total
    assert explain["positive_weighted_contribution"] == 0
    assert explain["negative_weighted_contribution"] < 0


def test_three_positive_rcts_equals_three_null_rcts():
    all_positive_total, _, _ = _evq([
        _rct("PMID:1"), _rct("PMID:2"), _rct("PMID:3"),
    ])
    all_null_total, _, explain = _evq([
        _null_rct("PMID:1"), _null_rct("PMID:2"), _null_rct("PMID:3"),
    ])
    assert all_null_total == all_positive_total
    assert explain["positive_weighted_contribution"] == 0
    assert explain["negative_weighted_contribution"] == 0


def test_changing_only_direction_does_not_change_evidence_quality_score():
    """General-case version: identical designs/authorities/record counts,
    ONLY the direction wording differs, across positive/negative/null/
    mixed -- Evidence_Quality_Score must be the same number every time."""
    variants = {
        "all_positive": [_rct("PMID:1"), _rct("PMID:2")],
        "all_negative": [_rct("PMID:1", negative=True), _rct("PMID:2", negative=True)],
        "mixed": [_rct("PMID:1"), _rct("PMID:2", negative=True)],
        "all_null": [_null_rct("PMID:1"), _null_rct("PMID:2")],
    }
    totals = {name: _evq(rows)[0] for name, rows in variants.items()}
    assert len(set(totals.values())) == 1, totals


def test_direction_changes_signed_contribution_but_not_evidence_quality_score():
    positive_total, _, positive_explain = _evq([_rct("PMID:1")])
    negative_total, _, negative_explain = _evq([_rct("PMID:1", negative=True)])
    # The scored total is unchanged...
    assert positive_total == negative_total
    # ...but the signed contribution genuinely flips.
    assert positive_explain["positive_weighted_contribution"] > 0
    assert positive_explain["negative_weighted_contribution"] == 0
    assert negative_explain["positive_weighted_contribution"] == 0
    assert negative_explain["negative_weighted_contribution"] < 0


def test_negative_high_authority_rct_retains_larger_magnitude_than_positive_animal_evidence():
    """Same guarantee as test_positive_animal_versus_negative_rct_magnitude_comparison
    above, re-verified after the consistency_points removal: a stronger
    study design still produces a stronger |contribution| regardless of
    sign, and this is untouched by the outcome-independence fix."""
    _, _, negative_rct_explain = _evq([_rct("PMID:1", negative=True)])
    _, _, positive_animal_explain = _evq([_row(
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="animal study, rat model",
        Scientific_Rationale="significant improvement, beneficial effect",
        Has_Negative_Evidence=False,
    )])
    negative_rct_contribution = negative_rct_explain["top_contradicting_evidence"][0]["signed_contribution"]
    positive_animal_contribution = positive_animal_explain["top_supporting_evidence"][0]["signed_contribution"]
    assert abs(negative_rct_contribution) > positive_animal_contribution


def test_evidence_quality_score_never_derived_from_result_category_or_negative_evidence_field():
    """Guards indirect leaks: neither `Has_Negative_Evidence` nor
    `_result_category()`'s classification may influence the scored total
    through any other route than the ones already checked above -- a
    pool of 5 identical-design RCTs must score the same total no matter
    how the 5 records split across positive/negative/null."""
    baseline_total, _, _ = _evq([_rct(f"PMID:{i}") for i in range(5)])
    every_split = [
        [_rct("PMID:0"), _rct("PMID:1"), _rct("PMID:2", negative=True), _rct("PMID:3", negative=True), _null_rct("PMID:4")],
        [_rct("PMID:0", negative=True), _rct("PMID:1", negative=True), _rct("PMID:2", negative=True), _rct("PMID:3", negative=True), _rct("PMID:4", negative=True)],
        [_null_rct("PMID:0"), _null_rct("PMID:1"), _null_rct("PMID:2"), _null_rct("PMID:3"), _null_rct("PMID:4")],
    ]
    for rows in every_split:
        total, _, _ = _evq(rows)
        assert total == baseline_total


# ---------------------------------------------------------------------
# 34: PHASE 3, problem 1 fix — real per-source Source Authority now
# reaches botanical_rd_candidate_engine.py's live call to
# interpret_evidence(), not just candidate_shortlisting.py.
# ---------------------------------------------------------------------

def test_botanical_rd_candidate_engine_passes_real_source_authority_into_interpret_evidence():
    """Two otherwise-identical evidence pools, differing ONLY in
    Source Authority (one carries Source_Organization metadata
    identifying an EMA HMPC Monograph, the other carries none at all)
    must, once run through the real
    botanical_rd_candidate_engine._build_evidence_text_index() ->
    _collect_raw_evidence() -> evidence_interpretation.interpret_evidence()
    chain, produce the SAME direction sign but a DIFFERENT contribution
    magnitude — proving the previously-hardcoded 1.0 default is gone
    on this call site — with an explainable reason available from the
    same shared classifier both pipelines use."""
    import pandas as pd
    from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
    from evidence_interpretation import interpret_evidence
    import evidence_authority as ea

    positive_text = (
        "A randomized controlled trial, double-blind and placebo-controlled, "
        "found significant hepatoprotective effects."
    )

    def _engine_for(evidence_row):
        plant_compounds_df = pd.DataFrame([dict(
            scientific_name="TestPlant", compound_name="ActiveCompound",
            indication="TestIndication", target="Hepatoprotective",
            common_name="", plant_part="", extraction_method="",
        )])
        return BotanicalRDCandidateEngine(
            plant_compounds_df=plant_compounds_df,
            compound_profiles_df=pd.DataFrame(),
            scientific_evidence_df=pd.DataFrame(),
            evidence_df=pd.DataFrame([evidence_row]),
            use_live_search=False,
        )

    def _interpret(engine):
        index, source_index, _applicability_index, authority_index = (
            engine._build_evidence_text_index()
        )
        text, _sources, authority_factor = engine._collect_raw_evidence(
            evidence_index=index,
            plant="TestPlant",
            compound="ActiveCompound",
            problem="TestIndication",
            source_index=source_index,
            authority_index=authority_index,
        )
        result = interpret_evidence(text, source_authority_factor=authority_factor)
        return result, authority_factor

    high_authority_result, high_authority_factor = _interpret(_engine_for({
        "Scientific_Name": "TestPlant",
        "Notes": positive_text,
        "Source_Organization": "EMA HMPC Monograph",
    }))
    unknown_authority_result, unknown_authority_factor = _interpret(_engine_for({
        "Scientific_Name": "TestPlant",
        "Notes": positive_text,
    }))

    # Same sign — Source Authority never flips direction.
    assert high_authority_result.evidence_direction == unknown_authority_result.evidence_direction
    assert high_authority_result.contribution > 0
    assert unknown_authority_result.contribution > 0
    # Different, REAL magnitude — no longer a hardcoded 1.0 on both sides.
    assert high_authority_factor > unknown_authority_factor
    assert high_authority_result.contribution > unknown_authority_result.contribution

    # Explainable: the same shared classifier both pipelines use exposes
    # a human-readable reason distinguishing the two.
    high_reason = ea.classify_source_authority_from_row(
        {"Source_Organization": "EMA HMPC Monograph", "Notes": positive_text}
    ).reason
    unknown_reason = ea.classify_source_authority_from_row({"Notes": positive_text}).reason
    assert high_reason and unknown_reason
    assert high_reason != unknown_reason
