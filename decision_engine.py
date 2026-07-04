import pandas as pd


def _safe_numeric(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _score_from_evidence(row):
    """
    Uses the newest standardized evidence fields first.
    Falls back to older fields if needed.
    """

    score = 0

    # 1. Existing AI / evidence score
    if "ai_score" in row and _safe_numeric(row.get("ai_score")) > 0:
        score += _safe_numeric(row.get("ai_score"))

    elif "Evidence_Score" in row and _safe_numeric(row.get("Evidence_Score")) > 0:
        score += _safe_numeric(row.get("Evidence_Score"))

    else:
        # 2. Evidence level
        evidence_level = _safe_text(row.get("Evidence_Level")).lower()

        level_points = {
            "very high": 40,
            "high": 35,
            "moderate": 25,
            "low": 12,
            "very low": 6,
            "traditional": 10,
            "unknown": 0,
        }

        score += level_points.get(evidence_level, 0)

        # 3. Study type
        study_type = (
            _safe_text(row.get("Study_Type")) + " " +
            _safe_text(row.get("Evidence_Type"))
        ).lower()

        if "meta-analysis" in study_type or "meta analysis" in study_type:
            score += 35
        elif "systematic review" in study_type:
            score += 30
        elif "randomized" in study_type or "rct" in study_type:
            score += 30
        elif "clinical" in study_type:
            score += 22
        elif "observational" in study_type:
            score += 15
        elif "animal" in study_type:
            score += 8
        elif "in vitro" in study_type:
            score += 5

        # 4. Study model
        study_model = _safe_text(row.get("Study_Model")).lower()

        if "human" in study_model:
            score += 15
        elif "animal" in study_model:
            score += 5
        elif "vitro" in study_model or "cell" in study_model:
            score += 3

        # 5. Dosage-form relevance
        relevance = (
            _safe_text(row.get("Direct_For_Selected_Product")) + " " +
            _safe_text(row.get("Dosage_Form_Relevance"))
        ).lower()

        if "yes" in relevance or "direct" in relevance:
            score += 25
        elif "indirect" in relevance:
            score += 10

        # 6. Regulatory support
        regulatory = (
            _safe_text(row.get("Regulatory_Evidence")) + " " +
            _safe_text(row.get("EMA_Status")) + " " +
            _safe_text(row.get("WHO_Status")) + " " +
            _safe_text(row.get("ESCOP_Status"))
        ).lower()

        if "ema" in regulatory or "who" in regulatory or "escop" in regulatory or "yes" in regulatory:
            score += 20

    return min(int(score), 100)


def _decision_class(score):
    if score >= 80:
        return "Priority candidate"
    if score >= 60:
        return "Promising candidate"
    if score >= 40:
        return "Evidence gap"
    return "Not recommended yet"


def _decision_reason(row, score):
    reasons = []

    study_type = _safe_text(row.get("Study_Type")) or _safe_text(row.get("Evidence_Type"))
    study_model = _safe_text(row.get("Study_Model"))
    dosage_relevance = _safe_text(row.get("Dosage_Form_Relevance"))
    directness = _safe_text(row.get("Direct_For_Selected_Product"))
    regulatory = _safe_text(row.get("Regulatory_Evidence"))

    if study_type:
        reasons.append(f"Study type: {study_type}")

    if study_model:
        reasons.append(f"Study model: {study_model}")

    if dosage_relevance:
        reasons.append(f"Dosage-form relevance: {dosage_relevance}")

    if directness:
        reasons.append(f"Direct for selected product: {directness}")

    if regulatory and regulatory != "None":
        reasons.append(f"Regulatory evidence: {regulatory}")

    if not reasons:
        reasons.append("Limited structured evidence available.")

    reasons.append(f"Computed evidence score: {score}/100")

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

    for col in [
        "Scientific_Name",
        "Common_Name",
        "Product_Type",
        "Dosage_Form",
        "Target_Indication",
        "Target_Market",
        "Evidence_Score",
        "Evidence_Type",
        "Evidence_Level",
        "Study_Type",
        "Study_Model",
        "Dosage_Form_Relevance",
        "Direct_For_Selected_Product",
        "Directness_Reason",
        "Regulatory_Evidence",
        "Notes",
    ]:
        if col not in result.columns:
            result[col] = ""

    result["Evidence_Score"] = result.apply(_score_from_evidence, axis=1)
    result["Decision_Class"] = result["Evidence_Score"].apply(_decision_class)
    result["Decision_Reason"] = result.apply(
        lambda row: _decision_reason(row, row["Evidence_Score"]),
        axis=1,
    )

    if min_score and min_score > 0:
        result = result[result["Evidence_Score"] >= min_score]

    result = result.sort_values(
        by=["Evidence_Score", "Scientific_Name"],
        ascending=[False, True],
    )

    return result.reset_index(drop=True)
