from pubmed_connector import search_and_fetch_pubmed
from evidence_extractor import extract_evidence_from_text
from evidence_standardizer import standardize_extracted_record
from database import save_evidence_record


def build_pubmed_query(scientific_name, indication, dosage_form):
    return f'"{scientific_name}" AND ({indication}) AND ({dosage_form} OR clinical OR trial OR randomized OR review)'


def collect_pubmed_evidence(
    scientific_name,
    indication,
    dosage_form,
    market="European Union",
    max_results=10,
    save=True
):
    query = build_pubmed_query(
        scientific_name=scientific_name,
        indication=indication,
        dosage_form=dosage_form
    )

    articles = search_and_fetch_pubmed(
        query=query,
        max_results=max_results
    )

    saved_records = []

    for article in articles:
        extracted = extract_evidence_from_text(article["Raw_Text"])

        extracted["Scientific_Name"] = scientific_name
        extracted["Target_Indication"] = indication
        extracted["Dosage_Form"] = dosage_form
        extracted["Target_Market"] = market
        extracted["Source_Type"] = "PubMed"
        extracted["Source_Title"] = article["Title"]
        extracted["Source_Organization"] = "NCBI PubMed"
        extracted["Source_URL"] = article["Source_URL"]
        extracted["Notes"] = article["Raw_Text"]

        standardized = standardize_extracted_record(
            extracted=extracted,
            source_metadata={
                "source_type": "PubMed",
                "source_title": article["Title"],
                "source_url": article["Source_URL"],
                "source_organization": "NCBI PubMed",
                "source_year": "",
            }
        )

        row_id = None

        if save:
            row_id = save_evidence_record(standardized)

        saved_records.append({
            "row_id": row_id,
            "pmid": article["PMID"],
            "title": article["Title"],
            "record": standardized,
        })

    return saved_records
