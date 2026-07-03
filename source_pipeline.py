from evidence_extractor import extract_evidence_from_text
from evidence_standardizer import standardize_extracted_record
from database import save_evidence_record


def run_source_pipeline(source_metadata, save=True):
    raw_text = source_metadata.get("raw_text", "")

    if not raw_text.strip():
        raise ValueError("No source text provided.")

    extracted = extract_evidence_from_text(raw_text)

    standardized = standardize_extracted_record(
        extracted=extracted,
        source_metadata=source_metadata
    )

    row_id = None

    if save:
        row_id = save_evidence_record(standardized)

    return {
        "row_id": row_id,
        "extracted": extracted,
        "standardized": standardized,
    }
