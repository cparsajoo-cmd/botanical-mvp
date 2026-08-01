import pandas as pd

from candidate_shortlisting import build_plant_candidate_shortlist, merge_authoritative_scores


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


def test_mechanism_only_inferred_link_cannot_enter_shortlist():
    row = _row(
        Target_or_Mechanism="Aldose-Reductase-Inhibitor; AMPK",
        Scientific_Rationale=(
            "Shares a validated biological target with the reference compound "
            "(seed_data.COMPOUND_TARGETS hardcoded knowledge base, not a specific study)."
        ),
        Evidence_Level="General literature signal",
        Evidence_Hierarchy_Detail="Unclassified",
        Source_Record_IDs="PMID:999",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Exploratory"
    assert result["Indication_Evidence_Mode"] == "Mechanistic inference only"


def test_direct_preclinical_evidence_needs_independent_traceability():
    row = _row(
        Scientific_Rationale="reduced fasting glucose and improved insulin sensitivity in vivo",
        Evidence_Level="Preclinical / mechanistic evidence",
        Evidence_Hierarchy_Detail="Validated in vivo",
        Source_Record_IDs="PMID:100",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Exploratory"
    assert result["Indication_Evidence_Mode"] in {"Direct preclinical", "Direct but limited"}


def test_direct_human_evidence_can_shortlist_with_one_traceable_source():
    row = _row(
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:101",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Scientific_Triage_Status"] == "Shortlist"
    assert result["Indication_Evidence_Mode"] == "Direct human/clinical"


def test_hard_stop_overrides_high_scientific_scores():
    row = _row(
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:102",
        Decision_Class="No-Go / safety concern",
        Go_Investigate_Hold_NoGo="No-Go",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    assert summary.iloc[0]["Scientific_Triage_Status"] == "Excluded"


def test_single_no_go_row_does_not_exclude_multirow_candidate_with_clean_support():
    risky = _row(
        Alternative_Plant="Balanced candidate",
        Scientific_Rationale="mechanistic evidence for insulin sensitivity",
        Target_or_Mechanism="AMPK and insulin sensitivity",
        Source_Record_IDs="PMID:201",
        Decision_Class="No-Go / safety concern",
        Go_Investigate_Hold_NoGo="No-Go",
    )
    clean = _row(
        Alternative_Plant="Balanced candidate",
        Scientific_Rationale="preclinical evidence for improved insulin sensitivity",
        Target_or_Mechanism="AMPK and insulin sensitivity",
        Source_Record_IDs="PMID:202",
        Decision_Class="Investigate",
        Go_Investigate_Hold_NoGo="Investigate",
    )
    clean2 = _row(
        Alternative_Plant="Balanced candidate",
        Scientific_Rationale="preclinical glucose uptake evidence",
        Target_or_Mechanism="GLUT4 glucose uptake",
        Source_Record_IDs="PMID:203",
        Decision_Class="Investigate",
        Go_Investigate_Hold_NoGo="Investigate",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([risky, clean, clean2]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    assert summary.iloc[0]["Scientific_Triage_Status"] != "Excluded"
    assert summary.iloc[0]["Safety_Regulatory_Score"] > 0


def test_replicated_mechanistic_evidence_can_support_rd_shortlist():
    rows = [
        _row(
            Alternative_Plant="Mechanistic candidate",
            Scientific_Rationale="candidate-specific AMPK activation and insulin sensitivity",
            Target_or_Mechanism="AMPK; insulin sensitivity",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="Validated in vivo",
            Source_Record_IDs="PMID:301",
        ),
        _row(
            Alternative_Plant="Mechanistic candidate",
            Scientific_Rationale="candidate-specific GLUT4 glucose uptake",
            Target_or_Mechanism="GLUT4; glucose uptake",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="Validated in vivo",
            Source_Record_IDs="PMID:302",
        ),
    ]
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame(rows),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    assert summary.iloc[0]["Scientific_Triage_Status"] == "Shortlist"


# =====================================================================
# Phase 3 (IMPLEMENTATION_PLAN.md) — Overall_Score reconciliation.
# =====================================================================

def test_rd_opportunity_score_is_an_alias_for_overall_score():
    df = pd.DataFrame([_row()])
    summary, _ = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    row = summary.iloc[0]
    assert row["R&D_Opportunity_Score"] == row["Overall_Score"]


def test_score_breakdown_is_a_parseable_dict_that_reconstructs_overall_score():
    from score_breakdown_schema import parse_score_breakdown, AUTHORITATIVE_CANONICAL_SECTIONS
    df = pd.DataFrame([_row()])
    summary, _ = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    row = summary.iloc[0]
    assert isinstance(row["Score_Breakdown"], dict)
    components = parse_score_breakdown(row["Score_Breakdown"])
    assert set(components.keys()) == AUTHORITATIVE_CANONICAL_SECTIONS
    assert round(sum(components.values()), 1) == row["Overall_Score"]


def test_three_separate_outputs_are_not_collapsed_into_one_number():
    # Evidence_Confidence, R&D_Opportunity_Score (Overall_Score), and
    # Decision_Class_AH/Go_Investigate_Hold_NoGo must all be present and
    # independently readable — not merged into a single field.
    df = pd.DataFrame([_row()])
    summary, _ = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    row = summary.iloc[0]
    for field in ("Evidence_Confidence", "R&D_Opportunity_Score", "Decision_Class_AH", "Go_Investigate_Hold_NoGo"):
        assert field in row.index
    # Evidence_Confidence is not simply a copy of the full Overall_Score —
    # it's the narrower evidence-only sub-combination.
    assert row["Evidence_Confidence"] != row["Overall_Score"] or row["Evidence_Confidence"] == 0


def test_excluded_plant_gets_a_hold_or_nogo_call_never_go():
    df = pd.DataFrame([_row(
        Scientific_Rationale="", Target_or_Mechanism="unrelated pathway",
        Applicability_Summary="",
    )])
    summary, _ = build_plant_candidate_shortlist(df, indication="anxiety", dosage_form="Infusion")
    row = summary.iloc[0]
    if row["Scientific_Triage_Status"] == "Excluded":
        assert row["Go_Investigate_Hold_NoGo"] in ("Hold", "No-Go")
        assert row["Decision_Class_AH"].startswith("G") or row["Decision_Class_AH"].startswith("H")


def _authoritative_row(plant, status, score, breakdown=None, **extra):
    row = {
        "Alternative_Plant": plant,
        "Scientific_Triage_Status": status,
        "Overall_Score": score,
        "Score_Breakdown": breakdown or {"Indication Relevance": score},
        "Score_Breakdown_Display": f"Indication Relevance .... {score}/35",
        "Evidence_Confidence": min(100.0, score),
        "Decision_Class_AH": "B — Established scientific candidate",
        "Go_Investigate_Hold_NoGo": "Go" if score >= 78 else "Investigate",
    }
    row.update(extra)
    return row


def test_merge_keeps_excluded_plants_with_their_rejection_reason():
    # Post-Phase-3-review correction: Excluded plants must NOT be dropped —
    # the platform needs to be able to explain why a plant was rejected,
    # which requires it still being present in the report-ready frame.
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plant A", "Rationale": "narrative A", "R&D_Opportunity_Score": 40},
        {"Alternative_Plant": "Plant B", "Rationale": "narrative B", "R&D_Opportunity_Score": 90},
    ])
    plant_summary = pd.DataFrame([
        _authoritative_row("Plant A", "Excluded", 20.0, Why_Selected_or_Rejected="Rejected: no safety data"),
        _authoritative_row("Plant B", "Shortlist", 85.0),
    ])
    merged = merge_authoritative_scores(raw_df, plant_summary)
    assert set(merged["Alternative_Plant"]) == {"Plant A", "Plant B"}
    excluded_row = merged[merged["Alternative_Plant"] == "Plant A"].iloc[0]
    assert excluded_row["Scientific_Triage_Status"] == "Excluded"
    assert excluded_row["Why_Selected_or_Rejected"] == "Rejected: no safety data"


def test_merge_all_excluded_still_returns_the_rows_not_empty():
    raw_df = pd.DataFrame([{"Alternative_Plant": "Plant A", "R&D_Opportunity_Score": 10}])
    plant_summary = pd.DataFrame([
        _authoritative_row("Plant A", "Excluded", 5.0, Why_Selected_or_Rejected="Rejected: safety concern"),
    ])
    merged = merge_authoritative_scores(raw_df, plant_summary)
    assert len(merged) == 1
    assert merged.iloc[0]["Scientific_Triage_Status"] == "Excluded"
    assert merged.iloc[0]["Why_Selected_or_Rejected"] == "Rejected: safety concern"


def test_merge_preserves_raw_narrative_fields_not_covered_by_the_authoritative_score():
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plant A", "Rationale": "rich narrative text",
         "Next_Experiment_Suggestion": "run assay X", "R&D_Opportunity_Score": 40},
    ])
    plant_summary = pd.DataFrame([_authoritative_row("Plant A", "Shortlist", 85.0)])
    merged = merge_authoritative_scores(raw_df, plant_summary)
    assert merged.iloc[0]["Rationale"] == "rich narrative text"
    assert merged.iloc[0]["Next_Experiment_Suggestion"] == "run assay X"


def test_merge_overwrites_score_fields_with_the_authoritative_values():
    # The raw row's OWN (pre-Phase-3) score must not survive the merge —
    # the plant_summary (Overall_Score-derived) value always wins.
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plant A", "R&D_Opportunity_Score": 12,
         "Decision_Class_AH": "G — Hold / insufficient evidence",
         "Go_Investigate_Hold_NoGo": "Hold"},
    ])
    plant_summary = pd.DataFrame([_authoritative_row("Plant A", "Shortlist", 91.0)])
    merged = merge_authoritative_scores(raw_df, plant_summary)
    row = merged.iloc[0]
    assert row["R&D_Opportunity_Score"] == 91.0
    assert row["Overall_Score"] == 91.0
    assert row["Decision_Class_AH"] == "B — Established scientific candidate"
    assert row["Go_Investigate_Hold_NoGo"] == "Go"


def test_merge_result_is_one_row_per_plant_sorted_by_overall_score_descending():
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Weak plant", "R&D_Opportunity_Score": 10},
        {"Alternative_Plant": "Strong plant", "R&D_Opportunity_Score": 10},
    ])
    plant_summary = pd.DataFrame([
        _authoritative_row("Weak plant", "Exploratory", 40.0),
        _authoritative_row("Strong plant", "Shortlist", 92.0),
    ])
    merged = merge_authoritative_scores(raw_df, plant_summary)
    assert list(merged["Alternative_Plant"]) == ["Strong plant", "Weak plant"]
    assert list(merged["Overall_Score"]) == [92.0, 40.0]


def test_merge_picks_richest_raw_row_when_a_plant_has_several():
    raw_df = pd.DataFrame([
        {"Alternative_Plant": "Plant A", "Rationale": "thin row", "R&D_Opportunity_Score": 5},
        {"Alternative_Plant": "Plant A", "Rationale": "richest row", "R&D_Opportunity_Score": 60},
    ])
    plant_summary = pd.DataFrame([_authoritative_row("Plant A", "Shortlist", 88.0)])
    merged = merge_authoritative_scores(raw_df, plant_summary)
    assert merged.iloc[0]["Rationale"] == "richest row"
    # Even the "richest" row's own score is still overwritten.
    assert merged.iloc[0]["R&D_Opportunity_Score"] == 88.0


def test_merge_empty_inputs_return_empty_dataframe_not_a_crash():
    assert merge_authoritative_scores(pd.DataFrame(), pd.DataFrame()).empty
    assert merge_authoritative_scores(None, pd.DataFrame([_authoritative_row("A", "Shortlist", 80.0)])).empty
    assert merge_authoritative_scores(pd.DataFrame([{"Alternative_Plant": "A"}]), pd.DataFrame()).empty


def test_merge_all_excluded_returns_empty_dataframe():
    # Superseded by test_merge_all_excluded_still_returns_the_rows_not_empty
    # above (post-Phase-3-review correction) — kept here only as an explicit
    # marker that the old "drop everything" behavior was intentionally
    # reversed, not silently changed.
    raw_df = pd.DataFrame([{"Alternative_Plant": "Plant A", "R&D_Opportunity_Score": 10}])
    plant_summary = pd.DataFrame([_authoritative_row("Plant A", "Excluded", 5.0)])
    merged = merge_authoritative_scores(raw_df, plant_summary)
    assert not merged.empty
    assert merged.iloc[0]["Scientific_Triage_Status"] == "Excluded"

# --- Post-record-level ranking-resolution correction -----------------------

def test_direct_human_indication_relevance_preserves_source_depth_differences():
    shallow = _row(
        Alternative_Plant="Shallow plant",
        Scientific_Rationale="improved fasting glucose",
        Clinical_Rationale="human clinical trial",
        Source_Record_IDs="PMID:1",
    )
    deep_rows = []
    for i, text in enumerate([
        "improved fasting glucose and HbA1c",
        "reduced postprandial glucose",
        "improved insulin sensitivity",
        "improved glycemic control",
    ], start=10):
        deep_rows.append(_row(
            Alternative_Plant="Deep plant",
            Scientific_Rationale=text,
            Clinical_Rationale="human randomized clinical trial",
            Source_Record_IDs=f"PMID:{i}",
        ))

    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([shallow] + deep_rows),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    scores = dict(zip(summary["Alternative_Plant"], summary["Indication_Relevance_Score"]))
    assert scores["Deep plant"] > scores["Shallow plant"]
    assert scores["Deep plant"] <= 35.0


def test_missing_safety_and_regulatory_data_is_not_scored_as_clean():
    row = _row(
        Scientific_Rationale="improved fasting glucose in humans",
        Safety_Flags="No explicit flag found",
        Interaction_Flags="No explicit flag found",
        Regulatory_Barriers="Not assessed",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]), indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    out = summary.iloc[0]
    assert out["Safety_Regulatory_Score"] == 8.0
    assert "not adequately assessed" in out["Score_Breakdown_Display"].lower() or out["Safety_Regulatory_Score"] < 11.0


def test_explicit_safety_and_market_information_create_real_differentiation():
    unknown = _row(
        Alternative_Plant="Unknown plant",
        Scientific_Rationale="improved fasting glucose in humans",
        Safety_Flags="No explicit flag found",
        Regulatory_Barriers="Not assessed",
        Novelty_Status="Indication-derived candidate",
        Market_Status="Search not performed",
    )
    supported = _row(
        Alternative_Plant="Supported plant",
        Scientific_Rationale="improved fasting glucose in humans",
        Safety_Flags="Well tolerated; no serious adverse events",
        Regulatory_Barriers="Traditional use monograph available",
        Novelty_Status="Underexplored white space",
        Market_Status="Limited products; emerging market",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([unknown, supported]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    indexed = summary.set_index("Alternative_Plant")
    assert indexed.loc["Supported plant", "Safety_Regulatory_Score"] > indexed.loc["Unknown plant", "Safety_Regulatory_Score"]
    assert indexed.loc["Supported plant", "Novelty_Market_Score"] > indexed.loc["Unknown plant", "Novelty_Market_Score"]
    assert indexed.loc["Unknown plant", "Novelty_Market_Score"] == 2.5
