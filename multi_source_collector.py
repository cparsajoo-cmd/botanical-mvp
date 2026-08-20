from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import time

from evidence_standardizer import standardize_extracted_record
from database import save_evidence_record
from source_registry import get_enabled_sources
from plant_compound_extractor import extract_plant_compounds_from_text

try:
    from evidence_collector import collect_pubmed_evidence
except Exception:
    collect_pubmed_evidence = None

try:
    from clinicaltrials_connector import search_clinicaltrials
except Exception:
    search_clinicaltrials = None

try:
    from regulatory_connector import search_regulatory_sources
except Exception:
    search_regulatory_sources = None

try:
    from europepmc_connector import search_europepmc
except Exception:
    search_europepmc = None

try:
    from openalex_connector import search_openalex
except Exception:
    search_openalex = None

try:
    from crossref_connector import search_crossref
except Exception:
    search_crossref = None

try:
    from semantic_scholar_connector import search_semantic_scholar
except Exception:
    search_semantic_scholar = None

try:
    from pubchem_connector import search_pubchem
except Exception:
    search_pubchem = None

try:
    from chembl_connector import search_chembl
except Exception:
    search_chembl = None

try:
    from chebi_connector import search_chebi
except Exception:
    search_chebi = None

try:
    from dailymed_connector import search_dailymed
except Exception:
    search_dailymed = None

try:
    from openfda_connector import search_openfda_faers
except Exception:
    search_openfda_faers = None

try:
    from fda_connector import search_fda_labels
except Exception:
    search_fda_labels = None

try:
    from livertox_connector import search_livertox
except Exception:
    search_livertox = None

try:
    from patent_connector import search_patents
except Exception:
    search_patents = None


CONNECTOR_MAP = {
    "ClinicalTrials.gov": search_clinicaltrials,
    "EMA/WHO/ESCOP Regulatory": search_regulatory_sources,
    "Europe PMC": search_europepmc,
    "OpenAlex": search_openalex,
    "CrossRef": search_crossref,
    "Semantic Scholar": search_semantic_scholar,
    "PubChem": search_pubchem,
    "ChEMBL": search_chembl,
    "ChEBI": search_chebi,
    "DailyMed": search_dailymed,
    "OpenFDA FAERS": search_openfda_faers,
    "FDA Labels": search_fda_labels,
    "LiverTox": search_livertox,
    "Patent Landscape": search_patents,
}


SOURCE_TIMEOUT_SECONDS = 15

# Previously a fixed cap of 6, forcing 15 enabled sources through
# ceil(15/6)=3 sequential waves per plant even though every source is an
# independent, unrelated HTTP call (different domains, no shared
# resource) -- pure I/O-bound work with nothing to gain from serializing
# it. That artificial wave-queueing was the actual root cause of the
# production incident where TOTAL_TIME_BUDGET (previously 30s, then 60s)
# was hit for nearly every source on nearly every plant: sources queued
# behind other slow/rate-limited ones never even got a worker slot before
# the overall budget expired, regardless of how large the budget was made.
# max_workers is now set per-call to the actual number of enabled sources
# (see collect_multi_source_evidence below), so every source starts at
# once and the wall-clock time is bounded by the SLOWEST single source,
# not by (sources / a fixed worker cap) sequential rounds of them.
MAX_WORKERS = None  # kept for any external references; no longer used to cap concurrency

# Total wall-clock ceiling for ONE plant's collect_multi_source_evidence()
# call, across every enabled source. This is a real module-level constant,
# imported by research_engine.py, so there is exactly one place that
# knows how long a plant collection can legitimately take -- the two
# previously drifted apart (research_engine.py's own independent guess vs.
# this one), which was the first Step 2 wall-clock regression.
#
# Value derivation, now that every source runs in a single concurrent wave
# (no more artificial ceil(sources / MAX_WORKERS) rounds): the dominant
# single-source worst case is one connector's 20s HTTP request timeout
# (clinicaltrials_connector.py, europepmc_connector.py, chebi_connector.py,
# etc.), plus the retry-with-backoff loop in openalex_connector.py /
# semantic_scholar_connector.py on HTTP 429 (observed in production
# alongside real NCBI PubMed 429 rate-limiting -- this does happen, not
# just in theory). 20s request timeout + ~2 backoff retries (~15s worst
# case combined) + scheduling margin rounds to 45s.
TOTAL_TIME_BUDGET = 45


def _extract_and_save_compounds(record, source_name):
    compound_text = " ".join([
        str(record.get("Scientific_Name", "")),
        str(record.get("Source_Title", "")),
        str(record.get("Notes", "")),
        str(record.get("Abstract", "")),
        str(record.get("Raw_Text", "")),
        str(record.get("Evidence_Text", "")),
        str(record.get("Summary", "")),
    ])

    return extract_plant_compounds_from_text(
        scientific_name=record.get("Scientific_Name", ""),
        text=compound_text,
        indication=record.get("Target_Indication", ""),
        dosage_form=record.get("Dosage_Form", ""),
        market=record.get("Target_Market", ""),
        reference_title=record.get("Source_Title", ""),
        reference_url=record.get("Source_URL", ""),
        source=record.get("Source_Type", source_name),
        source_year=record.get("Source_Year", ""),
        save=True,
    )


def _save_records_from_connector(records, source_config, save=True):
    saved_records = []
    errors = []

    source_name = source_config["name"]

    for record in records:
        try:
            record["Source_Category"] = source_config.get("category", "")
            record["Source_Priority"] = source_config.get("priority", "")
            record["Source_Authority_Weight"] = source_config.get("authority_weight", "")

            standardized = standardize_extracted_record(
                extracted=record,
                source_metadata={
                    "source_type": record.get("Source_Type", source_name),
                    "source_title": record.get("Source_Title", ""),
                    "source_url": record.get("Source_URL", ""),
                    "source_organization": record.get("Source_Organization", source_name),
                    "source_year": record.get("Source_Year", ""),
                },
            )

            row_id = None
            compound_records = []

            if save:
                row_id = save_evidence_record(standardized)

                compound_records = _extract_and_save_compounds(
                    record=record,
                    source_name=source_name,
                )

            saved_records.append({
                "row_id": row_id,
                "pmid": record.get("PMID", ""),
                "nct_id": record.get("NCT_ID", ""),
                "title": record.get("Source_Title", ""),
                "source": source_name,
                "category": source_config.get("category", ""),
                "compound_records_saved": len(compound_records),
                "record": standardized,
            })

        except Exception as e:
            errors.append({
                "source": source_name,
                "title": record.get("Source_Title", ""),
                "error": str(e),
            })

    return saved_records, errors


def _run_one_source(
    source_config,
    scientific_name,
    indication,
    dosage_form,
    market,
    max_pubmed_results,
    save,
    max_results_override=None,
):
    source_name = source_config["name"]
    # Task 6 — pilot-scope coverage. When provided, max_results_override
    # takes TOP precedence over both this source's own SOURCE_REGISTRY
    # default AND (for PubMed specifically) max_pubmed_results — the
    # default (max_results_override=None) leaves every existing caller's
    # behavior completely unchanged.
    max_results = (
        max_results_override if max_results_override is not None
        else source_config.get("max_results", 5)
    )

    try:
        if source_name == "PubMed":
            if collect_pubmed_evidence is None:
                return [], [{
                    "source": source_name,
                    "plant": scientific_name,
                    "error": "PubMed connector not available.",
                }]

            pubmed_max_results = (
                max_results_override if max_results_override is not None
                else (max_pubmed_results or max_results)
            )
            records = collect_pubmed_evidence(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                max_results=pubmed_max_results,
                save=save,
            )

            for item in records:
                try:
                    record = item.get("record", {})
                    compound_text = " ".join([
                        str(item.get("title", "")),
                        str(record.get("Notes", "")),
                        str(record.get("Source_Title", "")),
                    ])

                    compound_records = extract_plant_compounds_from_text(
                        scientific_name=scientific_name,
                        text=compound_text,
                        indication=indication,
                        dosage_form=dosage_form,
                        market=market,
                        reference_title=item.get("title", ""),
                        reference_url=record.get("Source_URL", ""),
                        source="PubMed",
                        source_year=record.get("Source_Year", ""),
                        save=save,
                    )

                    item["compound_records_saved"] = len(compound_records)

                except Exception:
                    item["compound_records_saved"] = 0

            return records, []

        connector = CONNECTOR_MAP.get(source_name)

        if connector is None:
            return [], [{
                "source": source_name,
                "plant": scientific_name,
                "error": "Connector not implemented yet.",
            }]

        if source_name == "EMA/WHO/ESCOP Regulatory":
            records = connector(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
            )
        else:
            records = connector(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                max_results=max_results,
            )

        saved_records, errors = _save_records_from_connector(
            records=records,
            source_config=source_config,
            save=save,
        )

        return saved_records, errors

    except Exception as e:
        return [], [{
            "source": source_name,
            "plant": scientific_name,
            "error": str(e),
        }]


def collect_multi_source_evidence(
    scientific_name,
    indication,
    dosage_form,
    market="European Union",
    max_pubmed_results=3,
    max_clinicaltrials_results=5,
    save=True,
    max_results_override=None,
):
    """Runs every enabled source (source_registry.py) concurrently for
    one plant/indication pair.

    max_results_override (Task 6, default None — no change to any
    existing caller's behavior): when provided, overrides the
    per-source max_results ceiling from SOURCE_REGISTRY, uniformly,
    for every source in this call — including PubMed, taking
    precedence over max_pubmed_results too. Intended for a small
    number of explicitly pilot-scoped calls (see
    source_registry.PILOT_MAX_RESULTS and research_engine.py's
    pilot_mode parameter) — not a general-purpose knob every call site
    should start passing.
    """
    saved_records = []
    errors = []

    enabled_sources = sorted(
        get_enabled_sources(),
        key=lambda x: (x.get("priority", 99), x.get("name", ""))
    )

    sources_checked = [s["name"] for s in enabled_sources]

    # TOTAL_TIME_BUDGET is now a module-level constant (see definition
    # above) instead of being redefined here -- research_engine.py imports
    # the same constant for its outer per-plant-wave scheduling budget, so
    # the two can no longer independently drift out of sync.
    #
    # max_workers is set to the actual number of enabled sources so every
    # source runs concurrently in a single wave (see MAX_WORKERS comment
    # above for why this replaced the previous fixed cap of 6).
    executor = ThreadPoolExecutor(max_workers=max(1, len(enabled_sources)))
    try:
        future_map = {}

        # Small stagger between submissions: launching all N sources in the
        # exact same instant (0.15s apart here, so ~2s to launch 15) sends a
        # burst of near-simultaneous requests to a handful of shared hosts
        # (e.g. PubMed and LiverTox both hit eutils.ncbi.nlm.nih.gov;
        # CrossRef and Patent Landscape both hit api.crossref.org). Several
        # of these providers rate-limit per-second request bursts, not just
        # cumulative volume -- observed in production as real HTTP 429s from
        # PubMed, CrossRef, and Semantic Scholar on the same run, even after
        # the identification-header fixes in crossref_connector.py /
        # patent_connector.py / livertox_connector.py. This does not
        # guarantee an already-throttled provider recovers instantly, but it
        # reduces how often this run itself is the thing that trips the
        # limiter. Sources still all run concurrently and overlap in flight
        # -- this is not a return to the old fixed-wave serialization (see
        # MAX_WORKERS comment above), just spacing out when each one starts.
        _SOURCE_LAUNCH_STAGGER_SECONDS = 0.15
        for i, source_config in enumerate(enabled_sources):
            if i > 0:
                time.sleep(_SOURCE_LAUNCH_STAGGER_SECONDS)
            future = executor.submit(
                _run_one_source,
                source_config,
                scientific_name,
                indication,
                dosage_form,
                market,
                max_pubmed_results,
                save,
                max_results_override,
            )
            future_map[future] = source_config["name"]

        try:
            for future in as_completed(future_map, timeout=TOTAL_TIME_BUDGET):
                source_name = future_map[future]

                try:
                    sr, er = future.result(timeout=1)
                    saved_records.extend(sr)
                    errors.extend(er)

                except Exception as e:
                    errors.append({
                        "source": source_name,
                        "plant": scientific_name,
                        "error": str(e),
                    })
        except TimeoutError:
            # Whichever sources haven't finished within the overall time
            # budget are recorded as timed-out and abandoned -- we do NOT
            # wait for them. They keep running in the background
            # (harmlessly) but this function returns immediately with
            # whatever succeeded so far, instead of blocking the whole
            # Step 2 page indefinitely on one slow/rate-limited source.
            finished = {f for f in future_map if f.done()}
            for future, source_name in future_map.items():
                if future not in finished:
                    errors.append({
                        "source": source_name,
                        "plant": scientific_name,
                        "error": f"Timed out after {TOTAL_TIME_BUDGET}s "
                                 f"(overall budget, not this source alone).",
                    })
    finally:
        # wait=False is the key fix: never let a slow/stuck source hold
        # up the entire Step 2 page. See the same fix applied in
        # Bulk_Evidence.py's _fast_retry_sources for the full reasoning.
        executor.shutdown(wait=False, cancel_futures=True)

    return {
        "saved_records": saved_records,
        "errors": errors,
        "sources_checked": sorted(set(sources_checked)),
    }
