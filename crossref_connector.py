import requests


def search_crossref(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f"{scientific_name} {indication} {dosage_form}"

    url = "https://api.crossref.org/works"
    params = {
        "query": query,
        "rows": max_results,
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    items = r.json().get("message", {}).get("items", [])

    records = []

    for item in items:
        title = " ".join(item.get("title", []) or [])
        abstract = item.get("abstract", "") or ""
        year_parts = item.get("published-print", item.get("published-online", {})).get("date-parts", [[]])
        year = year_parts[0][0] if year_parts and year_parts[0] else ""

        doi = item.get("DOI", "")
        url_out = f"https://doi.org/{doi}" if doi else item.get("URL", "")

        raw_text = f"{title}\n{abstract}"

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "CrossRef",
            "Source_Organization": "CrossRef",
            "Source_Title": title,
            "Source_URL": url_out,
            "Source_Year": str(year),

            "Notes": raw_text,

            "Publication_Type": "Scholarly literature",
            "Evidence_Type": "Review",
            "Study_Type": "Review",
            "Study_Model": "Unknown",
            "Evidence_Level": "Low",

            "EMA_Status": "",
            "WHO_Status": "",
            "ESCOP_Status": "",

            "Clinical_Level": "To classify",
            "Clinical_RCT_Count": 0,
            "Meta_Level": "To classify",
            "Meta_Count": 0,

            "Detected_Dosage_Forms": dosage_form,
            "Detected_Indications": indication,
            "Dosage_Form_Relevance": "Unknown",

            "Safety_Level": "Unknown",
            "Safety_Signal": "",
            "Drug_Interaction_Level": "Unknown",
            "Commercial_Level": "Unknown",
            "Regulatory_Status": "",
            "Novel_Food_Status": "To verify",

            "Population": "",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "",
            "Result_Direction": "Unknown",
        })

    return records
