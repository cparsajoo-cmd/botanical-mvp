import os
import re
import base64
import requests
import pandas as pd
# ------------------------------------------------------------------ #
    # 6. Market landscape: EU regulatory status, patents, retail products
    #
    # This answers the person's Phase-3 vision ("what already exists in
    # the market") and is intentionally a SEPARATE table from run()'s
    # decision table, not extra columns bolted onto it — the 16-column
    # contract stays exactly as specified.
    # ------------------------------------------------------------------ #

    def _eu_regulatory_status(self, plant: str) -> dict:
        curated = self._curated_evidence_for(plant)
        if curated:
            return {
                "EMA_HMPC_Status": curated["ema_status"],
                "WHO_Status": curated["who_status"],
                "ESCOP_Status": curated["escop_status"],
                "Source": "Curated (seed_data.SLEEP_TEA_EVIDENCE) — manually verified",
            }
        return {
            "EMA_HMPC_Status": "Not yet verified",
            "WHO_Status": "Not yet verified",
            "ESCOP_Status": "Not yet verified",
            "Source": "No EMA HMPC bulk API exists (browse-only site) — "
                      "needs manual lookup at ema.europa.eu and adding to "
                      "seed_data.py, same pattern as the sleep-tea plants",
        }

    def _search_patents(self, query: str, max_results: int = 5) -> list:
        """
        EPO Open Patent Services (OPS) — real free API, needs registration:
        https://developers.epo.org/ (free account -> consumer key/secret).
        Set env vars EPO_OPS_KEY and EPO_OPS_SECRET to activate.
        """
        key, secret = os.environ.get("EPO_OPS_KEY"), os.environ.get("EPO_OPS_SECRET")
        if not key or not secret:
            return [{
                "status": "Not configured",
                "detail": "Set EPO_OPS_KEY and EPO_OPS_SECRET (free registration "
                          "at https://developers.epo.org/) to enable patent search.",
            }]

        try:
            auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
            token_r = requests.post(
                "https://ops.epo.org/3.2/auth/accesstoken",
                headers={"Authorization": f"Basic {auth}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials"},
                timeout=20,
            )
            token_r.raise_for_status()
            access_token = token_r.json().get("access_token")

            search_r = requests.get(
                f"https://ops.epo.org/3.2/rest-services/published-data/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": f'ctxt="{query}"', "Range": f"1-{max_results}"},
                timeout=20,
            )
            search_r.raise_for_status()
            return [{"status": "OK", "raw_response": search_r.json()}]
        except Exception as e:
            return [{"status": "Error", "detail": str(e)}]

    def _search_retail_products(self, query: str) -> list:
        """
        Retail/brand product presence needs a paid web-search API (there is
        no free, structured, ToS-compliant source for 'which brands sell
        X'). Set SEARCH_API_KEY (+ optionally SEARCH_API_PROVIDER) to
        activate once you've picked a provider (Bing Web Search API,
        SerpAPI, etc.) — this function is the single place to wire it in.
        """
        api_key = os.environ.get("SEARCH_API_KEY")
        if not api_key:
            return [{
                "status": "Not configured",
                "detail": "Set SEARCH_API_KEY to a paid web-search provider "
                          "(e.g. Bing Web Search API, SerpAPI) to enable "
                          "retail/brand product scanning. No free source "
                          "exists for this data.",
            }]
        return [{
            "status": "Not implemented",
            "detail": "SEARCH_API_KEY is set, but no provider call is wired "
                      "in yet. Implement the request for your chosen "
                      "provider inside _search_retail_products().",
        }]

    def market_landscape(self, plant: str) -> dict:
        """Single-plant market snapshot: regulatory + patents + retail."""
        return {
            "plant": plant,
            "region": get_region(plant),
            "regulatory": self._eu_regulatory_status(plant),
            "patents": self._search_patents(plant),
            "retail_products": self._search_retail_products(plant),
        }

    def market_landscape_df(self, plants) -> pd.DataFrame:
        """Step-3 table: one row per plant, market landscape flattened."""
        rows = []
        for plant in plants:
            snap = self.market_landscape(plant)
            reg = snap["regulatory"]
            patents = snap["patents"]
            retail = snap["retail_products"]
            rows.append({
                "Plant": snap["plant"],
                "Region_of_Origin": snap["region"],
                "EMA_HMPC_Status": reg["EMA_HMPC_Status"],
                "WHO_Status": reg["WHO_Status"],
                "ESCOP_Status": reg["ESCOP_Status"],
                "Regulatory_Source": reg["Source"],
                "Patent_Search_Status": patents[0].get("status", "Unknown"),
                "Patent_Detail": patents[0].get("detail", patents[0].get("raw_response", "")),
                "Retail_Products_Status": retail[0].get("status", "Unknown"),
                "Retail_Products_Detail": retail[0].get("detail", ""),
            })
        return pd.DataFrame(rows)
