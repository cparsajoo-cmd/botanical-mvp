from multi_source_collector import collect_multi_source_evidence
from global_candidate_ranking_engine import rank_global_candidates
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from source_registry import PILOT_MAX_RESULTS


def _richer_candidate_plants(indication, dosage_form, target_market, target_count):
    """Evidence-first candidate-plant source for live evidence search.

    The central engine now prioritizes ``scientific_evidence`` and
    ``evidence_records``.  Broad phytochemical compilation labels in
    ``plant_compounds.indication`` are not accepted as direct
    plant-indication evidence, preventing the live search from sampling an
    alphabetic slice of nearly the whole catalogue.

    Returns None (not an empty list) on any failure so the caller can fall
    back to the small curated global candidate list.
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
    global_candidate_count=8,
    pilot_mode=False,
):
    """Collects and saves live evidence for the plants relevant to this
    indication/dosage_form/market. Returns what was actually searched
    and saved — nothing more.

    pilot_mode (Task 6, default False — no change to any existing
    caller's behavior): when True, every source's per-plant result
    ceiling is raised to source_registry.PILOT_MAX_RESULTS instead of
    the default per-source SOURCE_REGISTRY ceiling (and instead of
    max_results_per_plant for PubMed specifically) — see
    multi_source_collector.collect_multi_source_evidence's
    max_results_override parameter. Intended for a small number of
    explicitly scoped pilot deliverables, not routine use.

    This used to also run a second, parallel scoring/decision pass
    (decision_engine.analyze_evidence(), merged with
    global_candidate_ranking_engine's score columns) and return it as
    "decision"/"global_candidates". That output was never read by any
    caller (step_evidence.py only ever used candidate_plants,
    saved_records, errors, sources_checked) — it ran on every Step 2
    click, cost real time, and produced Decision_Class/score values
    the user never saw, using different weights than the ONE decision
    engine that's actually shown to the user
    (BotanicalRDCandidateEngine, in Step 5). Removed rather than fixed,
    since fixing it would have meant maintaining two scoring systems
    that need to agree — see the Phase 1 audit for the full trace.

    evidence_strictness is kept as a parameter purely for
    backward-compatible call signatures; it's currently unused inside
    this function.
    """
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

    # Prefer the evidence-first Supabase candidate list. Only fall back to
    # the small curated global list if no evidence-backed plants are found
    # or Supabase is unavailable.
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
            max_results_override=PILOT_MAX_RESULTS if pilot_mode else None,
        )
        all_saved_records.extend(result.get("saved_records", []))
        all_errors.extend(result.get("errors", []))
        all_sources_checked.extend(result.get("sources_checked", []))

    return {
        "candidate_plants": candidate_plants,
        "saved_records": all_saved_records,
        "errors": all_errors,
        "sources_checked": sorted(set(all_sources_checked)),
    }
