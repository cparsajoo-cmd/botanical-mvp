import requests

GBIF_API = "https://api.gbif.org/v1/species/search"

# Part 19 (Stage 2 remediation) -- see kew_connector.DEFAULT_TIMEOUT_SECONDS
# for the same rationale.
DEFAULT_TIMEOUT_SECONDS = 30


def search_gbif_plants(keyword, limit=30, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Fails closed (returns []) on any network/HTTP error, including a
    timeout -- never raises. ``timeout`` should be derived from the
    caller's remaining Stage 2 budget when one exists (Part 19)."""

    try:

        response = requests.get(

            GBIF_API,

            params={
                "q": keyword,
                "rank": "SPECIES",
                "limit": limit
            },

            timeout=max(0.01, timeout) if timeout is not None else DEFAULT_TIMEOUT_SECONDS

        )

        response.raise_for_status()

        data = response.json()

        plants = []

        for item in data.get("results", []):

            if item.get("kingdom") != "Plantae":
                continue

            plants.append({

                "Scientific_Name": item.get("scientificName"),

                "Family": item.get("family"),

                "Genus": item.get("genus"),

                "Region": "",

                "Source": "GBIF"

            })

        return plants

    except Exception:

        return []
