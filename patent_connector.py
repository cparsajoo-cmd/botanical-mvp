import requests


def search_patents(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f"{scientific_name} {indication} {dosage_form}"

    url = "https://api.crossref.org/works"
    params = {
        "query": f"{query} patent",
        "rows": max_results,
    }

    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])
    except Exception:
        items = []

    records = []

    for item in items:
        title = " ".join(item.get("title", []) or [])
        doi = item.get("DOI", "")
        url_out = f"https://doi.org/{doi}" if doi else item.get("URL", "")

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "Patent/Literature",
            "Source_Organization": "Patent proxy via CrossRef",
            "Source_Title": title,
            "Source_URL": url_out,
            "Source_Year": "",

            "Notes": f"Patent/protection landscape proxy search for {query}. Title: {title}",

            "Publication_Type": "Patent/Commercial landscape",
            "Evidence_Type": "Patent landscape",
            "Study_Type": "Patent/Commercial",
            "Study_Model": "Commercial/IP",
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
            "Drug_Interaction_Level": "Unknown",
            "Commercial_Level": "To analyze",
            "Regulatory_Status": "",
            "Novel_Food_Status": "To verify",

            "Population": "",
            "Sample_Size": "",
            "Comparator": "",
            "Primary_Outcome": "Patent/commercial opportunity signal",
            "Result_Direction": "Supporting",
        })

    return records
