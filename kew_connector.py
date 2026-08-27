import requests


KEW_API = "https://powo.science.kew.org/api/2/search"

# Part 19 (Stage 2 remediation) -- default connector timeout when a
# caller does not supply a deadline-derived one. Was hardcoded at 30s
# unconditionally; callers on a tight remaining Stage 2 budget should
# pass a smaller explicit ``timeout``.
DEFAULT_TIMEOUT_SECONDS = 30


def search_kew_plants(keyword, limit=20, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Fails closed (returns []) on any network/HTTP error, including a
    timeout -- never raises. ``timeout`` should be derived from the
    caller's remaining Stage 2 budget when one exists (Part 19); a
    caller with only a few seconds left must not still request the full
    30s default."""

    try:

        response = requests.get(

            KEW_API,

            params={
                "q": keyword,
                "perPage": limit
            },

            timeout=max(0.01, timeout) if timeout is not None else DEFAULT_TIMEOUT_SECONDS

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
