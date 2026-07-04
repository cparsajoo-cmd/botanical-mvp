from evidence_standardizer import standardize_extracted_record
from database import save_evidence_record

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


def _save_records_from_connector(records, source_name, save=True):
    saved_records = []
    errors = []

    for record in records:
        try:
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
            if save:
                row_id = save_evidence_record(standardized)

            saved_records.append({
                "row_id": row_id,
                "pmid": "",
                "nct_id": "",
                "title": record.get("Source_Title", ""),
                "source": source_name,
                "record": standardized,
            })

        except Exception as e:
            errors.append({
                "source": source_name,
                "title": record.get("Source_Title", ""),
                "error": str(e),
            })

    return saved_records, errors


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
    sources_checked = []

    if collect_pubmed_evidence is not None:
        sources_checked.append("PubMed")
        try:
            pubmed_records = collect_pubmed_evidence(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                max_results=max_pubmed_results,
                save=save,
            )
            saved_records.extend(pubmed_records)
        except Exception as e:
            errors.append({"source": "PubMed", "plant": scientific_name, "error": str(e)})

    connectors = [
        ("ClinicalTrials.gov", search_clinicaltrials, max_clinicaltrials_results),
        ("EMA/WHO/ESCOP Regulatory", search_regulatory_sources, 1),
        ("Europe PMC", search_europepmc, 5),
        ("OpenAlex", search_openalex, 5),
        ("CrossRef", search_crossref, 5),
    ]

    for source_name, connector, max_results in connectors:
        if connector is None:
            continue

        sources_checked.append(source_name)

        try:
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

            sr, er = _save_records_from_connector(
                records=records,
                source_name=source_name,
                save=save,
            )

            saved_records.extend(sr)
            errors.extend(er)

        except Exception as e:
            errors.append({
                "source": source_name,
                "plant": scientific_name,
                "error": str(e),
            })

    return {
        "saved_records": saved_records,
        "errors": errors,
        "sources_checked": sources_checked,
    }
