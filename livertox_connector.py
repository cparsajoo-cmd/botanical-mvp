import requests


def search_livertox(scientific_name, indication, dosage_form="", market="Global", max_results=5):
    query = scientific_name

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "books",
        "term": f"{query} LiverTox",
        "retmode": "json",
        "retmax": max_results,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        ids = r.json().get("esearchresult", {}).get("idlist", [])
    except Exception:
        ids = []

    records = []

    for bid in ids:
        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "LiverTox",
            "Source_Organization": "NIH NCBI Bookshelf LiverTox",
            "Source_Title": f"LiverTox safety record for {scientific_name}",
            "Source_URL": f"https://www.ncbi.nlm.nih.gov/books/{bid}/",
            "Source_Year": "",

            "Notes": f"LiverTox hepatotoxicity/safety source found for {scientific_name}.",

            "Publication_Type": "Safety monograph",
            "Evidence_Type": "Safety",
            "Study_Type": "Safety monograph",
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
            "Safety_Signal": "LiverTox safety source found",
            "Drug_Interaction_Level": "To verify",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "NIH LiverTox safety evidence",
            "Novel_Food_Status": "Not applicable",

            "Population": "Human",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "Hepatotoxicity/safety evidence",
            "Result_Direction": "Safety evidence",
        })

    return records
