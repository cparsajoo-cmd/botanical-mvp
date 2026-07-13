import os
import time

import requests

# OpenAlex's "polite pool" gives a much higher, much more reliable rate
# limit to any request that identifies itself with a contact email — no
# registration needed, just add the email to every request. Without this,
# all unauthenticated traffic worldwide shares one small pool, which is
# what was producing the 429 (Too Many Requests) errors seen during bulk
# evidence collection.
#
# Set this via an environment variable so it isn't hardcoded in source:
#     export OPENALEX_CONTACT_EMAIL="you@example.com"
# Falls back to a generic placeholder if not set (still works, just
# without the polite-pool benefit).
OPENALEX_CONTACT_EMAIL = os.environ.get("OPENALEX_CONTACT_EMAIL", "")

MAX_RETRIES = 4


def _get_with_retry(url, params, timeout=20):
    last_exc = None

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, timeout=timeout)

            if r.status_code == 429:
                # Respect Retry-After if the server sent one, otherwise
                # back off with increasing delay.
                retry_after = r.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else (2 ** attempt) * 2
                time.sleep(wait)
                continue

            r.raise_for_status()
            return r

        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep((2 ** attempt) * 1.5)

    if last_exc:
        raise last_exc

    raise RuntimeError(f"OpenAlex request failed after {MAX_RETRIES} attempts.")


def search_openalex(scientific_name, indication, dosage_form="", market="European Union", max_results=5):
    query = f"{scientific_name} {indication} {dosage_form}"

    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": max_results,
    }

    if OPENALEX_CONTACT_EMAIL:
        params["mailto"] = OPENALEX_CONTACT_EMAIL

    r = _get_with_retry(url, params)

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
