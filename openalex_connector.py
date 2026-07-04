import requests


def search_openalex(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f"{scientific_name} {indication} {dosage_form}"

    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results,
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    data = r.json()
    works = data.get("results", [])

    records = []

    for w in works:
        title = w.get("title", "")
        year = w.get("publication_year", "")
        doi = w.get("doi", "")
        abstract_index = w.get("abstract_inverted_index") or {}

        words = []
        for word, positions in abstract_index.items():
            for pos in positions:
                words.append((pos, word))
        abstract = " ".join([w for _, w in sorted(words)]) if words else ""

        raw_text = f"{title}\n{abstract}"

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "OpenAlex",
            "Source_Organization": "OpenAlex",
            "Source_Title": title,
            "Source_URL": doi or w.get("id", ""),
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
