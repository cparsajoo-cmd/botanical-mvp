import os
import time

import requests

# Unauthenticated Semantic Scholar API traffic shares one very small
# global rate-limit pool -- this is what was producing 429 (Too Many
# Requests) errors during bulk evidence collection across thousands of
# plants. A free API key raises this limit substantially. Register (free,
# instant) at: https://www.semanticscholar.org/product/api
#
# Set it via an environment variable so it isn't hardcoded in source:
#     export SEMANTIC_SCHOLAR_API_KEY="your-key-here"
# Falls back to unauthenticated requests (with retry/backoff) if not set.
SEMANTIC_SCHOLAR_API_KEY = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

MAX_RETRIES = 2


def _get_with_retry(url, params, headers, timeout=20):
    last_exc = None

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)

            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                wait = min(5.0, float(retry_after)) if retry_after else (attempt + 1) * 2
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r

        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.5)

    if last_exc:
        raise last_exc

    raise RuntimeError(f"Semantic Scholar request failed after {MAX_RETRIES} attempts.")


def search_semantic_scholar(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f"{scientific_name} {indication} {dosage_form}"

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,year,url,citationCount,publicationTypes"
    }

    headers = {}
    if SEMANTIC_SCHOLAR_API_KEY:
        headers["x-api-key"] = SEMANTIC_SCHOLAR_API_KEY

    r = _get_with_retry(url, params, headers)

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
