import pandas as pd

from evidence_quality_engine import apply_evidence_quality
from compound_intelligence_engine import apply_compound_intelligence


CLINICAL_WEIGHT = 0.25
CHEMISTRY_WEIGHT = 0.20
ACTIVE_COMPOUND_WEIGHT = 0.15
TARGET_WEIGHT = 0.10
EXTRACTION_WEIGHT = 0.10
REGULATORY_WEIGHT = 0.10
SAFETY_WEIGHT = 0.05
NOVELTY_WEIGHT = 0.05
MARKET_WEIGHT = 0.05
COMMERCIAL_WEIGHT = 0.05


def _txt(value):
    if value is None:
        return ""
    return str(value).strip()


def _num(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def _series_text(group, col):
    if col not in group.columns:
        return ""
    return " ".join(group[col].fillna("").astype(str).tolist()).lower()


def _any_yes(group, col):
    if col not in group.columns:
        return False
    return group[col].fillna("").astype(str).str.lower().isin(
        ["yes", "true", "supported"]
    ).any()


def _decision_class(score):
    if score >= 85:
        return "Product-ready candidate"
    if score >= 70:
        return "Strategic development candidate"
    if score >= 55:
        return "R&D candidate"
    if score >= 40:
        return "Early research candidate"
    return "Not recommended yet"


def _clinical_score(group):
    text = (
        _series_text(group, "Source_Title") + " " +
        _series_text(group, "Notes") + " " +
        _series_text(group, "Study_Type") + " " +
        _series_text(group, "Evidence_Type") + " " +
        _series_text(group, "Study_Model") + " " +
        _series_text(group, "Evidence_Level")
    )

    score = 0

    meta_count = text.count("meta-analysis") + text.count("meta analysis")
    systematic_count = text.count("systematic review")
    rct_count = text.count("randomized") + text.count("randomised") + text.count("rct")
    clinical_count = text.count("clinical trial") + text.count("patients") + text.count("subjects")

    if meta_count > 0:
        score += min(35, 20 + meta_count * 5)

    if systematic_count > 0:
        score += min(25, 15 + systematic_count * 4)

    if rct_count > 0:
        score += min(35, 20 + rct_count * 4)

    if clinical_count > 0:
        score += min(20, 10 + clinical_count * 2)

    if "human" in text or "patients" in text or "subjects" in text:
        score += 15

    elif "animal" in text or "rat" in text or "mouse" in text or "mice" in text:
        score += 8

    elif "in vitro" in text or "cell" in text:
        score += 4

    if "Evidence_Quality_Score" in group.columns:
        avg_quality = group["Evidence_Quality_Score"].apply(_num).mean()
        score += min(20, avg_quality * 0.20)

    return min(round(score, 1), 100)


def _regulatory_score(group):
    text = (
        _series_text(group, "Regulatory_Evidence") + " " +
        _series_text(group, "Notes") + " " +
        _series_text(group, "Source_Title")
    )

    score = 0

    if _any_yes(group, "EMA_Status") or "ema" in text or "hmpc" in text:
        score += 45

    if _any_yes(group, "WHO_Status") or "who monograph" in text:
        score += 25

    if _any_yes(group, "ESCOP_Status") or "escop" in text:
        score += 25

    if "fda" in text or "dailymed" in text:
        score += 10

    return min(score, 100)


def _chemistry_score(group):
    if "Chemistry_Score" in group.columns:
        return min(round(group["Chemistry_Score"].apply(_num).mean(), 1), 100)

    return 0


def _active_compound_score(group):
    text = _series_text(group, "Active_Compounds") + " " + _series_text(group, "Known_Active_Compounds")

    if not text.strip():
        return 0

    compounds = set()

    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk and chunk != "nan":
            compounds.add(chunk)

    return min(30 + len(compounds) * 12, 100)


def _target_score(group):
    text = _series_text(group, "Molecular_Targets") + " " + _series_text(group, "Known_Targets")

    if not text.strip():
        return 0

    targets = set()

    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk and chunk != "nan":
            targets.add(chunk)

    return min(30 + len(targets) * 15, 100)


def _extraction_score(group):
    text = (
        _series_text(group, "Extraction_Method") + " " +
        _series_text(group, "Dosage_Form") + " " +
        _series_text(group, "Detected_Dosage_Forms")
    )

    if not text.strip():
        return 20

    score = 55

    if "infusion" in text or "aqueous" in text:
        score += 25

    if "extract" in text or "hydroalcoholic" in text or "ethanolic" in text:
        score += 20

    if "essential oil" in text or "distillation" in text:
        score += 15

    return min(score, 100)


def _safety_score(group):
    text = (
        _series_text(group, "Safety_Level") + " " +
        _series_text(group, "Safety_Signal") + " " +
        _series_text(group, "Notes")
    )

    if "hepatotoxic" in text or "warning" in text or "contraindication" in text:
        return 35

    if "adverse" in text or "caution" in text:
        return 55

    if "safe" in text or "well tolerated" in text:
        return 85

    return 70


def _novelty_score(group):
    if "Novelty_Score" in group.columns:
        values = group["Novelty_Score"].apply(_num)
        if values.max() > 0:
            return min(round(values.max(), 1), 100)

    text = _series_text(group, "Region") + " " + _series_text(group, "EMA_Status")

    score = 35

    if "no" in _series_text(group, "EMA_Status"):
        score += 30

    if any(x in text for x in ["china", "india", "asia", "pacific", "africa"]):
        score += 25

    return min(score, 100)


def _market_score(group):
    if "Market_Score" in group.columns:
        values = group["Market_Score"].apply(_num)
        if values.max() > 0:
            return min(round(values.max(), 1), 100)

    return 50


def _commercial_score(group):
    if "Commercial_Score" in group.columns:
        values = group["Commercial_Score"].apply(_num)
        if values.max() > 0:
            return min(round(values.max(), 1), 100)

    extraction = _extraction_score(group)
    regulatory = _regulatory_score(group)

    return min(round((extraction * 0.6 + regulatory * 0.4), 1), 100)


def _weighted_final_score(scores):
    return round(
        scores["Clinical_Score"] * CLINICAL_WEIGHT
        + scores["Chemistry_Score"] * CHEMISTRY_WEIGHT
        + scores["Active_Compound_Score"] * ACTIVE_COMPOUND_WEIGHT
        + scores["Target_Score"] * TARGET_WEIGHT
        + scores["Extraction_Score"] * EXTRACTION_WEIGHT
        + scores["Regulatory_Score"] * REGULATORY_WEIGHT
        + scores["Safety_Score"] * SAFETY_WEIGHT
        + scores["Novelty_Score"] * NOVELTY_WEIGHT
        + scores["Market_Score"] * MARKET_WEIGHT
        + scores["Commercial_Score"] * COMMERCIAL_WEIGHT,
        1,
    )


def _reason_text(scores):
    reasons = []

    reasons.append(f"Clinical evidence: {scores['Clinical_Score']}/100")
    reasons.append(f"Chemistry: {scores['Chemistry_Score']}/100")
    reasons.append(f"Active compounds: {scores['Active_Compound_Score']}/100")
    reasons.append(f"Molecular targets: {scores['Target_Score']}/100")
    reasons.append(f"Extraction feasibility: {scores['Extraction_Score']}/100")
    reasons.append(f"Regulatory fit: {scores['Regulatory_Score']}/100")
    reasons.append(f"Safety: {scores['Safety_Score']}/100")
    reasons.append(f"Novelty/R&D opportunity: {scores['Novelty_Score']}/100")
    reasons.append(f"Market opportunity: {scores['Market_Score']}/100")
    reasons.append(f"Commercial feasibility: {scores['Commercial_Score']}/100")

    return " | ".join(reasons)


def analyze_evidence(
    df,
    product_type,
    dosage_form,
    indication,
    market,
    min_score=0,
):
    if df is None or df.empty:
        return pd.DataFrame()

    result = df.copy()

    required_cols = [
        "Scientific_Name",
        "Common_Name",
        "Product_Type",
        "Dosage_Form",
        "Target_Indication",
        "Target_Market",
        "EMA_Status",
        "WHO_Status",
        "ESCOP_Status",
        "Evidence_Type",
        "Evidence_Level",
        "Study_Type",
        "Study_Model",
        "Detected_Dosage_Forms",
        "Detected_Indications",
        "Dosage_Form_Detected",
        "Target_Indication_Detected",
        "Dosage_Form_Relevance",
        "Direct_For_Selected_Product",
        "Directness_Reason",
        "Safety_Level",
        "Safety_Signal",
        "Regulatory_Evidence",
        "Notes",
        "Source_Title",
        "Source_URL",
        "Source_Type",
        "Source_Organization",
        "Source_Year",
        "Active_Compounds",
        "Molecular_Targets",
        "Plant_Part",
        "Extraction_Method",
        "Known_Active_Compounds",
        "Known_Targets",
        "Region",
        "Novelty_Score",
        "Market_Score",
        "Commercial_Score",
    ]

    for col in required_cols:
        if col not in result.columns:
            result[col] = ""

    result = apply_evidence_quality(result)
    result = apply_compound_intelligence(result)

    plant_scores = {}

    for plant, group in result.groupby("Scientific_Name", dropna=False):
        scores = {
            "Clinical_Score": _clinical_score(group),
            "Chemistry_Score": _chemistry_score(group),
            "Active_Compound_Score": _active_compound_score(group),
            "Target_Score": _target_score(group),
            "Extraction_Score": _extraction_score(group),
            "Regulatory_Score": _regulatory_score(group),
            "Safety_Score": _safety_score(group),
            "Novelty_Score": _novelty_score(group),
            "Market_Score": _market_score(group),
            "Commercial_Score": _commercial_score(group),
        }

        final_score = _weighted_final_score(scores)

        plant_scores[plant] = {
            **scores,
            "Final_Score": final_score,
            "Evidence_Score": final_score,
            "Decision_Class": _decision_class(final_score),
            "Decision_Reason": _reason_text(scores),
        }

    for col in [
        "Clinical_Score",
        "Chemistry_Score",
        "Active_Compound_Score",
        "Target_Score",
        "Extraction_Score",
        "Regulatory_Score",
        "Safety_Score",
        "Novelty_Score",
        "Market_Score",
        "Commercial_Score",
        "Final_Score",
        "Evidence_Score",
        "Decision_Class",
        "Decision_Reason",
    ]:
        result[col] = result["Scientific_Name"].apply(
            lambda x: plant_scores.get(x, {}).get(col, 0 if "Score" in col else "")
        )

    if min_score and min_score > 0:
        result = result[result["Final_Score"] >= min_score]

    result = result.sort_values(
        by=["Final_Score", "Scientific_Name"],
        ascending=[False, True],
    )

    return result.reset_index(drop=True)
