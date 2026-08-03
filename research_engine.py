import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from collections import defaultdict
from datetime import datetime

import requests

from multi_source_collector import collect_multi_source_evidence
from global_candidate_ranking_engine import rank_global_candidates
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from pubmed_connector import search_and_fetch_pubmed
from source_registry import PILOT_MAX_RESULTS
from supabase_data import load_plants_df
import therapeutic_area_registry
import candidate_selection


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
    """Search-query terms for an indication.

    Delegates to therapeutic_area_registry.py, which returns curated terms
    for a known therapeutic area or a safe generic lexical expansion of the
    user's own text for an unknown one -- no per-indication if-statements
    are needed here or in the registry as new areas are added.
    """
    return therapeutic_area_registry.get_query_terms(indication)


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
        timeout=8,
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


def _literature_quality_signals(title, abstract, source_type="", year=None):
    """Return transparent quality signals for one literature record.

    These are deliberately conservative text signals, not claims that a paper
    has been fully critically appraised. They improve discovery ranking by
    favouring human/clinical and synthesis evidence over purely mechanistic or
    ambiguous mentions while keeping every component visible in diagnostics.
    """
    text = _norm_text(f"{title} {abstract}")
    source = _norm_text(source_type)

    systematic_terms = (
        "systematic review", "meta analysis", "meta-analysis", "umbrella review"
    )
    clinical_terms = (
        "randomized", "randomised", "double blind", "placebo controlled",
        "clinical trial", "controlled trial", "patients", "participants",
        "human study", "type 2 diabetes patients"
    )
    observational_terms = (
        "cohort", "case control", "cross sectional", "observational study"
    )
    preclinical_terms = (
        "in vitro", "cell line", "mice", "mouse", "rats", "rat model",
        "animal model", "streptozotocin", "alloxan"
    )
    regulatory_terms = (
        "ema", "hmpc", "escop", "world health organization monograph",
        "who monograph", "community herbal monograph"
    )
    safety_terms = (
        "toxicity", "toxic", "hepatotoxic", "nephrotoxic", "adverse event",
        "adverse effect", "contraindication", "drug interaction"
    )

    systematic = int(any(term in text for term in systematic_terms))
    clinical = int(any(term in text for term in clinical_terms))
    observational = int(any(term in text for term in observational_terms))
    preclinical = int(any(term in text for term in preclinical_terms))
    regulatory = int(any(term in text or term in source for term in regulatory_terms))
    safety = int(any(term in text for term in safety_terms))

    recency = 0.0
    try:
        record_year = int(str(year)[:4])
        age = max(0, datetime.utcnow().year - record_year)
        recency = max(0.0, 1.5 - min(age, 15) * 0.1)
    except Exception:
        pass

    quality_bonus = (
        systematic * 6.0
        + clinical * 4.0
        + observational * 1.5
        + regulatory * 3.0
        + recency
    )
    # Preclinical evidence remains useful for discovery, but should not outrank
    # human evidence merely because many animal papers mention the plant.
    evidence_penalty = preclinical * 0.75

    return {
        "systematic_review": systematic,
        "clinical_human": clinical,
        "observational": observational,
        "preclinical": preclinical,
        "regulatory": regulatory,
        "safety_signal": safety,
        "recency_bonus": round(recency, 2),
        "quality_bonus": round(quality_bonus, 2),
        "evidence_penalty": round(evidence_penalty, 2),
    }


def _extract_catalogued_plants(records, alias_catalog, indication_terms, dosage_form=""):
    """Extract and quality-rank catalogue-validated plant entities.

    Ranking combines entity confidence, independent supporting records,
    title mentions, human/synthesis evidence, regulatory signals, recency and
    dosage-form relevance. All components are returned for auditability.
    """
    scores = defaultdict(float)
    supports = defaultdict(set)
    title_supports = defaultdict(set)
    matched_aliases = defaultdict(set)
    exact_scientific_hits = defaultdict(int)
    clinical_supports = defaultdict(set)
    systematic_supports = defaultdict(set)
    preclinical_supports = defaultdict(set)
    regulatory_supports = defaultdict(set)
    safety_supports = defaultdict(set)
    dosage_supports = defaultdict(set)
    indication_aliases = [_norm_text(term) for term in indication_terms if term]
    dosage_norm = _norm_text(dosage_form)
    dosage_terms = []
    if "infusion" in dosage_norm or "tea" in dosage_norm:
        dosage_terms = ["infusion", "herbal tea", "aqueous extract", "water extract", "decoction"]
    elif "extract" in dosage_norm:
        dosage_terms = ["extract", "standardized extract", "standardised extract", "hydroalcoholic"]
    elif "essential oil" in dosage_norm:
        dosage_terms = ["essential oil", "volatile oil", "distillation"]

    for index, record in enumerate(records):
        raw_title = record.get("Title") or record.get("Source_Title") or ""
        raw_abstract = record.get("Abstract") or record.get("Notes") or record.get("Raw_Text") or ""
        title = _norm_text(raw_title)
        abstract = _norm_text(raw_abstract)
        combined = f" {title} {abstract} "

        if indication_aliases and not any(term in combined for term in indication_aliases):
            continue

        source = str(record.get("Source_Type") or record.get("Source") or "literature")
        support_id = str(record.get("PMID") or record.get("Record_ID") or record.get("DOI") or index)
        support_key = f"{source}:{support_id}"
        quality = _literature_quality_signals(
            title, abstract, source, record.get("Year") or record.get("Publication_Year")
        )
        dosage_hit = bool(dosage_terms and any(term in combined for term in dosage_terms))

        for scientific_name, aliases in alias_catalog.items():
            best_record_score = 0.0
            best_alias = None
            best_alias_type = None
            title_hit_for_plant = False
            for alias, alias_type in aliases:
                title_hit = f" {alias} " in f" {title} "
                abstract_hit = f" {alias} " in f" {abstract} "
                if not title_hit and not abstract_hit:
                    continue

                score = 6.0 if title_hit else 2.0
                if alias_type == "scientific":
                    score += 2.5
                else:
                    # Common names can be ambiguous (e.g. olive, potato).
                    score -= 0.5
                score += min(2.0, len(alias.split()) * 0.35)
                if score > best_record_score:
                    best_record_score = score
                    best_alias = alias
                    best_alias_type = alias_type
                    title_hit_for_plant = title_hit

            if best_record_score <= 0:
                continue

            record_score = best_record_score + quality["quality_bonus"] - quality["evidence_penalty"]
            if dosage_hit:
                record_score += 2.0
            scores[scientific_name] += max(0.5, record_score)
            supports[scientific_name].add(support_key)
            if title_hit_for_plant:
                title_supports[scientific_name].add(support_key)
            if best_alias:
                matched_aliases[scientific_name].add(best_alias)
            if best_alias_type == "scientific":
                exact_scientific_hits[scientific_name] += 1
            if quality["clinical_human"]:
                clinical_supports[scientific_name].add(support_key)
            if quality["systematic_review"]:
                systematic_supports[scientific_name].add(support_key)
            if quality["preclinical"]:
                preclinical_supports[scientific_name].add(support_key)
            if quality["regulatory"]:
                regulatory_supports[scientific_name].add(support_key)
            if quality["safety_signal"]:
                safety_supports[scientific_name].add(support_key)
            if dosage_hit:
                dosage_supports[scientific_name].add(support_key)

    # Independent-record breadth receives a capped bonus, preventing one plant
    # with many near-duplicate papers from dominating purely by volume.
    final_scores = {}
    for plant in scores:
        breadth_bonus = min(12.0, len(supports[plant]) * 1.2)
        title_bonus = min(10.0, len(title_supports[plant]) * 2.0)
        human_bonus = min(15.0, len(clinical_supports[plant]) * 3.0)
        synthesis_bonus = min(12.0, len(systematic_supports[plant]) * 4.0)
        regulatory_bonus = min(6.0, len(regulatory_supports[plant]) * 2.0)
        dosage_bonus = min(8.0, len(dosage_supports[plant]) * 2.0)
        ambiguity_penalty = 0.0 if exact_scientific_hits[plant] else 3.0
        safety_penalty = min(8.0, len(safety_supports[plant]) * 1.5)
        final_scores[plant] = (
            scores[plant] + breadth_bonus + title_bonus + human_bonus
            + synthesis_bonus + regulatory_bonus + dosage_bonus
            - ambiguity_penalty - safety_penalty
        )

    ranked = sorted(
        final_scores,
        key=lambda plant: (
            -len(systematic_supports[plant]),
            -len(clinical_supports[plant]),
            -len(title_supports[plant]),
            -final_scores[plant],
            -len(supports[plant]),
            plant.lower(),
        ),
    )
    diagnostics = {
        plant: {
            "score": round(final_scores[plant], 2),
            "entity_score": round(scores[plant], 2),
            "supporting_records": len(supports[plant]),
            "title_supporting_records": len(title_supports[plant]),
            "clinical_human_records": len(clinical_supports[plant]),
            "systematic_review_records": len(systematic_supports[plant]),
            "preclinical_records": len(preclinical_supports[plant]),
            "regulatory_records": len(regulatory_supports[plant]),
            "dosage_form_records": len(dosage_supports[plant]),
            "safety_signal_records": len(safety_supports[plant]),
            "exact_scientific_mentions": exact_scientific_hits[plant],
            "matched_aliases": sorted(matched_aliases[plant]),
            "ranking_basis": "literature quality + entity confidence + dosage-form relevance",
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
    pool = list(therapeutic_area_registry.get_candidate_hypotheses(indication))

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
    # Validate a broader hypothesis pool and rank it afterwards.  The previous
    # implementation stopped as soon as ``slots`` plants had any supporting
    # record, which made selection depend on pool order rather than evidence
    # quality.  Oversampling keeps API cost bounded while allowing stronger
    # later candidates to displace weaker early matches.
    max_hypotheses = min(len(pool), max(8, slots * 2))
    primary_terms = [t for t in indication_terms if t][:5]
    therapeutic_or = " OR ".join(f'"{term}"' for term in primary_terms)

    for plant in pool[:max_hypotheses]:
        query = f'"{plant}" AND ({therapeutic_or})'
        diagnostics["candidate_queries_attempted"] += 1
        records = []
        errors = []
        try:
            records.extend(search_and_fetch_pubmed(query, max_results=3, timeout=8))
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
            qualities = [
                _literature_quality_signals(
                    _norm_text(r.get("Title") or r.get("Source_Title")),
                    _norm_text(r.get("Abstract") or r.get("Raw_Text") or r.get("Notes")),
                    r.get("Source_Type") or "literature",
                    r.get("Year") or r.get("Publication_Year"),
                )
                for r in supporting
            ]
            clinical_count = sum(q["clinical_human"] for q in qualities)
            systematic_count = sum(q["systematic_review"] for q in qualities)
            preclinical_count = sum(q["preclinical"] for q in qualities)
            regulatory_count = sum(q["regulatory"] for q in qualities)
            safety_count = sum(q["safety_signal"] for q in qualities)
            score = (
                len(supporting) * 3 + title_hits * 2
                + clinical_count * 4 + systematic_count * 6
                + regulatory_count * 3 - preclinical_count * 0.75
                - safety_count * 1.5
            )
            validation_meta[plant] = {
                "score": round(score, 2),
                "entity_score": round(len(supporting) * 3 + title_hits * 2, 2),
                "supporting_records": len(supporting),
                "title_supporting_records": title_hits,
                "clinical_human_records": clinical_count,
                "systematic_review_records": systematic_count,
                "preclinical_records": preclinical_count,
                "regulatory_records": regulatory_count,
                "dosage_form_records": 0,
                "safety_signal_records": safety_count,
                "exact_scientific_mentions": len(supporting),
                "matched_aliases": [plant_norm],
                "validation_route": "candidate-specific literature query",
                "ranking_basis": "focused literature quality validation",
                "query": query,
                "errors": errors,
            }
        elif errors:
            diagnostics["connector_errors"].append(
                f"Candidate validation [{plant}]: " + " | ".join(errors)
            )

    validated = sorted(
        validated,
        key=lambda plant: (
            float(validation_meta.get(plant, {}).get("score") or 0),
            int(validation_meta.get(plant, {}).get("clinical_human_records") or 0),
            int(validation_meta.get(plant, {}).get("systematic_review_records") or 0),
            int(validation_meta.get(plant, {}).get("supporting_records") or 0),
        ),
        reverse=True,
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
        for term in diagnostics["query_terms"][:4]:
            query = (
                f'("{term}") AND '
                "(medicinal plant OR herbal medicine OR phytotherapy OR botanical)"
            )
            diagnostics["queries_attempted"] += 1

            try:
                all_records.extend(search_and_fetch_pubmed(query, max_results=12, timeout=8))
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
            dosage_form=dosage_form,
        )

        existing_list = [str(p).strip() for p in (seed_plants or []) if p]
        existing = {_norm_text(p) for p in existing_list}
        ranked = [plant for plant in ranked if _norm_text(plant) not in existing]
        discovery_slots = max(0, int(target_count) - len(existing))

        # Retain a wider generic discovery pool for comparison rather than
        # accepting the first N matches.  Candidate-specific validation is run
        # independently, then both routes compete on the same quality score.
        generic_pool_limit = max(12, discovery_slots * 4)
        generic_pool = ranked[:generic_pool_limit]
        validated, validation_meta = _candidate_specific_literature_validation(
            indication=indication,
            indication_terms=diagnostics["query_terms"],
            alias_catalog=alias_catalog,
            existing_plants=existing_list,
            slots=max(1, discovery_slots),
            diagnostics=diagnostics,
        )

        merged_meta = dict(match_diagnostics)
        merged_meta.update(validation_meta)
        candidate_pool = list(dict.fromkeys(generic_pool + validated))
        candidate_pool = sorted(
            candidate_pool,
            key=lambda plant: (
                float(merged_meta.get(plant, {}).get("score") or 0),
                int(merged_meta.get(plant, {}).get("clinical_human_records") or 0),
                int(merged_meta.get(plant, {}).get("systematic_review_records") or 0),
                int(merged_meta.get(plant, {}).get("supporting_records") or 0),
            ),
            reverse=True,
        )
        selected = candidate_pool[:discovery_slots]
        excluded = candidate_pool[discovery_slots:]

        diagnostics["ranked_matches"] = merged_meta
        diagnostics["generic_discovery_count"] = len(generic_pool)
        diagnostics["candidate_validated_count"] = len(validated)
        diagnostics["discovery_candidate_pool"] = candidate_pool
        diagnostics["discovery_candidate_pool_count"] = len(candidate_pool)
        diagnostics["selected_discovery_candidates"] = selected
        diagnostics["excluded_discovery_candidates"] = excluded
        return selected, diagnostics
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
    requested_count = max(1, int(global_candidate_count))

    # --- Staged candidate selection (general architecture) -----------------
    # A. Reference/database seeds. These are NOT yet validated for this
    #    indication -- they are only a stable starting inventory.
    reference_seed_plants = _richer_candidate_plants(
        indication=indication,
        dosage_form=dosage_form,
        target_market=target_market,
        target_count=requested_count,
    ) or []
    reference_seed_plants = list(dict.fromkeys(reference_seed_plants))[:requested_count]

    # B + C. Generic literature discovery, plus focused plant+indication
    # validation of candidate hypotheses (both already implemented by
    # _online_discovered_candidate_plants -- reused unchanged here). Seeds
    # are intentionally NOT passed in as an exclusion set: discovery is run
    # at full requested strength so that a strong literature-discovered
    # candidate can outrank a weak seed later, instead of being crowded out
    # by a fixed seed/discovery quota.
    discovered, discovery_diagnostics = _online_discovered_candidate_plants(
        indication=indication,
        dosage_form=dosage_form,
        target_market=target_market,
        target_count=requested_count,
        seed_plants=[],
    )
    discovered = list(dict.fromkeys(discovered or []))
    ranked_meta = discovery_diagnostics.get("ranked_matches", {}) or {}
    connector_failure = bool(discovery_diagnostics.get("connector_errors")) and not discovered

    # D. Globally ranked fallback candidates. Oversample relative to the
    # requested count so the merge/rank stage (E-G) below has real
    # alternatives to choose from, rather than returning the first N rows
    # regardless of quality.
    global_candidates = rank_global_candidates(
        indication=indication,
        dosage_form=dosage_form,
        market=target_market,
        target_count=max(requested_count * 3, requested_count),
    )
    if global_candidates is None or global_candidates.empty:
        fallback_plants = []
    else:
        fallback_plants = (
            global_candidates["Scientific_Name"]
            .dropna().astype(str).drop_duplicates().tolist()
        )

    # Candidate hypotheses that were part of the discovery pool but never
    # confirmed against literature -- exposed for transparency/diagnostics
    # only. They can still be selected (per the architecture's "attempt to
    # fill the requested count" goal) but only ever with a
    # pending_validation status, never labelled evidence-backed.
    candidate_hypotheses = [
        plant for plant in therapeutic_area_registry.get_candidate_hypotheses(indication)
        if plant not in discovered
    ]

    # E. Merge candidate inputs from every origin into a single, provenance-
    #    tagged pool.
    candidate_records = []
    for plant in discovered:
        meta = ranked_meta.get(plant, {})
        has_strong_support = bool(
            meta.get("clinical_human_records") or meta.get("systematic_review_records")
        )
        candidate_records.append(candidate_selection.make_candidate(
            plant,
            candidate_selection.ORIGIN_VALIDATED_LITERATURE,
            score=float(meta.get("score") or 5.0),
            score_components=meta,
            sources=("literature_discovery",),
            evidence_status=(
                candidate_selection.STATUS_VALIDATED_DIRECT if has_strong_support
                else candidate_selection.STATUS_VALIDATED_INDIRECT
            ),
        ))
    for plant in reference_seed_plants:
        candidate_records.append(candidate_selection.make_candidate(
            plant,
            candidate_selection.ORIGIN_REFERENCE_SEED,
            sources=("reference_database",),
        ))
    for plant in candidate_hypotheses:
        candidate_records.append(candidate_selection.make_candidate(
            plant,
            candidate_selection.ORIGIN_CANDIDATE_HYPOTHESIS,
            sources=("therapeutic_area_registry",),
        ))
    for plant in fallback_plants:
        candidate_records.append(candidate_selection.make_candidate(
            plant,
            candidate_selection.ORIGIN_RANKED_FALLBACK,
            sources=("global_candidate_ranking",),
        ))

    # F + G + H. Deduplicate, rank by evidence strength/relevance, and
    # select up to the requested count -- with a shortfall reported only
    # when scientifically plausible candidates genuinely run out.
    selected_records, selection_diagnostics = candidate_selection.select_candidates(
        candidate_records, requested_count, connector_failure=connector_failure,
    )
    candidate_plants = [record.name for record in selected_records]

    validated_literature_plants = [
        record.name for record in selected_records
        if record.origin == candidate_selection.ORIGIN_VALIDATED_LITERATURE
    ]
    reference_seed_selected = [
        record.name for record in selected_records
        if record.origin == candidate_selection.ORIGIN_REFERENCE_SEED
    ]
    # Backward-compatible key: only genuinely validated plants are exposed
    # as "evidence-backed" now. Reference-database seeds that were not
    # confirmed against literature are exposed separately below under
    # reference_seed_plants instead of being mislabelled here.
    evidence_backed = validated_literature_plants

    # Always expose a complete, UI-friendly pipeline trace.  This makes it
    # possible to distinguish "discovery returned nothing" from "discovery
    # worked but candidates were later removed or replaced by fallback rows".
    discovery_diagnostics = dict(discovery_diagnostics or {})
    discovery_diagnostics.update({
        "requested_candidate_count": requested_count,
        "seed_plants_before_discovery": reference_seed_plants,
        "seed_plant_count": len(reference_seed_plants),
        "online_discovered_plants": list(discovered or []),
        "online_discovered_count": len(discovered or []),
        "fallback_ranked_plants": list(fallback_plants or []),
        "fallback_ranked_count": len(fallback_plants or []),
        "candidate_hypothesis_plants": list(candidate_hypotheses or []),
        "final_candidate_plants": list(candidate_plants),
        "final_candidate_count": len(candidate_plants),
        "candidate_shortfall": selection_diagnostics["candidate_shortfall"],
        "shortfall_reason": selection_diagnostics["shortfall_reason"],
        "candidate_selection_diagnostics": selection_diagnostics,
    })

    all_saved_records = []
    all_errors = []
    all_sources_checked = []

    # Step 2 used to process plants strictly one after another.  Each plant can
    # legitimately consume the collector's whole per-plant time budget, so an
    # 8-plant quick run could block the Streamlit page for many minutes.  Run a
    # small number of plants concurrently and enforce one global wall-clock
    # ceiling.  Successful partial results are preserved; unfinished plants are
    # reported explicitly instead of leaving the UI spinner running forever.
    quick_step_budget_seconds = 105 if not pilot_mode else 180
    plant_workers = 2 if len(candidate_plants) > 1 else 1
    started_at = time.monotonic()

    def _collect_one_plant(plant):
        return plant, collect_multi_source_evidence(
            scientific_name=plant,
            indication=indication,
            dosage_form=dosage_form,
            market=target_market,
            max_pubmed_results=max_results_per_plant,
            max_clinicaltrials_results=3,
            save=save,
            max_results_override=PILOT_MAX_RESULTS if pilot_mode else None,
        )

    executor = ThreadPoolExecutor(max_workers=plant_workers)
    future_map = {
        executor.submit(_collect_one_plant, plant): plant
        for plant in candidate_plants
    }
    completed_plants = []
    try:
        for future in as_completed(future_map, timeout=quick_step_budget_seconds):
            plant = future_map[future]
            try:
                completed_plant, result = future.result(timeout=1)
                completed_plants.append(completed_plant)
                all_saved_records.extend(result.get("saved_records", []))
                all_errors.extend(result.get("errors", []))
                all_sources_checked.extend(result.get("sources_checked", []))
            except Exception as exc:
                all_errors.append({
                    "source": "Step 2 plant collection",
                    "plant": plant,
                    "error": f"{type(exc).__name__}: {exc}",
                })
    except FuturesTimeoutError:
        pass
    finally:
        unfinished = [
            plant for future, plant in future_map.items()
            if not future.done()
        ]
        for plant in unfinished:
            all_errors.append({
                "source": "Step 2 global time budget",
                "plant": plant,
                "error": (
                    f"Skipped after the {quick_step_budget_seconds}s Step 2 "
                    "wall-clock budget was reached; completed plant results "
                    "were retained."
                ),
            })
        executor.shutdown(wait=False, cancel_futures=True)

    discovery_diagnostics.update({
        "collection_time_budget_seconds": quick_step_budget_seconds,
        "collection_elapsed_seconds": round(time.monotonic() - started_at, 2),
        "collection_completed_plants": completed_plants,
        "collection_completed_plant_count": len(completed_plants),
        "collection_unfinished_plants": unfinished,
        "collection_unfinished_plant_count": len(unfinished),
    })

    return {
        # --- Existing public keys, preserved unchanged in type/shape -------
        "candidate_plants": candidate_plants,
        "evidence_backed_plants": evidence_backed,
        "online_discovered_plants": discovered,
        "candidate_discovery_diagnostics": discovery_diagnostics,
        "saved_records": all_saved_records,
        "errors": all_errors,
        "sources_checked": sorted(set(all_sources_checked)),
        # --- New, additive keys ---------------------------------------------
        "candidate_records": [
            {
                "name": record.name,
                "origin": record.origin,
                "evidence_status": record.evidence_status,
                "score": record.score,
                "sources": list(record.sources),
            }
            for record in selected_records
        ],
        "candidate_selection_diagnostics": selection_diagnostics,
        "validated_literature_plants": validated_literature_plants,
        "reference_seed_plants": reference_seed_selected,
    }
