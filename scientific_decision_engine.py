import os
import pandas as pd
from supabase import create_client


def get_supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is missing.")

    return create_client(url, key)


def load_scientific_evidence(plant=None, indication=None, market=None):
    supabase = get_supabase_client()

    query = supabase.table("scientific_evidence").select("*")

    if plant:
        query = query.eq("plant", plant)

    if indication:
        query = query.eq("indication", indication)

    if market:
        query = query.eq("market", market)

    response = query.execute()
    data = response.data or []

    return pd.DataFrame(data)


def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _decision_class(score):
    if score >= 80:
        return "High-priority development candidate"
    if score >= 65:
        return "Promising R&D candidate"
    if score >= 50:
        return "Early research candidate"
    return "Insufficient evidence / low priority"


def summarize_scientific_evidence(df):
    if df is None or df.empty:
        return pd.DataFrame()

    rows = []

    for plant, group in df.groupby("plant"):
        clinical = group[group["source"].isin(["PubMed", "Europe PMC", "ClinicalTrials.gov"])]
        chemistry = group[group["source"].isin(["PubChem", "ChEMBL", "ChEBI"])]
        regulatory = group[group["source"].isin(["Regulatory Search"])]

        clinical_score = (
            clinical["final_source_score"].apply(_num).mean()
            if not clinical.empty else 0
        )

        chemistry_score = (
            chemistry["final_source_score"].apply(_num).mean()
            if not chemistry.empty else 0
        )

        regulatory_score = (
            regulatory["final_source_score"].apply(_num).mean()
            if not regulatory.empty else 0
        )

        final_scientific_score = round(
            clinical_score * 0.45
            + chemistry_score * 0.30
            + regulatory_score * 0.25,
            1,
        )

        sources = sorted(set(group["source"].dropna().astype(str).tolist()))

        top_titles = (
            group.sort_values("final_source_score", ascending=False)
            .head(5)["title"]
            .dropna()
            .astype(str)
            .tolist()
        )

        rows.append(
            {
                "Scientific_Name": plant,
                "Scientific_Evidence_Record_Count": len(group),
                "Scientific_Clinical_Score": round(clinical_score, 1),
                "Scientific_Chemistry_Score": round(chemistry_score, 1),
                "Scientific_Regulatory_Score": round(regulatory_score, 1),
                "Final_Scientific_Score": final_scientific_score,
                "Scientific_Decision_Class": _decision_class(final_scientific_score),
                "Scientific_Sources": ", ".join(sources),
                "Top_Scientific_Evidence": " | ".join(top_titles),
            }
        )

    return pd.DataFrame(rows).sort_values(
        "Final_Scientific_Score",
        ascending=False,
    ).reset_index(drop=True)


def get_scientific_decision(plant=None, indication=None, market=None):
    df = load_scientific_evidence(
        plant=plant,
        indication=indication,
        market=market,
    )

    return summarize_scientific_evidence(df)
