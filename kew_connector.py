import requests


KEW_API = "https://powo.science.kew.org/api/2/search"


def search_kew_plants(keyword, limit=20):

    try:

        response = requests.get(

            KEW_API,

            params={
                "q": keyword,
                "perPage": limit
            },

            timeout=30

        )

        response.raise_for_status()

        data = response.json()

        plants = []

        for item in data.get("results", []):

            plants.append({

                "Scientific_Name": item.get("name"),

                "Family": item.get("family"),

                "Region": item.get("distribution"),

                "Source": "Kew POWO"

            })

        return plants

    except Exception:

        return []
