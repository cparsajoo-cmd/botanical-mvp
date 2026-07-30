import re
from collections import defaultdict

import requests

from multi_source_collector import collect_multi_source_evidence
from global_candidate_ranking_engine import rank_global_candidates
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from pubmed_connector import search_and_fetch_pubmed
from source_registry import PILOT_MAX_RESULTS
from supabase_data import load_plants_df


_DISCOVERY_QUERY_TERMS = {
    "metabolic and blood sugar support": [
        "diabetes", "type 2 diabetes", "hyperglycemia", "blood glucose",
        "glycemic control", "insulin resistance", "metabolic syndrome",
        "postprandial glucose", "HbA1c",
    ],
    "energy fatigue": [
        "fatigue", "chronic fatigue", "asthenia", "tiredness", "energy",
    ],
    "sleep": ["sleep", "insomnia", "sleep quality", "sleep disorder"],
    "anxiety stress": ["anxiety", "stress", "anxiolytic"],
}



# Candidate-driven discovery pools are deliberately small and indication-specific.
# They are not treated as evidence by themselves: every plant must still be
# validated against live literature before entering the shortlist.
_DISCOVERY_CANDIDATE_POOLS = {
    "metabolic and blood sugar support": [
        "Gymnema sylvestre",
        "Momordica charantia",
        "Morus alba",
        "Salacia reticulata",
        "Syzygium cumini",
        "Camellia sinensis",
        "Olea europaea",
        "Vaccinium myrtillus",
        "Galega officinalis",
        "Gynostemma pentaphyllum",
        "Panax ginseng",
        "Curcuma longa",
        "Allium sativum",
        "Nigella sativa",
        "Aloe vera",
        "Ocimum tenuiflorum",
        "Zingiber officinale",
        "Silybum marianum",
        "Cichorium intybus",
        "Phaseolus vulgaris",
        "Plantago ovata",
        "Urtica dioica",
        "Taraxacum officinale",
        "Arctium lappa",
    ],
    "energy fatigue": [
        "Rhodiola rosea", "Panax ginseng", "Eleutherococcus senticosus",
        "Withania somnifera", "Schisandra chinensis", "Lepidium meyenii",
        "Ilex paraguariensis", "Camellia sinensis", "Cordyceps sinensis",
    ],
    "sleep": [
        "Valeriana officinalis", "Melissa officinalis",
        "Passiflora incarnata", "Humulus lupulus",
        "Lavandula angustifolia", "Matricaria chamomilla",
        "Tilia cordata", "Ziziphus jujuba",
    ],
    "anxiety stress": [
        "Withania somnifera", "Rhodiola rosea", "Melissa officinalis",
        "Passiflora incarnata", "Lavandula angustifolia",
        "Valeriana officinalis", "Matricaria chamomilla",
    ],
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
        key_tokens = set(key.split())
        indication_tokens = set(indication_norm.split())
        if key in indication_norm or len(key_tokens & indication_tokens) >= 2:
            terms.extend(synonyms)

    return list(dict.fromkeys(term for term in terms if term))


def _split_common_names(value):
    raw = str(value or "")
    return [part.strip() for part in re.split(r"[;,|/]", raw) if part.strip()]


def _candidate_alias_catalog(engine=None):
    """Map validated botanical aliases to canonical scientific names.

    The canonical ``plants`` table is the preferred source.  The compound table
    is added as a secondary catalogue source for deployments whose ``plants``
    table is still incomplete.  No free-form Latin-looking phrase is accepted.
    """
    aliases = defaultdict(set)

    frames = []
    plants_df = load_plants_df()
    if plants_df is not None and not plants_df.empty:
        frames.append((plants_df, "scientific_name", "common_name"))

    pc = getattr(engine, "plant_compounds_df", None) if engine is not None else None
    if pc is not None and not pc.empty:
        frames.append((pc, "scientific_name", "common_name"))

    for frame, scientific_col, common_col in frames:
        if scientific_col not in frame.columns:
            continue
        for _, row in frame.iterrows():
            scientific_name = str(row.get(scientific_col) or "").strip()
            scientific_alias = _norm_text(scientific_name)
            if not scientific_name or len(scientific_alias.split()) < 2:
                continue

            aliases[scientific_name].add((scientific_alias, "scientific"))

            if common_col in frame.columns:
                for common_name in _split_common_names(row.get(common_col)):
                    common_alias = _norm_text(common_name)
                    if (
                        len(common_alias) >= 5
                        and common_alias not in _COMMON_NAME_STOPWORDS
                        and not common_alias.isdigit()
                    ):
                        aliases[scientific_name].add((common_alias, "common"))

    return aliases


def _fetch_europepmc_discovery_records(query, max_results=25):
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

    records = []
    for item in response.json().get("resultList", {}).get("result", []):
        records.append({
            "Title": item.get("title", ""),
            "Abstract": item.get("abstractText", ""),
            "Source_Type": "Europe PMC discovery",
            "Record_ID": item.get("id") or item.get("pmid") or item.get("doi"),
        })
    return records


def _record_key(record):
    return (
        str(record.get("PMID") or record.get("Record_ID") or "").strip(),
        _norm_text(record.get("Title") or record.get("Source_Title")),
    )


def _extract_catalogued_plants(records, alias_catalog, indication_terms):
    """Extract and rank catalogue-validated plant entities from literature."""
    scores = defaultdict(float)
    supports = defaultdict(set)
    title_supports = defaultdict(set)
    matched_aliases = defaultdict(set)
    indication_aliases = [_norm_text(term) for term in indication_terms if term]

    for index, record in enumerate(records):
        title = _norm_text(record.get("Title") or record.get("Source_Title"))
        abstract = _norm_text(
            record.get("Abstract") or record.get("Notes") or record.get("Raw_Text")
        )
        combined = f" {title} {abstract} "

        # A returned record must still contain at least one therapeutic term;
        # this protects against noisy connector results.
        if indication_aliases and not any(
            f" {term} " in combined or term in combined for term in indication_aliases
        ):
            continue

        source = str(record.get("Source_Type") or "literature")
        support_id = str(record.get("PMID") or record.get("Record_ID") or index)

        for scientific_name, aliases in alias_catalog.items():
            best_record_score = 0.0
            best_alias = None
            title_hit_for_plant = False
            for alias, alias_type in aliases:
                title_hit = f" {alias} " in f" {title} "
                abstract_hit = f" {alias} " in f" {abstract} "
                if not title_hit and not abstract_hit:
                    continue

                score = 6.0 if title_hit else 2.0
                if alias_type == "scientific":
                    score += 2.0
                # Longer aliases are less likely to be ambiguous.
                score += min(2.0, len(alias.split()) * 0.35)
                if score > best_record_score:
                    best_record_score = score
                    best_alias = alias
                    title_hit_for_plant = title_hit

            if best_record_score > 0:
                scores[scientific_name] += best_record_score
                supports[scientific_name].add(f"{source}:{support_id}")
                if title_hit_for_plant:
                    title_supports[scientific_name].add(f"{source}:{support_id}")
                if best_alias:
                    matched_aliases[scientific_name].add(best_alias)

    ranked = sorted(
        scores,
        key=lambda plant: (
            -len(title_supports[plant]),
            -len(supports[plant]),
            -scores[plant],
            plant.lower(),
        ),
    )
    diagnostics = {
        plant: {
            "score": round(scores[plant], 2),
            "supporting_records": len(supports[plant]),
            "title_supporting_records": len(title_supports[plant]),
            "matched_aliases": sorted(matched_aliases[plant]),
        }
        for plant in ranked
    }
    return ranked, diagnostics


def _candidate_pool_for_indication(indication, alias_catalog):
    """Return a deterministic pool for candidate-specific literature checks.

    Generic therapeutic searches are useful for finding unexpected species,
    but their first 20 results are often broad reviews and may not expose the
    plant name in a reliably extractable field.  This pool provides a second,
    candidate-driven route.  Membership is only a search hypothesis; live
    literature support is required before a plant is returned.
    """
    indication_norm = _norm_text(indication)
    pool = []

    for key, plants in _DISCOVERY_CANDIDATE_POOLS.items():
        key_tokens = set(key.split())
        indication_tokens = set(indication_norm.split())
        if key in indication_norm or len(key_tokens & indication_tokens) >= 2:
            pool.extend(plants)

    # Add matching entries from the platform's own global candidate database.
    try:
        ranked = rank_global_candidates(
            indication=indication, dosage_form="", market="", target_count=50
        )
        if ranked is not None and not ranked.empty:
            pool.extend(ranked["Scientific_Name"].dropna().astype(str).tolist())
    except Exception:
        pass

    # Canonicalize against the alias catalogue when possible, while retaining
    # curated scientific names that may not yet have been inserted in Supabase.
    canonical_by_norm = {_norm_text(name): name for name in alias_catalog}
    out = []
    for plant in pool:
        canonical = canonical_by_norm.get(_norm_text(plant), str(plant).strip())
        if canonical and canonical not in out:
            out.append(canonical)
    return out


def _candidate_specific_literature_validation(
    indication, indication_terms, alias_catalog, existing_plants, slots, diagnostics
):
    """Validate likely plants with focused plant+indication literature queries."""
    if slots <= 0:
        return [], {}

    pool = _candidate_pool_for_indication(indication, alias_catalog)
    existing = {_norm_text(p) for p in existing_plants if p}
    pool = [p for p in pool if _norm_text(p) not in existing]

    diagnostics["candidate_pool_size"] = len(pool)
    diagnostics["candidate_queries_attempted"] = 0
    diagnostics["candidate_validation_records"] = 0

    validated = []
    validation_meta = {}
    # Query only as many hypotheses as needed, with a modest oversampling
    # allowance for plants that have no relevant literature.
    max_hypotheses = min(len(pool), max(10, slots * 3))
    primary_terms = [t for t in indication_terms if t][:5]
    therapeutic_or = " OR ".join(f'"{term}"' for term in primary_terms)

    for plant in pool[:max_hypotheses]:
        if len(validated) >= slots:
            break
        query = f'"{plant}" AND ({therapeutic_or})'
        diagnostics["candidate_queries_attempted"] += 1
        records = []
        errors = []
        try:
            records.extend(search_and_fetch_pubmed(query, max_results=3))
        except Exception as exc:
            errors.append(f"PubMed: {type(exc).__name__}: {exc}")
        try:
            records.extend(_fetch_europepmc_discovery_records(query, max_results=3))
        except Exception as exc:
            errors.append(f"Europe PMC: {type(exc).__name__}: {exc}")

        # De-duplicate and require both the plant and a therapeutic concept in
        # the returned title/abstract.  The plant-specific query alone is not
        # accepted as proof because APIs can return loosely related records.
        unique = []
        seen = set()
        for record in records:
            key = _record_key(record)
            if key in seen:
                continue
            seen.add(key)
            unique.append(record)
        diagnostics["candidate_validation_records"] += len(unique)

        plant_norm = _norm_text(plant)
        supporting = []
        title_hits = 0
        for record in unique:
            title = _norm_text(record.get("Title") or record.get("Source_Title"))
            abstract = _norm_text(record.get("Abstract") or record.get("Raw_Text") or record.get("Notes"))
            combined = f" {title} {abstract} "
            plant_hit = plant_norm in combined
            indication_hit = any(_norm_text(term) in combined for term in indication_terms if term)
            if plant_hit and indication_hit:
                supporting.append(record)
                if plant_norm in title:
                    title_hits += 1

        if supporting:
            validated.append(plant)
            validation_meta[plant] = {
                "score": round(len(supporting) * 3 + title_hits * 2, 2),
                "supporting_records": len(supporting),
                "title_supporting_records": title_hits,
                "matched_aliases": [plant_norm],
                "validation_route": "candidate-specific literature query",
                "query": query,
                "errors": errors,
            }
        elif errors:
            diagnostics["connector_errors"].append(
                f"Candidate validation [{plant}]: " + " | ".join(errors)
            )

    return validated, validation_meta


def _online_discovered_candidate_plants(
    indication,
    dosage_form,
    target_market,
    target_count,
    seed_plants=None,
):
    """Discover additional catalogue-validated, evidence-bearing plants."""
    diagnostics = {
        "query_terms": _query_terms(indication),
        "queries_attempted": 0,
        "records_retrieved": 0,
        "unique_records": 0,
        "catalogue_size": 0,
        "connector_errors": [],
        "ranked_matches": {},
    }

    try:
        engine = BotanicalRDCandidateEngine(use_live_search=False)
        alias_catalog = _candidate_alias_catalog(engine)
        diagnostics["catalogue_size"] = len(alias_catalog)
        if not alias_catalog:
            diagnostics["connector_errors"].append("Plant alias catalogue is empty")
            return [], diagnostics

        all_records = []
        # Separate focused searches retrieve far more botanical names than one
        # very broad OR query, while keeping each query interpretable.
        for term in diagnostics["query_terms"][:9]:
            query = (
                f'("{term}") AND '
                "(medicinal plant OR herbal medicine OR phytotherapy OR botanical)"
            )
            diagnostics["queries_attempted"] += 1

            try:
                all_records.extend(search_and_fetch_pubmed(query, max_results=20))
            except Exception as exc:
                diagnostics["connector_errors"].append(
                    f"PubMed [{term}]: {type(exc).__name__}: {exc}"
                )
            try:
                all_records.extend(_fetch_europepmc_discovery_records(query, max_results=20))
            except Exception as exc:
                diagnostics["connector_errors"].append(
                    f"Europe PMC [{term}]: {type(exc).__name__}: {exc}"
                )

        diagnostics["records_retrieved"] = len(all_records)
        unique_records = []
        seen = set()
        for record in all_records:
            key = _record_key(record)
            if key in seen:
                continue
            seen.add(key)
            unique_records.append(record)
        diagnostics["unique_records"] = len(unique_records)

        ranked, match_diagnostics = _extract_catalogued_plants(
            unique_records,
            alias_catalog,
            diagnostics["query_terms"],
        )

        existing_list = [str(p).strip() for p in (seed_plants or []) if p]
        existing = {_norm_text(p) for p in existing_list}
        ranked = [plant for plant in ranked if _norm_text(plant) not in existing]
        discovery_slots = max(0, int(target_count) - len(existing))
        generic_selected = ranked[:discovery_slots]

        remaining_slots = max(0, discovery_slots - len(generic_selected))
        validated, validation_meta = _candidate_specific_literature_validation(
            indication=indication,
            indication_terms=diagnostics["query_terms"],
            alias_catalog=alias_catalog,
            existing_plants=existing_list + generic_selected,
            slots=remaining_slots,
            diagnostics=diagnostics,
        )

        combined = list(dict.fromkeys(generic_selected + validated))
        merged_meta = dict(match_diagnostics)
        merged_meta.update(validation_meta)
        diagnostics["ranked_matches"] = merged_meta
        diagnostics["generic_discovery_count"] = len(generic_selected)
        diagnostics["candidate_validated_count"] = len(validated)
        return combined[:discovery_slots], diagnostics
    except Exception as exc:
        diagnostics["connector_errors"].append(
            f"Discovery pipeline: {type(exc).__name__}: {exc}"
        )
        return [], diagnostics


def _richer_candidate_plants(indication, dosage_form, target_market, target_count):
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
            refs["Scientific_Name"].dropna().astype(str).drop_duplicates().tolist()
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
            .dropna().astype(str).drop_duplicates().tolist()
        )

    evidence_backed = _richer_candidate_plants(
        indication=indication,
        dosage_form=dosage_form,
        target_market=target_market,
        target_count=global_candidate_count,
    ) or []

    candidate_plants = list(dict.fromkeys(evidence_backed))
    seed_plants_before_discovery = list(candidate_plants)
    discovered, discovery_diagnostics = _online_discovered_candidate_plants(
        indication=indication,
        dosage_form=dosage_form,
        target_market=target_market,
        target_count=global_candidate_count,
        seed_plants=candidate_plants,
    )
    candidate_plants.extend(
        plant for plant in discovered if plant not in candidate_plants
    )

    for plant in fallback_plants:
        if plant not in candidate_plants:
            candidate_plants.append(plant)
        if len(candidate_plants) >= global_candidate_count:
            break

    candidate_plants = candidate_plants[:global_candidate_count]

    # Always expose a complete, UI-friendly pipeline trace.  This makes it
    # possible to distinguish "discovery returned nothing" from "discovery
    # worked but candidates were later removed or replaced by fallback rows".
    discovery_diagnostics = dict(discovery_diagnostics or {})
    discovery_diagnostics.update({
        "requested_candidate_count": int(global_candidate_count),
        "seed_plants_before_discovery": seed_plants_before_discovery,
        "seed_plant_count": len(seed_plants_before_discovery),
        "online_discovered_plants": list(discovered or []),
        "online_discovered_count": len(discovered or []),
        "fallback_ranked_plants": list(fallback_plants or []),
        "fallback_ranked_count": len(fallback_plants or []),
        "final_candidate_plants": list(candidate_plants),
        "final_candidate_count": len(candidate_plants),
        "candidate_shortfall": max(0, int(global_candidate_count) - len(candidate_plants)),
    })

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
        "candidate_discovery_diagnostics": discovery_diagnostics,
        "saved_records": all_saved_records,
        "errors": all_errors,
        "sources_checked": sorted(set(all_sources_checked)),
    }
