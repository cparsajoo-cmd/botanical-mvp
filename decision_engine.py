import pandas as pd

from evidence_quality_engine import apply_evidence_quality


def _txt(value):
    if value is None:
        return ""
    return str(value).strip()


def _lower(value):
    return _txt(value).lower()


def _has_yes(row, cols):
    for col in cols:
        if _lower(row.get(col)) in ["yes", "true", "supported", "ema", "who", "escop"]:
            return True
    return False


def _combined_text(row):
    parts = [
        row.get("Source_Title", ""),
        row.get("Notes", ""),
        row.get("Evidence_Type", ""),
        row.get("Study_Type", ""),
        row.get("Study_Model", ""),
        row.get("Detected_Dosage_Forms", ""),
        row.get("Dosage_Form_Detected", ""),
        row.get("Detected_Indications", ""),
        row.get("Target_Indication_Detected", ""),
        row.get("Regulatory_Evidence", ""),
    ]
    return " ".join([_txt(p) for p in parts]).lower()


def _score_row(row):
    text = _combined_text(row)
    score = 0
    reasons = []

    quality_score = row.get("Evidence_Quality_Score", 0)
    try:
        quality_score = float(quality_score or 0)
    except Exception:
        quality_score = 0

    score += min(int(quality_score * 0.35), 35)
    if quality_score > 0:
        reasons.append(f"Evidence quality score: {int(quality_score)}/100")

    if _has_yes(row, ["EMA_Status", "ema_status"]) or "ema" in text:
        score += 25
        reasons.append("EMA support")

    if _has_yes(row, ["WHO_Status", "who_status"]) or "who" in text:
        score += 15
        reasons.append("WHO support")

    if _has_yes(row, ["ESCOP_Status", "escop_status"]) or "escop" in text:
        score += 15
        reasons.append("ESCOP support")

    study_type = _lower(row.get("Study_Type") or row.get("Evidence_Type"))

    if "meta" in study_type or "meta-analysis" in text or "meta analysis" in text:
        score += 20
        reasons.append("Meta-analysis")

    elif "systematic" in study_type or "systematic review" in text:
        score += 18
        reasons.append("Systematic review")

    elif "randomized" in study_type or "randomised" in study_type or "rct" in study_type:
        score += 18
        reasons.append("Randomized clinical evidence")

    elif "clinical" in study_type:
        score += 12
        reasons.append("Clinical evidence")

    study_model = _lower(row.get("Study_Model"))

    if "human" in study_model or "patients" in text or "subjects" in text:
        score += 10
        reasons.append("Human relevance")

    selected_form = _lower(row.get("Dosage_Form"))
    detected_forms = (
        _lower(row.get("Detected_Dosage_Forms")) + " " +
        _lower(row.get("Dosage_Form_Detected")) + " " +
        _lower(row.get("Dosage_Form_Relevance")) + " " +
        _lower(row.get("Direct_For_Selected_Product"))
    )

    if selected_form and selected_form in detected_forms:
        score += 20
        reasons.append("Direct dosage-form match")
    elif "direct" in detected_forms or "yes" in detected_forms:
        score += 20
        reasons.append("Direct product relevance")
    elif detected_forms.strip():
        score += 8
        reasons.append("Indirect dosage-form evidence")

    selected_indication = _lower(row.get("Target_Indication"))
    detected_indication = (
        _lower(row.get("Detected_Indications")) + " " +
        _lower(row.get("Target_Indication_Detected"))
    )

    if selected_indication and selected_indication in detected_indication:
        score += 10
        reasons.append("Direct indication match")
    elif detected_indication.strip():
        score += 5
        reasons.append("Related indication evidence")

    safety = (
        _lower(row.get("Safety_Level")) + " " +
        _lower(row.get("Safety_Signal"))
    )

    if "good" in safety or "safe" in text or "well tolerated" in text:
        score += 8
        reasons.append("Positive safety signal")
    elif "adverse" in safety or "warning" in safety or "caution" in safety:
        score += 3
        reasons.append("Safety caution")

    return min(int(score), 100), " | ".join(reasons)


def _decision_class(score):
    if score >= 80:
        return "Priority candidate"
    if score >= 60:
        return "Promising candidate"
    if score >= 40:
        return "Evidence gap"
    return "Not recommended yet"


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

    scores = []
    reasons = []

    for _, row in result.iterrows():
        score, reason = _score_row(row)
        scores.append(score)
        reasons.append(reason)

    result["Evidence_Score"] = scores
    result["Decision_Class"] = result["Evidence_Score"].apply(_decision_class)
    result["Decision_Reason"] = reasons

    if min_score and min_score > 0:
        result = result[result["Evidence_Score"] >= min_score]

    result = result.sort_values(
        by=["Evidence_Score", "Scientific_Name"],
        ascending=[False, True],
    )

    return result.reset_index(drop=True)
