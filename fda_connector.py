import requests


def search_fda_labels(scientific_name, indication, dosage_form="", market="United States", max_results=5):
    url = "https://api.fda.gov/drug/label.json"
    params = {
        "search": f'openfda.substance_name:"{scientific_name}"',
        "limit": max_results,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        results = r.json().get("results", [])
    except Exception:
        results = []

    records = []

    for item in results:
        title = ", ".join(item.get("openfda", {}).get("brand_name", []) or []) or f"FDA label for {scientific_name}"
        warnings = " ".join(item.get("warnings", []) or [])
        adverse = " ".join(item.get("adverse_reactions", []) or [])
        indications = " ".join(item.get("indications_and_usage", []) or [])

        raw_text = f"{title}\n{indications}\n{warnings}\n{adverse}"

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "FDA Label",
            "Source_Organization": "US FDA",
            "Source_Title": title,
            "Source_URL": "https://open.fda.gov/apis/drug/label/",
            "Source_Year": "",

            "Notes": raw_text,

            "Publication_Type": "Regulatory safety label",
            "Evidence_Type": "Safety/Regulatory",
            "Study_Type": "Regulatory label",
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

            "Safety_Level": "Caution" if warnings or adverse else "To verify",
            "Safety_Signal": "FDA label safety information found" if warnings or adverse else "",
            "Drug_Interaction_Level": "To verify",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "FDA label evidence",
            "Novel_Food_Status": "Not applicable",

            "Population": "Human",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "FDA label/safety evidence",
            "Result_Direction": "Supporting",
        })

    return records
