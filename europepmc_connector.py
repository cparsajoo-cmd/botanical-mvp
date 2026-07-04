import requests


def search_europepmc(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f'"{scientific_name}" AND "{indication}"'

    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query,
        "format": "json",
        "pageSize": max_results,
    }

    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()

    items = r.json().get("resultList", {}).get("result", [])

    records = []

    for item in items:
        title = item.get("title", "")
        abstract = item.get("abstractText", "")
        year = item.get("pubYear", "")
        pmid = item.get("pmid", "")
        doi = item.get("doi", "")

        url_out = ""
        if pmid:
            url_out = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        elif doi:
            url_out = f"https://doi.org/{doi}"

        raw_text = f"{title}\n{abstract}"

        records.append({
            "Scientific_Name": scientific_name,
            "Common_Name": "",
            "Product_Type": "Herbal product",
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,

            "Source_Type": "Europe PMC",
            "Source_Organization": "Europe PMC",
            "Source_Title": title,
            "Source_URL": url_out,
            "Source_Year": str(year),

            "Notes": raw_text,

            "Publication_Type": item.get("pubType", "Scholarly literature"),
            "Evidence_Type": item.get("pubType", "Review"),
            "Study_Type": item.get("pubType", "Review"),
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
