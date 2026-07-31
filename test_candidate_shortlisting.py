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


def test_plant_with_no_indication_specific_evidence_is_excluded():
    # Passes every generic gate (direct evidence, supported target, specific
    # compound) but nothing in the text mentions the requested indication.
    df = pd.DataFrame([_row(Target_or_Mechanism="AMPK activation, general metabolic pathway")])
    summary, audit = build_plant_candidate_shortlist(
        df, indication="wound healing", dosage_form="Infusion"
    )
    assert summary.iloc[0]["Scientific_Triage_Status"] == "Excluded"
    assert summary.iloc[0]["Indication_Relevance"] == "No relevance"


def test_indication_specific_evidence_is_shortlisted_and_scored():
    df = pd.DataFrame([_row(
        Scientific_Rationale="supports wound healing via collagen synthesis",
        Applicability_Summary='{"critical_mismatches":[],"evidence_items":[]}',
    )])
    summary, audit = build_plant_candidate_shortlist(
        df, indication="wound healing", dosage_form="Infusion"
    )
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Shortlist"
    assert row["Indication_Relevance"] == "High relevance"
    assert 0 <= row["Overall_Score"] <= 100
    assert "Indication Relevance" in row["Score_Breakdown"]
    assert row["Why_Selected_or_Rejected"].startswith("Selected because")


def test_no_indication_supplied_preserves_legacy_behaviour():
    # No indication string -> the new gate must stay neutral (as before this
    # requirement existed) rather than excluding every candidate.
    df = pd.DataFrame([_row()])
    summary, _ = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    assert summary.iloc[0]["Scientific_Triage_Status"] == "Shortlist"
    assert summary.iloc[0]["Indication_Relevance"].startswith("Not evaluated")


def test_near_duplicate_congener_is_demoted_without_independent_evidence():
    strong = _row(
        Alternative_Plant="Scutellaria baicalensis",
        Target_or_Mechanism="GABA modulation relevant to anxiety",
        Scientific_Rationale="anxiety reduction via GABA modulation",
        Source_Record_IDs="PMID:1",
    )
    weak_congener = _row(
        Alternative_Plant="Scutellaria sp.",
        Target_or_Mechanism="general antioxidant activity, unrelated pathway",
        Scientific_Rationale="antioxidant capacity assay",
        Source_Record_IDs="PMID:2",
        Candidate_Evidence_Strength_Tier="Weak",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([strong, weak_congener]), indication="anxiety", dosage_form="Infusion"
    )
    statuses = dict(zip(summary["Alternative_Plant"], summary["Scientific_Triage_Status"]))
    # The weak congener has zero indication-specific text, so it is excluded
    # by the indication gate before duplicate-pruning even runs — the
    # stronger species remains the sole shortlisted representative of the genus.
    assert statuses["Scutellaria baicalensis"] == "Shortlist"
    assert statuses["Scutellaria sp."] == "Excluded"


def test_templated_rationale_does_not_create_indication_relevance():
    df = pd.DataFrame([_row(
        Target_or_Mechanism="general antioxidant activity",
        Scientific_Rationale="Shares an exact compound with the reference plant.",
        Rationale=(
            "For Infusion targeting Metabolic & blood sugar support, Candidate plant "
            "is compared with Reference plant because it shares a compound."
        ),
    )])
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    row = summary.iloc[0]
    assert row["Indication_Relevance"] == "No relevance"
    assert row["Scientific_Triage_Status"] == "Excluded"


def test_generic_antiinflammatory_mechanism_is_not_blood_sugar_relevance():
    df = pd.DataFrame([_row(
        Target_or_Mechanism="NF-kB inhibition; antioxidant; anti-inflammatory",
        Scientific_Rationale="reduces oxidative stress in a general cell assay",
    )])
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    assert summary.iloc[0]["Indication_Relevance"] == "No relevance"


def test_two_relevant_congeners_keep_only_stronger_shortlist_representative():
    strong = _row(
        Alternative_Plant="Scutellaria baicalensis",
        Target_or_Mechanism="alpha-glucosidase inhibition and AMPK activation",
        Scientific_Rationale="improved blood glucose and insulin sensitivity in a human clinical study",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Human clinical evidence",
        Source_Record_IDs="PMID:1; PMID:2; PMID:3",
    )
    weaker = _row(
        Alternative_Plant="Scutellaria discolor",
        Target_or_Mechanism="alpha-glucosidase inhibition",
        Scientific_Rationale="blood glucose reduction in an in vitro screening assay",
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="In vitro evidence",
        Source_Record_IDs="PMID:4",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([strong, weaker]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    statuses = dict(zip(summary["Alternative_Plant"], summary["Scientific_Triage_Status"]))
    assert statuses["Scutellaria baicalensis"] == "Shortlist"
    assert statuses["Scutellaria discolor"] == "Exploratory"
    weaker_text = summary.loc[
        summary["Alternative_Plant"] == "Scutellaria discolor", "Why_Selected_or_Rejected"
    ].iloc[0]
    assert weaker_text.startswith("Kept for further investigation because")


def test_exploratory_explanation_never_says_selected():
    df = pd.DataFrame([_row(
        Target_or_Mechanism="AMPK activation",
        Scientific_Rationale="AMPK activation in a mechanistic assay",
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="In vitro evidence",
    )])
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Exploratory"
    assert row["Why_Selected_or_Rejected"].startswith("Kept for further investigation because")
    assert not row["Why_Selected_or_Rejected"].startswith("Selected because")


def test_mixed_candidates_are_not_all_high_relevance():
    rows = [
        _row(
            Alternative_Plant="Direct candidate",
            Target_or_Mechanism="alpha-glucosidase inhibition",
            Scientific_Rationale="improved blood glucose and insulin sensitivity in humans",
        ),
        _row(
            Alternative_Plant="Mechanistic candidate",
            Target_or_Mechanism="AMPK activation",
            Scientific_Rationale="AMPK activation in vitro",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="In vitro evidence",
        ),
        _row(
            Alternative_Plant="Unrelated candidate",
            Target_or_Mechanism="GABAergic sedation",
            Scientific_Rationale="sleep latency reduction",
        ),
    ]
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame(rows), indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    assert set(summary["Indication_Relevance"]) != {"High relevance"}
