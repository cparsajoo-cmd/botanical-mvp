import requests

GBIF_API = "https://api.gbif.org/v1/species/search"


def search_gbif_plants(keyword, limit=30):

    try:

        response = requests.get(

            GBIF_API,

            params={
                "q": keyword,
                "rank": "SPECIES",
                "limit": limit
            },

            timeout=30

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
