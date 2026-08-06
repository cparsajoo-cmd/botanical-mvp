import pandas as pd

from candidate_shortlisting import build_plant_candidate_shortlist


def _row(plant="Plant A", source="PMID:1", direction="positive", preparation="Compatible", safety="Well tolerated; no serious adverse events"):
    return {
        "Alternative_Plant": plant,
        "Reference_Plant": "Indication-centric discovery",
        "Reference_Compound": "Not used as candidate gate",
        "Shared_or_Similar_Compound": "specific-marker",
        "Novelty_Status": "Search not performed",
        "Target_or_Mechanism": "blood glucose; insulin resistance",
        "Target_Provenance": "Candidate-specific indication evidence",
        "Evidence_Level": "Randomized clinical trial",
        "Evidence_Hierarchy_Detail": "Randomized controlled trial",
        "Candidate_Evidence_Strength_Tier": "Direct human evidence",
        "Scientific_Rationale": "Type 2 diabetes blood glucose fasting glucose outcome",
        "Clinical_Rationale": "Human randomized clinical evidence",
        "Evidence_Source": source,
        "Source_Record_IDs": source,
        "Result_Direction": direction,
        "Has_Negative_Evidence": direction in {"no significant difference", "no effect", "worsened"},
        "Negative_Evidence_Types": "Negative/null reported result" if direction in {"no significant difference", "no effect", "worsened"} else "",
        "Preparation_Applicability": preparation,
        "Applicability_Summary": {
            "critical_mismatches": ["preparation mismatch"] if preparation == "Mismatch" else [],
            "evidence_items": [{"applicability_classification": preparation}],
        },
        "Safety_Flags": safety,
        "Interaction_Flags": "",
        "Regulatory_Barriers": "Traditional use monograph",
        "Market_Status": "Search not performed",
        "R&D_Opportunity_Score": 50,
    }


def test_null_human_evidence_cannot_be_go_or_high_relevance():
    """PHASE 5 REGRESSION (converted from a pre-Phase-5 characterization
    test per the Phase 5 implementation brief §13 — "direction embedded
    in Indication Relevance" is one of the five named cases).

    OLD assertion (pre-Phase-5): `Indication_Relevance_Score <= 15` —
    this relied on _indication_relevance_detail_authoritative()
    discounting its own points for null/negative human evidence, the
    exact conceptually-misplaced mechanism the Phase 5 audit identified
    (Direction affecting a component whose job is "is this evidence
    about the right topic," not "does this evidence support efficacy").

    NEW, approved behavior: Direction no longer touches Indication_
    Relevance at all — a positive and a negative/null RCT with the same
    indication relationship now score IDENTICAL Indication_Relevance
    (confirmed: 33.4 here, unaffected by direction). Direction instead
    affects ONLY Scientific_Evidence_Score, via Direction_Factor /
    Evidence_Consistency_Class (addendum §1/§9) — a null-only evidence
    pool (2 records, both null) classifies CONSISTENT_NULL ->
    Direction_Factor=0.00, which zeroes Scientific_Evidence_Score
    (0.00) regardless of Evidence_Quality_Score's own magnitude, per the
    multiplicative formula. This is the SAME underlying protection
    (null evidence cannot look scientifically strong) implemented in
    the correct, dedicated place instead of the wrong one — not a
    weakening of the check.
    """
    rows = [_row(source="PMID:1", direction="no significant difference"),
            _row(source="PMID:2", direction="no effect")]
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame(rows), indication="type 2 diabetes", dosage_form="Infusion")
    row = summary.iloc[0]
    assert row["Indication_Relevance_Score"] == 33.4, (
        "Indication_Relevance must be IDENTICAL to the positive-evidence "
        "case now that Direction has been removed from this component "
        "(addendum §1/§9) -- this is a positive assertion of the fix, "
        "not a loosened check."
    )
    assert row["Evidence_Consistency_Class"] == "CONSISTENT_NULL"
    assert row["Direction_Factor"] == 0.0
    assert row["Scientific_Evidence_Score"] == 0.0
    assert row["Scientific_Triage_Status"] == "Exploratory"
    assert not str(row["Go_Investigate_Hold_NoGo"]).startswith("Go")
    assert row["Outcome_Consistency"] == "No demonstrated benefit"


def test_mixed_results_score_below_consistently_positive_results():
    positive_rows = [_row("Positive plant", "PMID:1", "positive"), _row("Positive plant", "PMID:2", "improved")]
    mixed_rows = [_row("Mixed plant", "PMID:3", "positive"), _row("Mixed plant", "PMID:4", "no significant difference")]
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame(positive_rows + mixed_rows), indication="type 2 diabetes", dosage_form="Infusion")
    scores = summary.set_index("Alternative_Plant")["Overall_Score"]
    assert scores["Positive plant"] > scores["Mixed plant"]


def test_preparation_mismatch_is_excluded_for_selected_product_form():
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame([_row(preparation="Mismatch")]), indication="type 2 diabetes", dosage_form="Infusion")
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Excluded"
    assert "preparation" in row["Why_Selected_or_Rejected"].lower()


def test_unknown_safety_or_preparation_blocks_go_but_not_scientific_review():
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([_row(preparation="Unknown", safety="")]),
        indication="type 2 diabetes", dosage_form="Infusion",
    )
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Shortlist"
    assert str(row["Go_Investigate_Hold_NoGo"]).startswith("Investigate")


def test_go_requires_positive_results_compatible_preparation_and_explicit_safety():
    """PHASE 5 REGRESSION (converted per the Phase 5 implementation
    brief §13): this fixture's rows never carry the Phase-5 evidence-
    vs-target fields (Evidence_Species/Indication_Match_Type) — they
    predate the applicability contract and rely only on the legacy
    Preparation_Applicability="Compatible" signal (which the Phase 5
    legacy adapter DOES pick up, giving 'preparation'=MATCH) and free
    text for indication (which the authoritative contract deliberately
    does NOT re-derive from text a second time -- addendum §3.4/main
    audit's core "one authoritative relevance computation" finding).
    With no Indication_Match_Type on these rows, the 'indication'
    dimension is honestly UNKNOWN (not assumed MATCH), so
    Plant_Applicability_Factor = min(preparation=MATCH=1.00,
    indication=UNKNOWN=0.60) = 0.60 — reducing Scientific_Evidence_Score
    enough that Overall_Score (77.8) falls just under the Go threshold
    (78), yielding "Investigate" rather than "Go".

    This is not a defect: a candidate whose indication-match status was
    never actually run through the authoritative relevance engine
    genuinely SHOULD be treated as less certain than one that was —
    exactly the "missing data must not receive full credit" principle
    the whole Phase 5 audit exists to enforce, now applied to
    Applicability the same way it already applied to Direction/
    Consistency/Market status. A fixture using the modern
    Indication_Match_Type field would reach Go; this one deliberately
    tests the legacy/no-target-context path.
    """
    rows = [_row(source=f"PMID:{i}", direction="positive") for i in range(1, 8)]
    summary, _ = build_plant_candidate_shortlist(pd.DataFrame(rows), indication="type 2 diabetes", dosage_form="Infusion")
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Shortlist"
    assert row["Outcome_Consistency"] == "Predominantly positive results"
    assert row["Dosage_Form_Compatibility"] == "Compatible"
    assert row["Dimension_Status"]["preparation"] == "MATCH", (
        "The legacy Preparation_Applicability='Compatible' adapter "
        "should map to a real MATCH (addendum §3.4 legacy adapter)."
    )
    assert row["Dimension_Status"]["indication"] == "UNKNOWN", (
        "No Indication_Match_Type on these rows -- honestly UNKNOWN, "
        "not assumed MATCH from free text."
    )
    assert row["Overall_Score"] == 77.8
    assert row["Go_Investigate_Hold_NoGo"] == "Investigate"


def test_discovery_preserves_record_result_preparation_and_safety_fields():
    from indication_candidate_discovery import discover_indication_candidates

    class Engine:
        def __init__(self):
            self.evidence_df = pd.DataFrame()
            self.scientific_evidence_df = pd.DataFrame()
            self.evidence_records_df = pd.DataFrame([{
                "id": 10,
                "plant": "Ginkgo biloba",
                "target_indication": "Type 2 diabetes",
                "study_type": "Systematic review and meta-analysis",
                "primary_outcome": "HbA1c and fasting glucose",
                "result_direction": "no significant difference",
                "preparation": "standardized dry extract capsule",
                "safety_findings": "bleeding interaction concern",
                "interactions": "anticoagulant interaction",
                "source_url": "https://example.org/ginkgo",
            }])
        def _candidate_frame(self):
            return pd.DataFrame([{"Scientific_Name": "Ginkgo biloba", "Known_Active_Compounds": "ginkgolide", "Known_Targets": "blood glucose"}])
        def _pick(self, row, names):
            for name in names:
                if name in row and pd.notna(row[name]) and str(row[name]).strip():
                    return str(row[name])
            return ""
        def _split_compound_terms(self, value):
            return [str(value)] if str(value).strip() else []
        def _evidence_level(self, text):
            return "Systematic review and meta-analysis"

    raw = discover_indication_candidates(Engine(), "Type 2 diabetes", dosage_form="Infusion")
    row = raw.iloc[0]
    assert row["Result_Direction"] == "no significant difference"
    assert row["Preparation_Applicability"] == "Mismatch"
    assert "bleeding" in row["Safety_Flags"].lower()
    assert "anticoagulant" in row["Interaction_Flags"].lower()
    assert bool(row["Has_Negative_Evidence"])
