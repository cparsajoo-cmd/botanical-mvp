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


SEMANTIC_SCHOLAR_API_KEY = (
    os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    or _optional_streamlit_secret("SEMANTIC_SCHOLAR_API_KEY")
)

MAX_RETRIES = 3
_SEMANTIC_SCHOLAR_GUARD = ProcessRateLimitGuard(
    "Semantic Scholar", default_cooldown_seconds=90
)


def _get_with_retry(url, params, headers, timeout=20):
    last_exc = None
    last_rate_limit_wait = 0.0

    _SEMANTIC_SCHOLAR_GUARD.ensure_available()

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)

            if r.status_code == 429:
                wait = retry_after_seconds(
                    r.headers,
                    fallback_seconds=3 * (2 ** attempt),
                    maximum_seconds=35,
                )
                last_rate_limit_wait = wait
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                    continue

                _SEMANTIC_SCHOLAR_GUARD.block(max(90.0, wait))
                raise RateLimitUnavailable(
                    "Semantic Scholar temporarily unavailable due to rate limit "
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
        "Semantic Scholar temporarily unavailable due to rate limit "
        f"(HTTP 429); last retry delay was {last_rate_limit_wait:.1f}s."
    )


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
