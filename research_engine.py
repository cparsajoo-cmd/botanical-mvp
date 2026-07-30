import re
from collections import defaultdict

import requests

from multi_source_collector import collect_multi_source_evidence
from global_candidate_ranking_engine import rank_global_candidates
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from pubmed_connector import search_and_fetch_pubmed
from source_registry import PILOT_MAX_RESULTS


_DISCOVERY_QUERY_TERMS = {
    "metabolic blood sugar support": [
        "diabetes", "type 2 diabetes", "hyperglycemia", "blood glucose",
        "glycemic control", "insulin resistance", "metabolic syndrome",
    ],
    "energy fatigue": [
        "fatigue", "chronic fatigue", "asthenia", "tiredness", "energy",
    ],
    "sleep": ["sleep", "insomnia", "sleep quality", "sleep disorder"],
    "anxiety stress": ["anxiety", "stress", "anxiolytic"],
}

_COMMON_NAME_STOPWORDS = {
    "plant", "herb", "herbal", "tea", "root", "leaf", "leaves", "seed",
    "flower", "fruit", "bark", "extract", "oil", "sage", "mint", "date",
    "nettle", "pepper", "ginger", "cinnamon", "garlic", "coffee", "cocoa",
}


def _norm_text(value):
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _query_terms(indication):
    indication_norm = _norm_text(indication)
    terms = [str(indication or "").strip()]

    for key, synonyms in _DISCOVERY_QUERY_TERMS.items():
        if key in indication_norm or any(term in indication_norm for term in synonyms):
            terms.extend(synonyms)

    # Keep order deterministic while removing duplicates.
    return list(dict.fromkeys(term for term in terms if term))


def _candidate_alias_catalog(engine):
    """Return aliases that can map literature text back to scientific names.

    The catalogue comes from the project's own Supabase-backed plant data. A
    literature mention is therefore not accepted merely because it resembles a
    Latin binomial; it must map to a plant already known to the platform.
    """
    aliases = defaultdict(set)
    pc = getattr(engine, "plant_compounds_df", None)

    if pc is None or pc.empty or "scientific_name" not in pc.columns:
        return aliases

    for _, row in pc.iterrows():
        scientific_name = str(row.get("scientific_name") or "").strip()
        if not scientific_name:
            continue

        scientific_alias = _norm_text(scientific_name)
        if len(scientific_alias) >= 5 and " " in scientific_alias:
            aliases[scientific_name].add((scientific_alias, "scientific"))

        common_name = str(row.get("common_name") or "").strip()
        common_alias = _norm_text(common_name)
        if (
            len(common_alias) >= 5
            and common_alias not in _COMMON_NAME_STOPWORDS
            and not common_alias.isdigit()
        ):
            aliases[scientific_name].add((common_alias, "common"))

    return aliases


def _fetch_europepmc_discovery_records(query, max_results=25):
    """Broad literature discovery query used only to identify plant names."""
    try:
        response = requests.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={
                "query": query,
                "format": "json",
                "pageSize": max_results,
                "resultType": "core",
            },
            timeout=25,
        )
        response.raise_for_status()
    except Exception:
        return []

    records = []
    for item in response.json().get("resultList", {}).get("result", []):
        records.append({
            "Title": item.get("title", ""),
            "Abstract": item.get("abstractText", ""),
            "Source_Type": "Europe PMC discovery",
        })
    return records


def _online_discovered_candidate_plants(
    indication,
    dosage_form,
    target_market,
    target_count,
    seed_plants=None,
):
    """Discover additional evidence-bearing plants from broad literature.

    This is a controlled expansion step, not a free-form botanical guesser:
    - PubMed and Europe PMC are queried for the therapeutic area plus botanical
      concepts.
    - Plant names are extracted only when they match the platform's own plant
      catalogue (scientific name, or a sufficiently specific common name).
    - Title mentions score more than abstract mentions; scientific-name matches
      score more than common-name matches.
    - Existing evidence-backed seed plants are retained and not duplicated.

    Returns an ordered list of newly discovered scientific names. Any network or
    parsing failure returns an empty list so the existing workflow still runs.
    """
    try:
        engine = BotanicalRDCandidateEngine(use_live_search=False)
        alias_catalog = _candidate_alias_catalog(engine)
        if not alias_catalog:
            return []

        terms = _query_terms(indication)
        quoted_terms = " OR ".join(f'"{term}"' for term in terms[:7])
        query = (
            f"({quoted_terms}) AND "
            "(medicinal plant OR herbal medicine OR phytotherapy OR botanical)"
        )

        records = []
        try:
            records.extend(search_and_fetch_pubmed(query, max_results=25))
        except Exception:
            pass
        records.extend(_fetch_europepmc_discovery_records(query, max_results=25))

        if not records:
            return []

        scores = defaultdict(float)
        supports = defaultdict(set)

        for index, record in enumerate(records):
            title = _norm_text(record.get("Title") or record.get("Source_Title"))
            abstract = _norm_text(
                record.get("Abstract") or record.get("Notes") or record.get("Raw_Text")
            )
            source = str(record.get("Source_Type") or "literature")

            for scientific_name, aliases in alias_catalog.items():
                best_record_score = 0.0
                for alias, alias_type in aliases:
                    # Normalized aliases contain spaces, so padding both sides
                    # prevents substring matches inside longer words.
                    title_hit = f" {alias} " in f" {title} "
                    abstract_hit = f" {alias} " in f" {abstract} "
                    if not title_hit and not abstract_hit:
                        continue

                    score = 4.0 if title_hit else 1.5
                    if alias_type == "scientific":
                        score += 1.0
                    best_record_score = max(best_record_score, score)

                if best_record_score > 0:
                    scores[scientific_name] += best_record_score
                    supports[scientific_name].add(f"{source}:{index}")

        existing = {str(p).strip().lower() for p in (seed_plants or []) if p}
        ranked = sorted(
            (
                plant for plant in scores
                if plant.lower() not in existing
            ),
            key=lambda plant: (
                -len(supports[plant]),
                -scores[plant],
                plant.lower(),
            ),
        )

        # Discovery should broaden a focused shortlist, not flood Step 2.
        discovery_slots = max(0, min(4, int(target_count) - len(existing)))
        return ranked[:discovery_slots]
    except Exception:
        return []


def _richer_candidate_plants(indication, dosage_form, target_market, target_count):
    """Evidence-first candidate-plant source for live evidence search.

    The central engine prioritizes ``scientific_evidence`` and
    ``evidence_records``. Broad phytochemical compilation labels in
    ``plant_compounds.indication`` are not accepted as direct
    plant-indication evidence.

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
    """Collect and save live evidence for a focused candidate shortlist.

    Candidate selection is now hybrid:
    1. evidence-backed plants already present in Supabase;
    2. additional plants discovered from broad PubMed/Europe PMC literature,
       validated against the platform plant catalogue;
    3. the curated global candidate ranking only as a fallback/fill source.

    The total number searched remains capped by ``global_candidate_count``.
    """
    global_candidates = rank_global_candidates(
        indication=indication,
        dosage_form=dosage_form,
        market=target_market,
        target_count=global_candidate_count,
    )
    if global_candidates is None or global_candidates.empty:
        fallback_plants = []
    else:
        fallback_plants = (
            global_candidates["Scientific_Name"]
            .dropna()
            .astype(str)
            .drop_duplicates()
            .tolist()
        )

    evidence_backed = _richer_candidate_plants(
        indication=indication,
        dosage_form=dosage_form,
        target_market=target_market,
        target_count=global_candidate_count,
    ) or []

    candidate_plants = list(dict.fromkeys(evidence_backed))

    discovered = _online_discovered_candidate_plants(
        indication=indication,
        dosage_form=dosage_form,
        target_market=target_market,
        target_count=global_candidate_count,
        seed_plants=candidate_plants,
    )
    candidate_plants.extend(
        plant for plant in discovered if plant not in candidate_plants
    )

    # Fill any remaining slots from the curated ranking. This preserves
    # coverage when literature discovery is unavailable or returns too few
    # catalogue-mapped plant names.
    for plant in fallback_plants:
        if plant not in candidate_plants:
            candidate_plants.append(plant)
        if len(candidate_plants) >= global_candidate_count:
            break

    candidate_plants = candidate_plants[:global_candidate_count]

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
        "evidence_backed_plants": evidence_backed,
        "online_discovered_plants": discovered,
        "saved_records": all_saved_records,
        "errors": all_errors,
        "sources_checked": sorted(set(all_sources_checked)),
    }
