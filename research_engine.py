from multi_source_collector import collect_multi_source_evidence
from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence
from deduplication_engine import deduplicate_evidence
from global_candidate_ranking_engine import rank_global_candidates
from compound_source_engine import collect_compounds_from_all_sources


def run_research_engine(
    product_type,
    dosage_form,
    indication,
    target_market,
    evidence_strictness="Dosage-form specific only",
    max_results_per_plant=3,
    save=True,
    global_candidate_count=50,
):
    global_candidates = rank_global_candidates(
        indication=indication,
        dosage_form=dosage_form,
        market=target_market,
        target_count=global_candidate_count,
    )

    if global_candidates is None or global_candidates.empty:
        candidate_plants = []
    else:
        candidate_plants = (
            global_candidates["Scientific_Name"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .tolist()
        )

    all_saved_records = []
    all_errors = []
    all_sources_checked = []
    all_compound_results = []

    for plant in candidate_plants:
        compound_result = collect_compounds_from_all_sources(
            scientific_name=plant,
            indication=indication,
            dosage_form=dosage_form,
            market=target_market,
            max_results_per_source=10,
        )

        all_compound_results.append(compound_result)
        all_errors.extend(compound_result.get("errors", []))

        result = collect_multi_source_evidence(
            scientific_name=plant,
            indication=indication,
            dosage_form=dosage_form,
            market=target_market,
            max_pubmed_results=max_results_per_plant,
            max_clinicaltrials_results=3,
            save=save,
        )

        all_saved_records.extend(result.get("saved_records", []))
        all_errors.extend(result.get("errors", []))
        all_sources_checked.extend(result.get("sources_checked", []))

    df = load_evidence_database()

    retrieved = retrieve_knowledge(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=target_market,
        evidence_strictness=evidence_strictness,
    )

    filtered = apply_evidence_filters(
        df=retrieved,
        dosage_form=dosage_form,
        evidence_strictness=evidence_strictness,
    )

    filtered = deduplicate_evidence(filtered)

    decision = analyze_evidence(
        df=filtered,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=target_market,
        min_score=0,
    )

    if (
        decision is not None
        and not decision.empty
        and global_candidates is not None
        and not global_candidates.empty
    ):
        merge_cols = [
            "Scientific_Name",
            "Region",
            "Known_Active_Compounds",
            "Known_Targets",
            "Plant_Part",
            "Extraction_Method",
            "Global_Ranking_Score",
            "Candidate_Status",
            "Clinical_Score",
            "Chemistry_Score",
            "Active_Compound_Score",
            "Target_Score",
            "Extraction_Score",
            "Regulatory_Score",
            "Safety_Score",
            "Novelty_Score",
            "Market_Score",
            "Commercial_Score",
        ]

        available_merge_cols = [
            col for col in merge_cols
            if col in global_candidates.columns
        ]

        decision = decision.merge(
            global_candidates[available_merge_cols].drop_duplicates("Scientific_Name"),
            on="Scientific_Name",
            how="left",
            suffixes=("", "_Global"),
        )

    return {
        "candidate_plants": candidate_plants,
        "global_candidates": global_candidates,
        "compound_results": all_compound_results,
        "saved_records": all_saved_records,
        "errors": all_errors,
        "sources_checked": sorted(set(all_sources_checked)),
        "decision": decision,
    }
