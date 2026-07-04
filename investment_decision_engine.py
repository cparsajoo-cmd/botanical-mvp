import pandas as pd


def _txt(x):
    return "" if x is None else str(x).strip()


def _num(x):
    try:
        return float(x or 0)
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


def aggregate_investment_decision(df):
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()

    if "Scientific_Name" not in data.columns:
        data["Scientific_Name"] = ""

    if "Evidence_Score" not in data.columns:
        data["Evidence_Score"] = 0

    rows = []

    for plant, group in data.groupby("Scientific_Name", dropna=False):
        scores = group["Evidence_Score"].apply(_num)

        max_score = int(scores.max()) if len(scores) else 0
        mean_score = int(scores.mean()) if len(scores) else 0

        ema = "Yes" if _any_yes(group, "EMA_Status") else "No"
        who = "Yes" if _any_yes(group, "WHO_Status") else "No"
        escop = "Yes" if _any_yes(group, "ESCOP_Status") else "No"

        study_text = (
            _series_text(group, "Study_Type") + " " +
            _series_text(group, "Evidence_Type") + " " +
            _series_text(group, "Study_Model") + " " +
            _series_text(group, "Notes") + " " +
            _series_text(group, "Source_Title")
        )

        has_human = any(x in study_text for x in ["human", "clinical", "patients", "subjects", "volunteers"])
        has_rct = any(x in study_text for x in ["randomized", "randomised", "rct", "placebo"])
        has_meta = "meta" in study_text
        has_review = "systematic" in study_text or "review" in study_text

        direct_text = (
            _series_text(group, "Direct_For_Selected_Product") + " " +
            _series_text(group, "Dosage_Form_Relevance") + " " +
            _series_text(group, "Directness_Reason")
        )

        has_direct = "yes" in direct_text or "direct" in direct_text

        safety_text = (
            _series_text(group, "Safety_Level") + " " +
            _series_text(group, "Safety_Signal")
        )

        safety = "Good" if any(x in safety_text for x in ["safe", "well tolerated", "good"]) else "To verify"

        investment_score = 0

        investment_score += min(max_score, 40)

        if has_meta:
            investment_score += 15
        elif has_rct:
            investment_score += 12
        elif has_human:
            investment_score += 8
        elif has_review:
            investment_score += 5

        if ema == "Yes":
            investment_score += 15
        if who == "Yes":
            investment_score += 8
        if escop == "Yes":
            investment_score += 8

        if has_direct:
            investment_score += 10

        if safety == "Good":
            investment_score += 4

        investment_score = min(int(investment_score), 100)

        if investment_score >= 80:
            final_decision = "GO"
            investment_class = "High-priority investment candidate"
        elif investment_score >= 60:
            final_decision = "GO WITH VALIDATION"
            investment_class = "Promising candidate, validation needed"
        elif investment_score >= 40:
            final_decision = "WAIT"
            investment_class = "Evidence gap, more validation needed"
        else:
            final_decision = "NO-GO"
            investment_class = "Not recommended yet"

        rows.append({
            "Scientific_Name": plant,
            "Investment_Score": investment_score,
            "Final_Decision": final_decision,
            "Investment_Class": investment_class,
            "Best_Evidence_Score": max_score,
            "Mean_Evidence_Score": mean_score,
            "Human_Evidence": "Yes" if has_human else "No",
            "RCT_Evidence": "Yes" if has_rct else "No",
            "Meta_Analysis": "Yes" if has_meta else "No",
            "Direct_Dosage_Form_Evidence": "Yes" if has_direct else "No",
            "EMA": ema,
            "WHO": who,
            "ESCOP": escop,
            "Safety": safety,
            "Number_of_Records": len(group),
        })

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    return result.sort_values(
        by=["Investment_Score", "Scientific_Name"],
        ascending=[False, True]
    ).reset_index(drop=True)
