import pandas as pd

from evidence_quality_engine import apply_evidence_quality


def _txt(value):
    if value is None:
        return ""
    return str(value).strip()


def _lower(value):
    return _txt(value).lower()


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
    if score >= 80:
        return "Priority candidate"
    if score >= 60:
        return "Promising candidate"
    if score >= 40:
        return "Evidence gap"
    return "Not recommended yet"


def _aggregate_plant_score(group):
    score = 0
    reasons = []

    text = (
        _series_text(group, "Source_Title") + " " +
        _series_text(group, "Notes") + " " +
        _series_text(group, "Study_Type") + " " +
        _series_text(group, "Evidence_Type") + " " +
        _series_text(group, "Study_Model") + " " +
        _series_text(group, "Evidence_Level") + " " +
        _series_text(group, "Regulatory_Evidence")
    )

    # Regulatory
    if _any_yes(group, "EMA_Status") or "ema" in text or "hmpc" in text:
        score += 25
        reasons.append("EMA/HMPC support")

    if _any_yes(group, "WHO_Status") or "who monograph" in text:
        score += 15
        reasons.append("WHO support")

    if _any_yes(group, "ESCOP_Status") or "escop" in text:
        score += 15
        reasons.append("ESCOP support")

    # Evidence hierarchy
    meta_count = text.count("meta-analysis") + text.count("meta analysis")
    systematic_count = text.count("systematic review")
    rct_count = text.count("randomized") + text.count("randomised") + text.count("rct")
    clinical_count = text.count("clinical trial") + text.count("patients") + text.count("subjects")

    if meta_count > 0:
        score += min(25, 15 + meta_count * 5)
        reasons.append(f"Meta-analysis evidence: {meta_count}")

    if systematic_count > 0:
        score += min(18, 10 + systematic_count * 4)
        reasons.append(f"Systematic review evidence: {systematic_count}")

    if rct_count > 0:
        score += min(25, 12 + rct_count * 4)
        reasons.append(f"RCT evidence: {rct_count}")

    elif clinical_count > 0:
        score += min(15, 8 + clinical_count * 2)
        reasons.append("Clinical human evidence")

    # Human / animal / in vitro
    if "human" in text or "patients" in text or "subjects" in text:
        score += 10
        reasons.append("Human relevance")

    elif "animal" in text or "rat" in text or "mouse" in text or "mice" in text:
        score += 5
        reasons.append("Animal evidence")

    elif "in vitro" in text or "cell" in text:
        score += 3
        reasons.append("In vitro evidence")

    # Dosage directness
    direct_text = (
        _series_text(group, "Direct_For_Selected_Product") + " " +
        _series_text(group, "Dosage_Form_Relevance") + " " +
        _series_text(group, "Directness_Reason") + " " +
        _series_text(group, "Detected_Dosage_Forms") + " " +
        _series_text(group, "Dosage_Form_Detected")
    )

    if "yes" in direct_text or "direct" in direct_text:
        score += 15
        reasons.append("Direct or relevant dosage-form evidence")
    elif direct_text.strip():
        score += 6
        reasons.append("Indirect dosage-form evidence")

    # Indication relevance
    indication_text = (
        _series_text(group, "Detected_Indications") + " " +
        _series_text(group, "Target_Indication_Detected") + " " +
        _series_text(group, "Target_Indication")
    )

    if indication_text.strip():
        score += 8
        reasons.append("Indication relevance detected")

    # Evidence quality
    if "Evidence_Quality_Score" in group.columns:
        avg_quality = group["Evidence_Quality_Score"].apply(_num).mean()
        score += min(15, int(avg_quality * 0.15))
        reasons.append(f"Average evidence quality: {int(avg_quality)}/100")

    # Safety
    safety_text = (
        _series_text(group, "Safety_Level") + " " +
        _series_text(group, "Safety_Signal")
    )

    if "good" in safety_text or "safe" in safety_text or "well tolerated" in text:
        score += 7
        reasons.append("Positive safety signal")
    elif "adverse" in safety_text or "warning" in safety_text or "caution" in safety_text:
        score += 2
        reasons.append("Safety caution")

    score = min(int(score), 100)

    return score, " | ".join(reasons)


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
    ]

    for col in required_cols:
        if col not in result.columns:
            result[col] = ""

    result = apply_evidence_quality(result)

    plant_scores = {}

    for plant, group in result.groupby("Scientific_Name", dropna=False):
        score, reason = _aggregate_plant_score(group)
        plant_scores[plant] = {
            "score": score,
            "reason": reason,
            "decision": _decision_class(score),
        }

    result["Evidence_Score"] = result["Scientific_Name"].apply(
        lambda x: plant_scores.get(x, {}).get("score", 0)
    )

    result["Decision_Class"] = result["Scientific_Name"].apply(
        lambda x: plant_scores.get(x, {}).get("decision", "Not recommended yet")
    )

    result["Decision_Reason"] = result["Scientific_Name"].apply(
        lambda x: plant_scores.get(x, {}).get("reason", "")
    )

    if min_score and min_score > 0:
        result = result[result["Evidence_Score"] >= min_score]

    result = result.sort_values(
        by=["Evidence_Score", "Scientific_Name"],
        ascending=[False, True],
    )

    return result.reset_index(drop=True)
