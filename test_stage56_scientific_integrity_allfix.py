import pandas as pd

import evidence_adjudication_engine as ea
import ai_rd_insight_service as insights
import candidate_shortlisting as cs
import step_rd_candidates as src


def test_sleep_fallback_does_not_treat_and_as_indication_evidence():
    df = pd.DataFrame([
        {
            "Scientific_Name": "Citrus limon",
            "Evidence_Record_ID": "IRRELEVANT",
            "Notes": "spinal cord injury repair and inflammatory signaling",
            "Study_Type": "animal study",
        },
        {
            "Scientific_Name": "Citrus limon",
            "Evidence_Record_ID": "SLEEP",
            "Primary_Outcome": "sleep quality improved in a randomized controlled trial",
            "Study_Type": "randomized controlled trial",
            "PMID": "12345",
        },
    ])
    items = ea.build_adjudication_evidence_items(
        df, "Citrus limon", "Sleep and relaxation", max_items=10
    )
    assert [x["evidence_id"] for x in items] == ["SLEEP"]
    assert items[0]["indication_match_strength"] == "DIRECT"


def test_ai_insight_and_adjudication_use_same_curated_evidence_scope():
    df = pd.DataFrame([
        {
            "Scientific_Name": "Test plant",
            "Evidence_Record_ID": "IRRELEVANT",
            "Notes": "spinal cord repair and wound healing",
        },
        {
            "Scientific_Name": "Test plant",
            "Evidence_Record_ID": "SLEEP",
            "Primary_Outcome": "reduced sleep latency",
            "Study_Type": "clinical trial",
        },
    ])
    adjudication_ids = [
        x["evidence_id"] for x in ea.build_adjudication_evidence_items(
            df, "Test plant", "Sleep and relaxation", max_items=30
        )
    ]
    insight_ids = [
        x["evidence_id"] for x in insights._evidence_items_from_df(
            df, "Test plant", "Sleep and relaxation"
        )
    ]
    assert adjudication_ids == insight_ids == ["SLEEP"]


def test_authoritative_direct_evidence_requires_direct_match_and_empirical_traceability():
    base = {
        "Evidence_Level": "Clinical / human evidence",
        "Evidence_Hierarchy_Detail": "Clinical trial",
        "Source_Record_IDs": "PMID:1",
    }
    supportive = pd.Series({**base, "Indication_Match_Type": "outcome_or_mechanism_support"})
    direct = pd.Series({**base, "Indication_Match_Type": "exact_indication"})
    source_only = pd.Series({
        "Source_Record_IDs": "PMID:2",
        "Evidence_Level": "general literature signal",
        "Indication_Match_Type": "exact_indication",
    })
    assert cs._has_direct_evidence(supportive) is False
    assert cs._has_direct_evidence(direct) is True
    assert cs._has_direct_evidence(source_only) is False


def test_mechanism_display_is_indication_specific_not_whole_plant_bioactivity_dump():
    group = pd.DataFrame([{
        "Indication_Match_Type": "outcome_or_mechanism_support",
        "Indication_Match_Terms": "gabaergic;benzodiazepine receptor",
        "Target_or_Mechanism": (
            "GABAergic system, Anticancer, Pesticide, Cytotoxic, "
            "benzodiazepine receptor"
        ),
    }])
    values = cs._indication_specific_mechanism_values(
        group, "Sleep and relaxation", limit=10
    )
    normalized = {x.lower() for x in values}
    assert "gabaergic system" in normalized
    assert "benzodiazepine receptor" in normalized
    assert "anticancer" not in normalized
    assert "pesticide" not in normalized
    assert "cytotoxic" not in normalized


def test_protective_toxicity_study_is_not_a_safety_flag():
    group = pd.DataFrame([
        {"Safety_Flags": (
            "Exploring the protective impacts of Rhodiola rosea extract against "
            "vancomycin-induced hepatic and renal toxicity"
        )},
        {"Safety_Flags": "Rhodiola rosea caused nausea in participants."},
    ])
    result = cs._clean_safety_flags_for_plant(group, "Rhodiola rosea")
    assert "protective impacts" not in result.lower()
    assert "nausea" in result.lower()


def test_different_valeriana_species_safety_text_is_not_attributed_to_officinalis():
    group = pd.DataFrame([
        {"Safety_Flags": "Valeriana pilosa caused toxicity in rats."},
        {"Safety_Flags": "Valeriana officinalis caused nausea in participants."},
    ])
    result = cs._clean_safety_flags_for_plant(group, "Valeriana officinalis")
    assert "pilosa" not in result.lower()
    assert "officinalis" in result.lower()


def test_adjudication_budget_targets_highest_ranked_candidates(monkeypatch):
    frame = pd.DataFrame([
        {"Alternative_Plant": "low", "Scientific_Triage_Status": "Shortlist", "Overall_Score": 10,
         "Decision_Class_AH": "C — Alternative-source R&D candidate", "Go_Investigate_Hold_NoGo": "Investigate"},
        {"Alternative_Plant": "high", "Scientific_Triage_Status": "Shortlist", "Overall_Score": 90,
         "Decision_Class_AH": "C — Alternative-source R&D candidate", "Go_Investigate_Hold_NoGo": "Investigate"},
        {"Alternative_Plant": "mid", "Scientific_Triage_Status": "Exploratory", "Overall_Score": 50,
         "Decision_Class_AH": "F — Exploratory hypothesis", "Go_Investigate_Hold_NoGo": "Investigate"},
    ])
    calls = []
    monkeypatch.setattr(src, "_ADJUDICATION_MAX_CANDIDATES", 2)

    def fake_adjudicate(plant, *args, **kwargs):
        calls.append(plant)
        return {
            "Indication_Evidence_Direction": "MOSTLY_POSITIVE",
            "Human_Evidence_Strength": "MODERATE",
            "Evidence_Conflict_Level": "LOW",
            "Negative_Evidence_Severity": "NONE",
            "Preparation_Compatibility": "UNKNOWN",
            "Plant_Part_Compatibility": "UNKNOWN",
            "Route_Compatibility": "UNKNOWN",
            "Scientific_Evidence_Confidence": "MODERATE",
            "Positive_Evidence_IDs": [], "Negative_Evidence_IDs": [],
            "Key_Human_Evidence_IDs": [], "Preparation_Mismatch_Evidence_IDs": [],
            "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
            "Evidence_Adjudication_Evidence_Count": 1,
            "Evidence_Adjudication_Rationale": "ok",
            "Evidence_Adjudication_Fallback_Reason": None,
        }

    monkeypatch.setattr(src, "adjudicate_candidate", fake_adjudicate)
    src._run_evidence_adjudication(frame.copy(), pd.DataFrame(), "Sleep and relaxation", {})
    assert calls == ["high", "mid"]


def test_final_decision_reconciliation_never_leaves_ai_no_evidence_green():
    common = {
        "Decision_Class_AH": "C — Alternative-source R&D candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "direct_match",
        "Final_Decision_Status": "",
    }
    assert src._reconcile_final_decision_status(pd.Series({
        **common, "Evidence_Adjudication_Status": "AI_ADJUDICATION_NO_EVIDENCE"
    })) == "EXPERT REVIEW REQUIRED"
    assert src._reconcile_final_decision_status(pd.Series({
        **common,
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "MOSTLY_POSITIVE",
        "Human_Evidence_Strength": "MODERATE",
        "Scientific_Evidence_Confidence": "MODERATE",
        "Evidence_Conflict_Level": "LOW",
    })) == "GO WITH CAUTION"
    assert src._reconcile_final_decision_status(pd.Series({
        **common, "Final_Decision_Status": "NO GO REGULATORY",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
    })) == "NO GO REGULATORY"


def test_final_decision_reconciliation_blocks_incompatible_preparation():
    row = pd.Series({
        "Decision_Class_AH": "B — Established scientific candidate",
        "Relevance_Gate_Result": "passed_direct",
        "Preparation_Applicability_Class": "incompatible",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
        "Human_Evidence_Strength": "STRONG",
    })
    assert src._reconcile_final_decision_status(row) == "EXPERT REVIEW REQUIRED"
