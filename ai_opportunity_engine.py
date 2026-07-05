"""
AI Opportunity Engine
Step 8 - R&D Opportunity Interpretation

This module converts unified R&D ranking rows into
business/R&D opportunity recommendations.
"""


def _num(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def calculate_opportunity_scores(row):
    evidence = _num(row.get("Evidence_Score_Unified", 0))
    chemistry = _num(row.get("Chemistry_Score_Unified", 0))
    target = _num(row.get("Target_Match_Score", 0))
    extraction = _num(row.get("Extraction_Score_Unified", 0))
    regulatory = _num(row.get("Regulatory_Score_Unified", 0))
    safety = _num(row.get("Safety_Score_Unified", 0))
    innovation = _num(row.get("Innovation_Score", 0))

    market_saturation = max(0, 100 - innovation)
    patent_risk = max(0, 100 - innovation)

    investment_score = round(
        evidence * 0.18
        + chemistry * 0.18
        + target * 0.14
        + extraction * 0.10
        + regulatory * 0.12
        + safety * 0.10
        + innovation * 0.18,
        1,
    )

    risk_score = round(
        (100 - safety) * 0.30
        + (100 - regulatory) * 0.30
        + market_saturation * 0.20
        + patent_risk * 0.20,
        1,
    )

    return {
        "Scientific_Strength": round(evidence, 1),
        "Chemistry_Strength": round(chemistry, 1),
        "Target_Relevance": round(target, 1),
        "Extraction_Feasibility": round(extraction, 1),
        "Regulatory_Readiness": round(regulatory, 1),
        "Safety_Profile": round(safety, 1),
        "Innovation_Opportunity": round(innovation, 1),
        "Market_Saturation_Risk": round(market_saturation, 1),
        "Patent_Crowding_Risk": round(patent_risk, 1),
        "Investment_Opportunity_Score": investment_score,
        "Overall_Risk_Score": risk_score,
    }


def classify_opportunity(scores):
    investment = scores["Investment_Opportunity_Score"]
    risk = scores["Overall_Risk_Score"]
    innovation = scores["Innovation_Opportunity"]
    regulatory = scores["Regulatory_Readiness"]

    if investment >= 80 and risk <= 40 and regulatory >= 65:
        return "GO"

    if investment >= 70 and innovation >= 65:
        return "GO FOR R&D"

    if investment >= 60:
        return "WAIT / VALIDATE"

    return "NO GO"


def generate_ai_opportunity_summary(row):
    plant = row.get("Scientific_Name", "")
    compound = row.get("compound_name", "")
    final_class = row.get("Final_Class", "")

    scores = calculate_opportunity_scores(row)
    decision = classify_opportunity(scores)

    if decision == "GO":
        summary = (
            f"{plant} with {compound} is suitable for near-term product development. "
            f"It has acceptable scientific, regulatory, safety, and formulation readiness."
        )

    elif decision == "GO FOR R&D":
        summary = (
            f"{plant} with {compound} is a strong R&D opportunity. "
            f"It appears scientifically and chemically promising, but it needs more validation "
            f"before commercialization."
        )

    elif decision == "WAIT / VALIDATE":
        summary = (
            f"{plant} with {compound} should remain in the research pipeline. "
            f"More evidence, safety, regulatory, or extraction data are needed before investment."
        )

    else:
        summary = (
            f"{plant} with {compound} is not a priority for investment at this stage. "
            f"The current evidence or opportunity profile is not strong enough."
        )

    return {
        "Plant": plant,
        "Compound": compound,
        "Current_Class": final_class,
        "AI_Opportunity_Decision": decision,
        "AI_Opportunity_Summary": summary,
        **scores,
    }


def build_opportunity_table(ranking_df):
    if ranking_df is None or ranking_df.empty:
        return ranking_df

    rows = []

    for _, row in ranking_df.iterrows():
        rows.append(generate_ai_opportunity_summary(row))

    return rows
