import pandas as pd

from candidate_shortlisting import build_plant_candidate_shortlist


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


def test_aggregates_to_one_row_per_alternative_plant():
    df = pd.DataFrame([
        _row(Shared_or_Similar_Compound="compound A"),
        _row(Shared_or_Similar_Compound="compound B"),
    ])
    summary, audit = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    assert len(summary) == 1
    assert summary.iloc[0]["Distinctive_Compound_Count"] == 2
    assert len(audit) == 2


def test_generic_compound_without_supported_target_is_not_shortlisted():
    df = pd.DataFrame([_row(
        Shared_or_Similar_Compound="glucose",
        Novelty_Status="Common / non-specific",
        Target_or_Mechanism="Not clearly extracted",
        Target_Provenance="Not applicable (no shared-target claim for this match type)",
    )])
    summary, audit = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    assert summary.iloc[0]["Scientific_Triage_Status"] != "Shortlist"
    assert bool(audit.iloc[0]["Generic_Compound_Only"])


def test_explicit_dosage_mismatch_is_excluded_but_zero_count_is_not():
    mismatch = _row(Applicability_Summary='{"critical_mismatches":["dosage form mismatch: capsule vs infusion"]}')
    harmless = _row(
        Alternative_Plant="Second candidate",
        Applicability_Summary='{"counts":{"Not applicable":0},"critical_mismatches":[],"evidence_items":[]}',
    )
    summary, audit = build_plant_candidate_shortlist(pd.DataFrame([mismatch, harmless]), dosage_form="Infusion")
    statuses = dict(zip(summary["Alternative_Plant"], summary["Scientific_Triage_Status"]))
    assert statuses["Candidate plant"] == "Excluded"
    assert statuses["Second candidate"] == "Shortlist"
