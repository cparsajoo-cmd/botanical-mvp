"""Regression coverage for this session's correction: negative evidence
that is ALREADY represented in the deterministic scientific score
(Direction_Factor / Evidence_Consistency_Factor / Scientific_Evidence_
Score in candidate_shortlisting.py) must not ALSO receive a second,
arbitrary additive penalty (-8/-4/-1) from evidence_adjudication_engine.
compute_deterministic_adjustments().

Adjudication's role for negative evidence is DECISION interpretation/
capping (apply_negative_evidence_cap) -- never a second scoring pass.
"""
import pandas as pd

import evidence_adjudication_engine as ea


# ---------------------------------------------------------------------
# 1-4. No second numerical penalty, for any severity/strength
# combination -- Evidence_Adjudication_Adjustment and Negative_Human_
# Evidence_Adjustment are always 0.0, and Final == Base.
# ---------------------------------------------------------------------
def test_high_severity_strong_human_negative_evidence_gets_zero_adjustment():
    adjudication = {
        "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE",
        "Human_Evidence_Strength": "STRONG",
        "Negative_Evidence_Severity": "HIGH",
    }
    adjustments = ea.compute_deterministic_adjustments(adjudication, base_score=82.0)
    assert adjustments["Evidence_Adjudication_Adjustment"] == 0.0
    assert adjustments["Negative_Human_Evidence_Adjustment"] == 0.0
    assert adjustments["Base_R&D_Opportunity_Score"] == 82.0
    assert adjustments["Final_R&D_Opportunity_Score"] == 82.0


def test_moderate_severity_moderate_human_negative_evidence_gets_zero_adjustment():
    adjudication = {
        "Indication_Evidence_Direction": "MOSTLY_NEGATIVE",
        "Human_Evidence_Strength": "MODERATE",
        "Negative_Evidence_Severity": "MODERATE",
    }
    adjustments = ea.compute_deterministic_adjustments(adjudication, base_score=60.0)
    assert adjustments["Evidence_Adjudication_Adjustment"] == 0.0
    assert adjustments["Negative_Human_Evidence_Adjustment"] == 0.0
    assert adjustments["Final_R&D_Opportunity_Score"] == adjustments["Base_R&D_Opportunity_Score"]
    assert adjustments["Final_R&D_Opportunity_Score"] == 60.0


def test_low_severity_negative_evidence_gets_zero_adjustment():
    adjudication = {
        "Indication_Evidence_Direction": "MOSTLY_NEGATIVE",
        "Human_Evidence_Strength": "WEAK",
        "Negative_Evidence_Severity": "LOW",
    }
    adjustments = ea.compute_deterministic_adjustments(adjudication, base_score=45.0)
    assert adjustments["Evidence_Adjudication_Adjustment"] == 0.0
    assert adjustments["Negative_Human_Evidence_Adjustment"] == 0.0
    assert adjustments["Final_R&D_Opportunity_Score"] == 45.0


def test_mechanistic_only_high_severity_also_gets_zero_adjustment():
    # Previously this specific combination (no human evidence, HIGH
    # severity) still received a -1.0 penalty -- also removed.
    adjudication = {
        "Indication_Evidence_Direction": "MOSTLY_NEGATIVE",
        "Human_Evidence_Strength": "NONE",
        "Negative_Evidence_Severity": "HIGH",
    }
    adjustments = ea.compute_deterministic_adjustments(adjudication, base_score=50.0)
    assert adjustments["Evidence_Adjudication_Adjustment"] == 0.0
    assert adjustments["Negative_Human_Evidence_Adjustment"] == 0.0
    assert adjustments["Final_R&D_Opportunity_Score"] == 50.0


def test_preparation_and_plant_part_adjustments_remain_zero_too():
    # Unaffected by this correction, but must remain 0.0 -- same
    # no-double-counting principle, already correct before this session.
    adjudication = {
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "STRONG",
        "Negative_Evidence_Severity": "NONE",
    }
    adjustments = ea.compute_deterministic_adjustments(adjudication, base_score=90.0)
    assert adjustments["Preparation_Adjustment"] == 0.0
    assert adjustments["Plant_Part_Adjustment"] == 0.0
    assert adjustments["Final_R&D_Opportunity_Score"] == 90.0


def test_score_never_moves_regardless_of_base_score_value():
    # Confirms the fix is not just "0.0 near a specific base score" --
    # Final always equals Base, at any value, for negative evidence.
    for base in (0.0, 12.5, 33.0, 55.5, 99.9, 100.0):
        adjustments = ea.compute_deterministic_adjustments(
            {
                "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE",
                "Human_Evidence_Strength": "STRONG",
                "Negative_Evidence_Severity": "HIGH",
            },
            base_score=base,
        )
        assert adjustments["Final_R&D_Opportunity_Score"] == round(base, 1)


# ---------------------------------------------------------------------
# 5. Strong consistent negative human evidence can STILL cap the final
# decision to Hold/insufficient evidence -- the CAP logic is untouched.
# ---------------------------------------------------------------------
def test_strong_consistent_negative_human_evidence_still_caps_to_hold():
    adjudication = {
        "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE",
        "Human_Evidence_Strength": "STRONG",
        "Negative_Evidence_Severity": "HIGH",
    }
    new_class, new_go, reason = ea.apply_negative_evidence_cap(
        "B — Established scientific candidate", "Go", adjudication,
    )
    assert new_class == "G — Hold / insufficient evidence"
    assert new_go == "Hold"
    assert reason == "consistent_negative_human_evidence"


# ---------------------------------------------------------------------
# 6. Negative efficacy never becomes a safety concern.
# ---------------------------------------------------------------------
def test_negative_efficacy_never_becomes_a_safety_concern():
    adjudication = {
        "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE",
        "Human_Evidence_Strength": "STRONG",
        "Negative_Evidence_Severity": "HIGH",
    }
    new_class, new_go, reason = ea.apply_negative_evidence_cap(
        "B — Established scientific candidate", "Go", adjudication,
    )
    assert new_class != "H — No-go / safety concern"
    assert new_go != "No-Go"


# ---------------------------------------------------------------------
# 7. Existing safety/regulatory No-Go retains precedence over the
# (score-neutral) negative-efficacy cap.
# ---------------------------------------------------------------------
def test_existing_safety_no_go_is_never_weakened_by_the_efficacy_cap():
    adjudication = {
        "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE",
        "Human_Evidence_Strength": "STRONG",
        "Negative_Evidence_Severity": "HIGH",
    }
    # Candidate already has a real safety/regulatory No-Go from elsewhere
    # in the pipeline -- the efficacy cap (which would only ask for Hold)
    # must never downgrade it back to something weaker.
    new_class, new_go, reason = ea.apply_negative_evidence_cap(
        "H — No-go / safety concern", "No-Go", adjudication,
    )
    assert new_class == "H — No-go / safety concern"
    assert new_go == "No-Go"


# ---------------------------------------------------------------------
# End-to-end: the full _run_evidence_adjudication -> merge pipeline
# never moves the score for negative evidence, while still capping the
# decision.
# ---------------------------------------------------------------------
def test_end_to_end_negative_evidence_caps_decision_without_moving_score(monkeypatch):
    import step_rd_candidates as src

    def _fake_adjudicate_candidate(plant, indication, evidence_df, **kwargs):
        return {
            "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE",
            "Human_Evidence_Strength": "STRONG",
            "Evidence_Conflict_Level": "NONE",
            "Negative_Evidence_Severity": "HIGH",
            "Scientific_Evidence_Confidence": "MODERATE",
            "Preparation_Compatibility": "DIRECT",
            "Plant_Part_Compatibility": "DIRECT",
            "Route_Compatibility": "DIRECT",
            "Positive_Evidence_IDs": [], "Negative_Evidence_IDs": ["E1"],
            "Key_Human_Evidence_IDs": ["E1"], "Preparation_Mismatch_Evidence_IDs": [],
            "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
            "Evidence_Adjudication_Fallback_Reason": None,
            "Evidence_Adjudication_Evidence_Count": 1,
            "Evidence_Adjudication_Rationale": "Strong human evidence consistently does not support.",
        }

    monkeypatch.setattr(src, "adjudicate_candidate", _fake_adjudicate_candidate)

    plant_summary_df = pd.DataFrame([{
        "Alternative_Plant": "Plant A", "Overall_Score": 75.0,
        "Scientific_Triage_Status": "Shortlist",
        "Decision_Class_AH": "B — Established scientific candidate",
        "Go_Investigate_Hold_NoGo": "Go",
    }])
    evidence_df = pd.DataFrame([{"Evidence_Record_ID": "E1", "Scientific_Name": "Plant A"}])

    result = src._run_evidence_adjudication(plant_summary_df, evidence_df, "sleep", {})

    # Score is untouched (no double counting)...
    assert result.loc[0, "Overall_Score"] == 75.0
    assert result.loc[0, "Final_R&D_Opportunity_Score"] == 75.0
    assert result.loc[0, "Base_R&D_Opportunity_Score"] == 75.0
    assert result.loc[0, "Evidence_Adjudication_Adjustment"] == 0.0
    assert result.loc[0, "Negative_Human_Evidence_Adjustment"] == 0.0
    # ...but the decision is still capped to Hold, never to a safety No-Go.
    assert result.loc[0, "Decision_Class_AH"] == "G — Hold / insufficient evidence"
    assert result.loc[0, "Go_Investigate_Hold_NoGo"] == "Hold"
