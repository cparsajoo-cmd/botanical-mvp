"""Phase 5 — Scoring Calibration: characterization + desired-behavior
tests (audit addendum, pre-implementation).

NO PRODUCTION CODE IS MODIFIED OR REIMPLEMENTED HERE. Every assertion
calls a real, existing, public/module-level function from the
repository. Where a helper is needed to build a faithful fixture, the
helper only *constructs pandas.DataFrame rows* (data), never
re-implements any scoring/classification logic.

Section A — Characterization tests (`test_characterizes_current_...`):
document CURRENT behavior, including confirmed defects. These are
expected to PASS today and continue to pass until an approved
implementation phase deliberately changes the behavior they document.

Section B — Desired-behavior tests: encode the Phase 5 addendum's
acceptance criteria. Several of these are EXPECTED TO FAIL today — that
is the point (see PHASE5_SCORING_CALIBRATION_AUDIT_ADDENDUM.md). They
are ordinary `assert`-based tests, not `xfail`/`skip`, per the corrected
test contract: a missing production schema field or a missing scoring
capability is an ordinary desired-behavior gap, not an environment
dependency, and must fail normally.

THIS FILE CONTAINS NO `pytest.mark.xfail` AND NO `pytest.mark.skip`.

Several tests below exercise the REAL, AUTHORITATIVE plant-level scoring
path (`candidate_shortlisting.build_plant_candidate_shortlist()` and
`candidate_shortlisting.merge_authoritative_scores()`), not just the
lower-level `_evidence_quality()` helper, per the corrected test
contract's instruction to target `Overall_Score`/`Scientific_Triage_Score`
directly rather than assume a lower-level function's behavior generalizes
to the authoritative output. Where a test still calls `_evidence_quality()`
directly, it is only to establish the (already-true, already-tested)
claim that Evidence Quality itself stays unsigned — never to stand in for
a claim about `Overall_Score`.
"""
from __future__ import annotations

import math
import inspect

import pandas as pd
import pytest

from botanical_rd_candidate_engine import (
    BotanicalRDCandidateEngine as Engine,
    ScoringConfig,
    GateStatus,
    HARD_SAFETY_TERMS,
)
import candidate_shortlisting as cs
import decision_class_ah as dch
import eligibility_gate as eg
import evidence_authority as ea
import global_candidate_ranking_engine as gr
from general_indication_relevance import MATCH_EXACT_INDICATION, MATCH_NO_MATCH
from evidence_consistency import classify_evidence_consistency


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def make_engine():
    """A BotanicalRDCandidateEngine instance with only the attributes
    _score_candidate()/_decision_class()/_evaluate_gates() actually read
    (scoring_config, compound_commonality_threshold). Bypasses __init__
    (which needs live Supabase/seed data sources) via __new__ — this is
    the standard way to unit-test a method that doesn't depend on the
    rest of the object's construction, and does not alter any production
    code path."""
    engine = Engine.__new__(Engine)
    engine.scoring_config = ScoringConfig()
    engine.compound_commonality_threshold = None
    return engine


def evidence_row(
    *,
    plant="Alt Plant",
    source_record_id="REC-1",
    evidence_source="PubMed",
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="",
    scientific_rationale="",
    clinical_rationale="",
    grade_certainty="",
    candidate_evidence_strength_tier="",
    target_provenance="",
    result_direction="",
    negative_evidence_types="",
    evidence_conflict_reasoning="",
    has_negative_evidence=False,
    direct_evidence_present=True,
    target_or_mechanism="COX-2 inhibition",
    shared_or_similar_compound="Compound-A",
    novelty_status="Other",
    alternative_plant=None,
    source_organization="",
    source_type="",
    source_category="",
    source_title="",
    source_url="",
    eligible_for_normal_ranking=None,
    eligibility_status=None,
    extraction_method="",
    dosage_form_compatibility="Not evaluated",
    indication_match_type=None,
    indication_match_terms="",
):
    """Builds ONE faithful evidence/candidate row with every column read
    by _row_has_candidate_specific_empirical_support(), _result_category(),
    _outcome_profile(), _evidence_quality(), _evidence_points(),
    _row_classification(), and classify_source_authority_from_row() —
    verified by direct reading of each function's body (see the audit
    addendum). No production logic is duplicated here: only data.
    """
    row = {
        "Alternative_Plant": alternative_plant or plant,
        "Source_Record_IDs": source_record_id,
        "Evidence_Source": evidence_source,
        "Evidence_Level": evidence_level,
        "Evidence_Hierarchy_Detail": evidence_hierarchy_detail,
        "Scientific_Rationale": scientific_rationale,
        "Clinical_Rationale": clinical_rationale,
        "GRADE_Certainty": grade_certainty,
        "Candidate_Evidence_Strength_Tier": candidate_evidence_strength_tier,
        "Target_Provenance": target_provenance,
        "Result_Direction": result_direction,
        "Negative_Evidence_Types": negative_evidence_types,
        "Evidence_Conflict_Reasoning": evidence_conflict_reasoning,
        "Has_Negative_Evidence": has_negative_evidence,
        "Direct_Evidence_Present": direct_evidence_present,
        "Target_or_Mechanism": target_or_mechanism,
        "Shared_or_Similar_Compound": shared_or_similar_compound,
        "Novelty_Status": novelty_status,
        "Source_Organization": source_organization,
        "Source_Type": source_type,
        "Source_Category": source_category,
        "Source_Title": source_title,
        "Source_URL": source_url,
        "Extraction_Method": extraction_method,
        "Dosage_Form_Compatibility": dosage_form_compatibility,
        "Reference_Plant": "Ref Plant",
        "Supported_Target_or_Mechanism": True,
        "Hard_Stop_Present": False,
        "Negative_Evidence_Present": has_negative_evidence,
    }
    if eligible_for_normal_ranking is not None:
        row["Eligible_For_Normal_Ranking"] = eligible_for_normal_ranking
    if eligibility_status is not None:
        row["Eligibility_Status"] = eligibility_status
    if indication_match_type is not None:
        row["Indication_Match_Type"] = indication_match_type
        row["Indication_Match_Terms"] = indication_match_terms
    return row


def group_df(rows):
    return pd.DataFrame(rows)


POSITIVE_RCT = dict(
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="randomized controlled trial",
    clinical_rationale="significant positive effect reported; improvement in symptoms",
    result_direction="positive",
)

NEGATIVE_RCT = dict(
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="randomized controlled trial",
    clinical_rationale="no significant improvement; no effect on primary endpoint",
    result_direction="negative",
    has_negative_evidence=True,
)

NULL_RCT = dict(
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="randomized controlled trial",
    clinical_rationale="no significant difference from placebo; null result",
    result_direction="null",
    has_negative_evidence=True,
)

MIXED_RCT = dict(
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="randomized controlled trial",
    clinical_rationale="mixed and inconsistent results across endpoints",
    result_direction="mixed",
)

HARMFUL_RCT = dict(
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="randomized controlled trial",
    clinical_rationale="adverse effect reported; increased risk of harm",
    result_direction="negative",
)

POSITIVE_ANIMAL = dict(
    evidence_level="Preclinical / mechanistic evidence",
    evidence_hierarchy_detail="animal model in vivo study",
    clinical_rationale="",
    scientific_rationale="significant improvement observed in animal model",
    result_direction="positive",
)


def with_ids(base, source_record_id):
    row = dict(base)
    row["source_record_id"] = source_record_id
    return row


# ---------------------------------------------------------------------------
# Plant-level (authoritative) fixture helper. Used by every test that must
# exercise the REAL Overall_Score/Scientific_Triage_Score path, per the
# corrected test contract -- not a synthetic stand-in.
#
# Sets Indication_Match_Type=MATCH_EXACT_INDICATION so the row is scored
# via _indication_relevance_detail_authoritative() (the real, production-
# authoritative relevance engine's own output columns), the SAME path
# indication_candidate_discovery.py wires in production -- not the
# compound-source legacy fallback. No relevance/consistency/direction
# logic is reimplemented here: only the input columns those real
# functions read are populated with data.
# ---------------------------------------------------------------------------

INDICATION = "test indication"


def plant_row(
    direction_kwargs,
    *,
    plant="Plantus testus",
    rec_id="REC-1",
    evidence_level="Clinical / human evidence",
    evidence_hierarchy_detail="randomized controlled trial",
    extraction_method="aqueous extract",
    safety_flags="well tolerated; no serious adverse events",
    applicability_summary="",
):
    return {
        "Alternative_Plant": plant,
        "Reference_Plant": "Ref Plant",
        "Source_Record_IDs": rec_id,
        "Evidence_Source": "PubMed",
        "Evidence_Level": evidence_level,
        "Evidence_Hierarchy_Detail": evidence_hierarchy_detail,
        "Scientific_Rationale": direction_kwargs.get("scientific_rationale", ""),
        "Clinical_Rationale": direction_kwargs.get("clinical_rationale", ""),
        "GRADE_Certainty": "",
        "Candidate_Evidence_Strength_Tier": "",
        "Target_Provenance": "",
        "Result_Direction": direction_kwargs.get("result_direction", ""),
        "Negative_Evidence_Types": "",
        "Evidence_Conflict_Reasoning": "",
        "Has_Negative_Evidence": direction_kwargs.get("has_negative_evidence", False),
        "Direct_Evidence_Present": True,
        "Target_or_Mechanism": "COX-2 inhibition",
        "Shared_or_Similar_Compound": "Compound-A",
        "Novelty_Status": "Alternative",
        "Source_Organization": "",
        "Source_Type": "",
        "Source_Category": "",
        "Source_Title": "",
        "Source_URL": "",
        "Extraction_Method": extraction_method,
        "Safety_Flags": safety_flags,
        "Interaction_Flags": "",
        "Regulatory_Barriers": "",
        "Market_Status": "",
        "Indication_Match_Type": MATCH_EXACT_INDICATION,
        "Indication_Match_Terms": INDICATION,
        "Applicability_Summary": applicability_summary,
        "Preparation_Applicability": "",
    }


def run_authoritative(rows, *, indication=INDICATION, dosage_form="", target_context=None):
    """Runs the REAL production plant-level path end to end:
    build_plant_candidate_shortlist() -> merge_authoritative_scores().
    Returns (plant_summary_row, merged_row) as pandas Series, or
    (None, None) if the plant produced no summary row at all. No
    scoring/classification logic is reimplemented -- these are the
    actual public functions candidate_shortlisting.py exports.

    When target_context is supplied, asserts (via inspect.signature(),
    per addendum §3.8 FINAL correction round 6) that the REAL production
    signature accepts it before calling -- this assertion fails normally
    today because the parameter does not exist yet. No test-side
    adapter computes applicability itself; if the parameter existed,
    it would be passed straight through to the real function."""
    raw_df = pd.DataFrame(rows)
    if target_context is not None:
        sig = inspect.signature(cs.build_plant_candidate_shortlist)
        assert "target_context" in sig.parameters, (
            "build_plant_candidate_shortlist() does not yet accept a "
            "target_context parameter -- confirmed gap, addendum §3.8 "
            "(NOT implemented in this pass)."
        )
        plant_summary, _row_audit = cs.build_plant_candidate_shortlist(
            raw_df, indication=indication, dosage_form=dosage_form,
            target_context=target_context,
        )
    else:
        plant_summary, _row_audit = cs.build_plant_candidate_shortlist(
            raw_df, indication=indication, dosage_form=dosage_form,
        )
    if plant_summary.empty:
        return None, None
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    merged_row = merged.iloc[0] if not merged.empty else None
    return plant_summary.iloc[0], merged_row


# ===========================================================================
# SECTION A — Characterization tests (current behavior, incl. defects)
# ===========================================================================

def test_characterizes_current_legacy_behavior_overall_score_is_authoritative():
    """1. Overall_Score is authoritative: merge_authoritative_scores()
    overwrites the raw row's numeric/classification fields with the
    plant_summary's own Overall_Score, not the other way around."""
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 40.0,
         "Rationale": "raw rationale", "Evidence_Confidence": 20.0,
         "Decision_Class_AH": "G — Hold / insufficient evidence",
         "Go_Investigate_Hold_NoGo": "Hold"},
    ])
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 91.0,
         "Score_Breakdown": "x", "Score_Breakdown_Display": "x",
         "Evidence_Confidence": 88.0,
         "Decision_Class_AH": "B — Established scientific candidate",
         "Go_Investigate_Hold_NoGo": "Go",
         "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "strong evidence"},
    ])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    assert merged.loc[0, "Overall_Score"] == 91.0
    assert merged.loc[0, "Decision_Class_AH"] == "B — Established scientific candidate"
    assert merged.loc[0, "Go_Investigate_Hold_NoGo"] == "Go"


def test_characterizes_current_legacy_behavior_rd_opportunity_score_equals_overall_score_after_merge():
    """2. R&D_Opportunity_Score, after merge, equals Overall_Score exactly
    (explicit alias, not a second computation)."""
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 12.0},
    ])
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 67.5,
         "Evidence_Confidence": 50.0, "Decision_Class_AH": "C — Alternative-source R&D candidate",
         "Go_Investigate_Hold_NoGo": "Investigate", "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "ok"},
    ])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    assert merged.loc[0, "R&D_Opportunity_Score"] == merged.loc[0, "Overall_Score"] == 67.5


def test_characterizes_current_legacy_behavior_raw_score_selects_richest_narrative_row_not_overall_score():
    """3. CONFIRMED PROVENANCE DEFECT (addendum §4): the raw, PRE-merge
    R&D_Opportunity_Score decides which raw row's narrative
    (Rationale/Gate_Results/etc.) is kept -- a criterion that has nothing
    to do with Overall_Score. Here, row LOW_RAW would have contributed
    more to a real Overall_Score (richer narrative, "strong" rationale)
    but row HIGH_RAW wins the narrative purely because its OWN raw
    R&D_Opportunity_Score happens to be numerically higher."""
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 80.0,
         "Rationale": "generic / low-information rationale from a weak row",
         "Gate_Results": "weak-row-gates"},
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 20.0,
         "Rationale": "rich, specific rationale describing the real strong evidence",
         "Gate_Results": "strong-row-gates"},
    ])
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 85.0,
         "Evidence_Confidence": 80.0, "Decision_Class_AH": "B — Established scientific candidate",
         "Go_Investigate_Hold_NoGo": "Go", "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "strong evidence"},
    ])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    assert len(merged) == 1
    # The published Overall_Score (85.0) is attributed to narrative text
    # that came from the row with raw R&D_Opportunity_Score == 80.0 (the
    # "weak-row" narrative), NOT the row that actually describes strong
    # evidence -- reproducing the confirmed provenance defect.
    assert merged.loc[0, "Overall_Score"] == 85.0
    assert merged.loc[0, "Rationale"] == "generic / low-information rationale from a weak row"
    assert merged.loc[0, "Gate_Results"] == "weak-row-gates"


def test_characterizes_current_legacy_behavior_row_level_decision_class_ah_is_overwritten():
    """4. Row-level Decision_Class_AH (from decision_class_ah.classify_decision_ah,
    engine row-level) is overwritten by the plant-level value computed in
    candidate_shortlisting._derive_decision_class_ah() once merged."""
    row_level_ah = dch.classify_decision_ah(
        existing_decision_class="Low priority / insufficient data",
        evidence_confidence=5.0,
        rd_opportunity_score=10.0,
        market_status="Unknown",
        match_quality="class_only",
        same_plant=False,
    )
    assert row_level_ah != "B — Established scientific candidate"

    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 10.0,
         "Decision_Class_AH": row_level_ah},
    ])
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 92.0,
         "Evidence_Confidence": 90.0, "Decision_Class_AH": "B — Established scientific candidate",
         "Go_Investigate_Hold_NoGo": "Go", "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "strong"},
    ])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    assert merged.loc[0, "Decision_Class_AH"] == "B — Established scientific candidate"
    assert merged.loc[0, "Decision_Class_AH"] != row_level_ah


def test_characterizes_current_legacy_behavior_row_level_evidence_confidence_is_overwritten():
    """5. Row-level Evidence_Confidence (evidence_confidence.compute_evidence_confidence)
    is overwritten by the plant-level Evidence_Confidence once merged."""
    from evidence_confidence import compute_evidence_confidence
    row_level_confidence = compute_evidence_confidence(
        evidence_hierarchy_detail=None,
        evidence_level="No direct evidence",
        has_negative_evidence=False,
    )
    assert row_level_confidence == 0.0

    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 10.0,
         "Evidence_Confidence": row_level_confidence},
    ])
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 92.0,
         "Evidence_Confidence": 77.0, "Decision_Class_AH": "B — Established scientific candidate",
         "Go_Investigate_Hold_NoGo": "Go", "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "strong"},
    ])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    assert merged.loc[0, "Evidence_Confidence"] == 77.0
    assert merged.loc[0, "Evidence_Confidence"] != row_level_confidence


def test_characterizes_current_legacy_behavior_eligibility_no_go_returns_before_score_threshold():
    """6. Eligibility No-Go (here: EXPERT_REVIEW_REQUIRED, the status a
    HARD_SAFETY_TERMS hit actually reaches in production -- see addendum
    §5b) short-circuits _decision_class() BEFORE the score>=78 tier logic
    is ever reached, even for a very high score."""
    engine = make_engine()
    decision = engine._decision_class(
        score=99.0,
        safety_flags="teratogenic",
        interaction_flags="",
        has_evidence=True,
        match_quality="exact",
        evidence_level="Clinical / human evidence",
        same_plant=False,
        regulatory_barrier_types=None,
        has_evidence_text=True,
    )
    assert "Strong R&D candidate" not in decision
    assert "not eligible for normal ranking" in decision or "not suitable" in decision


def test_characterizes_current_legacy_behavior_duplicate_evidence_removed_in_evidence_quality():
    """7. Duplicate evidence (same Source_Record_IDs) is de-duplicated
    before _evidence_quality() scores it -- two identical rows do not
    score higher than one."""
    single = group_df([evidence_row(source_record_id="REC-DUP", **POSITIVE_RCT)])
    duplicated = group_df([
        evidence_row(source_record_id="REC-DUP", **POSITIVE_RCT),
        evidence_row(source_record_id="REC-DUP", **POSITIVE_RCT),
    ])
    total_single, _, _ = cs._evidence_quality(single, sources=["REC-DUP"], references=[])
    total_dup, _, _ = cs._evidence_quality(duplicated, sources=["REC-DUP", "REC-DUP"], references=[])
    assert total_single == total_dup


def test_characterizes_current_legacy_behavior_source_authority_applied_once_in_published_evidence_quality(monkeypatch):
    """8. STRENGTHENED per third supervisory review (correction #5): the
    previous version only checked that a total was positive -- it never
    actually proved Source Authority is applied exactly once. Uses a
    non-invasive monkeypatch call-counter wrapped around the exact symbol
    _evidence_quality() calls (candidate_shortlisting.classify_source_
    authority_from_row -- confirmed by reading candidate_shortlisting.py
    line 21's import and line 1072's call site; it is imported directly
    into this module's namespace, so patching it on the `cs` module
    object intercepts the real call). Does NOT reproduce the authority-
    scoring formula itself -- only counts calls to the real function.

    Asserts:
    (1) For one de-duplicated EvidenceRecord, the authority classifier is
        called EXACTLY ONCE.
    (2) For two rows sharing the same deduplication key (identical
        Source_Record_IDs), deduplication occurs before scoring and the
        authority classifier is applied to the SURVIVING row only once --
        not once per raw row before dedup.

    Both ALREADY TRUE today (this is a characterization test, documenting
    correct existing behavior, per the file's own naming convention)."""
    call_count = {"n": 0}
    real_classifier = ea.classify_source_authority_from_row

    def counting_wrapper(row):
        call_count["n"] += 1
        return real_classifier(row)

    monkeypatch.setattr(cs, "classify_source_authority_from_row", counting_wrapper)

    single_row = evidence_row(
        source_record_id="REC-AUTH-SINGLE",
        evidence_level="Clinical / human evidence",
        evidence_hierarchy_detail="randomized controlled trial",
        clinical_rationale="significant positive effect",
        source_organization="EMA",
        source_type="Regulatory monograph",
    )
    cs._evidence_quality(group_df([single_row]), sources=["REC-AUTH-SINGLE"], references=[])
    assert call_count["n"] == 1, (
        "Expected exactly one call to classify_source_authority_from_row "
        f"for a single EvidenceRecord; got {call_count['n']}."
    )

    call_count["n"] = 0
    duplicate_rows = [
        evidence_row(
            source_record_id="REC-AUTH-DUP",
            evidence_level="Clinical / human evidence",
            evidence_hierarchy_detail="randomized controlled trial",
            clinical_rationale="significant positive effect",
            source_organization="EMA",
            source_type="Regulatory monograph",
        ),
        evidence_row(
            source_record_id="REC-AUTH-DUP",  # same dedup key
            evidence_level="Clinical / human evidence",
            evidence_hierarchy_detail="randomized controlled trial",
            clinical_rationale="significant positive effect",
            source_organization="EMA",
            source_type="Regulatory monograph",
        ),
    ]
    cs._evidence_quality(group_df(duplicate_rows), sources=["REC-AUTH-DUP", "REC-AUTH-DUP"], references=[])
    assert call_count["n"] == 1, (
        "Two rows sharing the same deduplication key should be "
        "de-duplicated BEFORE scoring, so the authority classifier "
        f"should be called exactly once, not twice; got {call_count['n']}."
    )


def test_characterizes_current_legacy_behavior_global_ranking_score_affects_only_sourcing_fallback():
    """9. Global_Ranking_Score / Candidate_Status (global_candidate_ranking_engine.py)
    are never read by any other production module -- confirmed by
    checking they are absent from every dependency of the published
    Overall_Score/Decision_Class path (candidate_shortlisting.py,
    botanical_rd_candidate_engine.py)."""
    import inspect
    cs_source = inspect.getsource(cs)
    engine_source = inspect.getsource(__import__("botanical_rd_candidate_engine"))
    assert "Global_Ranking_Score" not in cs_source
    assert "Global_Ranking_Score" not in engine_source
    assert "Candidate_Status" not in cs_source
    # rank_global_candidates IS referenced by the engine (as a candidate
    # sourcing fallback), confirming it is reachable, just not
    # score-authoritative.
    assert "rank_global_candidates" in engine_source


# ===========================================================================
# SECTION B — Desired-behavior tests
# ===========================================================================

# --- Direction / Quality / Consistency (items 1-9) -------------------------

def test_desired_positive_high_quality_human_rct_increases_scientific_efficacy_support():
    """1. A positive high-quality human RCT should increase whatever
    component represents scientific EFFICACY support (not just Evidence
    Quality, which is intentionally direction-blind -- see addendum
    §1). No such efficacy-support component/adjustment exists yet, so
    this is measured against the *only* currently-existing signed
    per-row contribution (`signed_contribution`, computed but never
    summed into a published score -- addendum §1.1)."""
    row = evidence_row(source_record_id="REC-POS", **POSITIVE_RCT)
    _, _, explain = cs._evidence_quality(group_df([row]), sources=["REC-POS"], references=[])
    assert explain["positive_weighted_contribution"] > 0
    assert explain["negative_weighted_contribution"] == 0


def test_desired_negative_high_quality_human_rct_does_not_add_positive_efficacy_support():
    """2. A negative high-quality human RCT must not add positive
    efficacy support."""
    row = evidence_row(source_record_id="REC-NEG", **NEGATIVE_RCT)
    _, _, explain = cs._evidence_quality(group_df([row]), sources=["REC-NEG"], references=[])
    assert explain["positive_weighted_contribution"] == 0
    assert explain["negative_weighted_contribution"] <= 0


def test_desired_negative_rct_reduces_final_scientific_support_relative_to_identical_positive_rct():
    """3. FURTHER CORRECTED per second supervisory review: the previous
    version of this test passed today only because direction is
    INCIDENTALLY embedded inside Indication Relevance -- not because a
    dedicated Scientific_Evidence_Score/Evidence_Direction_Profile
    mechanism exists. Rewritten to require the actual proposed
    authoritative outputs (addendum §1.5/§1.3) rather than accept the
    incidental Overall_Score difference as sufficient.

    Asserts:
    (1) otherwise-identical positive/negative RCTs retain equivalent
        unsigned Evidence_Quality_Score -- ALREADY TRUE today (Phase 3).
    (2) The authoritative plant-level output contains dedicated
        'Scientific_Evidence_Score' and 'Evidence_Direction_Profile'
        columns/fields -- NEITHER EXISTS TODAY (confirmed absent by
        column check on the real merge_authoritative_scores() output).
    (3) The negative-RCT candidate's Scientific_Evidence_Score is lower
        than the positive-RCT candidate's.
    (4) Direction is NOT implemented solely through a change in
        Indication_Relevance -- i.e. in the desired architecture, the two
        candidates' Indication_Relevance component should be EQUAL
        (direction lives in Evidence_Direction_Profile/Direction_Factor
        instead, addendum §1.3-§1.5), unlike today where Indication_
        Relevance itself differs (30.2 vs 13.6, empirically verified) and
        is the ONLY thing carrying the distinction.

    THIS TEST MUST FAIL TODAY, and does: (2) fails because neither column
    exists; (4) fails because Indication_Relevance currently DOES differ
    between the two candidates (today's incidental mechanism), which is
    exactly the "direction embedded in the wrong component" problem
    addendum §1.1/§1.2 identifies and this test is designed to catch.
    """
    positive_evq, _, _ = cs._evidence_quality(
        group_df([evidence_row(source_record_id="REC-A", **POSITIVE_RCT)]),
        sources=["REC-A"], references=[],
    )
    negative_evq, _, _ = cs._evidence_quality(
        group_df([evidence_row(source_record_id="REC-A", **NEGATIVE_RCT)]),
        sources=["REC-A"], references=[],
    )
    assert positive_evq == negative_evq, (
        "Evidence_Quality_Score must remain unsigned/direction-independent "
        "(Phase 3 requirement, still correctly in effect)."
    )

    pos_summary, _ = run_authoritative([plant_row(POSITIVE_RCT, rec_id="REC-POS")])
    neg_summary, _ = run_authoritative([plant_row(NEGATIVE_RCT, rec_id="REC-NEG")])
    assert pos_summary is not None and neg_summary is not None

    assert "Scientific_Evidence_Score" in pos_summary.index, (
        "No dedicated Scientific_Evidence_Score exists in the authoritative "
        "plant-level output today -- confirmed gap, addendum §1.5."
    )
    assert "Evidence_Direction_Profile" in pos_summary.index, (
        "No dedicated Evidence_Direction_Profile exists in the authoritative "
        "plant-level output today -- confirmed gap, addendum §1.3."
    )

    assert neg_summary["Scientific_Evidence_Score"] < pos_summary["Scientific_Evidence_Score"]

    pos_indication = pos_summary["Score_Breakdown"]["Indication Relevance"]
    neg_indication = neg_summary["Score_Breakdown"]["Indication Relevance"]
    assert pos_indication == neg_indication, (
        "Direction must not be implemented solely through a change in "
        "Indication_Relevance -- today it IS the sole mechanism "
        f"(positive={pos_indication} vs negative={neg_indication}, "
        "confirmed to differ), which is exactly the conceptual-"
        "misplacement problem addendum §1.1/§1.2 identifies."
    )


def test_desired_null_rct_does_not_add_positive_efficacy_points():
    """4. A null RCT (no significant difference) should not add positive
    efficacy points."""
    row = evidence_row(source_record_id="REC-NULL", **NULL_RCT)
    _, _, explain = cs._evidence_quality(group_df([row]), sources=["REC-NULL"], references=[])
    assert explain["positive_weighted_contribution"] == 0


def test_desired_mixed_evidence_receives_limited_contribution():
    """5. Mixed evidence should receive a limited (small-magnitude)
    contribution, not a strong positive or strong negative one."""
    row = evidence_row(source_record_id="REC-MIXED", **MIXED_RCT)
    pos_row = evidence_row(source_record_id="REC-CLEAR-POS", **POSITIVE_RCT)
    _, _, explain_mixed = cs._evidence_quality(group_df([row]), sources=["REC-MIXED"], references=[])
    _, _, explain_pos = cs._evidence_quality(group_df([pos_row]), sources=["REC-CLEAR-POS"], references=[])
    mixed_contribution = abs(
        explain_mixed["positive_weighted_contribution"] + explain_mixed["negative_weighted_contribution"]
    )
    positive_contribution = explain_pos["positive_weighted_contribution"]
    assert mixed_contribution < positive_contribution, (
        "Mixed-direction evidence should contribute less in magnitude "
        "than a clean, fully positive study of the same design."
    )


def test_desired_conflicting_evidence_reduces_consistency_factor():
    """6. FURTHER CORRECTED per third supervisory review: renamed to the
    single authoritative name 'Evidence_Consistency_Factor' (never
    'Evidence_Consistency_Score' -- there is no separate signed numeric
    consistency scale in the approved design, only this positive-
    magnitude factor, addendum §1 terminology note).

    Asserts:
    (1) Evidence Quality stays comparable between an otherwise-equivalent
        consistent set and a conflicting set -- ALREADY TRUE today.
    (2) The authoritative plant-level output contains
        'Evidence_Consistency_Class' and 'Evidence_Consistency_Factor'
        columns -- NEITHER EXISTS TODAY.
    (3) Consistent positive evidence has a STRONGER (numerically higher)
        Evidence_Consistency_Factor than conflicting evidence
        (provisional table: CONSISTENT_POSITIVE=1.00 > MIXED=0.60).

    THIS TEST MUST FAIL TODAY (and does), because (2)'s columns do not
    exist on the real merge_authoritative_scores() output -- confirmed by
    column check, not assumed. See addendum §1.3 Step 4 / §2.1.
    """
    consistent_evq, _, _ = cs._evidence_quality(
        group_df([
            evidence_row(source_record_id="REC-1", **POSITIVE_RCT),
            evidence_row(source_record_id="REC-2", **{**POSITIVE_RCT, "clinical_rationale": "clear benefit reported, significant improvement"}),
        ]),
        sources=["REC-1", "REC-2"], references=[],
    )
    conflicting_evq, _, _ = cs._evidence_quality(
        group_df([
            evidence_row(source_record_id="REC-1", **POSITIVE_RCT),
            evidence_row(source_record_id="REC-2", **HARMFUL_RCT),
        ]),
        sources=["REC-1", "REC-2"], references=[],
    )
    assert consistent_evq == conflicting_evq, (
        "Evidence Quality should remain comparable between an otherwise-"
        "equivalent consistent and conflicting evidence set."
    )

    pos_row1 = plant_row(POSITIVE_RCT, rec_id="REC-P1")
    pos_row2 = plant_row(POSITIVE_RCT, rec_id="REC-P2")
    harm_row = plant_row(HARMFUL_RCT, rec_id="REC-H1")
    conflicting_summary, _ = run_authoritative([pos_row1, harm_row])
    consistent_summary, _ = run_authoritative([pos_row1, pos_row2])
    assert conflicting_summary is not None and consistent_summary is not None

    assert "Evidence_Consistency_Class" in consistent_summary.index, (
        "No dedicated Evidence_Consistency_Class exists in the "
        "authoritative plant-level output today -- confirmed gap."
    )
    assert "Evidence_Consistency_Factor" in consistent_summary.index, (
        "No dedicated Evidence_Consistency_Factor exists in the "
        "authoritative plant-level output today -- confirmed gap."
    )
    assert (
        consistent_summary["Evidence_Consistency_Factor"]
        > conflicting_summary["Evidence_Consistency_Factor"]
    )


def test_desired_mixed_only_evidence_pool_scores_lower_than_clean_positive_through_real_pipeline():
    """NEW (per second supervisory review, correction #3). The addendum
    has proven, by direct execution, that a single explicitly mixed/
    inconsistent RCT currently receives the SAME Overall_Score as a
    clean positive RCT (both 65.7) -- addendum §1.1 point 3. This test
    exercises the real authoritative pipeline, not only the internal
    'explain' diagnostic contribution (test 5 above), and requires the
    dedicated Scientific_Evidence_Score output.

    THIS MUST FAIL TODAY, and does both ways:
    - Scientific_Evidence_Score does not exist yet (column-presence check).
    - Overall_Score itself does not currently distinguish a mixed-only
      pool from a clean positive RCT (both 65.7, confirmed by execution).
    """
    mixed_summary, _ = run_authoritative([plant_row(MIXED_RCT, rec_id="REC-MIXED-ONLY")])
    positive_summary, _ = run_authoritative([plant_row(POSITIVE_RCT, rec_id="REC-CLEAN-POS")])
    assert mixed_summary is not None and positive_summary is not None

    assert "Scientific_Evidence_Score" in mixed_summary.index, (
        "No dedicated Scientific_Evidence_Score exists in the "
        "authoritative plant-level output today -- confirmed gap."
    )
    assert mixed_summary["Scientific_Evidence_Score"] < positive_summary["Scientific_Evidence_Score"]

    assert mixed_summary["Overall_Score"] < positive_summary["Overall_Score"], (
        "CONFIRMED DEFECT (addendum §1.1 point 3): a mixed-only evidence "
        f"pool currently scores Overall_Score={mixed_summary['Overall_Score']}, "
        "IDENTICAL to a clean positive RCT "
        f"({positive_summary['Overall_Score']}) -- _indication_relevance_"
        "detail_authoritative()'s outcome discount only fires for "
        "positive+null/harmful/mixed or positive==0-with-null/harmful "
        "pools; a pool that is ONLY 'mixed' (no positive, no null, no "
        "harmful counted) falls through to the full, undiscounted "
        "'High relevance' branch."
    )


def test_desired_one_positive_rct_plus_three_negative_rcts_cannot_produce_strong_positive_consistency():
    """7. FURTHER STRENGTHENED per third supervisory review: renamed to
    'Evidence_Consistency_Factor' (never '..._Score') and now asserts the
    EXACT provisional contract given for this precise scenario (addendum
    §1.5 worked example): 1 positive + 3 null human RCTs ->
    Evidence_Consistency_Class=MOSTLY_NULL, Direction_Factor=0.00,
    Evidence_Consistency_Factor=0.85, Scientific_Evidence_Score=0.00
    (Direction_Factor=0.00 alone zeroes the multiplicative product,
    regardless of Evidence_Quality_Score's own magnitude).

    Asserts:
    (1) _outcome_profile() counts are as expected (positive=1, null=3) --
        ALREADY TRUE today, kept as a grounding sanity check.
    (2)-(5) The authoritative output for the 1-positive+3-null pool
        contains 'Evidence_Consistency_Class' == 'MOSTLY_NULL',
        'Direction_Factor' == 0.00, 'Evidence_Consistency_Factor' == 0.85,
        and 'Scientific_Evidence_Score' == 0.00.
    (6) The resulting 'Scientific_Evidence_Score' is lower than a
        consistently-positive comparator's (4 positive RCTs).

    THIS MUST FAIL TODAY (and does) -- none of Evidence_Consistency_Class/
    Direction_Factor/Evidence_Consistency_Factor/Scientific_Evidence_Score
    exist on the real authoritative output yet.
    """
    profile = cs._outcome_profile(group_df([
        evidence_row(source_record_id="REC-1", **POSITIVE_RCT),
        evidence_row(source_record_id="REC-2", **NEGATIVE_RCT),
        evidence_row(source_record_id="REC-3", **{**NEGATIVE_RCT, "clinical_rationale": "no effect on primary endpoint, no significant benefit"}),
        evidence_row(source_record_id="REC-4", **{**NEGATIVE_RCT, "clinical_rationale": "failed to improve outcome versus placebo"}),
    ]))
    assert profile["label"] != "Predominantly positive results"
    assert profile["positive"] == 1
    assert profile["null"] == 3

    mixed_pool_rows = [
        plant_row(POSITIVE_RCT, rec_id="REC-P1"),
        plant_row(NEGATIVE_RCT, rec_id="REC-N1"),
        plant_row({**NEGATIVE_RCT, "clinical_rationale": "no effect on primary endpoint, no significant benefit"}, rec_id="REC-N2"),
        plant_row({**NEGATIVE_RCT, "clinical_rationale": "failed to improve outcome versus placebo"}, rec_id="REC-N3"),
    ]
    consistent_positive_rows = [
        plant_row(POSITIVE_RCT, rec_id="REC-CP1"),
        plant_row({**POSITIVE_RCT, "clinical_rationale": "significant benefit confirmed, clear improvement"}, rec_id="REC-CP2"),
        plant_row({**POSITIVE_RCT, "clinical_rationale": "positive outcome replicated, meaningful improvement"}, rec_id="REC-CP3"),
        plant_row({**POSITIVE_RCT, "clinical_rationale": "consistent positive effect observed again"}, rec_id="REC-CP4"),
    ]
    mixed_pool_summary, _ = run_authoritative(mixed_pool_rows)
    consistent_positive_summary, _ = run_authoritative(consistent_positive_rows)
    assert mixed_pool_summary is not None and consistent_positive_summary is not None

    assert "Evidence_Consistency_Class" in mixed_pool_summary.index, (
        "No dedicated Evidence_Consistency_Class exists today -- confirmed gap."
    )
    assert mixed_pool_summary["Evidence_Consistency_Class"] == "MOSTLY_NULL"

    assert "Direction_Factor" in mixed_pool_summary.index
    assert mixed_pool_summary["Direction_Factor"] == 0.00

    assert "Evidence_Consistency_Factor" in mixed_pool_summary.index
    assert mixed_pool_summary["Evidence_Consistency_Factor"] == 0.85

    assert "Scientific_Evidence_Score" in mixed_pool_summary.index
    assert mixed_pool_summary["Scientific_Evidence_Score"] == 0.00
    assert (
        mixed_pool_summary["Scientific_Evidence_Score"]
        < consistent_positive_summary["Scientific_Evidence_Score"]
    )


def test_desired_several_weak_observational_studies_cannot_reverse_systematic_review_direction():
    """NEW per third supervisory review (correction #2). Refines the
    animal-vs-human proof above: several WEAKER HUMAN studies (Tier A3 --
    observational, not randomized/controlled) must not reverse or dilute
    the direction established by a single higher-tier RCT (Tier A2) row,
    just as animal (Tier B) evidence must not dilute human (Tier A1/A2/
    A3) evidence. This specifically targets the finer-grained precedence
    within human evidence itself (addendum §1.3 Step 2/3, corrected from
    a single flat 'Tier A' into A1/A2/A3).

    Constructs one clean positive RCT (A2) alone, versus that same RCT
    plus five NEGATIVE observational studies (A3, same species/plant,
    'observational cohort study' -- deliberately not randomized/
    controlled so row_hierarchy_points() classifies them as 'human', not
    'rct'). Asserts the authoritative Direction_Factor and
    Evidence_Consistency_Class are UNCHANGED by adding the five A3
    rows -- the single A2 (RCT) row alone should still establish primary
    direction, per tier precedence.

    THIS MUST FAIL TODAY (and does), because neither 'Direction_Factor'
    nor 'Evidence_Consistency_Class' exist on the real authoritative
    output yet -- confirmed absent by column check.
    """
    rct_alone_row = plant_row(POSITIVE_RCT, rec_id="REC-RCT-ALONE")
    rct_plus_weak_observational_rows = [plant_row(POSITIVE_RCT, rec_id="REC-RCT-WITH-OBS")] + [
        plant_row(
            {
                "clinical_rationale": "no significant improvement; no effect on primary endpoint",
                "result_direction": "negative",
                "has_negative_evidence": True,
            },
            rec_id=f"REC-OBS{i}",
            evidence_hierarchy_detail="observational cohort study",
        )
        for i in range(5)
    ]
    rct_alone_summary, _ = run_authoritative([rct_alone_row])
    rct_plus_observational_summary, _ = run_authoritative(rct_plus_weak_observational_rows)
    assert rct_alone_summary is not None and rct_plus_observational_summary is not None

    assert "Direction_Factor" in rct_alone_summary.index, (
        "No dedicated Direction_Factor exists in the authoritative "
        "plant-level output today -- confirmed gap."
    )
    assert "Evidence_Consistency_Class" in rct_alone_summary.index, (
        "No dedicated Evidence_Consistency_Class exists in the "
        "authoritative plant-level output today -- confirmed gap."
    )
    assert (
        rct_plus_observational_summary["Direction_Factor"]
        == rct_alone_summary["Direction_Factor"]
    ), (
        "Five weaker (A3, observational) negative studies should not "
        "change Direction_Factor when a single higher-tier (A2, RCT) "
        "positive row already establishes primary direction."
    )
    assert (
        rct_plus_observational_summary["Evidence_Consistency_Class"]
        == rct_alone_summary["Evidence_Consistency_Class"]
    )


def test_desired_multiple_animal_studies_cannot_outweigh_strong_negative_human_evidence():
    """8. CORRECTED per supervisory review: must compare the AUTHORITATIVE
    scientific-support contribution (Overall_Score, real plant-level
    pipeline), not only unsigned Evidence Quality. Compares:
    (a) one strong negative human RCT plus several positive animal
        studies, against
    (b) an otherwise comparable genuinely positive human evidence profile
        (a positive RCT alone).
    The lower-tier animal evidence must not reverse the direction
    established by strong human evidence -- i.e. (a)'s Overall_Score must
    NOT exceed (b)'s.

    THIS IS EXPECTED TO FAIL TODAY, and does: empirically,
    negative-RCT-alone scores Overall_Score=49.1; negative-RCT +
    6 positive animal studies scores Overall_Score=72.6 -- HIGHER than
    positive-RCT-alone (65.7). Six lower-tier positive findings
    numerically outvote one higher-tier negative finding in
    _indication_relevance_detail_authoritative()'s flat, tier-blind
    outcome pooling (it computes _outcome_profile() over the WHOLE group,
    human and animal rows together, with no tier precedence). This is
    the exact failure mode the required tier-aware aggregation design
    (addendum §1.4) exists to prevent -- confirmed here empirically
    against the real authoritative path, not assumed."""
    negative_rct_alone, _ = run_authoritative([plant_row(NEGATIVE_RCT, rec_id="REC-RCTNEG")])
    positive_rct_alone, _ = run_authoritative([plant_row(POSITIVE_RCT, rec_id="REC-RCTPOS")])
    animal_rows = [
        plant_row(
            dict(scientific_rationale="significant improvement observed in animal model", result_direction="positive"),
            rec_id=f"REC-A{i}", evidence_level="Preclinical / mechanistic evidence",
            evidence_hierarchy_detail="animal model in vivo study",
        )
        for i in range(6)
    ]
    negative_rct_plus_animals, _ = run_authoritative(
        [plant_row(NEGATIVE_RCT, rec_id="REC-RCTNEG2")] + animal_rows
    )
    assert negative_rct_alone is not None
    assert positive_rct_alone is not None
    assert negative_rct_plus_animals is not None

    assert negative_rct_plus_animals["Overall_Score"] <= positive_rct_alone["Overall_Score"], (
        "CONFIRMED DEFECT (addendum §1.1 point 2): several lower-tier "
        "positive animal studies currently push Overall_Score for a "
        "negative-human-RCT candidate ABOVE what a clean positive-RCT-"
        "alone candidate scores -- lower tiers are outvoting a higher, "
        "decision-relevant tier by flat count."
    )


def test_desired_several_low_quality_studies_show_diminishing_returns():
    """9. Several low-quality (e.g. in-vitro) studies should show
    diminishing, not linear, returns -- verified against the existing
    depth_points log2 term."""
    one = group_df([evidence_row(source_record_id="REC-0", evidence_level="Preclinical / mechanistic evidence",
                                  evidence_hierarchy_detail="in vitro cell study", scientific_rationale="effect observed")])
    many = group_df([
        evidence_row(source_record_id=f"REC-{i}", evidence_level="Preclinical / mechanistic evidence",
                     evidence_hierarchy_detail="in vitro cell study", scientific_rationale="effect observed")
        for i in range(8)
    ])
    total_one, _, _ = cs._evidence_quality(one, sources=["REC-0"], references=[])
    total_many, _, _ = cs._evidence_quality(many, sources=[f"REC-{i}" for i in range(8)], references=[])
    # 8x the studies must not produce anywhere near 8x the score.
    assert total_many < total_one * 4


# --- Duplicate / connector counting (10-14) --------------------------------

def test_desired_duplicate_article_does_not_change_score():
    """10. A duplicate article (identical Source_Record_IDs) must not
    change the score."""
    single = group_df([evidence_row(source_record_id="REC-X", **POSITIVE_RCT)])
    dup = group_df([
        evidence_row(source_record_id="REC-X", **POSITIVE_RCT),
        evidence_row(source_record_id="REC-X", **POSITIVE_RCT),
        evidence_row(source_record_id="REC-X", **POSITIVE_RCT),
    ])
    total_single, _, _ = cs._evidence_quality(single, sources=["REC-X"], references=[])
    total_dup, _, _ = cs._evidence_quality(dup, sources=["REC-X"] * 3, references=[])
    assert total_single == total_dup


def test_desired_same_article_from_multiple_connectors_counted_once():
    """11. The same article, ingested via multiple connectors (different
    Evidence_Source, same Source_Record_IDs), must be counted once."""
    via_connectors = group_df([
        evidence_row(source_record_id="REC-Y", evidence_source="PubMed", **POSITIVE_RCT),
        evidence_row(source_record_id="REC-Y", evidence_source="EuropePMC", **POSITIVE_RCT),
    ])
    single = group_df([evidence_row(source_record_id="REC-Y", evidence_source="PubMed", **POSITIVE_RCT)])
    total_connectors, _, _ = cs._evidence_quality(via_connectors, sources=["REC-Y", "REC-Y"], references=[])
    total_single, _, _ = cs._evidence_quality(single, sources=["REC-Y"], references=[])
    assert total_connectors == total_single


# --- Missing / unknown data (12-14, 21) -------------------------------------

def test_desired_unknown_data_receives_no_positive_default_reward():
    """12. THIS IS EXPECTED TO FAIL TODAY (confirmed defect, main audit
    §3.1). 'Unknown' market status must not receive a positive default
    reward greater than a verified positive market finding."""
    engine = make_engine()
    base = dict(
        same_plant=False, matched_compound="X", reference_compound="X",
        match_quality="exact", concentration=None, extraction=None,
        dosage_form=None, co_compounds="", safety_flags="", interaction_flags="",
        novelty_status="Other", target=None, evidence="",
        evidence_level="No direct evidence", compound_plant_count=0,
    )
    _, comp_unknown = engine._score_candidate(market_status="Unknown", **base)
    _, comp_verified = engine._score_candidate(market_status="Verified marketed product", **base)
    assert comp_unknown["Market signal"] <= comp_verified["Market signal"], (
        "CONFIRMED DEFECT (main audit §3.1): 'Unknown' market status "
        "(market_neutral_default=+3) currently scores HIGHER than "
        "'Verified marketed product' (+1)."
    )


def test_desired_search_not_performed_receives_no_positive_default_reward():
    """13. THIS IS EXPECTED TO FAIL TODAY, same defect as test 12,
    different label."""
    engine = make_engine()
    base = dict(
        same_plant=False, matched_compound="X", reference_compound="X",
        match_quality="exact", concentration=None, extraction=None,
        dosage_form=None, co_compounds="", safety_flags="", interaction_flags="",
        novelty_status="Other", target=None, evidence="",
        evidence_level="No direct evidence", compound_plant_count=0,
    )
    _, comp_not_performed = engine._score_candidate(market_status="Search not performed", **base)
    _, comp_verified = engine._score_candidate(market_status="Verified marketed product", **base)
    assert comp_not_performed["Market signal"] <= comp_verified["Market signal"]


def test_desired_source_unavailable_receives_no_positive_default_reward():
    """14. THIS IS EXPECTED TO FAIL TODAY, same defect as tests 12-13."""
    engine = make_engine()
    base = dict(
        same_plant=False, matched_compound="X", reference_compound="X",
        match_quality="exact", concentration=None, extraction=None,
        dosage_form=None, co_compounds="", safety_flags="", interaction_flags="",
        novelty_status="Other", target=None, evidence="",
        evidence_level="No direct evidence", compound_plant_count=0,
    )
    _, comp_unavailable = engine._score_candidate(market_status="Source unavailable", **base)
    _, comp_verified = engine._score_candidate(market_status="Verified marketed product", **base)
    assert comp_unavailable["Market signal"] <= comp_verified["Market signal"]


# --- Applicability (15-21) --------------------------------------------------
#
# FINAL contract per third supervisory review (correction round 4):
# applicability is a comparison between an EVIDENCE-side attribute and a
# TARGET-PRODUCT/session-side attribute -- never a judgment on an
# isolated value (addendum §3, evidence-vs-target table). "leaf" is not
# inherently more applicable than "root"; it is only a MATCH when the
# target product also specifies "leaf". Every test below constructs an
# explicit target_context alongside the evidence row and calls the
# FUTURE standard_evidence_builder.evaluate_applicability() contract
# defensively (via getattr, never a top-level import) so that a missing
# function fails the test body at runtime -- not at collection/import
# time -- per the corrected test contract.

import standard_evidence_builder as seb


def _call_future_evaluate_applicability(evidence_row, target_context):
    """Calls the FUTURE, NOT-YET-IMPLEMENTED
    standard_evidence_builder.evaluate_applicability(evidence_row,
    target_context) contract (addendum §3 FINAL: evidence-vs-target-
    context comparison). Uses getattr() defensively so a missing function
    never breaks test COLLECTION -- only this call, at test RUN time,
    fails with a clear assertion message. No production logic is
    reimplemented here; this only looks up and invokes the real function
    if and when it exists."""
    fn = getattr(seb, "evaluate_applicability", None)
    assert fn is not None, (
        "standard_evidence_builder.evaluate_applicability(evidence_row, "
        "target_context) does not exist yet -- confirmed gap, addendum "
        "§3 FINAL contract (not implemented in this pass)."
    )
    return fn(evidence_row, target_context)


def test_desired_different_plant_part_reduces_applicability():
    """16. FURTHER CORRECTED per third supervisory review (correction
    round 4, item 2): 'leaf' vs 'root' is not a match/mismatch judgment
    on its own -- it only means something relative to an explicit
    Target_Plant_Part. Uses the same target context for both evidence
    rows, varying only the evidence-side attribute.

    THIS MUST FAIL TODAY (and does), because evaluate_applicability()
    does not exist yet -- confirmed via getattr, not assumed."""
    target = {"Target_Plant_Part": "leaf"}
    evidence_match = {"Evidence_Plant_Part": "leaf"}
    evidence_mismatch = {"Evidence_Plant_Part": "root"}

    result_match = _call_future_evaluate_applicability(evidence_match, target)
    result_mismatch = _call_future_evaluate_applicability(evidence_mismatch, target)

    assert result_match["Dimension_Status"]["plant_part"] == "MATCH"
    assert result_mismatch["Dimension_Status"]["plant_part"] == "MISMATCH"
    assert result_mismatch["Applicability_Factor"] < result_match["Applicability_Factor"]


def test_desired_different_preparation_reduces_applicability():
    """17. FURTHER CORRECTED per third supervisory review (correction
    round 4, item 5): the target preparation must be given explicitly,
    not inferred from whichever evidence value happens to appear in the
    row.

    THIS MUST FAIL TODAY (and does), because evaluate_applicability()
    does not exist yet -- confirmed via getattr, not assumed."""
    target = {"Target_Preparation": "aqueous infusion"}
    evidence_match = {"Evidence_Preparation": "aqueous infusion"}
    evidence_mismatch = {"Evidence_Preparation": "essential oil"}

    result_match = _call_future_evaluate_applicability(evidence_match, target)
    result_mismatch = _call_future_evaluate_applicability(evidence_mismatch, target)

    assert result_match["Dimension_Status"]["preparation"] == "MATCH"
    assert result_mismatch["Dimension_Status"]["preparation"] == "MISMATCH"
    assert result_mismatch["Applicability_Factor"] < result_match["Applicability_Factor"]


def test_desired_different_route_reduces_applicability():
    """18. FURTHER CORRECTED per third supervisory review (correction
    round 4, item 3): oral is not inherently preferable to topical -- the
    test asserts only that the route that MATCHES the explicit
    Target_Route scores higher applicability than the one that does not,
    never that either route is universally better.

    THIS MUST FAIL TODAY (and does), because evaluate_applicability()
    does not exist yet -- confirmed via getattr, not assumed."""
    target = {"Target_Route": "oral"}
    evidence_match = {"Evidence_Route": "oral"}
    evidence_mismatch = {"Evidence_Route": "topical"}

    result_match = _call_future_evaluate_applicability(evidence_match, target)
    result_mismatch = _call_future_evaluate_applicability(evidence_mismatch, target)

    assert result_match["Dimension_Status"]["route"] == "MATCH"
    assert result_mismatch["Dimension_Status"]["route"] == "MISMATCH"
    assert result_mismatch["Applicability_Factor"] < result_match["Applicability_Factor"]


def test_desired_large_dose_mismatch_reduces_applicability():
    """20. FURTHER CORRECTED per third supervisory review (correction
    round 4, item 4): dose applicability requires an explicit target
    dose RANGE and comparable, matching units -- not a bare number. No
    unit conversion, pharmacokinetic equivalence, or clinical dose
    validation is implemented or assumed here; both evidence and target
    use the same unit ('mg/day') so the comparison is a plain normalized-
    range check.

    THIS MUST FAIL TODAY (and does), because evaluate_applicability()
    does not exist yet -- confirmed via getattr, not assumed."""
    target = {
        "Target_Dose_Min": 250,
        "Target_Dose_Max": 350,
        "Target_Dose_Unit": "mg/day",
    }
    evidence_match = {"Evidence_Dose": 300, "Evidence_Dose_Unit": "mg/day"}
    evidence_mismatch = {"Evidence_Dose": 3000, "Evidence_Dose_Unit": "mg/day"}

    result_match = _call_future_evaluate_applicability(evidence_match, target)
    result_mismatch = _call_future_evaluate_applicability(evidence_mismatch, target)

    assert result_match["Dimension_Status"]["dose"] == "MATCH"
    assert result_mismatch["Dimension_Status"]["dose"] == "MISMATCH"
    assert result_mismatch["Applicability_Factor"] < result_match["Applicability_Factor"]


def test_desired_dose_with_incompatible_or_missing_units_is_unknown_not_invented():
    """NEW per third supervisory review (correction round 4, item 4):
    unknown or incompatible units must yield UNKNOWN, never an invented
    MATCH or MISMATCH -- e.g. an evidence dose reported in a unit that
    cannot be compared to the target's unit (or missing a unit
    altogether) must not be silently treated as a numeric match/mismatch.

    THIS MUST FAIL TODAY (and does), because evaluate_applicability()
    does not exist yet -- confirmed via getattr, not assumed."""
    target = {
        "Target_Dose_Min": 250,
        "Target_Dose_Max": 350,
        "Target_Dose_Unit": "mg/day",
    }
    evidence_incompatible_unit = {"Evidence_Dose": 300, "Evidence_Dose_Unit": "IU/day"}
    evidence_missing_unit = {"Evidence_Dose": 300}

    result_incompatible = _call_future_evaluate_applicability(evidence_incompatible_unit, target)
    result_missing = _call_future_evaluate_applicability(evidence_missing_unit, target)

    assert result_incompatible["Dimension_Status"]["dose"] == "UNKNOWN"
    assert result_missing["Dimension_Status"]["dose"] == "UNKNOWN"


def test_desired_different_indication_is_not_treated_as_direct_evidence():
    """19. IMPLEMENTED dimension (indication IS tracked, per
    Target_Indication/Detected_Indications -- addendum §3.1). A row whose
    evidence concerns a different indication than requested must not be
    treated as direct, candidate-specific evidence."""
    off_target_row = evidence_row(
        source_record_id="REC-OFF",
        evidence_level="Clinical / human evidence",
        clinical_rationale="significant improvement in an unrelated indication never requested here",
        indication_match_type="not_relevant",
    )
    match_type, terms = cs._row_authoritative_relevance(pd.Series(off_target_row))
    assert match_type == "not_relevant"


def test_desired_missing_applicability_information_does_not_receive_full_applicability():
    """21. FURTHER CORRECTED per second supervisory review (correction #5):
    the previous version asserted the WRONG ordering (Unknown <=
    Mismatch), which is not the scientifically correct requirement --
    not having checked applicability is genuinely better than having
    checked and found a real problem. The correct ordering is
    Compatible > Unknown > Mismatch, exercised through the real
    plant-level path.

    Asserts:
    (1) Unknown receives less credit than Compatible (Scientific_Triage_
        Score) -- ALREADY TRUE today.
    (2) Confirmed mismatch receives the strongest penalty (forced
        Excluded status, capped score, lower than Unknown) -- ALREADY
        TRUE today.
    (3) The full ordering Compatible > Unknown > Mismatch holds --
        ALREADY TRUE today (kept as a grounding sanity check, not the
        gap this test targets).
    (4) Unknown is marked incomplete/preliminary via a dedicated
        'Applicability_Data_Completeness' field when applicability
        information is materially missing -- DOES NOT EXIST TODAY.

    THIS MUST FAIL TODAY on assertion (4) specifically -- confirmed
    absent by column check on the real authoritative output. Assertions
    (1)-(3) are retained as characterization facts (the current ordering
    is correct) so a future implementation cannot silently break it while
    adding the new completeness marker.
    """
    compatible_row = plant_row(POSITIVE_RCT, rec_id="REC-COMPAT", extraction_method="infusion")
    unknown_row = plant_row(POSITIVE_RCT, rec_id="REC-UNK", extraction_method="", applicability_summary="")
    mismatch_row = plant_row(
        POSITIVE_RCT, rec_id="REC-MIS", extraction_method="",
        applicability_summary='{"critical_mismatches": ["dosage form mismatch"]}',
    )
    compatible_summary, _ = run_authoritative([compatible_row], dosage_form="infusion")
    unknown_summary, _ = run_authoritative([unknown_row], dosage_form="infusion")
    mismatch_summary, _ = run_authoritative([mismatch_row], dosage_form="infusion")
    assert compatible_summary is not None and unknown_summary is not None and mismatch_summary is not None

    assert unknown_summary["Scientific_Triage_Score"] < compatible_summary["Scientific_Triage_Score"], (
        "Unknown should receive less credit than a confirmed Compatible match."
    )
    assert mismatch_summary["Scientific_Triage_Status"] == "Excluded", (
        "A confirmed mismatch should receive the strongest penalty (exclusion)."
    )
    assert (
        compatible_summary["Scientific_Triage_Score"]
        > unknown_summary["Scientific_Triage_Score"]
        > mismatch_summary["Scientific_Triage_Score"]
    ), "Expected ordering Compatible > Unknown > Mismatch (already correct today)."

    assert "Applicability_Data_Completeness" in unknown_summary.index, (
        "No dedicated completeness marker exists on the authoritative "
        "output today -- confirmed gap, addendum §1.4: an 'Unknown' "
        "applicability state should be explicitly marked incomplete/"
        "preliminary so a reviewer can distinguish 'confirmed compatible' "
        "from 'never checked' without reading raw applicability text."
    )
    assert unknown_summary["Applicability_Data_Completeness"] in {"incomplete", "preliminary"}


def test_desired_different_plant_species_reduces_applicability():
    """15. FURTHER CORRECTED per fifth supervisory review (correction
    round 6, item 3): the previous authoritative-pipeline fixture used
    two rows that differed only by rec_id -- no actual Species
    information at all, so it was not a valid integration test. Rewritten
    with explicit Evidence_Species fields on the rows and an explicit
    target_context passed through run_authoritative(), per addendum §3.8.

    Asserts:
    (1) Evidence_Quality_Score is EQUAL for otherwise-identical same-
        species vs different-species evidence records -- ALREADY TRUE
        today (grounding characterization fact).
    (2) The future evaluate_applicability() contract classifies a
        Target_Species match as MATCH and a mismatch as MISMATCH, with
        the mismatch's Applicability_Factor lower than the match's.
    (3) Through the REAL authoritative plant-level pipeline, given
        rows that explicitly carry Evidence_Species and an explicit
        target_context, the mismatch candidate's Scientific_Evidence_Score
        is lower than the match candidate's.

    THIS MUST FAIL TODAY on (2) and (3) -- evaluate_applicability(),
    target_context wiring, and Scientific_Evidence_Score do not exist
    yet."""
    same_species_row = evidence_row(source_record_id="REC-SAME", **POSITIVE_RCT)
    same_species_row["Scientific_Name"] = "Plantus testus"

    different_species_row = evidence_row(source_record_id="REC-DIFF", **POSITIVE_RCT)
    different_species_row["Scientific_Name"] = "Totally Different Species L."

    same_species_total, _, _ = cs._evidence_quality(
        group_df([same_species_row]), sources=["REC-SAME"], references=[],
    )
    different_species_total, _, _ = cs._evidence_quality(
        group_df([different_species_row]), sources=["REC-DIFF"], references=[],
    )
    assert different_species_total == same_species_total, (
        "Evidence_Quality_Score must remain unsigned and independent of "
        "applicability -- species mismatch must not change it. Already "
        "true today; species mismatch belongs in Applicability_Factor "
        "instead (addendum §3.4/§1.5)."
    )

    target = {"Target_Species": "Plantus testus"}
    evidence_match = {"Evidence_Species": "Plantus testus"}
    evidence_mismatch = {"Evidence_Species": "Totally Different Species L."}

    result_match = _call_future_evaluate_applicability(evidence_match, target)
    result_mismatch = _call_future_evaluate_applicability(evidence_mismatch, target)

    assert result_match["Dimension_Status"]["species"] == "MATCH"
    assert result_mismatch["Dimension_Status"]["species"] == "MISMATCH"
    assert result_mismatch["Applicability_Factor"] < result_match["Applicability_Factor"]

    target_context = {"Target_Species": "Plantus testus"}

    species_match_row = plant_row(POSITIVE_RCT, rec_id="REC-SPECIES-MATCH")
    species_match_row["Evidence_Species"] = "Plantus testus"

    species_mismatch_row = plant_row(POSITIVE_RCT, rec_id="REC-SPECIES-MISMATCH")
    species_mismatch_row["Evidence_Species"] = "Totally Different Species L."

    species_match_summary, _ = run_authoritative([species_match_row], target_context=target_context)
    species_mismatch_summary, _ = run_authoritative([species_mismatch_row], target_context=target_context)
    assert species_match_summary is not None and species_mismatch_summary is not None
    assert "Scientific_Evidence_Score" in species_match_summary.index, (
        "No dedicated Scientific_Evidence_Score exists in the "
        "authoritative plant-level output today -- confirmed gap."
    )
    assert (
        species_mismatch_summary["Scientific_Evidence_Score"]
        < species_match_summary["Scientific_Evidence_Score"]
    )


def test_desired_applicability_factor_is_actually_consumed_by_authoritative_scoring():
    """NEW/FURTHER CORRECTED per fifth supervisory review (correction
    round 6, item 4): the previous version used only the legacy
    Extraction_Method/dosage_form combination as proof -- not a full
    exercise of the new evidence-vs-target contract. Rewritten so every
    candidate carries explicit Evidence_* attributes, evaluated against
    the SAME explicit target_context, passed through run_authoritative().

    For four otherwise-identical positive-RCT candidates (confirmed
    match / partial / unknown / confirmed mismatch applicability on the
    Preparation dimension specifically), asserts the real authoritative
    output contains 'Dimension_Status', 'Applicability_Classification',
    'Applicability_Factor', 'Applicability_Data_Completeness', and
    'Scientific_Evidence_Score', and that:

        match > partial > unknown > mismatch   (Scientific_Evidence_Score)

    except where an existing approved mismatch gate excludes the
    candidate entirely (dosage_summary=='Mismatch' -> plant_status=
    'Excluded', already-approved behavior, addendum §3.2) -- in that
    case this test asserts exclusion instead of a published positive
    score, per your explicit instruction.

    Also asserts Score_Breakdown's evidence-contribution key is
    'Scientific Evidence', REPLACING the old raw 'Evidence Quality'
    key, per the approved architecture (addendum §1.5).

    THIS MUST FAIL TODAY (and does) -- none of these fields/behaviors
    exist on the real authoritative output yet."""
    target_context = {
        "Target_Species": "Plantus testus",
        "Target_Plant_Part": "leaf",
        "Target_Preparation": "aqueous infusion",
        "Target_Preparation_Category": "aqueous",
        "Target_Route": "oral",
        "Target_Dose_Min": 250, "Target_Dose_Max": 350, "Target_Dose_Unit": "mg/day",
        "Target_Indication": INDICATION,
    }

    def _row_with_evidence(rec_id, **evidence_fields):
        row = plant_row(POSITIVE_RCT, rec_id=rec_id)
        row.update(evidence_fields)
        return row

    match_row = _row_with_evidence(
        "REC-APPL-MATCH",
        Evidence_Species="Plantus testus", Evidence_Plant_Part="leaf",
        Evidence_Preparation="aqueous infusion", Evidence_Preparation_Category="aqueous",
        Evidence_Route="oral", Evidence_Dose=300, Evidence_Dose_Unit="mg/day",
    )
    partial_row = _row_with_evidence(
        "REC-APPL-PARTIAL",
        Evidence_Species="Plantus testus", Evidence_Plant_Part="leaf",
        Evidence_Preparation="decoction", Evidence_Preparation_Category="aqueous",  # same parent category -> PARTIAL
        Evidence_Route="oral", Evidence_Dose=300, Evidence_Dose_Unit="mg/day",
    )
    unknown_row = _row_with_evidence(
        "REC-APPL-UNKNOWN",
        Evidence_Species="Plantus testus", Evidence_Plant_Part="leaf",
        # Evidence_Preparation / Evidence_Preparation_Category deliberately omitted -> UNKNOWN
        Evidence_Route="oral", Evidence_Dose=300, Evidence_Dose_Unit="mg/day",
    )
    mismatch_row = _row_with_evidence(
        "REC-APPL-MISMATCH",
        Evidence_Species="Plantus testus", Evidence_Plant_Part="leaf",
        Evidence_Preparation="essential oil", Evidence_Preparation_Category="essential_oil",  # different parent category -> MISMATCH
        Evidence_Route="oral", Evidence_Dose=300, Evidence_Dose_Unit="mg/day",
        applicability_summary='{"critical_mismatches": ["dosage form mismatch"]}',
    )

    match_summary, _ = run_authoritative([match_row], dosage_form="infusion", target_context=target_context)
    partial_summary, _ = run_authoritative([partial_row], dosage_form="infusion", target_context=target_context)
    unknown_summary, _ = run_authoritative([unknown_row], dosage_form="infusion", target_context=target_context)
    mismatch_summary, _ = run_authoritative([mismatch_row], dosage_form="infusion", target_context=target_context)
    assert all(s is not None for s in (match_summary, partial_summary, unknown_summary, mismatch_summary))

    for label, summary in [
        ("match", match_summary), ("partial", partial_summary), ("unknown", unknown_summary),
    ]:
        for field in (
            "Dimension_Status", "Applicability_Classification", "Applicability_Factor",
            "Applicability_Data_Completeness", "Scientific_Evidence_Score",
        ):
            assert field in summary.index, (
                f"No dedicated {field} exists on the authoritative output "
                f"today (checked on the '{label}' candidate) -- confirmed gap."
            )

    if mismatch_summary["Scientific_Triage_Status"] == "Excluded":
        # Existing, already-approved mismatch gate: assert exclusion
        # rather than requiring a published positive score.
        pass
    else:
        assert "Scientific_Evidence_Score" in mismatch_summary.index
        assert (
            match_summary["Scientific_Evidence_Score"]
            > partial_summary["Scientific_Evidence_Score"]
            > unknown_summary["Scientific_Evidence_Score"]
            > mismatch_summary["Scientific_Evidence_Score"]
        )

    assert "Scientific Evidence" in match_summary["Score_Breakdown"], (
        "Score_Breakdown should use 'Scientific Evidence' (backed by "
        "Scientific_Evidence_Score) as the evidence contribution, "
        "replacing the old raw 'Evidence Quality' key -- confirmed gap: "
        f"actual keys today are {list(match_summary['Score_Breakdown'].keys()) if 'Score_Breakdown' in match_summary.index else 'N/A'}."
    )


def test_desired_multi_dimensional_applicability_aggregation_is_deterministic():
    """NEW/FURTHER CORRECTED per fifth supervisory review (correction
    round 6, item 6): the previous version used an undocumented
    assumption ("hydroalcoholic tincture" vs. "aqueous infusion" =
    PARTIAL) with no explicit parent-category field backing it. Replaced
    with the explicit same-parent-category scenario your correction
    specified: Evidence_Preparation_Category="aqueous" matches
    Target_Preparation_Category="aqueous" even though the specific
    preparations differ (decoction vs. infusion) -- PARTIAL per the
    deterministic rule (addendum §3.4), never inferred from free-text
    similarity between "decoction" and "infusion" themselves.

    Proves the deterministic multi-dimensional aggregation rule
    (addendum §3.5/§3.6: worst-evaluable-dimension-wins via min(), and
    MISMATCH > UNKNOWN > PARTIAL > MATCH > NOT_APPLICABLE classification
    precedence) against the real future contract -- not a duplicated
    reimplementation.

    Scenario 1: species=MATCH, plant_part=MATCH, preparation=PARTIAL
    (same explicit parent category, different specific preparation),
    route=MATCH, dose=UNKNOWN, indication=MATCH.
    Expected: Applicability_Classification=UNKNOWN,
    Applicability_Factor=0.60, Applicability_Data_Completeness=incomplete
    (UNKNOWN is present, so it dominates over the single PARTIAL).

    Scenario 2: same, but dose changed from UNKNOWN to MATCH.
    Expected: Applicability_Classification=PARTIAL,
    Applicability_Factor=0.80, Applicability_Data_Completeness=complete
    (no UNKNOWN remains; PARTIAL is now the worst present dimension).

    THIS MUST FAIL TODAY (and does) -- evaluate_applicability() does not
    exist yet."""
    target_with_unknown_dose = {
        "Target_Species": "Plantus testus",
        "Target_Plant_Part": "leaf",
        "Target_Preparation": "infusion",
        "Target_Preparation_Category": "aqueous",
        "Target_Route": "oral",
        "Target_Dose_Min": 250, "Target_Dose_Max": 350, "Target_Dose_Unit": "mg/day",
        "Target_Indication": INDICATION,
    }
    evidence_with_unknown_dose = {
        "Evidence_Species": "Plantus testus",
        "Evidence_Plant_Part": "leaf",
        "Evidence_Preparation": "decoction",
        "Evidence_Preparation_Category": "aqueous",  # same explicit parent category -> PARTIAL
        "Evidence_Route": "oral",
        # Evidence_Dose / Evidence_Dose_Unit deliberately omitted -> UNKNOWN
        "Indication_Match_Type": MATCH_EXACT_INDICATION,
        "Indication_Match_Terms": INDICATION,
    }
    result_with_unknown_dose = _call_future_evaluate_applicability(evidence_with_unknown_dose, target_with_unknown_dose)
    assert result_with_unknown_dose["Dimension_Status"]["preparation"] == "PARTIAL"
    assert result_with_unknown_dose["Applicability_Classification"] == "UNKNOWN"
    assert result_with_unknown_dose["Applicability_Factor"] == 0.60
    assert result_with_unknown_dose["Applicability_Data_Completeness"] == "incomplete"

    evidence_with_matched_dose = dict(evidence_with_unknown_dose)
    evidence_with_matched_dose["Evidence_Dose"] = 300
    evidence_with_matched_dose["Evidence_Dose_Unit"] = "mg/day"
    result_with_matched_dose = _call_future_evaluate_applicability(evidence_with_matched_dose, target_with_unknown_dose)
    assert result_with_matched_dose["Dimension_Status"]["preparation"] == "PARTIAL"
    assert result_with_matched_dose["Applicability_Classification"] == "PARTIAL"
    assert result_with_matched_dose["Applicability_Factor"] == 0.80
    assert result_with_matched_dose["Applicability_Data_Completeness"] == "complete"


def test_desired_partial_preparation_requires_explicit_matching_parent_category_not_free_text():
    """NEW per fifth supervisory review (correction round 6, item 5):
    locks in that PARTIAL is never inferred from free-text similarity.
    'tincture' and 'infusion' are both botanical preparations, but
    without an explicit, matching Evidence_Preparation_Category vs.
    Target_Preparation_Category, the comparison must be UNKNOWN (no
    category supplied on the evidence side) or MISMATCH (categories
    supplied and differ) -- never a PARTIAL inferred from domain
    knowledge about what "tincture" and "infusion" have in common.

    THIS MUST FAIL TODAY (and does) -- evaluate_applicability() does not
    exist yet."""
    target = {"Target_Preparation": "infusion", "Target_Preparation_Category": "aqueous"}

    # No category supplied on the evidence side at all -> UNKNOWN, not PARTIAL.
    evidence_no_category = {"Evidence_Preparation": "tincture"}
    result_no_category = _call_future_evaluate_applicability(evidence_no_category, target)
    assert result_no_category["Dimension_Status"]["preparation"] == "UNKNOWN"

    # Explicit, differing categories -> MISMATCH, not PARTIAL, even though
    # "tincture" and "infusion" are both botanical preparations.
    evidence_different_category = {
        "Evidence_Preparation": "tincture",
        "Evidence_Preparation_Category": "hydroalcoholic",
    }
    result_different_category = _call_future_evaluate_applicability(evidence_different_category, target)
    assert result_different_category["Dimension_Status"]["preparation"] == "MISMATCH"


def test_desired_record_to_plant_applicability_aggregation_is_quality_weighted_mean():
    """NEW per fifth supervisory review (correction round 6, item 7).
    Proves Plant_Applicability_Factor (addendum §3.7) -- the aggregate
    that actually enters Scientific_Evidence_Score -- is a quality-
    weighted mean of Record_Applicability_Factor across the primary
    tier's de-duplicated records, NOT the same thing as a single
    record's own factor.

    Two de-duplicated, equal-quality primary-tier records with
    Record_Applicability_Factor 1.00 and 0.60 respectively, equal
    record_quality_weight: expected Plant_Applicability_Factor = 0.80
    (the simple mean, since weights are equal). Adding a duplicate of
    either record must NOT change this result -- the existing
    deduplication (already approved, main audit §3.4) removes it before
    the weighted mean is computed.

    THIS MUST FAIL TODAY (and does) -- Plant_Applicability_Factor does
    not exist on the authoritative output yet."""
    target_context = {
        "Target_Species": "Plantus testus",
        "Target_Preparation": "infusion", "Target_Preparation_Category": "aqueous",
        "Target_Indication": INDICATION,
    }
    record_high_applicability = plant_row(POSITIVE_RCT, rec_id="REC-PLANT-APPL-HIGH")
    record_high_applicability["Evidence_Species"] = "Plantus testus"
    record_high_applicability["Evidence_Preparation"] = "infusion"
    record_high_applicability["Evidence_Preparation_Category"] = "aqueous"

    record_low_applicability = plant_row(POSITIVE_RCT, rec_id="REC-PLANT-APPL-LOW")
    record_low_applicability["Evidence_Species"] = "Plantus testus"
    # Evidence_Preparation / Evidence_Preparation_Category deliberately
    # OMITTED: target_context DOES specify Target_Preparation/Category
    # (below), so this dimension is a real, requested comparison the
    # evidence side cannot answer -> UNKNOWN (0.60), per §3.4's
    # NOT_APPLICABLE-vs-UNKNOWN rule -- NOT a species mismatch. This
    # produces Record_Applicability_Factor = min(species=MATCH=1.00,
    # preparation=UNKNOWN=0.60, indication=MATCH=1.00) = 0.60, matching
    # this test's stated "1.00 and 0.60" scenario exactly (an earlier
    # version of this fixture incorrectly used a species MISMATCH here,
    # which computes to 0.25, not 0.60 -- corrected after independent
    # review).

    two_record_summary, _ = run_authoritative(
        [record_high_applicability, record_low_applicability], target_context=target_context,
    )
    assert two_record_summary is not None
    assert "Plant_Applicability_Factor" in two_record_summary.index, (
        "No dedicated Plant_Applicability_Factor exists on the "
        "authoritative plant-level output today -- confirmed gap."
    )
    assert two_record_summary["Plant_Applicability_Factor"] == pytest.approx(0.80)

    duplicate_of_high = dict(record_high_applicability)
    three_record_summary, _ = run_authoritative(
        [record_high_applicability, record_low_applicability, duplicate_of_high],
        target_context=target_context,
    )
    assert three_record_summary is not None
    assert "Plant_Applicability_Factor" in three_record_summary.index
    assert three_record_summary["Plant_Applicability_Factor"] == pytest.approx(
        two_record_summary["Plant_Applicability_Factor"]
    ), (
        "A duplicate of an already-counted record must not change "
        "Plant_Applicability_Factor -- deduplication (§1.3 Step 1) must "
        "happen before the quality-weighted mean is computed."
    )


# --- Decision / gating (22-24) ---------------------------------------------

def test_desired_eligibility_no_go_overrides_a_high_opportunity_score():
    """22. A hard eligibility stop must override even a very high
    opportunity score. See addendum §5b: in production this status is
    EXPERT_REVIEW_REQUIRED, not literally NO_GO_SAFETY (scope is always
    UNKNOWN in the live pipeline) -- but both are hard,
    eligible_for_normal_ranking=False stops, and this test asserts the
    OUTCOME (never 'Strong'), not the specific status label."""
    engine = make_engine()
    decision = engine._decision_class(
        score=100.0,
        safety_flags="poison",
        interaction_flags="",
        has_evidence=True,
        match_quality="exact",
        evidence_level="Clinical / human evidence",
        same_plant=False,
        regulatory_barrier_types=None,
        has_evidence_text=True,
    )
    assert decision != "Strong R&D candidate"


def test_desired_incomplete_evidence_cannot_yield_a_validated_strong_decision():
    """23. Incomplete evidence (no evidence text existed) cannot yield a
    validated 'Strong' decision, even with a high raw score."""
    engine = make_engine()
    decision = engine._decision_class(
        score=95.0,
        safety_flags="",
        interaction_flags="",
        has_evidence=False,
        match_quality="exact",
        evidence_level="No direct evidence",
        same_plant=False,
        regulatory_barrier_types=None,
        has_evidence_text=False,
    )
    assert decision != "Strong R&D candidate"


def test_desired_decision_threshold_boundary_tests():
    """24. Score-tier boundaries behave as documented: 77.9 must not
    reach 'Strong', 78.0 must."""
    engine = make_engine()
    common_kwargs = dict(
        safety_flags="", interaction_flags="", has_evidence=True,
        match_quality="exact", evidence_level="Clinical / human evidence",
        same_plant=False, regulatory_barrier_types=None, has_evidence_text=True,
        compound_is_common=False, target_specificity=None,
    )
    below = engine._decision_class(score=77.9, **common_kwargs)
    at = engine._decision_class(score=78.0, **common_kwargs)
    assert below != "Strong R&D candidate"
    assert at == "Strong R&D candidate"


# --- Score integrity (25-27, 30) -------------------------------------------

def test_desired_score_breakdown_sums_to_final_score():
    """25. The row-level score breakdown returned by _score_candidate()
    must sum to the returned final score (within rounding)."""
    engine = make_engine()
    score, components = engine._score_candidate(
        same_plant=False, matched_compound="X", reference_compound="X",
        match_quality="exact", concentration="1mg", extraction="aqueous",
        dosage_form="infusion", co_compounds="B;C", safety_flags="",
        interaction_flags="", market_status="Verified marketed product",
        novelty_status="Alternative", target="COX-2", evidence="clinical trial",
        evidence_level="Clinical / human evidence", compound_plant_count=1,
    )
    assert math.isclose(sum(components.values()), score, abs_tol=0.2)


def test_desired_every_component_stays_within_its_declared_range():
    """26. Every _evidence_quality() component-derived total stays within
    its own documented cap (0-30)."""
    row = evidence_row(source_record_id="REC-CAP", **POSITIVE_RCT)
    total, tier, _ = cs._evidence_quality(group_df([row]), sources=["REC-CAP"], references=[])
    assert 0.0 <= total <= 30.0
    assert tier in {"None", "Weak", "Moderate", "Strong"}


def test_desired_scoring_model_version_is_present_in_authoritative_output():
    """27. THIS IS EXPECTED TO FAIL TODAY (addendum §6 item 5: no version
    stamp exists on any authoritative score today)."""
    raw_df = pd.DataFrame([{"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 10.0}])
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 50.0,
         "Evidence_Confidence": 40.0, "Decision_Class_AH": "C — Alternative-source R&D candidate",
         "Go_Investigate_Hold_NoGo": "Investigate", "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "ok"},
    ])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    assert "Scoring_Model_Version" in merged.columns, (
        "No Scoring_Model_Version column exists in merge_authoritative_"
        "scores()'s output today -- confirmed gap, addendum §6 item 5."
    )


def test_desired_a_small_evidence_change_near_a_threshold_is_documented_as_a_boundary_transition():
    """30. A small evidence change that crosses a score-tier boundary
    should be identifiable AS a boundary transition (i.e. the score
    components either side of 78 must differ by a small, explainable
    amount -- not an unexplained jump), not something else. Verified on
    _score_candidate()'s continuous modifiers directly (no hard internal
    cliffs inside the numeric formula itself; the only cliff is the
    tiering in _decision_class(), which is expected/by-design)."""
    engine = make_engine()
    base = dict(
        same_plant=False, matched_compound="X", reference_compound="X",
        match_quality="target_verified", concentration="1mg", extraction="aqueous",
        dosage_form="infusion", co_compounds="", safety_flags="", interaction_flags="",
        market_status="Regulatory monograph exists", novelty_status="Other",
        target="COX-2", evidence="clinical trial",
        evidence_level="Clinical / human evidence", compound_plant_count=1,
    )
    score_a, _ = engine._score_candidate(target_specificity=4, **base)
    score_b, _ = engine._score_candidate(target_specificity=5, **base)
    # A one-unit change in target_specificity (a small evidence change)
    # must not itself jump the raw score by more than a few points --
    # confirms _score_candidate() has no hidden cliff at this input.
    assert abs(score_a - score_b) < 5.0


# --- Duplicate raw rows / provenance (28-29) -------------------------------

def test_desired_duplicate_raw_rows_do_not_change_the_authoritative_plant_score():
    """28. Duplicate raw rows for the same plant (identical
    R&D_Opportunity_Score) must not change the authoritative plant-level
    Overall_Score -- merge_authoritative_scores() only ever picks ONE
    "richest" raw row per plant, regardless of how many duplicates exist."""
    raw_df_one = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 55.0, "Rationale": "r"},
    ])
    raw_df_many = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 55.0, "Rationale": "r"},
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 55.0, "Rationale": "r"},
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 55.0, "Rationale": "r"},
    ])
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 60.0,
         "Evidence_Confidence": 50.0, "Decision_Class_AH": "C — Alternative-source R&D candidate",
         "Go_Investigate_Hold_NoGo": "Investigate", "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "ok"},
    ])
    merged_one = cs.merge_authoritative_scores(raw_df_one, plant_summary)
    merged_many = cs.merge_authoritative_scores(raw_df_many, plant_summary)
    assert len(merged_one) == len(merged_many) == 1
    assert merged_one.loc[0, "Overall_Score"] == merged_many.loc[0, "Overall_Score"] == 60.0


def test_desired_narrative_gate_provenance_cannot_silently_mismatch_the_authoritative_selected_plant_result():
    """29. FURTHER CORRECTED per third supervisory review (correction #4):
    made deterministic. The prior version matched against the PLURAL
    'Authoritative_Source_Record_IDs' set alone -- ambiguous whenever
    more than one raw row's Source_Record_IDs intersects that set. Now
    uses the three-field contract (addendum §4, FINAL): the plural set
    names every contributing record, a separate SINGULAR
    'Authoritative_Narrative_Source_Record_ID' identifies the exact one
    record whose narrative fields should be used, and
    'Authoritative_Narrative_Provenance' explains the selection.

    The fixture provides THREE raw rows -- REC-WEAK, REC-STRONG, and
    REC-ALSO-CONTRIBUTING (the latter deliberately included so that
    'Authoritative_Source_Record_IDs' contains multiple entries and
    matching against the plural set alone would be genuinely ambiguous).
    'Authoritative_Source_Record_IDs' lists all three;
    'Authoritative_Narrative_Source_Record_ID' names exactly
    'REC-STRONG'. Asserts merge_authoritative_scores() selects narrative
    fields specifically from REC-STRONG's row, not merely any row whose
    ID happens to intersect the plural set.

    THIS MUST FAIL TODAY (and does): merge_authoritative_scores() reads
    neither field today (confirmed: both have zero effect on row
    selection), so it still selects REC-WEAK's narrative (raw
    R&D_Opportunity_Score=80.0, the highest of the three) even though the
    fixture explicitly designates REC-STRONG via the singular field.
    """
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 80.0,
         "Gate_Results": "weak-row-gates", "Source_Record_IDs": "REC-WEAK"},
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 20.0,
         "Gate_Results": "strong-row-gates", "Source_Record_IDs": "REC-STRONG"},
        {"Alternative_Plant": "Plantus testus", "R&D_Opportunity_Score": 50.0,
         "Gate_Results": "also-contributing-row-gates", "Source_Record_IDs": "REC-ALSO-CONTRIBUTING"},
    ])
    # The contract: the plural set names every contributing record (all
    # three here); the singular field is the ONLY deterministic selector
    # for which one row's narrative is used.
    plant_summary = pd.DataFrame([
        {"Alternative_Plant": "Plantus testus", "Overall_Score": 85.0,
         "Evidence_Confidence": 80.0, "Decision_Class_AH": "B — Established scientific candidate",
         "Go_Investigate_Hold_NoGo": "Go", "Scientific_Triage_Status": "Shortlist",
         "Why_Selected_or_Rejected": "strong evidence from REC-STRONG",
         "Authoritative_Source_Record_IDs": "REC-WEAK,REC-STRONG,REC-ALSO-CONTRIBUTING",
         "Authoritative_Narrative_Source_Record_ID": "REC-STRONG",
         "Authoritative_Narrative_Provenance": "selected: richest narrative among primary-tier records"},
    ])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)

    assert "Authoritative_Narrative_Provenance" in merged.columns, (
        "No Authoritative_Narrative_Provenance column exists in "
        "merge_authoritative_scores()'s output today -- confirmed gap, "
        "addendum §4 selected contract."
    )
    assert merged.loc[0, "Gate_Results"] == "strong-row-gates", (
        "CONFIRMED PROVENANCE DEFECT (addendum §4): merge_authoritative_"
        "scores() does not read the deterministic singular "
        "Authoritative_Narrative_Source_Record_ID field today -- it still "
        "selects narrative fields by raw, PRE-merge R&D_Opportunity_Score "
        "(REC-WEAK, 80.0), ignoring that the fixture explicitly "
        "designates REC-STRONG via the singular selector."
    )


# ---------------------------------------------------------------------------
# Post-implementation supervisory regressions: gaps not covered by the
# original 46-test contract but reproduced by independent execution.
# ---------------------------------------------------------------------------

def _diagnostic_only_animal_row(direction_kwargs, rec_id):
    """Lower-tier empirical evidence neutral for every non-scientific score component."""
    row = plant_row(
        direction_kwargs,
        rec_id=rec_id,
        evidence_level="Preclinical / mechanistic evidence",
        evidence_hierarchy_detail="animal model in vivo study",
        extraction_method="aqueous extract",
    )
    row.update({
        "Indication_Match_Type": MATCH_NO_MATCH,
        "Indication_Match_Terms": "",
        "Supported_Target_or_Mechanism": False,
        "Target_or_Mechanism": "",
        "Shared_or_Similar_Compound": "",
        "Novelty_Status": "",
        "Market_Status": "",
    })
    return row


def test_phase5_lower_tiers_are_score_inert_when_a_primary_tier_exists():
    """Lower-tier volume may change diagnostics, never the authoritative score."""
    primary = plant_row(POSITIVE_RCT, rec_id="REC-PRIMARY")
    supporting = [
        _diagnostic_only_animal_row(POSITIVE_ANIMAL, f"REC-ANIMAL-{i}")
        for i in range(6)
    ]

    primary_only, _ = run_authoritative([primary])
    with_supporting, _ = run_authoritative([primary, *supporting])

    assert primary_only is not None and with_supporting is not None
    for field in (
        "Evidence_Quality_Score",
        "Scientific_Evidence_Score",
        "Overall_Score",
        "Direction_Factor",
        "Evidence_Consistency_Class",
        "Plant_Applicability_Factor",
    ):
        assert with_supporting[field] == primary_only[field], field

    assert primary_only["Supporting_Evidence_Record_Count"] == 0
    assert with_supporting["Supporting_Evidence_Record_Count"] == 6
    assert with_supporting["Supporting_Evidence_Tiers_Present"] == ["B"]
    assert (
        with_supporting["All_Tier_Evidence_Quality_Diagnostic"]["Score"]
        > primary_only["All_Tier_Evidence_Quality_Diagnostic"]["Score"]
    )


def test_phase5_lower_tiers_cannot_change_a_primary_tier_go_decision():
    """Tier-B negative records cannot turn an A2 positive programme's Go into Investigate."""
    primary_rows = [
        plant_row(
            POSITIVE_RCT,
            rec_id=f"REC-RCT-{i}",
            extraction_method="aqueous extract",
        )
        for i in range(7)
    ]
    lower_negative = [
        _diagnostic_only_animal_row(NEGATIVE_RCT, f"REC-NEG-ANIMAL-{i}")
        for i in range(5)
    ]

    primary_only, _ = run_authoritative(primary_rows, dosage_form="aqueous extract")
    with_lower, _ = run_authoritative(
        [*primary_rows, *lower_negative], dosage_form="aqueous extract"
    )

    assert primary_only is not None and with_lower is not None
    assert primary_only["Go_Investigate_Hold_NoGo"] == "Go"
    assert with_lower["Go_Investigate_Hold_NoGo"] == "Go"
    assert with_lower["Overall_Score"] == primary_only["Overall_Score"]
    assert with_lower["Scientific_Evidence_Score"] == primary_only["Scientific_Evidence_Score"]
    assert with_lower["Primary_Tier_Outcome_Profile"] == primary_only["Primary_Tier_Outcome_Profile"]
    assert with_lower["Outcome_Consistency"] == primary_only["Outcome_Consistency"]
    assert (
        with_lower["All_Tier_Outcome_Consistency_Diagnostic"]
        != primary_only["All_Tier_Outcome_Consistency_Diagnostic"]
    )


def test_phase5_unreported_outcomes_remain_in_consistency_denominator():
    profile = {
        "positive": 2,
        "null": 0,
        "harmful": 0,
        "mixed": 0,
        "unreported": 8,
        "total": 10,
    }
    assert classify_evidence_consistency(profile) == "MIXED"


def test_phase5_consistency_distinguishes_no_records_from_unreported_records():
    assert classify_evidence_consistency({"total": 0}) == "INSUFFICIENT"
    assert classify_evidence_consistency({"unreported": 1, "total": 1}) == "MIXED"
    assert classify_evidence_consistency({"positive": 2, "total": 2}) == "CONSISTENT_POSITIVE"
    with pytest.raises(ValueError):
        classify_evidence_consistency({"positive": 2, "unreported": 1, "total": 2})


def test_phase5_component_provenance_includes_non_empirical_score_contributors():
    empirical = plant_row(POSITIVE_RCT, rec_id="REC-RCT")
    empirical.update({"Novelty_Status": "", "Safety_Flags": "", "Interaction_Flags": ""})

    market_only = plant_row(POSITIVE_RCT, rec_id="REC-MARKET")
    market_only.update({
        "Evidence_Level": "No direct evidence",
        "Evidence_Hierarchy_Detail": "",
        "Direct_Evidence_Present": False,
        "Supported_Target_or_Mechanism": False,
        "Target_or_Mechanism": "",
        "Shared_or_Similar_Compound": "",
        "Result_Direction": "",
        "Clinical_Rationale": "",
        "Scientific_Rationale": "",
        "Indication_Match_Type": MATCH_NO_MATCH,
        "Indication_Match_Terms": "",
        "Novelty_Status": "",
        "Market_Status": "limited products",
        "Safety_Flags": "",
        "Interaction_Flags": "",
        "Negative_Evidence_Types": "",
        "Regulatory_Barriers": "",
    })

    safety_only = plant_row(POSITIVE_RCT, rec_id="REC-SAFETY")
    safety_only.update({
        "Evidence_Level": "No direct evidence",
        "Evidence_Hierarchy_Detail": "",
        "Direct_Evidence_Present": False,
        "Supported_Target_or_Mechanism": False,
        "Target_or_Mechanism": "",
        "Shared_or_Similar_Compound": "",
        "Result_Direction": "",
        "Clinical_Rationale": "",
        "Scientific_Rationale": "",
        "Indication_Match_Type": MATCH_NO_MATCH,
        "Indication_Match_Terms": "",
        "Novelty_Status": "",
        "Market_Status": "",
        "Safety_Flags": "toxicity requires review",
        "Interaction_Flags": "",
        "Negative_Evidence_Types": "",
        "Regulatory_Barriers": "",
    })

    baseline, _ = run_authoritative([empirical])
    enriched, enriched_merged = run_authoritative([empirical, market_only, safety_only])
    assert baseline is not None and enriched is not None and enriched_merged is not None
    assert enriched["Novelty_Market_Score"] != baseline["Novelty_Market_Score"]
    assert enriched["Safety_Regulatory_Score"] != baseline["Safety_Regulatory_Score"]

    component_ids = enriched["Component_Source_Record_IDs"]
    assert "REC-MARKET" in component_ids["Novelty & Market"]
    assert "REC-MARKET" not in component_ids["Scientific Evidence"]
    assert "REC-SAFETY" in component_ids["Safety & Regulatory"]
    assert "REC-SAFETY" not in component_ids["Scientific Evidence"]
    assert {"REC-RCT", "REC-MARKET", "REC-SAFETY"}.issubset(
        set(enriched["Authoritative_Source_Record_IDs"])
    )
    assert enriched["Authoritative_Narrative_Source_Record_ID"] in set(
        enriched["Authoritative_Source_Record_IDs"]
    )
    assert enriched_merged["Component_Source_Record_IDs"] == component_ids
    assert enriched_merged["Authoritative_Source_Record_IDs"] == enriched[
        "Authoritative_Source_Record_IDs"
    ]
