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
            errors.append({
                "source": "PubMed",
                "plant": scientific_name,
                "error": str(e),
            })

    if search_clinicaltrials is not None:
        sources_checked.append("ClinicalTrials.gov")
        try:
            clinical_records = search_clinicaltrials(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
                max_results=max_clinicaltrials_results,
            )

            for record in clinical_records:
                standardized = standardize_extracted_record(
                    extracted=record,
                    source_metadata={
                        "source_type": "ClinicalTrials.gov",
                        "source_title": record.get("Source_Title", ""),
                        "source_url": record.get("Source_URL", ""),
                        "source_organization": "ClinicalTrials.gov",
                        "source_year": record.get("Source_Year", ""),
                    },
                )

                row_id = None
                if save:
                    row_id = save_evidence_record(standardized)

                saved_records.append({
                    "row_id": row_id,
                    "pmid": "",
                    "nct_id": record.get("Source_URL", "").split("/")[-1],
                    "title": record.get("Source_Title", ""),
                    "source": "ClinicalTrials.gov",
                    "record": standardized,
                })

        except Exception as e:
            errors.append({
                "source": "ClinicalTrials.gov",
                "plant": scientific_name,
                "error": str(e),
            })

    if search_regulatory_sources is not None:
        sources_checked.append("EMA/WHO/ESCOP regulatory seed")
        try:
            regulatory_records = search_regulatory_sources(
                scientific_name=scientific_name,
                indication=indication,
                dosage_form=dosage_form,
                market=market,
            )

            for record in regulatory_records:
                standardized = standardize_extracted_record(
                    extracted=record,
                    source_metadata={
                        "source_type": "Regulatory",
                        "source_title": record.get("Source_Title", ""),
                        "source_url": record.get("Source_URL", ""),
                        "source_organization": record.get("Source_Organization", ""),
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
                    "source": "Regulatory",
                    "record": standardized,
                })

        except Exception as e:
            errors.append({
                "source": "Regulatory",
                "plant": scientific_name,
                "error": str(e),
            })

    return {
        "saved_records": saved_records,
        "errors": errors,
        "sources_checked": sources_checked,
    }
