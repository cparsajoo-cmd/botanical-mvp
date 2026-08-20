import os

import requests


def _optional_streamlit_secret(name: str) -> str:
    """Read a Streamlit secret when available without requiring Streamlit."""
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        return str(value).strip() if value else ""
    except Exception:
        return ""


# Same host, same identification need as crossref_connector.py -- this
# connector is itself a CrossRef bibliographic-search proxy (see
# Source_Type below), so it benefits from CrossRef's "polite pool" the
# same way. See crossref_connector.py's own comment for the rationale.
CROSSREF_CONTACT_EMAIL = (
    os.environ.get("CROSSREF_CONTACT_EMAIL", "").strip()
    or os.environ.get("OPENALEX_CONTACT_EMAIL", "").strip()
    or _optional_streamlit_secret("CROSSREF_CONTACT_EMAIL")
    or _optional_streamlit_secret("OPENALEX_CONTACT_EMAIL")
)


def search_patents(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f"{scientific_name} {indication} {dosage_form}"

    url = "https://api.crossref.org/works"
    params = {
        "query": f"{query} patent",
        "rows": max_results,
    }
    if CROSSREF_CONTACT_EMAIL:
        params["mailto"] = CROSSREF_CONTACT_EMAIL

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

            "Source_Type": "Bibliographic search proxy — NOT a patent database",
            "Source_Organization": "CrossRef bibliographic proxy",
            "Source_Title": title,
            "Source_URL": url_out,
            "Source_Year": "",

            "Notes": f"Patent/protection landscape proxy search for {query}. Title: {title}",

            "Publication_Type": "Bibliographic proxy",
            "Evidence_Type": "Patent keyword proxy — unverified",
            "Study_Type": "Not scientific evidence",
            "Study_Model": "Search proxy",
            "Evidence_Level": "Not applicable",

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
            "Primary_Outcome": "CrossRef keyword hit only; not verified patent activity",
            "Result_Direction": "Not applicable",
            "Patent_Verification_Status": "PROXY_ONLY_NOT_PATENT_DATABASE",
        })

    return records
