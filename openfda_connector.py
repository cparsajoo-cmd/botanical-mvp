import requests


def search_openfda_faers(scientific_name, indication, dosage_form="", market="United States", max_results=5):
    url = "https://api.fda.gov/drug/event.json"
    params = {
        "search": f'patient.drug.openfda.substance_name:"{scientific_name}"',
        "limit": max_results,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception:
        results = []

    records = []

    if not results:
        return records

    records.append({
        "Scientific_Name": scientific_name,
        "Common_Name": "",
        "Product_Type": "Herbal product",
        "Dosage_Form": dosage_form,
        "Target_Indication": indication,
        "Target_Market": market,

        "Source_Type": "OpenFDA FAERS",
        "Source_Organization": "US FDA OpenFDA",
        "Source_Title": f"FAERS adverse event signal search for {scientific_name}",
        "Source_URL": "https://open.fda.gov/apis/drug/event/",
        "Source_Year": "",

        "Notes": f"OpenFDA FAERS returned {len(results)} adverse event records for {scientific_name}. This is a safety signal source and requires manual clinical interpretation.",

        "Publication_Type": "Pharmacovigilance database",
        "Evidence_Type": "Safety signal",
        "Study_Type": "Post-marketing safety",
        "Study_Model": "Human safety",
        "Evidence_Level": "Supporting",

        "EMA_Status": "",
        "WHO_Status": "",
        "ESCOP_Status": "",

        "Clinical_Level": "Not applicable",
        "Clinical_RCT_Count": 0,
        "Meta_Level": "Not applicable",
        "Meta_Count": 0,

        "Detected_Dosage_Forms": dosage_form,
        "Detected_Indications": indication,
        "Dosage_Form_Relevance": "Indirect",

        "Safety_Level": "Caution",
        "Safety_Signal": "FAERS safety signal found",
        "Drug_Interaction_Level": "To verify",
        "Commercial_Level": "Unknown",
        "Regulatory_Status": "FDA pharmacovigilance signal",
        "Novel_Food_Status": "Not applicable",

        "Population": "Human",
        "Sample_Size": str(len(results)),
        "Comparator": "",
        "Primary_Outcome": "Adverse event signal",
        "Result_Direction": "Safety caution",
    })

    return records
