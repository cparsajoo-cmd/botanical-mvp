import requests


def search_pubchem(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = scientific_name

    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{query}/cids/JSON"

    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        cids = r.json().get("IdentifierList", {}).get("CID", [])[:max_results]
    except Exception:
        cids = []

    records = []

    for cid in cids:
        summary_url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON"

        try:
            s = requests.get(summary_url, timeout=20)
            s.raise_for_status()
            data = s.json().get("Record", {})
        except Exception:
            data = {}

        title = data.get("RecordTitle", f"PubChem compound {cid}")
        raw_text = f"PubChem compound related to {scientific_name}. CID: {cid}. Title: {title}"

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "PubChem",
            "Source_Organization": "NCBI PubChem",
            "Source_Title": title,
            "Source_URL": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
            "Source_Year": "",

            "Notes": raw_text,

            "Publication_Type": "Chemical database",
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

            "Safety_Level": "To verify",
            "Safety_Signal": "",
            "Drug_Interaction_Level": "To verify",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "",
            "Novel_Food_Status": "To verify",

            "Population": "",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "Chemical identity support",
            "Result_Direction": "Supporting",
        })

    return records
