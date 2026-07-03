import pandas as pd


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


def source_records_to_dataframe(records):
    normalized = [normalize_source_record(r) for r in records]
    return pd.DataFrame(normalized)


def append_records_to_excel(existing_df, new_records):
    new_df = source_records_to_dataframe(new_records)

    combined = pd.concat(
        [existing_df, new_df],
        ignore_index=True
    )

    return combined
