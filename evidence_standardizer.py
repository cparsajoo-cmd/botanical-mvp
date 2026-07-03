from source_ingestion_engine import normalize_source_record


def standardize_extracted_record(extracted, source_metadata):
    raw_record = extracted.copy()

    raw_record["Source_Type"] = source_metadata.get("source_type", "")
    raw_record["Source_Title"] = source_metadata.get("source_title", "")
    raw_record["Source_URL"] = source_metadata.get("source_url", "")
    raw_record["Source_Organization"] = source_metadata.get("source_organization", "")
    raw_record["Source_Year"] = source_metadata.get("source_year", "")

    if not raw_record.get("Reference_Count"):
        raw_record["Reference_Count"] = 1

    return normalize_source_record(raw_record)
