"""PROBLEM 3 regression tests -- final rationale scientific-claim integrity.

The final rationale (build_final_rationale / Final_Rationale) must never
overstate evidence quantity, quality, directness, consistency, direction,
or certainty beyond what the canonical verified evidence pipeline
(Outcome_Specific_Human_Evidence_Count, Final_Canonical_Evidence_Direction
/_Source, Evidence_Consistency_Class) actually supports -- regardless of
what AI-adjudicated fields (Human_Evidence_Strength,
Indication_Evidence_Direction, Evidence_Adjudication_Rationale,
AI_Direct_Human_Outcome_Evidence_Count, Direct_Human_Outcome_Evidence_IDs)
say. This is a claim-AUTHORITY test suite, not exact-copywriting: assertions
check for semantically prohibited/required phrase classes via a small
bounded helper list, not one exact sentence.

All botanicals/indications used below are fictional.

Problems 1 and 2 remain CLOSED -- nothing here touches
Candidate_Intervention_Assertion / attribution / provenance (Problem 1)
or the evidence-sufficiency gate itself (Problem 2); those are exercised
here only insofar as build_final_rationale() must still render correctly
for gate-triggered rows (unchanged Problem-2 behavior).
"""
import pytest

from evidence_adjudication_engine import build_final_rationale
from step_rd_candidates import (
    _pre_gate_final_decision_status,
    _evidence_sufficiency_gate_triggered,
)


# ---------------------------------------------------------------------
# Bounded, central prohibited/required phrase vocabulary for tests.
# Mirrors (does not duplicate the wording logic of) the production
# vocabulary described in evidence_adjudication_engine.py's Problem-3
# note. Kept here, once, so no individual test hand-rolls its own
# ad-hoc string list.
# ---------------------------------------------------------------------
OVERCLAIM_PHRASES_FOR_ZERO_EVIDENCE = (
    "human evidence supports",
    "clinical evidence supports",
    "moderate human evidence",
    "strong human evidence",
    "consistent human evidence",
    "demonstrated efficacy",
    "established efficacy",
    "established clinical evidence",
    "proven benefit",
    "clinically proven",
    "strong body of human evidence",
    "replicated evidence",
    "multiple studies",
)

STRENGTH_INFLATION_TERMS = (
    "proven",
    "clinically proven",
    "established efficacy",
    "robust efficacy",
    "compelling clinical evidence",
    "strong clinical support",
)


def _no_overclaim(rationale: str, phrases=OVERCLAIM_PHRASES_FOR_ZERO_EVIDENCE):
    lowered = rationale.lower()
    hits = [p for p in phrases if p in lowered]
    assert not hits, f"Rationale overclaimed: {hits!r} found in {rationale!r}"


def _base_row(**overrides):
    """A minimal, otherwise-neutral report-ready row. Individual tests
    override only the fields relevant to the case being tested."""
    row = {
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Evidence_Sufficiency_Gate_Triggered": False,
    }
    row.update(overrides)
    return row


# =======================================================================
# REQUIRED ADVERSARIAL TESTS (numbered per the Problem-3 request)
# =======================================================================

def test_case1_zero_verified_count_ai_strong_does_not_claim_human_support():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Human_Evidence_Strength="STRONG",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
        Evidence_Adjudication_Rationale="Strong human evidence consistently supports efficacy.",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "no verified outcome-specific human evidence" in rationale.lower()


def test_case2_zero_verified_count_positive_adjudication_no_clinical_claim():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Evidence_Adjudication_Rationale="Moderate human evidence consistently supports efficacy.",
        Evidence_Adjudication_Status="AI_ADJUDICATION_OK",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)


def test_case3_zero_verified_count_many_ai_ids_no_human_support_claim():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        AI_Direct_Human_Outcome_Evidence_Count=15,
        Direct_Human_Outcome_Evidence_IDs=[f"ev{i}" for i in range(15)],
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "no verified outcome-specific human evidence" in rationale.lower()


def test_case4_one_verified_record_says_limited_not_consistent_or_strong():
    row = _base_row(Outcome_Specific_Human_Evidence_Count=1)
    rationale = build_final_rationale(row)
    assert "one verified outcome-specific human study" in rationale.lower()
    for term in ("consistent", "strong", "established", "multiple"):
        assert term not in rationale.lower()


def test_case5_multiple_positive_records_no_unjustified_proven():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=3,
        Final_Canonical_Evidence_Direction="CONSISTENT_POSITIVE",
        Final_Canonical_Evidence_Direction_Source="VERIFIED",
    )
    rationale = build_final_rationale(row)
    assert "multiple verified outcome-specific human studies" in rationale.lower()
    assert "positive evidence direction" in rationale.lower()
    for term in STRENGTH_INFLATION_TERMS:
        assert term not in rationale.lower()


def test_case6_conflicting_direction_records_says_mixed():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=2,
        Final_Canonical_Evidence_Direction="MIXED",
        Final_Canonical_Evidence_Direction_Source="VERIFIED",
    )
    rationale = build_final_rationale(row)
    assert "mixed" in rationale.lower()
    assert "does not support an unqualified efficacy conclusion" in rationale.lower()


def test_case7_negative_verified_evidence_with_positive_mechanism_stays_negative():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=2,
        Final_Canonical_Evidence_Direction="CONSISTENT_NEGATIVE",
        Final_Canonical_Evidence_Direction_Source="VERIFIED",
        Human_Evidence_Strength="STRONG",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
        Evidence_Adjudication_Rationale="Mechanistic evidence strongly supports efficacy.",
        Mechanistic_Evidence_Record_IDs=["m1", "m2"],
    )
    rationale = build_final_rationale(row)
    assert "predominantly negative" in rationale.lower()
    _no_overclaim(rationale)


def test_case8_human_study_wrong_indication_not_described_as_support():
    # Simulates the upstream-verified outcome-specific count being zero
    # (the human record exists but is for a different indication, so
    # candidate_shortlisting.py's fail-closed count never includes it),
    # while an AI field still references human evidence generically.
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Human_Evidence_Strength="MODERATE",
        Evidence_Adjudication_Rationale="Human evidence exists for a different indication.",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "no verified outcome-specific human evidence was identified for the requested indication" in rationale.lower()


def test_case9_unverified_candidate_attribution_no_candidate_specific_claim():
    # Candidate_Attribution_Verified=False upstream means
    # Outcome_Specific_Human_Evidence_Count is already 0 by the time this
    # row is built (Problem 1's fail-closed gate) -- verify the rationale
    # still refuses to claim support even if other AI fields disagree.
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Candidate_Attribution_Verified=False,
        Human_Evidence_Strength="STRONG",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)


def test_case10_missing_candidate_attribution_fails_closed():
    row = _base_row(Outcome_Specific_Human_Evidence_Count=0)
    row.pop("Candidate_Attribution_Verified", None)
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "no verified outcome-specific human evidence" in rationale.lower()


def test_case11_only_animal_evidence_says_no_verified_human_evidence():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Direct_Indication_Evidence_Count=0,
    )
    rationale = build_final_rationale(row)
    assert "no verified outcome-specific human evidence" in rationale.lower()
    _no_overclaim(rationale)


def test_case12_only_invitro_mechanistic_evidence_marked_indirect():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Mechanistic_Evidence_Record_IDs=["m1"],
    )
    rationale = build_final_rationale(row)
    assert "mechanistic or indirect evidence" in rationale.lower()
    assert "does not substitute for verified outcome-specific human evidence" in rationale.lower()
    _no_overclaim(rationale)


def test_case13_review_without_verified_direct_evidence_not_impersonated_as_direct():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Evidence_Adjudication_Rationale="A meta-analysis reviewing multiple related compounds.",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "no verified outcome-specific human evidence" in rationale.lower()


def test_case14_preparation_mismatch_no_efficacy_claim_for_requested_form():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=1,
        Preparation_Compatibility="MISMATCH",
    )
    rationale = build_final_rationale(row)
    assert "does not match the strongest available evidence" in rationale.lower()
    for term in ("demonstrated efficacy", "proven"):
        assert term not in rationale.lower()


def test_case15_problem2_gate_triggered_exact_insufficiency_rationale():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Evidence_Sufficiency_Gate_Triggered=True,
        Human_Evidence_Strength="STRONG",
    )
    rationale = build_final_rationale(row)
    assert rationale == (
        "No verified outcome-specific human evidence was identified for the "
        "requested indication; expert review is required before an "
        "actionable recommendation."
    )


def test_case16_genuine_safety_nogo_preserves_safety_not_turned_into_efficacy():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Safety_Status_Rationale="Contraindicated: verified hepatotoxicity signal.",
        Final_Decision_Status="NO GO SAFETY",
        Human_Evidence_Strength="STRONG",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "contraindicated" in rationale.lower()
    assert "no go safety" in rationale.lower()


# =======================================================================
# 15 ADDITIONAL ADVERSARIAL CASES -- combinations engineered to try to
# fool the rationale into overclaiming.
# =======================================================================

def test_extra1_zero_count_ai_consistent_positive_direction_alone():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
    )
    _no_overclaim(build_final_rationale(row))


def test_extra2_zero_count_large_ai_evidence_counts_and_mechanism_counts():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        AI_Direct_Outcome_Evidence_Count=9,
        AI_Direct_Human_Outcome_Evidence_Count=9,
        Mechanistic_Evidence_Record_IDs=["m1", "m2", "m3"],
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "mechanistic or indirect evidence" in rationale.lower()


def test_extra3_zero_count_legacy_direct_count_field_present():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Direct_Indication_Evidence_Count=4,
    )
    _no_overclaim(build_final_rationale(row))


def test_extra4_zero_count_direct_human_clinical_label_present():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Indication_Evidence_Mode="Direct human/clinical",
    )
    _no_overclaim(build_final_rationale(row))


def test_extra5_zero_count_positive_adjudication_prose_and_strong_strength():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Human_Evidence_Strength="STRONG",
        Evidence_Adjudication_Rationale="Strong human evidence consistently supports the requested indication.",
    )
    _no_overclaim(build_final_rationale(row))


def test_extra6_one_record_but_ai_says_consistent_positive_stays_conservative():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=1,
        Human_Evidence_Strength="STRONG",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
    )
    rationale = build_final_rationale(row)
    assert "one verified outcome-specific human study" in rationale.lower()
    for term in ("consistent", "strong", "established"):
        assert term not in rationale.lower()


def test_extra7_conflicting_canonical_direction_with_wrong_indication_ai_note():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=2,
        Final_Canonical_Evidence_Direction="MIXED",
        Final_Canonical_Evidence_Direction_Source="VERIFIED",
        Evidence_Adjudication_Rationale="Related indication evidence looks favorable.",
    )
    rationale = build_final_rationale(row)
    assert "mixed" in rationale.lower()
    _no_overclaim(rationale)


def test_extra8_unverified_candidate_attribution_with_large_ai_counts():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Candidate_Attribution_Verified=False,
        AI_Direct_Human_Outcome_Evidence_Count=20,
        Direct_Human_Outcome_Evidence_IDs=[f"e{i}" for i in range(20)],
    )
    _no_overclaim(build_final_rationale(row))


def test_extra9_preparation_mismatch_plus_zero_count_plus_ai_strong():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Preparation_Compatibility="MISMATCH",
        Human_Evidence_Strength="STRONG",
        Indication_Evidence_Direction="CONSISTENT_POSITIVE",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "does not match the strongest available evidence" in rationale.lower()


def test_extra10_ai_direction_consistent_positive_but_canonical_source_ai_fallback_not_verified():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=2,
        Final_Canonical_Evidence_Direction="CONSISTENT_POSITIVE",
        Final_Canonical_Evidence_Direction_Source="AI_FALLBACK",
    )
    rationale = build_final_rationale(row)
    # AI-fallback direction must not be treated as verified positive
    # consistency -- falls through to the "consistency not determined"
    # conservative wording instead of "with a positive evidence direction".
    assert "positive evidence direction" not in rationale.lower()
    for term in STRENGTH_INFLATION_TERMS:
        assert term not in rationale.lower()


def test_extra11_zero_count_legacy_direct_human_clinical_label_and_commercial_evidence():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Indication_Evidence_Mode="Direct human/clinical",
        Commercial_Status_Overall="ESTABLISHED",
    )
    rationale = build_final_rationale(row)
    _no_overclaim(rationale)
    assert "no verified outcome-specific human evidence" in rationale.lower()


def test_extra12_two_records_evidence_consistency_class_fallback_mostly_negative():
    # No Final_Canonical_Evidence_Direction populated -- must fall back to
    # Evidence_Consistency_Class (still VERIFIED, per the documented rule)
    # and correctly treat it as negative, not silently UNKNOWN/positive.
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=2,
        Evidence_Consistency_Class="MOSTLY_NEGATIVE",
    )
    rationale = build_final_rationale(row)
    assert "predominantly negative" in rationale.lower()
    _no_overclaim(rationale)


def test_extra13_zero_count_ai_evidence_conflict_level_high_with_confidence_high():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Evidence_Conflict_Level="HIGH",
        Scientific_Evidence_Confidence="HIGH",
        Human_Evidence_Strength="MODERATE",
    )
    _no_overclaim(build_final_rationale(row))


def test_extra14_multiple_records_null_direction_not_described_as_positive():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=3,
        Final_Canonical_Evidence_Direction="CONSISTENT_NULL",
        Final_Canonical_Evidence_Direction_Source="VERIFIED",
    )
    rationale = build_final_rationale(row)
    assert "no clear positive effect" in rationale.lower()
    assert "positive evidence direction" not in rationale.lower()
    _no_overclaim(rationale)


def test_extra15_one_record_ai_direct_human_outcome_ids_inflated_stays_single():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=1,
        AI_Direct_Human_Outcome_Evidence_Count=12,
        Direct_Human_Outcome_Evidence_IDs=[f"x{i}" for i in range(12)],
    )
    rationale = build_final_rationale(row)
    assert "one verified outcome-specific human study" in rationale.lower()
    assert "12" not in rationale


# =======================================================================
# END-TO-END TESTS: canonical evidence -> final decision -> final
# rationale, chaining the three real functions
# (_pre_gate_final_decision_status / _evidence_sufficiency_gate_triggered
# / build_final_rationale) rather than re-deriving decision logic in the
# test.
# =======================================================================

def test_e2e_a_zero_verified_human_evidence_non_actionable_and_no_overclaim():
    row = {
        "Decision_Class_AH": "B — Direct human/clinical candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Direct_Indication_Evidence_Count": 3,
        "Human_Evidence_Strength": "STRONG",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Evidence_Adjudication_Rationale": "Strong human evidence consistently supports efficacy.",
        "Evidence_Adjudication_Evidence_Count": 3,
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Scientific_Evidence_Confidence": "HIGH",
        "Evidence_Conflict_Level": "LOW",
    }
    pre_gate_status = _pre_gate_final_decision_status(row)
    gate_triggered = _evidence_sufficiency_gate_triggered(pre_gate_status, row)
    final_status = "EXPERT REVIEW REQUIRED" if gate_triggered else pre_gate_status
    row["Evidence_Sufficiency_Gate_Triggered"] = gate_triggered
    rationale = build_final_rationale(row)

    assert gate_triggered is True
    assert final_status == "EXPERT REVIEW REQUIRED"
    _no_overclaim(rationale)


def test_e2e_b_one_verified_positive_record_normal_logic_limited_wording():
    row = {
        "Decision_Class_AH": "C — Candidate requiring further evidence",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Outcome_Specific_Human_Evidence_Count": 1,
        "Outcome_Specific_Direct_Evidence_Count": 1,
        "Direct_Indication_Evidence_Count": 1,
        "Human_Evidence_Strength": "WEAK",
        "Indication_Evidence_Direction": "MOSTLY_POSITIVE",
        "Evidence_Adjudication_Evidence_Count": 1,
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Evidence_Conflict_Level": "LOW",
    }
    pre_gate_status = _pre_gate_final_decision_status(row)
    gate_triggered = _evidence_sufficiency_gate_triggered(pre_gate_status, row)
    row["Evidence_Sufficiency_Gate_Triggered"] = gate_triggered
    rationale = build_final_rationale(row)

    assert gate_triggered is False
    assert "one verified outcome-specific human study" in rationale.lower()
    for term in ("consistent", "strong", "established", "multiple"):
        assert term not in rationale.lower()


def test_e2e_c_multiple_mixed_verified_records_rationale_communicates_mixed():
    row = {
        "Decision_Class_AH": "C — Candidate requiring further evidence",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Outcome_Specific_Human_Evidence_Count": 2,
        "Outcome_Specific_Direct_Evidence_Count": 2,
        "Direct_Indication_Evidence_Count": 2,
        "Final_Canonical_Evidence_Direction": "MIXED",
        "Final_Canonical_Evidence_Direction_Source": "VERIFIED",
        "Human_Evidence_Strength": "MODERATE",
        "Indication_Evidence_Direction": "MIXED",
        "Evidence_Adjudication_Evidence_Count": 2,
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Evidence_Conflict_Level": "MODERATE",
    }
    pre_gate_status = _pre_gate_final_decision_status(row)
    gate_triggered = _evidence_sufficiency_gate_triggered(pre_gate_status, row)
    row["Evidence_Sufficiency_Gate_Triggered"] = gate_triggered
    rationale = build_final_rationale(row)

    assert gate_triggered is False
    assert "mixed" in rationale.lower()
    assert "does not support an unqualified efficacy conclusion" in rationale.lower()


# =======================================================================
# Independent post-review regressions: final rationale must not fabricate
# evidence signals while trying to explain authority/precedence.
# =======================================================================

def test_independent_negative_verified_evidence_does_not_invent_positive_ai_or_mechanistic_signal():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=2,
        Final_Canonical_Evidence_Direction="CONSISTENT_NEGATIVE",
        Final_Canonical_Evidence_Direction_Source="VERIFIED",
    )
    rationale = build_final_rationale(row)
    assert "predominantly negative" in rationale.lower()
    assert "positive mechanistic" not in rationale.lower()
    assert "ai-estimated signals" not in rationale.lower()


def test_independent_ai_rationale_alone_does_not_manufacture_indirect_evidence_clause():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Evidence_Adjudication_Rationale="No indication-relevant evidence was identified.",
    )
    rationale = build_final_rationale(row)
    assert "no verified outcome-specific human evidence" in rationale.lower()
    assert "other mechanistic or indirect evidence was identified" not in rationale.lower()


def test_independent_structured_mechanistic_signal_gets_neutral_non_substitution_wording():
    row = _base_row(
        Outcome_Specific_Human_Evidence_Count=0,
        Mechanistic_Evidence_Record_IDs=["m1"],
    )
    rationale = build_final_rationale(row)
    assert "other mechanistic or indirect evidence was identified" in rationale.lower()
    assert "does not substitute for verified outcome-specific human evidence" in rationale.lower()
    assert "supports efficacy" not in rationale.lower()
