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
        # Problem 1 (remaining defect 2) -- Candidate_Attribution_Verified
        # now fails CLOSED when absent (see candidate_shortlisting.py's
        # _row_has_verified_candidate_attribution). This fixture models a
        # complete, genuinely direct-evidence-bearing row (it already
        # asserts "Clinical / human evidence" / "Direct evidence" above),
        # so it correctly represents a record whose intervention
        # attribution WOULD have been established by a connector; True is
        # the honest default for what this fixture is modeling, not a
        # weakening of the new fail-closed rule.
        "Candidate_Attribution_Verified": True,
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
        # DEFECT 2 FIX (final pre-demo reliability pass): the original text
        # ("supports wound healing via collagen synthesis") is a mechanistic
        # claim, not a reported result -- it never states that an outcome
        # was actually observed. Under the corrected authority rule this
        # correctly no longer qualifies as verified direct human/clinical
        # evidence (it would score as UNVERIFIED_DIRECT_HUMAN_SIGNAL
        # instead). This test's purpose is to exercise a genuinely
        # verified direct-evidence candidate, so the fixture now states an
        # actual observed result for the requested indication.
        Scientific_Rationale="significant improvement in wound healing observed in a human clinical trial",
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


def test_weak_congener_is_excluded_by_its_own_evidence_not_by_genus():
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
    # by its own indication gate. Genus membership is not a scientific gate.
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


def test_two_relevant_congeners_are_judged_on_their_own_evidence():
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
    # This row is exploratory because its OWN evidence is only in-vitro, not
    # because Scutellaria baicalensis happens to share the genus.
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
    # DEFECT 7 FIX (pre-investor reliability repair): this row's
    # Safety_Flags/Regulatory_Barriers are both the default "no info"
    # placeholders (unknown, not reassuring) -- that must score 0.0, not
    # a positive score, per the corrected _safety_regulatory(). The
    # point of this test is that "unknown" no longer causes an automatic
    # Excluded (checked above via the explicit `prohibitive` signal), not
    # that unknown safety data earns positive points.
    assert summary.iloc[0]["Safety_Regulatory_Score"] == 0.0


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
    # DEFECT 7 FIX (pre-investor reliability repair): absence of safety
    # evidence and absence of a regulatory assessment must not earn
    # positive points (previously 5.0 + 3.0 = 8.0 for knowing nothing).
    assert out["Safety_Regulatory_Score"] == 0.0
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
    # DEFECT 6 FIX (pre-investor reliability repair): a missing/unperformed
    # market search must earn zero positive market-opportunity points, not
    # the previous 2.5 neutral-but-positive prior -- "not searched" is not
    # an opportunity. It must also not be labelled as commercial
    # novelty/white-space. Chemical/source novelty is tracked separately.
    assert indexed.loc["Unknown plant", "Novelty_Market_Score"] == 0.0
    assert indexed.loc["Unknown plant", "Commercial_Novelty_Status"] == "Commercial novelty not assessed"


def _mechanism_row(target_or_mechanism, **overrides):
    row = _row(
        Target_or_Mechanism=target_or_mechanism,
        Supported_Target_or_Mechanism=True,
        Indication_Match_Type="exact_indication",
        Indication_Match_Terms=target_or_mechanism,
    )
    row.update(overrides)
    return row


def test_duplicate_mechanism_rows_do_not_saturate_mechanism_support():
    # DEFECT 4 FIX (pre-investor reliability repair): 20 duplicate rows
    # for the SAME mechanism must not score as if 5 distinct mechanisms
    # were independently supported (2.0 pts/mechanism, capped at 10.0).
    from candidate_shortlisting import _mechanism_support

    duplicate_rows = pd.DataFrame([
        _mechanism_row("AMPK activation") for _ in range(20)
    ])
    points, tier = _mechanism_support(duplicate_rows, indication="metabolic support")
    assert points == 2.0
    assert tier == "Some"


def test_unrelated_mechanisms_do_not_score_for_requested_indication():
    from candidate_shortlisting import _mechanism_support

    unrelated_rows = pd.DataFrame([
        _row(Target_or_Mechanism="cytotoxic activity against unrelated cancer cell line",
             Supported_Target_or_Mechanism=True),
        _row(Target_or_Mechanism="pesticidal activity", Supported_Target_or_Mechanism=True),
    ])
    points, tier = _mechanism_support(unrelated_rows, indication="metabolic support")
    assert points == 0.0
    assert tier == "None"


def test_several_distinct_mechanisms_score_higher_than_one_duplicated_mechanism():
    from candidate_shortlisting import _mechanism_support

    one_duplicated = pd.DataFrame([_mechanism_row("AMPK activation") for _ in range(6)])
    several_distinct = pd.DataFrame([
        _mechanism_row("AMPK activation"),
        _mechanism_row("insulin sensitization"),
        _mechanism_row("glucose uptake stimulation"),
    ])
    dup_points, _ = _mechanism_support(one_duplicated, indication="metabolic support")
    distinct_points, _ = _mechanism_support(several_distinct, indication="metabolic support")
    assert distinct_points > dup_points


def test_duplicate_compound_rows_do_not_inflate_linked_mechanism_bonus():
    # DEFECT 5 FIX (pre-investor reliability repair): the linked-mechanism
    # bonus must de-duplicate by compound identity the same way the base
    # compound score already does -- 20 rows repeating the same compound
    # tied to a supported mechanism must not out-score one row.
    from candidate_shortlisting import _compound_quality

    one_row = pd.DataFrame([_row(
        Shared_or_Similar_Compound="specific alkaloid",
        Supported_Target_or_Mechanism=True,
    )])
    duplicate_rows = pd.DataFrame([_row(
        Shared_or_Similar_Compound="specific alkaloid",
        Supported_Target_or_Mechanism=True,
    ) for _ in range(20)])
    one_total, _ = _compound_quality(one_row, [])
    dup_total, _ = _compound_quality(duplicate_rows, [])
    assert one_total == dup_total


def test_zero_verified_outcome_scores_lower_than_verified_direct_human_evidence():
    # DEFECT 2 FIX (final pre-demo reliability pass), cahier acceptance
    # test: a candidate with strong indication-match/AI-semantic relevance
    # but zero verified outcome-specific human evidence must score lower
    # on direct clinical relevance than an otherwise-equivalent candidate
    # with verified direct human outcome evidence, and must not be
    # represented as verified direct clinical evidence.
    from candidate_shortlisting import _indication_relevance_detail

    unverified = pd.DataFrame([_row(
        Alternative_Plant="Unverified candidate",
        Scientific_Rationale="human clinical trial", Clinical_Rationale="clinical evidence",
        Evidence_Level="Clinical / human evidence", Evidence_Hierarchy_Detail="Clinical trial",
        Indication_Match_Type="exact_indication", Indication_Match_Terms="Metabolic & blood sugar support",
        Source_Record_IDs="PMID:201",
    )])
    verified = pd.DataFrame([_row(
        Alternative_Plant="Verified candidate",
        Scientific_Rationale="clinical trial reported improved fasting glucose",
        Clinical_Rationale="human clinical trial reported significant improvement in fasting glucose",
        Evidence_Level="Clinical / human evidence", Evidence_Hierarchy_Detail="Clinical trial",
        Indication_Match_Type="exact_indication", Indication_Match_Terms="Metabolic & blood sugar support",
        Source_Record_IDs="PMID:202",
    )])
    unverified_points, _, unverified_mode, _ = _indication_relevance_detail(
        unverified, "Metabolic & blood sugar support"
    )
    verified_points, _, verified_mode, _ = _indication_relevance_detail(
        verified, "Metabolic & blood sugar support"
    )
    assert verified_mode == "Direct human/clinical"
    assert unverified_mode == "UNVERIFIED_DIRECT_HUMAN_SIGNAL"
    assert unverified_points < verified_points
    # Never allowed to reach the verified-direct-human score range.
    assert unverified_points < 28.0

    summary, _ = build_plant_candidate_shortlist(
        pd.concat([unverified, verified], ignore_index=True),
        indication="Metabolic & blood sugar support", dosage_form="Infusion",
    )
    indexed = summary.set_index("Alternative_Plant")
    assert indexed.loc["Verified candidate", "Indication_Evidence_Mode"] == "Direct human/clinical"
    assert indexed.loc["Unverified candidate", "Indication_Evidence_Mode"] == "UNVERIFIED_DIRECT_HUMAN_SIGNAL"
    assert indexed.loc["Verified candidate", "Indication_Relevance_Score"] > indexed.loc["Unverified candidate", "Indication_Relevance_Score"]
    assert indexed.loc["Unverified candidate", "Outcome_Specific_Human_Evidence_Count"] == 0
    assert indexed.loc["Verified candidate", "Outcome_Specific_Human_Evidence_Count"] >= 1


def test_established_class_requires_verified_evidence_not_score_alone():
    # DEFECT 8 FIX (final pre-demo reliability pass): a high Overall_Score
    # built from market/compound/mechanism support -- but with an
    # unverified direct-human signal, not verified outcome-specific human
    # evidence -- must not be labelled "B - Established scientific
    # candidate". Only a candidate whose evidence actually clears go_call
    # == "Go" AND carries verified ("Direct human/clinical") indication
    # evidence may receive that label.
    from candidate_shortlisting import _derive_decision_class_ah, _STRONG_SCORE_THRESHOLD

    high_score_unverified = _derive_decision_class_ah(
        "Shortlist", _STRONG_SCORE_THRESHOLD + 10.0,
        go_call="Investigate — verify before proceeding",
        indication_mode="UNVERIFIED_DIRECT_HUMAN_SIGNAL",
    )
    assert high_score_unverified != "B — Established scientific candidate"

    high_score_verified_but_not_go = _derive_decision_class_ah(
        "Shortlist", _STRONG_SCORE_THRESHOLD + 10.0,
        go_call="Investigate — complete safety/interaction review",
        indication_mode="Direct human/clinical",
    )
    assert high_score_verified_but_not_go != "B — Established scientific candidate"

    genuinely_established = _derive_decision_class_ah(
        "Shortlist", _STRONG_SCORE_THRESHOLD + 10.0,
        go_call="Go",
        indication_mode="Direct human/clinical",
    )
    assert genuinely_established == "B — Established scientific candidate"

    # Legacy callers that don't pass go_call/indication_mode (e.g. a
    # commercial-only rescore with reduced context) must never default to
    # "Established" on missing context.
    no_context = _derive_decision_class_ah("Shortlist", _STRONG_SCORE_THRESHOLD + 10.0)
    assert no_context != "B — Established scientific candidate"


def test_incomplete_target_definition_blocks_go_but_not_score_or_shortlist():
    # TARGET DEFINITION COMPLETENESS FIX (final pre-demo reliability
    # pass): a project that only specifies indication + preparation (no
    # target dose/plant part/route) must not have its Scientific_Evidence_
    # Score penalized (Defect 3 fix), must still be able to reach
    # Shortlist, but must NOT receive an unjustified final "Go" -- the
    # product definition itself is incomplete. This must be the least
    # restrictive behavior: Investigate, never Excluded/No-Go/Hold.
    from candidate_shortlisting import _derive_go_call, _STRONG_SCORE_THRESHOLD

    complete = _derive_go_call(
        "Shortlist", _STRONG_SCORE_THRESHOLD + 5.0,
        dosage_compatibility="Compatible", safety_tier="Explicit reassuring evidence",
        outcome_label="Predominantly positive results",
        target_definition_completeness="complete",
    )
    assert complete == "Go"

    incomplete = _derive_go_call(
        "Shortlist", _STRONG_SCORE_THRESHOLD + 5.0,
        dosage_compatibility="Compatible", safety_tier="Explicit reassuring evidence",
        outcome_label="Predominantly positive results",
        target_definition_completeness="incomplete",
    )
    assert incomplete != "Go"
    assert incomplete.startswith("Investigate")
    assert "target product definition" in incomplete.lower()


def test_one_malformed_candidate_does_not_crash_the_whole_batch(monkeypatch):
    # DEFECT 10 FIX (final pre-demo reliability pass): a single candidate
    # whose evidence causes an internal processing exception must not take
    # down the whole run -- the remaining, well-formed candidates must
    # still be scored and returned. The per-plant scoring path is already
    # fairly defensive against odd input shapes, so this forces a genuine
    # exception deterministically (monkeypatching a function the loop body
    # calls for every plant) rather than relying on a specific malformed
    # value that might already be handled elsewhere.
    import candidate_shortlisting as cs_mod

    good_row = _row(Alternative_Plant="Well-formed candidate")
    bad_row = _row(Alternative_Plant="Malformed candidate")
    df = pd.DataFrame([good_row, bad_row])

    real_mechanism_support = cs_mod._mechanism_support

    def _boom(group, indication=""):
        plant_name = str(group["Alternative_Plant"].iloc[0])
        if plant_name == "Malformed candidate":
            raise ValueError("simulated malformed-evidence processing failure")
        return real_mechanism_support(group, indication)

    monkeypatch.setattr(cs_mod, "_mechanism_support", _boom)

    summary, audit = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    plants = set(summary["Alternative_Plant"])
    assert "Well-formed candidate" in plants
    assert "Malformed candidate" in plants
    good_summary = summary[summary["Alternative_Plant"] == "Well-formed candidate"].iloc[0]
    assert good_summary["Scientific_Triage_Status"] in {"Shortlist", "Exploratory"}
    malformed_summary = summary[summary["Alternative_Plant"] == "Malformed candidate"].iloc[0]
    assert malformed_summary["Scientific_Triage_Status"] == "Excluded"
    assert malformed_summary.get("Processing_Status") == "INCOMPLETE"


def test_unverified_direct_human_signal_can_reach_provisional_shortlist_but_never_go_or_established():
    # DEFECT 2 FIX, REVISED after live production feedback: a candidate
    # with substantive indication relevance/evidence quality and a
    # traceable primary-tier record, but zero verified outcome-specific
    # human evidence, now gets a PROVISIONAL Shortlist placement (fixing
    # the real-run collapse to a single plant) -- but must still never
    # reach "Go" or "B - Established scientific candidate" through this
    # signal alone.
    rows = [_row(
        Alternative_Plant="Provisional candidate",
        Scientific_Rationale="human clinical trial", Clinical_Rationale="clinical evidence",
        Evidence_Level="Clinical / human evidence", Evidence_Hierarchy_Detail="Clinical trial",
        Indication_Match_Type="exact_indication", Indication_Match_Terms="Metabolic & blood sugar support",
        Source_Record_IDs=f"PMID:{300+i}",
    ) for i in range(4)]
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame(rows), indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    row = summary.iloc[0]
    assert row["Indication_Evidence_Mode"] == "UNVERIFIED_DIRECT_HUMAN_SIGNAL"
    assert row["Outcome_Specific_Human_Evidence_Count"] == 0
    assert row["Scientific_Triage_Status"] == "Shortlist"
    assert row["Go_Investigate_Hold_NoGo"] != "Go"
    assert row["Decision_Class_AH"] != "B — Established scientific candidate"


def test_evidence_adjudication_ids_tolerate_scalar_nan_values():
    # STEP5_FLOAT_ITERABLE_FIX hardening: a cached/legacy adjudication
    # response with a scalar NaN in an evidence-ID field must not crash
    # with "'float' object is not iterable".
    from evidence_adjudication_engine import _as_id_list

    assert _as_id_list(float("nan")) == []
    assert _as_id_list(None) == []
    assert _as_id_list(["E1", "E2"]) == ["E1", "E2"]
    assert _as_id_list(("E1",)) == ["E1"]
    assert _as_id_list(3.5) == []


def test_target_unspecified_dimension_does_not_crash_multi_record_applicability_aggregation():
    # BUG FIX (2026-09-10): found via real production data -- 150/151
    # candidates in a live Sleep run were silently falling into the
    # Defect-10 crash guard with ValueError("tuple.index(x): x not in
    # tuple"). Root cause: the per-record applicability aggregation loop in
    # _scientific_evidence_components() only skipped NOT_APPLICABLE, not
    # the newer TARGET_UNSPECIFIED status (Defect 3 fix) -- which is
    # extremely common in real projects (most don't specify every one of
    # plant_part/route/dose). Any candidate with 2+ primary-tier records
    # crashed here. This reproduces the exact real-world shape: two
    # primary-tier records, a target_context built the same way production
    # builds it (via build_transferability_target_context), leaving
    # route/dose/plant_part unspecified.
    from standard_evidence_builder import build_transferability_target_context

    rows = [_row(
        Alternative_Plant="Humulus lupulus",
        Source_Record_IDs=f"PMID:{500+i}",
        Clinical_Rationale="human randomized controlled trial reported significant improvement in sleep quality",
        Evidence_Level="Clinical / human evidence", Evidence_Hierarchy_Detail="randomized controlled trial",
        Indication_Match_Type="exact_indication", Indication_Match_Terms="sleep",
    ) for i in range(2)]
    target_context = build_transferability_target_context(
        "sleep", "Infusion", {"target_indication": "sleep", "dosage_form": "Infusion"}
    )
    summary, audit = build_plant_candidate_shortlist(
        pd.DataFrame(rows), indication="sleep", dosage_form="Infusion", target_context=target_context
    )
    row = summary.iloc[0]
    assert row.get("Processing_Status") != "INCOMPLETE"
    assert pd.isna(row.get("Processing_Error")) or not row.get("Processing_Error")
    assert row["Scientific_Triage_Status"] in {"Shortlist", "Exploratory"}


def test_crash_guard_row_alone_never_breaks_the_post_loop_sort():
    # BUG FIX (2026-09-10): if every single plant in a batch hits the
    # Defect-10 crash guard (no successful row survives), pd.DataFrame(rows)
    # never creates Traceable_Source_Count/Distinctive_Compound_Count at
    # all, and the post-loop sort raised KeyError -- turning a partial
    # failure into a total one. Force the crash guard for the only plant in
    # the batch and confirm the run still completes and returns a row.
    import candidate_shortlisting as cs_mod

    def _boom(group, indication=""):
        raise ValueError("simulated malformed-evidence processing failure")

    df = pd.DataFrame([_row(Alternative_Plant="Only candidate")])
    original = cs_mod._mechanism_support
    cs_mod._mechanism_support = _boom
    try:
        summary, audit = build_plant_candidate_shortlist(df, dosage_form="Infusion")
    finally:
        cs_mod._mechanism_support = original
    assert len(summary) == 1
    assert summary.iloc[0]["Processing_Status"] == "INCOMPLETE"
