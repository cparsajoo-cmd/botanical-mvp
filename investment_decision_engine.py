import pandas as pd


def _txt(x):
    return "" if x is None else str(x).strip()


def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0


def aggregate_investment_decision(df):
    if df is None or df.empty:
        return pd.DataFrame()

    data = df.copy()

    if "Scientific_Name" not in data.columns:
        data["Scientific_Name"] = ""

    if "Evidence_Score" not in data.columns:
        data["Evidence_Score"] = 0

    rows = []

    for plant, group in data.groupby("Scientific_Name"):
        scores = group["Evidence_Score"].apply(_num)

        max_score = int(scores.max())
        mean_score = int(scores.mean())

        ema = "Yes" if (group.get("EMA_Status", "").astype(str).str.lower() == "yes").any() else "No"
        who = "Yes" if (group.get("WHO_Status", "").astype(str).str.lower() == "yes").any() else "No"
        escop = "Yes" if (group.get("ESCOP_Status", "").astype(str).str.lower() == "yes").any() else "No"

        study_text = " ".join(
            group.get("Study_Type", "").astype(str).tolist()
            + group.get("Evidence_Type", "").astype(str).tolist()
            + group.get("Study_Model", "").astype(str).tolist()
        ).lower()

        has_human = "human" in study_text or "clinical" in study_text or "randomized" in study_text
        has_rct = "randomized" in study_text or "rct" in study_text
        has_meta = "meta" in study_text
        has_review = "systematic" in study_text or "review" in study_text

        direct_text = " ".join(
            group.get("Direct_For_Selected_Product", "").astype(str).tolist()
            + group.get("Dosage_Form_Relevance", "").astype(str).tolist()
        ).lower()

        has_direct = "yes" in direct_text or "direct" in direct_text

        safety_text = " ".join(
            group.get("Safety_Level", "").astype(str).tolist()
            + group.get("Safety_Signal", "").astype(str).tolist()
        ).lower()

        safety = "Good" if ("safe" in safety_text or "well tolerated" in safety_text or "good" in safety_text) else "To verify"

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

    return result.sort_values(
        by=["Investment_Score", "Scientific_Name"],
        ascending=[False, True]
    ).reset_index(drop=True)
