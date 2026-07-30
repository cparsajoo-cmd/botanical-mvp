import os
import time

import requests

from rate_limit_guard import (
    ProcessRateLimitGuard,
    RateLimitUnavailable,
    retry_after_seconds,
)


def _optional_streamlit_secret(name: str) -> str:
    """Read a Streamlit secret when available without requiring Streamlit."""
    try:
        import streamlit as st
        value = st.secrets.get(name, "")
        return str(value).strip() if value else ""
    except Exception:
        return ""


OPENALEX_CONTACT_EMAIL = (
    os.environ.get("OPENALEX_CONTACT_EMAIL", "").strip()
    or _optional_streamlit_secret("OPENALEX_CONTACT_EMAIL")
)

MAX_RETRIES = 3
_OPENALEX_GUARD = ProcessRateLimitGuard("OpenAlex", default_cooldown_seconds=60)


def _get_with_retry(url, params, timeout=20):
    last_exc = None
    last_rate_limit_wait = 0.0

    _OPENALEX_GUARD.ensure_available()

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, timeout=timeout)

            if r.status_code == 429:
                wait = retry_after_seconds(
                    r.headers,
                    fallback_seconds=2 ** (attempt + 1),
                    maximum_seconds=30,
                )
                last_rate_limit_wait = wait
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                    continue

                # Do not let every plant immediately hit the same limited API.
                _OPENALEX_GUARD.block(max(60.0, wait))
                raise RateLimitUnavailable(
                    "OpenAlex temporarily unavailable due to rate limit "
                    f"(HTTP 429) after {MAX_RETRIES} attempts."
                )

            r.raise_for_status()
            return r

        except RateLimitUnavailable:
            raise
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                time.sleep(min(8.0, 1.5 * (attempt + 1)))

    if last_exc:
        raise last_exc

    raise RateLimitUnavailable(
        "OpenAlex temporarily unavailable due to rate limit "
        f"(HTTP 429); last retry delay was {last_rate_limit_wait:.1f}s."
    )


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
        abstract = " ".join([word for _, word in sorted(words)]) if words else ""

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
