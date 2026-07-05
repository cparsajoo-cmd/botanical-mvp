import pandas as pd

from plant_compound_database import load_plant_compound_database
from compound_profile_database import load_compound_profiles


def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _txt(x):
    if x is None:
        return ""
    return str(x).strip()


def build_compound_scores(indication="", dosage_form=""):
    compounds_raw = load_plant_compound_database()
    compounds_df = pd.DataFrame(compounds_raw)

    if compounds_df.empty:
        return pd.DataFrame()

    profiles_df = load_compound_profiles()

    if not profiles_df.empty:
        compounds_df["compound_name_key"] = (
            compounds_df["compound_name"].fillna("").astype(str).str.lower().str.strip()
        )
        profiles_df["compound_name_key"] = (
            profiles_df["compound_name"].fillna("").astype(str).str.lower().str.strip()
        )

        compounds_df = compounds_df.merge(
            profiles_df,
            on="compound_name_key",
            how="left",
            suffixes=("", "_profile"),
        )

    for col in ["scientific_name", "compound_name", "target", "extraction_method", "confidence_score"]:
        if col not in compounds_df.columns:
            compounds_df[col] = ""

    rows = []

    for plant, group in compounds_df.groupby("scientific_name", dropna=False):
        plant = _txt(plant)
        if not plant:
            continue

        compounds = sorted(set(group["compound_name"].dropna().astype(str)))
        compounds = [c for c in compounds if c and c.lower() != "nan"]

        compound_count = len(compounds)
        high_conf_count = int((group["confidence_score"].apply(_num) >= 70).sum())

        active_score = min(100, 20 + compound_count * 10 + high_conf_count * 5)

        target_text = " ; ".join(group["target"].fillna("").astype(str).tolist()).lower()
        extraction_text = " ; ".join(group["extraction_method"].fillna("").astype(str).tolist()).lower()

        target_score = 25
        if any(x in indication.lower() for x in ["sleep", "relaxation", "anxiety", "stress"]):
            for k in ["gaba", "gaba-a", "benzodiazepine", "serotonergic", "hpa"]:
                if k in target_text:
                    target_score += 15
        target_score = min(target_score, 100)

        extraction_score = 30
        if "infusion" in dosage_form.lower():
            if "infusion" in extraction_text:
                extraction_score += 35
            if "aqueous" in extraction_text or "water" in extraction_text:
                extraction_score += 30
        elif any(x in extraction_text for x in ["extract", "hydroalcoholic", "ethanolic", "essential oil"]):
            extraction_score += 40
        extraction_score = min(extraction_score, 100)

        compound_evidence_score = 50

        chemistry_score = round(
            active_score * 0.40
            + target_score * 0.30
            + extraction_score * 0.20
            + compound_evidence_score * 0.10,
            1,
        )

        rows.append({
            "Scientific_Name": plant,
            "Compound_Count": compound_count,
            "High_Value_Compound_Count": high_conf_count,
            "Best_Compounds": ", ".join(compounds[:10]),
            "Best_Targets": target_text[:500],
            "Best_Extraction_Methods": extraction_text[:500],
            "Active_Compound_Score": round(active_score, 1),
            "Target_Score": round(target_score, 1),
            "Extraction_Score": round(extraction_score, 1),
            "Compound_Evidence_Score": compound_evidence_score,
            "Chemistry_Score": chemistry_score,
        })

    return pd.DataFrame(rows)
