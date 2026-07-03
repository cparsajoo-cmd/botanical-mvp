from source_ingestion_engine import normalize_source_record
from evidence_classifier import classify_evidence


def standardize_extracted_record(extracted, source_metadata):
    record = extracted.copy()

    record["Source_Type"] = source_metadata.get(
        "source_type",
        record.get("Source_Type", "")
    )

    record["Source_Title"] = source_metadata.get(
        "source_title",
        record.get("Source_Title", "")
    )

    record["Source_URL"] = source_metadata.get(
        "source_url",
        record.get("Source_URL", "")
    )

    record["Source_Organization"] = source_metadata.get(
        "source_organization",
        record.get("Source_Organization", "")
    )

    record["Source_Year"] = source_metadata.get(
        "source_year",
        record.get("Source_Year", "")
    )

    normalized = normalize_source_record(record)

    classified = classify_evidence(normalized)

    return classified
