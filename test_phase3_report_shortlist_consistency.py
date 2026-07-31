"""End-to-end integration test for IMPLEMENTATION_PLAN.md Phase 3: the
shortlist (candidate_shortlisting.build_plant_candidate_shortlist) and the
downloaded report (pharma_report_generator.generate_pharma_report) must
agree on the top candidate, because both now derive from the same
authoritative Overall_Score via merge_authoritative_scores() — the exact
divergence this phase was created to close.
"""

import pandas as pd

from candidate_shortlisting import build_plant_candidate_shortlist, merge_authoritative_scores
from pharma_report_generator import generate_pharma_report


def _raw_row(plant, indication_text, legacy_score):
    # legacy_score deliberately does NOT correlate with which plant should
    # actually win — if anything downstream still used it, this test would
    # catch that by the report/shortlist top pick disagreeing.
    return {
        "Reference_Plant": "Indication-centric discovery",
        "Reference_Compound": "Not used as candidate gate",
        "Alternative_Plant": plant,
        "Shared_or_Similar_Compound": "Baicalein",
        "Target_or_Mechanism": "GABAA receptor modulation relevant to anxiety",
        "Target_Provenance": "supported",
        "Evidence_Source": "PubMed",
        "Source_Record_IDs": f"PMID:{hash(plant) % 10000}",
        "Evidence_Level": "Human RCT",
        "Candidate_Evidence_Strength_Tier": "High",
        "Scientific_Rationale": f"{indication_text} via GABA modulation",
        "Applicability_Summary": "anxiety relief demonstrated in clinical trial",
        "Novelty_Status": "Underexplored",
        "Market_Status": "Not saturated",
        "Regulatory_Barriers": "None identified",
        "Has_Negative_Evidence": False,
        "Negative_Evidence_Types": "",
        "Safety_Flags": "No explicit flag found",
        "Interaction_Flags": "No explicit flag found",
        "R&D_Opportunity_Score": legacy_score,
        "Rationale": f"Full narrative for {plant}.",
    }


def test_report_top_candidate_matches_shortlist_top_candidate():
    raw_df = pd.DataFrame([
        # Weak evidence but a deliberately HIGH legacy row-level score —
        # would win if the report still used the old, unreconciled score.
        _raw_row("Weakly-evidenced plant", "no anxiety-specific text here", legacy_score=99),
        # Strong, genuinely indication-specific evidence but a LOW legacy
        # score — must win once Overall_Score is authoritative.
        _raw_row("Strongly-evidenced plant", "anxiety reduction demonstrated", legacy_score=10),
    ])
    # Give the "weak" plant no real indication-specific text so its
    # authoritative Overall_Score is genuinely lower.
    raw_df.loc[raw_df["Alternative_Plant"] == "Weakly-evidenced plant", "Scientific_Rationale"] = "unrelated antioxidant assay"
    raw_df.loc[raw_df["Alternative_Plant"] == "Weakly-evidenced plant", "Applicability_Summary"] = ""

    plant_summary, _ = build_plant_candidate_shortlist(raw_df, indication="anxiety", dosage_form="Infusion")
    shortlist_top = plant_summary[plant_summary["Scientific_Triage_Status"] != "Excluded"].iloc[0]["Alternative_Plant"]

    report_ready_df = merge_authoritative_scores(raw_df, plant_summary)
    report_markdown = generate_pharma_report(
        report_ready_df, indication="anxiety", dosage_form="Infusion", market="EU",
    )

    # The report's own "## Top Candidates" section must lead with the same
    # plant the shortlist ranks first — not the plant with the highest
    # legacy (pre-Phase-3) row-level score.
    top_section_start = report_markdown.find("## Top Candidates")
    next_section_start = report_markdown.find("\n## ", top_section_start + 1)
    top_section = report_markdown[top_section_start:next_section_start if next_section_start != -1 else None]

    assert shortlist_top in top_section
    # And the plant that used to win on the old row-level score alone must
    # not be reported as the #1 candidate.
    first_candidate_heading = top_section.split("\n###")[1] if "\n###" in top_section else top_section
    assert shortlist_top in first_candidate_heading
