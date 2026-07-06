import pandas as pd
from evidence_database import load_evidence_database


def _text(x):
    if x is None:
        return ""
    return str(x).lower()


class MarketIntelligenceEngine:
    def __init__(self):
        try:
            self.evidence_df = load_evidence_database()
        except Exception:
            self.evidence_df = pd.DataFrame()

    def evaluate(self, row, indication="", dosage_form="", market=""):
        plant = row.get("Scientific_Name", "")
        common = row.get("Common_Name", "")
        compound = row.get("compound_name", "")

        if self.evidence_df is None or self.evidence_df.empty:
            return {
                "Market_Score": 0,
                "Market_Status": "No market data",
                "Product_Hits": 0,
                "Regulatory_Hits": 0,
                "Patent_Hits": 0,
                "White_Space": "Unknown",
            }

        df = self.evidence_df.copy()

        usable_cols = [
            c for c in df.columns
            if c.lower() in [
                "plant",
                "scientific_name",
                "common_name",
                "compound",
                "compound_name",
                "title",
                "source",
                "source_title",
                "source_url",
                "url",
                "indication",
                "dosage_form",
            ]
        ]

        if not usable_cols:
            return {
                "Market_Score": 0,
                "Market_Status": "No readable market data",
                "Product_Hits": 0,
                "Regulatory_Hits": 0,
                "Patent_Hits": 0,
                "White_Space": "Unknown",
            }

        df["_text"] = df[usable_cols].astype(str).agg(" ".join, axis=1).str.lower()

        terms = [
            _text(plant),
            _text(common),
            _text(compound),
        ]
        terms = [t for t in terms if t and t != "nan"]

        if not terms:
            return {
                "Market_Score": 0,
                "Market_Status": "No searchable term",
                "Product_Hits": 0,
                "Regulatory_Hits": 0,
                "Patent_Hits": 0,
                "White_Space": "Unknown",
            }

        mask = pd.Series(False, index=df.index)
        for term in terms:
            mask = mask | df["_text"].str.contains(term, case=False, na=False, regex=False)

        matched = df[mask]

        if matched.empty:
            return {
                "Market_Score": 0,
                "Market_Status": "No market signal yet",
                "Product_Hits": 0,
                "Regulatory_Hits": 0,
                "Patent_Hits": 0,
                "White_Space": "High",
            }

        product_hits = matched["_text"].str.contains(
            "product|label|dailymed|fda labels|amazon|iherb|boots|market",
            case=False,
            na=False,
            regex=True,
        ).sum()

        regulatory_hits = matched["_text"].str.contains(
            "ema|who|escop|fda|openfda|dailymed|regulatory|traditional use",
            case=False,
            na=False,
            regex=True,
        ).sum()

        patent_hits = matched["_text"].str.contains(
            "patent",
            case=False,
            na=False,
            regex=False,
        ).sum()

        market_score = min(
            100,
            int(product_hits * 15 + regulatory_hits * 10 + patent_hits * 5 + len(matched) * 2),
        )

        if market_score >= 60 or product_hits >= 2:
            status = "Marketed / commercial evidence exists"
            white_space = "Low or medium"
        elif market_score >= 25 or regulatory_hits >= 1:
            status = "Commercially plausible / emerging"
            white_space = "Medium"
        else:
            status = "Limited market signal"
            white_space = "High"

        return {
            "Market_Score": market_score,
            "Market_Status": status,
            "Product_Hits": int(product_hits),
            "Regulatory_Hits": int(regulatory_hits),
            "Patent_Hits": int(patent_hits),
            "White_Space": white_space,
        }
