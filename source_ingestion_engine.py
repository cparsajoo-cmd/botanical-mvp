STANDARD_FIELDS = {
    "Plant_ID": "",
    "Scientific_Name": "",
    "Common_Name": "",
    "Product_Type": "",
    "Dosage_Form": "",
    "Target_Indication": "",
    "Target_Market": "",
    "EMA_Status": "",
    "WHO_Status": "",
    "ESCOP_Status": "",
    # Phase 2C (regulatory single-source-of-truth cleanup) — a
    # text-mention annotation ("this publication's text mentions
    # EMA/HMPC somewhere"), never a regulatory finding. Added to this
    # allowlist so evidence_extractor.py's/evidence_standardizer.py's
    # annotation (Rule 2 of the Phase 2C audit) actually survives this
    # normalization step instead of being silently dropped the way
    # Evidence_Level once was (see the comment in evidence_standardizer.py).
    "Regulatory_Reference_Detected": False,
    "Clinical_Level": "",
    "Clinical_RCT_Count": 0,
    "Meta_Level": "",
    "Meta_Count": 0,
    "Infusion_Evidence": "",
    "Safety_Level": "",
    "Drug_Interaction_Level": "",
    "Commercial_Level": "",
    "Regulatory_Status": "",
    "Novel_Food_Status": "",
    "Reference_Count": 0,
    "Notes": "",
    "Source_Type": "",
    "Source_Title": "",
    "Source_Organization": "",
    "Source_Year": "",
    "Source_URL": "",
}


def create_empty_evidence_record():
    return STANDARD_FIELDS.copy()


def normalize_source_record(raw_record):
    record = create_empty_evidence_record()

    for key, value in raw_record.items():
        if key in record:
            record[key] = value

    return record
