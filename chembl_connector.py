import requests


def search_chembl(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    url = "https://www.ebi.ac.uk/chembl/api/data/molecule.json"
    params = {
        "molecule_synonyms__molecule_synonym__icontains": scientific_name,
        "limit": max_results,
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    molecules = r.json().get("molecules", [])
    records = []

    for m in molecules:
        name = m.get("pref_name") or scientific_name
        chembl_id = m.get("molecule_chembl_id", "")

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "ChEMBL",
            "Source_Organization": "EMBL-EBI ChEMBL",
            "Source_Title": f"ChEMBL molecule record: {name}",
            "Source_URL": f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/" if chembl_id else "",
            "Source_Year": "",

            "Notes": f"ChEMBL chemical/target evidence for {scientific_name}. Molecule: {name}. ChEMBL ID: {chembl_id}",

            "Publication_Type": "Chemical and bioactivity database",
            "Evidence_Type": "Mechanism/Chemistry",
            "Study_Type": "Bioactivity database",
            "Study_Model": "Chemical/Biological target",
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
            "Primary_Outcome": "Chemical and mechanism support",
            "Result_Direction": "Supporting",
        })

    return records
