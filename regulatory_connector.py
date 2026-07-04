REGULATORY_DB = {
    "Valeriana officinalis": {
        "EMA_Status": "Yes",
        "WHO_Status": "Yes",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC, WHO and ESCOP support for traditional use in mild nervous tension and sleep disorders.",
    },
    "Passiflora incarnata": {
        "EMA_Status": "Yes",
        "WHO_Status": "No",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC and ESCOP support for traditional use in mild symptoms of mental stress and sleep aid.",
    },
    "Melissa officinalis": {
        "EMA_Status": "Yes",
        "WHO_Status": "No",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC and ESCOP support for traditional use in mild stress and sleep disorders.",
    },
    "Lavandula angustifolia": {
        "EMA_Status": "Yes",
        "WHO_Status": "No",
        "ESCOP_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC and ESCOP support for traditional use in mild stress and exhaustion.",
    },
}


def search_regulatory_sources(
    scientific_name,
    indication,
    dosage_form="",
    market="European Union",
):
    data = REGULATORY_DB.get(scientific_name)

    if not data:
        return []

    return [{
        "Scientific_Name": scientific_name,
        "Common_Name": "",
        "Product_Type": "Herbal product",
        "Dosage_Form": dosage_form,
        "Target_Indication": indication,
        "Target_Market": market,

        "Source_Type": "Regulatory",
        "Source_Organization": "EMA/WHO/ESCOP seed database",
        "Source_Title": f"Regulatory evidence summary for {scientific_name}",
        "Source_URL": "",
        "Source_Year": "",

        "Notes": data["Regulatory_Status"],

        "Publication_Type": "Traditional/Regulatory",
        "Evidence_Type": "Traditional/Regulatory",
        "Study_Type": "Traditional/Regulatory",
        "Study_Model": "Traditional use",
        "Evidence_Level": "Traditional",

        "EMA_Status": data["EMA_Status"],
        "WHO_Status": data["WHO_Status"],
        "ESCOP_Status": data["ESCOP_Status"],

        "Clinical_Level": "Not found",
        "Clinical_RCT_Count": 0,
        "Meta_Level": "Not found",
        "Meta_Count": 0,

        "Detected_Dosage_Forms": dosage_form,
        "Detected_Indications": indication,
        "Dosage_Form_Relevance": "Direct",

        "Safety_Level": "To verify",
        "Safety_Signal": "",
        "Drug_Interaction_Level": "To verify",
        "Commercial_Level": "Unknown",
        "Regulatory_Status": data["Regulatory_Status"],
        "Novel_Food_Status": "To verify",

        "Population": "Traditional adult use",
        "Sample_Size": "",
        "Comparator": "",
        "Primary_Outcome": "Traditional regulatory support",
        "Result_Direction": "Positive",
    }]
