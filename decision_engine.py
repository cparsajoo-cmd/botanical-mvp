import pandas as pd


def _get(row, names, default=""):
    for name in names:
        if name in row.index:
            return row.get(name, default)
    return default


def _text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def score_row(row):
    score = 0

    ema = _text(_get(row, ["EMA_Status", "EMA", "EMA_HMPC_Status"]))
    who = _text(_get(row, ["WHO_Status", "WHO"]))
    escop = _text(_get(row, ["ESCOP_Status", "ESCOP"]))

    if ema in ["yes", "positive", "supported", "traditional use", "well-established use"]:
        score += 20

    if who in ["yes", "positive", "supported"]:
        score += 15

    if escop in ["yes", "positive", "supported"]:
        score += 15

    clinical = _text(_get(row, ["Clinical_Level", "Human_Evidence_Level", "Clinical_Evidence"]))
    if clinical == "strong":
        score += 20
    elif clinical == "moderate":
        score += 15
    elif clinical == "weak":
        score += 8

    meta = _text(_get(row, ["Meta_Level", "Meta_Analysis_Level"]))
    if meta == "strong":
        score += 10
    elif meta == "moderate":
        score += 6

    dosage = _text(_get(row, ["Infusion_Evidence", "Dosage_Form_Evidence", "Dosage_Form_Specific_Evidence"]))
    if dosage == "direct":
        score += 10
    elif dosage == "indirect":
        score += 5

    safety = _text(_get(row, ["Safety_Level", "Safety"]))
    if safety == "good":
        score += 5
    elif safety == "acceptable":
        score += 3
    elif safety in ["caution", "high risk"]:
        score -= 5

    commercial = _text(_get(row, ["Commercial_Level", "Commercial_Potential", "Market_Potential"]))
    if commercial == "high":
        score += 5
    elif commercial == "medium":
        score += 3

    return max(score, 0)


def classify(score):
    if score >= 85:
        return "Priority candidate"
    elif score >= 70:
        return "Conditional candidate"
    elif score >= 50:
        return "Supportive candidate"
    else:
        return "Evidence gap"


def analyze_evidence(df, product_type, dosage_form, indication, market, min_score=0):
    result = df.copy()

    filters = {
        "Product_Type": product_type,
        "Dosage_Form": dosage_form,
        "Target_Indication": indication,
        "Target_Market": market,
    }

    for column, value in filters.items():
        if column in result.columns:
            result = result[result[column].astype(str) == str(value)]

    if result.empty:
        return result

    result["Evidence_Score"] = result.apply(score_row, axis=1)
    result["Decision_Class"] = result["Evidence_Score"].apply(classify)

    result = result[result["Evidence_Score"] >= min_score]
    result = result.sort_values("Evidence_Score", ascending=False)

    return result
