import requests


def search_dailymed(scientific_name, indication, dosage_form="", market="United States", max_results=5):
    url = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
    params = {
        "drug_name": scientific_name,
        "pagesize": max_results,
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    data = r.json().get("data", [])
    records = []

    for item in data:
        title = item.get("title", "")
        setid = item.get("setid", "")

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "DailyMed",
            "Source_Organization": "NIH DailyMed",
            "Source_Title": title,
            "Source_URL": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}" if setid else "",
            "Source_Year": "",

            "Notes": f"DailyMed label/safety search result for {scientific_name}. Title: {title}",

            "Publication_Type": "Drug label database",
            "Evidence_Type": "Safety/Label",
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

            "Safety_Level": "To verify",
            "Safety_Signal": "DailyMed label evidence found",
            "Drug_Interaction_Level": "To verify",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "US label database evidence",
            "Novel_Food_Status": "Not applicable",

            "Population": "Human",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "Label/safety support",
            "Result_Direction": "Supporting",
        })

    return records
