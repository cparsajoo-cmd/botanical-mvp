import requests


def search_chebi(scientific_name, indication, dosage_form="", market="Global", max_results=5):
    url = "https://www.ebi.ac.uk/ols4/api/search"
    params = {
        "q": scientific_name,
        "ontology": "chebi",
        "rows": max_results,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        docs = r.json().get("response", {}).get("docs", [])
    except Exception:
        docs = []

    records = []

    for d in docs:
        label = d.get("label", "")
        iri = d.get("iri", "")

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "ChEBI",
            "Source_Organization": "EMBL-EBI ChEBI",
            "Source_Title": f"ChEBI chemical ontology record: {label}",
            "Source_URL": iri,
            "Source_Year": "",

            "Notes": f"ChEBI chemical ontology record related to {scientific_name}: {label}",

            "Publication_Type": "Chemical ontology",
            "Evidence_Type": "Chemical composition",
            "Study_Type": "Chemical database",
            "Study_Model": "Chemical",
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

            "Safety_Level": "Unknown",
            "Safety_Signal": "",
            "Drug_Interaction_Level": "To verify",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "",
            "Novel_Food_Status": "To verify",

            "Population": "",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "Chemical ontology support",
            "Result_Direction": "Supporting",
        })

    return records
