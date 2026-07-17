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
    """Regulatory lookup. Two layers:

    1. The tiny hand-curated REGULATORY_DB above — kept only for the 4
       original sleep-tea plants, where someone actually manually read
       the EMA/WHO/ESCOP monographs and wrote a precise, human-verified
       summary. This is richer than what automated text-extraction can
       safely produce, so it wins when available.
    2. For every other plant (the other ~99.8% of the database),
       ema_regulatory_connector does a REAL live/cached lookup against
       EMA's official HMPC inventory PDF, instead of silently returning
       nothing the way this function used to for anything outside the
       4-plant dict. See ema_regulatory_connector.py's module docstring
       for exactly what this connector can and can't tell you.
    """
    data = REGULATORY_DB.get(scientific_name)

    if data:
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

    try:
        from ema_regulatory_connector import search_regulatory_sources_real
        return search_regulatory_sources_real(
            scientific_name, indication, dosage_form, market
        )
    except Exception as exc:
        return [{
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,
            "Source_Type": "Regulatory",
            "Source_Organization": "EMA HMPC (lookup unavailable)",
            "Source_Title": "EMA HMPC inventory of herbal substances",
            "Source_URL": "",
            "Source_Year": "",
            "Notes": f"Real EMA lookup failed: {exc}",
            "Evidence_Level": "Not available",
            "EMA_Status": "Not yet verified",
            "WHO_Status": "Not yet verified",
            "ESCOP_Status": "Not yet verified",
            "Regulatory_Status": "Lookup failed — see Notes.",
        }]
