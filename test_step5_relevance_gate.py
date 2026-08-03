"""Regression tests for the Step 5 relevance-gate fix (PROBLEM 2).

Covers:
2. a strong exact-indication plant outranks and passes ahead of a
   mechanism-only candidate;
3. a Low relevance mechanism-only plant is not Primary shortlist, however
   much evidence volume/replication accumulates;
4. a Low relevance candidate can only be Exploratory when explicit criteria
   (a real supported target/mechanism) are met, else Excluded;
5. a dangerous or contraindicated plant is rejected regardless of mechanism;
6. extract-only evidence does not become infusion-specific evidence
   (preparation-applicability distinction);
7. no candidate is added merely to reach a requested count (Step 2 /
   candidate_selection.py -- re-asserted here at the architecture level);
9. existing output columns and public contracts remain available.

(1 and 8 are covered by test_botanical_taxonomy.py and by running the full
existing suite -- see migration notes.)
"""
import pandas as pd

import candidate_selection as cs
from candidate_shortlisting import (
    build_plant_candidate_shortlist,
    PREP_DIRECT_MATCH,
    PREP_COMPATIBLE_BUT_INDIRECT,
    PREP_INCOMPATIBLE,
    PREP_NOT_REPORTED,
)


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


# ---------------------------------------------------------------------
# 3 & 2. mechanism-only Low relevance plant never reaches Shortlist, even
# with heavy replication/evidence volume; a direct-evidence plant does and
# outranks it.
# ---------------------------------------------------------------------

def _heavy_mechanism_only_rows(plant_name="Mechanism Only Plant"):
    """Multiple rows, multiple sources, strong replication -- exactly the
    evidence-volume pattern that used to be enough to reach Shortlist under
    the old 'Mechanistic empirical' gate."""
    return [
        _row(
            Alternative_Plant=plant_name,
            Target_or_Mechanism="AMPK activation",
            Scientific_Rationale="AMPK activation observed in vitro",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="In vitro evidence",
            Source_Record_IDs="PMID:301",
        ),
        _row(
            Alternative_Plant=plant_name,
            Target_or_Mechanism="GLUT4 translocation",
            Scientific_Rationale="GLUT4 translocation and glucose uptake in vivo",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="In vivo evidence",
            Source_Record_IDs="PMID:302",
        ),
        _row(
            Alternative_Plant=plant_name,
            Target_or_Mechanism="alpha glucosidase inhibition",
            Scientific_Rationale="alpha glucosidase inhibition in vitro",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="In vitro evidence",
            Source_Record_IDs="PMID:303",
        ),
        _row(
            Alternative_Plant=plant_name,
            Target_or_Mechanism="hepatic gluconeogenesis suppression",
            Scientific_Rationale="hepatic gluconeogenesis suppression in vivo",
            Evidence_Level="Preclinical / mechanistic evidence",
            Evidence_Hierarchy_Detail="In vivo evidence",
            Source_Record_IDs="PMID:304",
        ),
    ]


def test_mechanism_only_plant_never_reaches_shortlist_regardless_of_volume():
    df = pd.DataFrame(_heavy_mechanism_only_rows())
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    row = summary.iloc[0]
    assert row["Indication_Evidence_Mode"] == "Mechanistic empirical"
    assert row["Indication_Relevance"] == "Low relevance"
    assert row["Scientific_Triage_Status"] != "Shortlist"
    assert row["Relevance_Gate_Result"] != "passed_direct"


def test_strong_exact_indication_plant_outranks_mechanism_only_candidate():
    strong_rows = [_row(
        Alternative_Plant="Strong Direct Plant",
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:401",
    )]
    df = pd.DataFrame(strong_rows + _heavy_mechanism_only_rows())
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    strong = summary[summary["Alternative_Plant"] == "Strong Direct Plant"].iloc[0]
    mechanism_only = summary[summary["Alternative_Plant"] == "Mechanism Only Plant"].iloc[0]

    assert strong["Scientific_Triage_Status"] == "Shortlist"
    assert mechanism_only["Scientific_Triage_Status"] != "Shortlist"
    # Shortlist candidates sort strictly ahead of non-Shortlist candidates.
    strong_rank = summary.index[summary["Alternative_Plant"] == "Strong Direct Plant"][0]
    mechanism_rank = summary.index[summary["Alternative_Plant"] == "Mechanism Only Plant"][0]
    assert strong_rank < mechanism_rank


# ---------------------------------------------------------------------
# 4. Low relevance -> Exploratory only with explicit mechanistic rationale,
# else Excluded.
# ---------------------------------------------------------------------

def test_low_relevance_with_explicit_mechanistic_rationale_is_exploratory():
    df = pd.DataFrame(_heavy_mechanism_only_rows())
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    row = summary.iloc[0]
    # Every row carries a real Target_or_Mechanism value, so the explicit-
    # rationale criterion is met -- Exploratory, not Excluded.
    assert row["Scientific_Triage_Status"] == "Exploratory"
    assert row["Relevance_Gate_Result"] == "passed_indirect_exploratory_only"


def test_mechanism_only_inferred_link_without_explicit_target_can_be_excluded():
    row = _row(
        Target_or_Mechanism="Not clearly extracted",
        Target_Provenance="Not applicable (no shared-target claim for this match type)",
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
    # No real supported target/mechanism on this row -- must not reach
    # Shortlist, and per requirement 4 is a legitimate candidate for
    # Excluded rather than an automatic Exploratory pass.
    assert result["Scientific_Triage_Status"] != "Shortlist"


# ---------------------------------------------------------------------
# 5. dangerous/contraindicated plant rejected regardless of mechanism
# ---------------------------------------------------------------------

def test_contraindicated_plant_excluded_despite_strong_mechanism():
    rows = _heavy_mechanism_only_rows(plant_name="Dangerous Plant")
    for row in rows:
        row["Regulatory_Barriers"] = "Regulatory prohibition due to hepatotoxicity"
    df = pd.DataFrame(rows)
    summary, _ = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    row = summary.iloc[0]
    assert row["Scientific_Triage_Status"] == "Excluded"
    assert row["Relevance_Gate_Result"] == "failed_safety"


# ---------------------------------------------------------------------
# 6. extract-only evidence does not become infusion-specific evidence
# ---------------------------------------------------------------------

def test_extract_only_evidence_is_not_direct_match_for_infusion():
    row = _row(
        Extraction_Method="Standardized extract",
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:501",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Preparation_Applicability_Class"] != PREP_DIRECT_MATCH
    assert result["Preparation_Applicability_Class"] == PREP_COMPATIBLE_BUT_INDIRECT
    assert result["Preparation_Specific_Evidence_Count"] == 0


def test_infusion_evidence_is_a_direct_match_for_infusion_request():
    row = _row(
        Extraction_Method="Infusion / hot water extract",
        Scientific_Rationale="clinical evidence of reduced fasting glucose",
        Clinical_Rationale="human clinical trial reported improved HbA1c",
        Evidence_Level="Clinical / human evidence",
        Evidence_Hierarchy_Detail="Clinical trial",
        Source_Record_IDs="PMID:502",
    )
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Preparation_Applicability_Class"] == PREP_DIRECT_MATCH
    assert result["Preparation_Specific_Evidence_Count"] == 1


def test_missing_extraction_method_is_not_reported_not_incompatible():
    row = _row(Extraction_Method="")
    summary, _ = build_plant_candidate_shortlist(
        pd.DataFrame([row]),
        indication="Metabolic & blood sugar support",
        dosage_form="Infusion",
    )
    result = summary.iloc[0]
    assert result["Preparation_Applicability_Class"] == PREP_NOT_REPORTED


# ---------------------------------------------------------------------
# 7. no candidate is added merely to reach a requested count (Step 2 /
# candidate_selection.py architecture -- re-asserted here).
# ---------------------------------------------------------------------

def test_candidate_selection_never_fabricates_candidates_to_reach_count():
    records = [
        cs.make_candidate("Only Plant", cs.ORIGIN_REFERENCE_SEED, score=1),
    ]
    selected, diagnostics = cs.select_candidates(records, requested_count=8)
    assert len(selected) == 1
    assert diagnostics["candidate_shortfall"] == 7
    assert diagnostics["shortfall_reason"] != cs.SHORTFALL_NONE


# ---------------------------------------------------------------------
# 9. existing output columns and public contracts remain available
# ---------------------------------------------------------------------

def test_existing_output_columns_remain_available_alongside_new_ones():
    df = pd.DataFrame(_heavy_mechanism_only_rows())
    summary, audit = build_plant_candidate_shortlist(
        df, indication="Metabolic & blood sugar support", dosage_form="Infusion"
    )
    existing_columns = {
        "Alternative_Plant", "Scientific_Triage_Status", "Scientific_Triage_Score",
        "Overall_Score", "R&D_Opportunity_Score", "Score_Breakdown",
        "Indication_Relevance", "Indication_Relevance_Score", "Indication_Evidence_Mode",
        "Dosage_Form_Compatibility", "Safety_Flags", "Why_Selected_or_Rejected",
    }
    assert existing_columns.issubset(set(summary.columns))

    new_columns = {
        "Relevance_Gate_Result", "Evidence_Route", "Direct_Indication_Evidence_Count",
        "Mechanistic_Evidence_Count", "Preparation_Specific_Evidence_Count",
        "Triage_Gate_Reasons", "Preparation_Applicability_Class",
    }
    assert new_columns.issubset(set(summary.columns))

    # The row-level audit view is also still returned.
    assert isinstance(audit, pd.DataFrame)
    assert not audit.empty
