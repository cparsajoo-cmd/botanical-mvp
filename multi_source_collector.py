from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

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


SOURCE_TIMEOUT_SECONDS = 25
MAX_WORKERS = 6


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
):
    source_name = source_config["name"]
    max_results = source_config.get("max_results", 5)

    try:
        if source_name == "PubMed":
            if collect_pubmed_evidence is None:
                return [], [{
                    "source": source_name,
                    "plant": scientific_name,
                    "error": "PubMed connector not available.",
                }]

            records = collect_pubmed_evidence(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                max_results=max_pubmed_results or max_results,
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
):
    saved_records = []
    errors = []

    enabled_sources = sorted(
        get_enabled_sources(),
        key=lambda x: (x.get("priority", 99), x.get("name", ""))
    )

    sources_checked = [s["name"] for s in enabled_sources]

    # Fixed, reasonable ceiling on total wait time, instead of
    # SOURCE_TIMEOUT_SECONDS * number_of_sources (which was 25 * 14 =
    # 350 seconds -- nearly 6 minutes -- before even raising a timeout
    # error). With MAX_WORKERS running concurrently, sources finish in
    # waves; this budget is enough for a few such waves even in a slow
    # case.
    TOTAL_TIME_BUDGET = SOURCE_TIMEOUT_SECONDS * 2

    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        future_map = {}

        for source_config in enabled_sources:
            future = executor.submit(
                _run_one_source,
                source_config,
                scientific_name,
                indication,
                dosage_form,
                market,
                max_pubmed_results,
                save,
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
