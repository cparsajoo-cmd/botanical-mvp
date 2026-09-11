"""DEFECT 9 FIX (final pre-demo reliability pass) — regression tests for the
canonical evidence-direction authority hierarchy: source-grounded/verified
evidence (Evidence_Consistency_Class) must control the final canonical
direction and final decision status; AI/semantic inference
(Indication_Evidence_Direction) is only a labeled fallback when the
verified classification is itself uninformative, and can never silently
override a resolved verified classification with a rosier one.
"""
import step_rd_candidates as srd


def test_verified_classification_is_canonical_even_when_ai_disagrees():
    # AI says positive; verified evidence says MIXED. Canonical direction
    # must follow the verified classification, not the AI's optimism.
    direction, source = srd._final_canonical_evidence_direction("MIXED", "CONSISTENT_POSITIVE")
    assert direction == "MIXED"
    assert source == "VERIFIED"


def test_verified_negative_classification_beats_ai_positive():
    direction, source = srd._final_canonical_evidence_direction(
        "MOSTLY_NEGATIVE", "CONSISTENT_POSITIVE"
    )
    assert direction == "MOSTLY_NEGATIVE"
    assert source == "VERIFIED"


def test_ai_is_only_a_fallback_when_verified_evidence_is_uninformative():
    # No known-direction evidence at all (verified classification itself
    # uninformative) -- AI may fill the gap, but is explicitly labeled as
    # a fallback, never presented as verified.
    direction, source = srd._final_canonical_evidence_direction(
        "INSUFFICIENT_DIRECTION_DATA", "CONSISTENT_POSITIVE"
    )
    assert direction == "CONSISTENT_POSITIVE"
    assert source == "AI_FALLBACK"

    direction2, source2 = srd._final_canonical_evidence_direction("INSUFFICIENT", "MIXED")
    assert direction2 == "MIXED"
    assert source2 == "AI_FALLBACK"


def test_neither_source_available_is_honestly_unknown():
    direction, source = srd._final_canonical_evidence_direction("", "")
    assert direction == "UNKNOWN"
    assert source == "UNKNOWN"
    direction2, source2 = srd._final_canonical_evidence_direction("INSUFFICIENT", "UNKNOWN")
    assert direction2 == "UNKNOWN"
    assert source2 == "UNKNOWN"


def test_ai_positive_direct_cannot_force_unqualified_go_over_unverified_signal():
    # DEFECT 9 acceptance test: AI says positive/direct (CONSISTENT_POSITIVE,
    # human=STRONG, AI_ADJUDICATION_OK) but the candidate's own verified
    # indication relevance is an unverified direct-human signal (Defect 2)
    # -- zero verified outcome-specific human evidence. The final decision
    # must follow the verified evidence, never reach unqualified "GO".
    row = {
        "Final_Decision_Status": "",
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "STRONG",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "HIGH",
        "Indication_Evidence_Mode": "UNVERIFIED_DIRECT_HUMAN_SIGNAL",
        "Safety_Flags": "",
        "Safety_Assertion_Status": "",
        "Safety_Concern_Level": "NONE",
        "Direct_Indication_Evidence_Count": 1,
        "Outcome_Specific_Direct_Evidence_Count": 0,
        "Outcome_Specific_Human_Evidence_Count": 0,
        "Evidence_Adjudication_Evidence_Count": 1,
    }
    result = srd._reconcile_final_decision_status(row)
    assert result != "GO"
    assert result in {"GO WITH CAUTION", "EXPERT REVIEW REQUIRED", "INSUFFICIENT EVIDENCE"}


def test_verified_direct_human_with_ai_agreement_can_reach_go():
    # Sanity check: a GENUINELY verified direct-human candidate, with AI
    # agreement and no conflict, can still reach GO -- the fix must not
    # make GO unreachable, only unreachable on unverified evidence alone.
    row = {
        "Final_Decision_Status": "",
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "STRONG",
        "Evidence_Conflict_Level": "NONE",
        "Scientific_Evidence_Confidence": "HIGH",
        "Indication_Evidence_Mode": "Direct human/clinical",
        "Safety_Flags": "",
        "Safety_Assertion_Status": "",
        "Safety_Concern_Level": "NONE",
        "Direct_Indication_Evidence_Count": 3,
        "Outcome_Specific_Direct_Evidence_Count": 2,
        "Outcome_Specific_Human_Evidence_Count": 2,
        # PROBLEM 5 FIX: this positive control is about verified-vs-
        # unverified evidence (Problem 2), not formulation compatibility
        # (Problem 5) -- both verified records are formulation-compatible
        # here, so the sequential Problem-5 gate must not additionally
        # block this genuinely-actionable GO.
        "Verified_Formulation_Compatible_Outcome_Specific_Human_Evidence_Count": 2,
        "Evidence_Adjudication_Evidence_Count": 3,
    }
    result = srd._reconcile_final_decision_status(row)
    assert result == "GO"
