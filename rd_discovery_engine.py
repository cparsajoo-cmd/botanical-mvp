import pandas as pd

from evidence_database import load_evidence_database
from plant_compound_database import load_plant_compound_database
from compound_profile_database import load_compound_profiles
from global_candidate_ranking_engine import rank_global_candidates


def _safe_df(data):
    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        return data.copy()
    return pd.DataFrame(data)


def _num(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _text(value):
    if value is None:
        return ""
    return str(value)


def _score_regulatory(row):
    ema = _text(row.get("EMA_Status", "")).lower()
    who = _text(row.get("WHO_Status", "")).lower()
    escop = _text(row.get("ESCOP_Status", "")).lower()

    score = 0

    if ema in ["yes", "true", "supported"]:
        score += 45
    if who in ["yes", "true", "supported"]:
        score += 25
    if escop in ["yes", "true", "supported"]:
        score += 25

    if score == 0:
        score = _num(row.get("Regulatory_Score", 25), 25)

    return min(score, 100)


def _score_safety(row):
    safety_text = (
        _text(row.get("Safety_Level", "")) + " " +
        _text(row.get("Safety_Signal", "")) + " " +
        _text(row.get("toxicity", "")) + " " +
        _text(row.get("safety_note", ""))
    ).lower()

    if any(x in safety_text for x in ["hepatotoxic", "contraindication", "serious", "warning"]):
        return 30

    if any(x in safety_text for x in ["caution", "adverse", "medium"]):
        return 60

    if any(x in safety_text for x in ["safe", "well tolerated", "low"]):
        return 85

    return 70


def _score_extraction(row):
    extraction = (
        _text(row.get("extraction_method", "")) + " " +
        _text(row.get("Extraction_Method", "")) + " " +
        _text(row.get("solvent", "")) + " " +
        _text(row.get("extraction_difficulty", ""))
    ).lower()

    if not extraction.strip():
        return 40

    score = 50

    if any(x in extraction for x in ["easy", "infusion", "aqueous", "water"]):
        score += 30

    if any(x in extraction for x in ["hydroalcoholic", "hydroethanolic", "ethanol", "extract"]):
        score += 25

    if any(x in extraction for x in ["essential oil", "steam distillation", "co2", "supercritical"]):
        score += 20

    if "difficult" in extraction:
        score -= 25

    return max(0, min(score, 100))


def _score_evidence(row):
    text = (
        _text(row.get("Evidence_Level", "")) + " " +
        _text(row.get("Evidence_Type", "")) + " " +
        _text(row.get("Study_Type", "")) + " " +
        _text(row.get("Source_Title", "")) + " " +
        _text(row.get("Notes", "")) + " " +
        _text(row.get("evidence_level", ""))
    ).lower()

    score = 20

    if "meta" in text:
        score += 30
    if "systematic" in text:
        score += 25
    if "randomized" in text or "randomised" in text or "rct" in text:
        score += 30
    if "clinical" in text or "human" in text or "patient" in text:
        score += 25
    if "animal" in text or "rat" in text or "mouse" in text:
        score += 10
    if "in vitro" in text or "cell" in text:
        score += 5

    quality = _num(row.get("Evidence_Quality_Score", 0), 0)
    if quality:
        score = max(score, quality)

    return min(score, 100)


def _score_chemistry(row):
    activity = _num(row.get("activity_score", 0), 0)

    if activity:
        return min(activity, 100)

    compound = _text(row.get("compound_name", "")) or _text(row.get("Compound", ""))
    target = _text(row.get("target", "")) or _text(row.get("major_target", ""))

    score = 30

    if compound:
        score += 30
    if target:
        score += 25

    compound_class = (
        _text(row.get("compound_class", "")) + " " +
        _text(row.get("Compound_Class", ""))
    ).lower()

    if any(x in compound_class for x in ["flavonoid", "terpene", "phenolic", "saponin", "lactone", "alkaloid"]):
        score += 15

    return min(score, 100)


def _score_target_match(row, indication):
    indication = _text(indication).lower()

    target_text = (
        _text(row.get("target", "")) + " " +
        _text(row.get("major_target", "")) + " " +
        _text(row.get("Known_Targets", "")) + " " +
        _text(row.get("Molecular_Targets", ""))
    ).lower()

    score = 30

    if any(x in indication for x in ["sleep", "relaxation", "anxiety"]):
        if "gaba" in target_text:
            score += 40
        if "benzodiazepine" in target_text:
            score += 25
        if "serotonin" in target_text or "serotonergic" in target_text:
            score += 20
        if "hpa" in target_text:
            score += 15

    if any(x in indication for x in ["inflammation", "skin"]):
        if "nf-kb" in target_text or "cox" in target_text:
            score += 40
        if "tnf" in target_text or "il-6" in target_text:
            score += 25

    return min(score, 100)


def _score_innovation(row):
    regulatory = _score_regulatory(row)
    chemistry = _score_chemistry(row)

    region = (
        _text(row.get("Region", "")) + " " +
        _text(row.get("country_region", ""))
    ).lower()

    score = 35

    if chemistry >= 80:
        score += 25

    if regulatory < 50:
        score += 20

    if any(x in region for x in ["china", "india", "africa", "egypt", "iran", "amazon", "south america"]):
        score += 20

    return min(score, 100)


def _classify(row):
    final_score = _num(row.get("Final_RnD_Score", 0), 0)
    regulatory = _num(row.get("Regulatory_Score_Unified", 0), 0)
    evidence = _num(row.get("Evidence_Score_Unified", 0), 0)
    innovation = _num(row.get("Innovation_Score", 0), 0)

    if final_score >= 80 and regulatory >= 70 and evidence >= 65:
        return "Commercial-ready"

    if final_score >= 70 and innovation >= 65:
        return "R&D candidate"

    if innovation >= 75 and final_score >= 60:
        return "Discovery / high-risk candidate"

    if final_score >= 50:
        return "Early research candidate"

    return "Low priority"


def _final_score(row):
    evidence = _num(row.get("Evidence_Score_Unified", 0), 0)
    chemistry = _num(row.get("Chemistry_Score_Unified", 0), 0)
    target = _num(row.get("Target_Match_Score", 0), 0)
    extraction = _num(row.get("Extraction_Score_Unified", 0), 0)
    regulatory = _num(row.get("Regulatory_Score_Unified", 0), 0)
    safety = _num(row.get("Safety_Score_Unified", 0), 0)
    innovation = _num(row.get("Innovation_Score", 0), 0)

    return round(
        evidence * 0.22
        + chemistry * 0.22
        + target * 0.16
        + extraction * 0.12
        + regulatory * 0.12
        + safety * 0.08
        + innovation * 0.08,
        1,
    )


def build_rd_discovery_ranking(
    product_type,
    dosage_form,
    indication,
    market,
    target_count=100,
):
    global_df = rank_global_candidates(
        indication=indication,
        dosage_form=dosage_form,
        market=market,
        target_count=target_count,
    )

    evidence_df = load_evidence_database()
    evidence_df = _safe_df(evidence_df)

    plant_compounds_df = _safe_df(load_plant_compound_database())
    compound_profiles_df = _safe_df(load_compound_profiles())

    if global_df is None or global_df.empty:
        return pd.DataFrame()

    global_df = global_df.copy()

    if not plant_compounds_df.empty:
        plant_compounds_df = plant_compounds_df.rename(
            columns={
                "scientific_name": "Scientific_Name",
                "compound_name": "compound_name",
            }
        )

        combined = global_df.merge(
            plant_compounds_df,
            on="Scientific_Name",
            how="left",
        )
    else:
        combined = global_df.copy()
        combined["compound_name"] = ""

    if not compound_profiles_df.empty and "compound_name" in combined.columns:
        combined = combined.merge(
            compound_profiles_df,
            on="compound_name",
            how="left",
            suffixes=("", "_profile"),
        )

    if not evidence_df.empty and "Scientific_Name" in evidence_df.columns:
        evidence_summary = (
            evidence_df
            .groupby("Scientific_Name", dropna=False)
            .agg(
                Evidence_Record_Count=("Scientific_Name", "count"),
                Source_Title=("Source_Title", lambda x: " | ".join(x.dropna().astype(str).head(5))),
                Source_URL=("Source_URL", lambda x: " | ".join(x.dropna().astype(str).head(5))),
                Study_Type=("Study_Type", lambda x: " | ".join(x.dropna().astype(str).head(5)) if "Study_Type" in evidence_df.columns else ""),
                Evidence_Level=("Evidence_Level", lambda x: " | ".join(x.dropna().astype(str).head(5)) if "Evidence_Level" in evidence_df.columns else ""),
                Evidence_Type=("Evidence_Type", lambda x: " | ".join(x.dropna().astype(str).head(5)) if "Evidence_Type" in evidence_df.columns else ""),
                Notes=("Notes", lambda x: " | ".join(x.dropna().astype(str).head(5)) if "Notes" in evidence_df.columns else ""),
            )
            .reset_index()
        )

        combined = combined.merge(
            evidence_summary,
            on="Scientific_Name",
            how="left",
        )
    else:
        combined["Evidence_Record_Count"] = 0

    needed_cols = [
        "compound_name",
        "compound_class",
        "major_target",
        "mechanism",
        "activity_score",
        "bioavailability",
        "stability",
        "extraction_difficulty",
        "toxicity",
        "commercial_interest",
        "Evidence_Record_Count",
        "Source_Title",
        "Source_URL",
        "Study_Type",
        "Evidence_Level",
        "Evidence_Type",
        "Notes",
    ]

    for col in needed_cols:
        if col not in combined.columns:
            combined[col] = ""

    combined["Evidence_Score_Unified"] = combined.apply(_score_evidence, axis=1)
    combined["Chemistry_Score_Unified"] = combined.apply(_score_chemistry, axis=1)
    combined["Target_Match_Score"] = combined.apply(lambda r: _score_target_match(r, indication), axis=1)
    combined["Extraction_Score_Unified"] = combined.apply(_score_extraction, axis=1)
    combined["Regulatory_Score_Unified"] = combined.apply(_score_regulatory, axis=1)
    combined["Safety_Score_Unified"] = combined.apply(_score_safety, axis=1)
    combined["Innovation_Score"] = combined.apply(_score_innovation, axis=1)
    combined["Final_RnD_Score"] = combined.apply(_final_score, axis=1)
    combined["Final_Class"] = combined.apply(_classify, axis=1)

    output_cols = [
        "Scientific_Name",
        "Common_Name",
        "Region",
        "compound_name",
        "compound_class",
        "major_target",
        "mechanism",
        "Plant_Part",
        "Extraction_Method",
        "extraction_method",
        "Evidence_Record_Count",
        "Evidence_Score_Unified",
        "Chemistry_Score_Unified",
        "Target_Match_Score",
        "Extraction_Score_Unified",
        "Regulatory_Score_Unified",
        "Safety_Score_Unified",
        "Innovation_Score",
        "Final_RnD_Score",
        "Final_Class",
        "Source_Title",
        "Source_URL",
    ]

    output_cols = [c for c in output_cols if c in combined.columns]

    output = combined[output_cols].copy()

    output = output.sort_values(
        by=["Final_RnD_Score", "Innovation_Score", "Chemistry_Score_Unified"],
        ascending=[False, False, False],
    )

    output = output.drop_duplicates(
        subset=["Scientific_Name", "compound_name"],
        keep="first",
    )

    return output.reset_index(drop=True)
