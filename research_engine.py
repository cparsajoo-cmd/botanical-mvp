from multi_source_collector import collect_multi_source_evidence
from evidence_database import load_evidence_database
from knowledge_retrieval_engine import retrieve_knowledge
from evidence_filtering_engine import apply_evidence_filters
from decision_engine import analyze_evidence
from deduplication_engine import deduplicate_evidence
from global_candidate_ranking_engine import rank_global_candidates
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def _richer_candidate_plants(indication, dosage_form, target_market, target_count):
    """Primary candidate-plant source for live evidence search.

    rank_global_candidates() only knows about the small, hand-tagged
    GLOBAL_PLANT_CANDIDATES list (~37 plants total, most indications
    covered by just 1-2 of them). After importing real data (e.g. Dr.
    Duke's, 900+ plants) into Supabase's plant_compounds table, that
    richer dataset has proper per-indication tagging that this step was
    never wired to use — so live evidence search was silently searching
    only 1-2 plants for many indications, even though Step 3-5 (which use
    BotanicalRDCandidateEngine directly) had access to hundreds.

    This reuses that same engine's reference-plant lookup so evidence
    search sees the same plant universe the rest of the app already does.
    Returns None (not an empty list) on any failure, so the caller can
    fall back to the older method cleanly.
    """
    try:
        engine = BotanicalRDCandidateEngine(use_live_search=False)
        refs = engine._get_reference_plants(
            problem=indication,
            dosage_form=dosage_form,
            market=target_market,
            max_reference_plants=target_count,
        )
        if refs is None or refs.empty or "Scientific_Name" not in refs.columns:
            return None

        plants = (
            refs["Scientific_Name"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .tolist()
        )
        return plants or None
    except Exception:
        return None


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

    # Prefer the Supabase-backed candidate list (hundreds of plants,
    # properly tagged per indication) over the small hardcoded one above.
    # Only fall back to the narrow list if the richer lookup finds nothing
    # (e.g. Supabase isn't configured / offline dev environment).
    richer_candidates = _richer_candidate_plants(
        indication=indication,
        dosage_form=dosage_form,
        target_market=target_market,
        target_count=global_candidate_count,
    )
    if richer_candidates:
        candidate_plants = richer_candidates

    all_saved_records = []
    all_errors = []
    all_sources_checked = []
    for plant in candidate_plants:
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
        "saved_records": all_saved_records,
        "errors": all_errors,
        "sources_checked": sorted(set(all_sources_checked)),
        "decision": decision,
    }
