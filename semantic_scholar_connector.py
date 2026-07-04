import requests


def search_semantic_scholar(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f"{scientific_name} {indication} {dosage_form}"

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,year,url,citationCount,publicationTypes"
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    papers = r.json().get("data", [])
    records = []

    for p in papers:
        title = p.get("title", "")
        abstract = p.get("abstract", "") or ""
        year = p.get("year", "")
        citation_count = p.get("citationCount", 0)
        pub_types = ", ".join(p.get("publicationTypes") or [])

        raw_text = f"{title}\n{abstract}\nPublication types: {pub_types}\nCitations: {citation_count}"

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "Semantic Scholar",
            "Source_Organization": "Semantic Scholar",
            "Source_Title": title,
            "Source_URL": p.get("url", ""),
            "Source_Year": str(year),

            "Notes": raw_text,

            "Publication_Type": pub_types or "Scholarly literature",
            "Evidence_Type": pub_types or "Review",
            "Study_Type": pub_types or "Review",
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
