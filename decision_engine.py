import pandas as pd

from evidence_quality_engine import apply_evidence_quality
from compound_intelligence_engine import apply_compound_intelligence
from compound_scoring_engine import build_compound_scores


def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _txt(x):
    if x is None:
        return ""
    return str(x).strip()


def _series_text(group, col):
    if col not in group.columns:
        return ""
    return " ".join(group[col].fillna("").astype(str).tolist()).lower()


def _first_nonempty(group, col):
    if col not in group.columns:
        return ""
    vals = group[col].dropna().astype(str)
    vals = vals[vals.str.strip() != ""]
    if vals.empty:
        return ""
    return vals.iloc[0]


def _unique_join(group, col, limit=10):
    if col not in group.columns:
        return ""
    vals = (
        group[col]
        .dropna()
        .astype(str)
        .str.strip()
    )
    vals = [v for v in vals if v and v.lower() != "nan"]
    return ", ".join(sorted(set(vals))[:limit])


def _clinical_score(group):
    text = (
        _series_text(group, "Source_Title") + " " +
        _series_text(group, "Notes") + " " +
        _series_text(group, "Study_Type") + " " +
        _series_text(group, "Evidence_Type") + " " +
        _series_text(group, "Evidence_Level")
    )

    score = 0

    if "meta-analysis" in text or "meta analysis" in text:
        score += 35
    if "systematic review" in text:
        score += 25
    if "randomized" in text or "randomised" in text or "rct" in text:
        score += 30
    if "clinical trial" in text or "human" in text or "patients" in text:
        score += 25
    if "animal" in text or "rat" in text or "mouse" in text:
        score += 10
    if "in vitro" in text or "cell" in text:
        score += 5

    score += min(20, len(group) * 2)

    if "Evidence_Quality_Score" in group.columns:
        score += min(20, group["Evidence_Quality_Score"].apply(_num).mean() * 0.2)

    return min(round(score, 1), 100)


def _regulatory_score(group):
    text = (
        _series_text(group, "Regulatory_Evidence") + " " +
        _series_text(group, "Source_Title") + " " +
        _series_text(group, "Notes")
    )

    score = 0

    if "ema" in text or "hmpc" in text:
        score += 45
    if "who" in text or "world health organization" in text:
        score += 25
    if "escop" in text:
        score += 25
    if "efsa" in text or "novel food" in text:
        score += 10
    if "fda" in text:
        score += 10

    return min(score, 100)


def _safety_score(group):
    text = (
        _series_text(group, "Safety_Level") + " " +
        _series_text(group, "Safety_Signal") + " " +
        _series_text(group, "Notes")
    )

    if "hepatotoxic" in text or "liver injury" in text or "contraindication" in text:
        return 35
    if "warning" in text or "adverse" in text or "caution" in text:
        return 55
    if "safe" in text or "well tolerated" in text:
        return 85

    return 70


def _novelty_score(group):
    text = (
        _series_text(group, "Region") + " " +
        _series_text(group, "EMA_Status")
    )

    score = 40

    if "no" in text:
        score += 20

    if any(x in text for x in ["china", "india", "iran", "africa", "south america", "asia"]):
        score += 25

    return min(score, 100)


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


def _final_score(scores):
    return round(
        scores["Clinical_Score"] * 0.25 +
        scores["Chemistry_Score"] * 0.25 +
        scores["Active_Compound_Score"] * 0.10 +
        scores["Target_Score"] * 0.10 +
        scores["Extraction_Score"] * 0.10 +
        scores["Regulatory_Score"] * 0.10 +
        scores["Safety_Score"] * 0.05 +
        scores["Novelty_Score"] * 0.03 +
        scores["Market_Score"] * 0.01 +
        scores["Commercial_Score"] * 0.01,
        1,
    )


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

    evidence = df.copy()

    required_cols = [
        "Scientific_Name",
        "Common_Name",
        "Region",
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
    ]

    for col in required_cols:
        if col not in evidence.columns:
            evidence[col] = ""

    evidence = apply_evidence_quality(evidence)
    evidence = apply_compound_intelligence(evidence)

    compound_scores = build_compound_scores(
        indication=indication,
        dosage_form=dosage_form,
    )

    output_rows = []

    for plant, group in evidence.groupby("Scientific_Name", dropna=False):
        plant = _txt(plant)

        if not plant:
            continue

        compound_row = pd.DataFrame()

        if compound_scores is not None and not compound_scores.empty:
            compound_row = compound_scores[
                compound_scores["Scientific_Name"] == plant
            ]

        if not compound_row.empty:
            cr = compound_row.iloc[0].to_dict()
        else:
            cr = {}

        clinical_score = _clinical_score(group)
        chemistry_score = _num(cr.get("Chemistry_Score", 30))
        active_score = _num(cr.get("Active_Compound_Score", 25))
        target_score = _num(cr.get("Target_Score", 25))
        extraction_score = _num(cr.get("Extraction_Score", 25))
        regulatory_score = _regulatory_score(group)
        safety_score = _safety_score(group)
        novelty_score = _novelty_score(group)
        market_score = 50
        commercial_score = 50

        scores = {
            "Clinical_Score": clinical_score,
            "Chemistry_Score": chemistry_score,
            "Active_Compound_Score": active_score,
            "Target_Score": target_score,
            "Extraction_Score": extraction_score,
            "Regulatory_Score": regulatory_score,
            "Safety_Score": safety_score,
            "Novelty_Score": novelty_score,
            "Market_Score": market_score,
            "Commercial_Score": commercial_score,
        }

        final_score = _final_score(scores)

        row = {
            "Scientific_Name": plant,
            "Common_Name": _first_nonempty(group, "Common_Name"),
            "Region": _first_nonempty(group, "Region"),
            "Product_Type": product_type,
            "Dosage_Form": dosage_form,
            "Target_Indication": indication,
            "Target_Market": market,
            "Decision_Class": _decision_class(final_score),
            "Final_Score": final_score,
            "Evidence_Score": final_score,
            **scores,
            "Compound_Count": cr.get("Compound_Count", 0),
            "High_Value_Compound_Count": cr.get("High_Value_Compound_Count", 0),
            "Best_Compounds": cr.get("Best_Compounds", ""),
            "Best_Targets": cr.get("Best_Targets", ""),
            "Best_Extraction_Methods": cr.get("Best_Extraction_Methods", ""),
            "Known_Active_Compounds": _unique_join(group, "Known_Active_Compounds"),
            "Known_Targets": _unique_join(group, "Known_Targets"),
            "Detected_Active_Compounds": _unique_join(group, "Active_Compounds"),
            "Detected_Molecular_Targets": _unique_join(group, "Molecular_Targets"),
            "Plant_Part": _unique_join(group, "Plant_Part"),
            "Extraction_Method": _unique_join(group, "Extraction_Method"),
            "EMA_Status": _first_nonempty(group, "EMA_Status"),
            "WHO_Status": _first_nonempty(group, "WHO_Status"),
            "ESCOP_Status": _first_nonempty(group, "ESCOP_Status"),
            "Regulatory_Evidence": _unique_join(group, "Regulatory_Evidence"),
            "Safety_Level": _first_nonempty(group, "Safety_Level"),
            "Safety_Signal": _first_nonempty(group, "Safety_Signal"),
            "Evidence_Record_Count": len(group),
            "Source_Title": _unique_join(group, "Source_Title", limit=20),
            "Source_URL": _unique_join(group, "Source_URL", limit=20),
            "Source_Type": _unique_join(group, "Source_Type", limit=20),
            "Decision_Reason": (
                f"Clinical: {clinical_score}/100 | "
                f"Chemistry: {chemistry_score}/100 | "
                f"Compounds: {active_score}/100 | "
                f"Targets: {target_score}/100 | "
                f"Extraction: {extraction_score}/100 | "
                f"Regulatory: {regulatory_score}/100 | "
                f"Safety: {safety_score}/100"
            ),
        }

        output_rows.append(row)

    result = pd.DataFrame(output_rows)

    if result.empty:
        return result

    if min_score and min_score > 0:
        result = result[result["Final_Score"] >= min_score]

    result = result.sort_values(
        by=["Final_Score", "Scientific_Name"],
        ascending=[False, True],
    )

    return result.reset_index(drop=True)
