import pandas as pd

from global_plant_candidate_database import GLOBAL_PLANT_CANDIDATES


def _matches_indication(candidate, indication):
    indication = str(indication).lower()
    indications = [str(x).lower() for x in candidate.get("Indications", [])]

    if indication in indications:
        return True

    for item in indications:
        if indication in item or item in indication:
            return True

    if "sleep" in indication:
        return any(x in indications for x in ["sleep and relaxation", "anxiety", "stress"])

    if "anxiety" in indication:
        return any(x in indications for x in ["anxiety", "sleep and relaxation", "stress"])

    if "digestive" in indication:
        return any(x in indications for x in ["digestive comfort", "ibs", "constipation"])

    return False


def _regulatory_score(candidate, market):
    ema = candidate.get("EMA_Status", "No")

    if market in ["European Union", "France"]:
        return 100 if ema == "Yes" else 25

    return 70 if ema == "Yes" else 45


def _chemistry_score(candidate):
    compounds = candidate.get("Known_Active_Compounds", [])
    targets = candidate.get("Known_Targets", [])
    extraction = candidate.get("Extraction_Method", "")

    score = 0
    score += min(40, len(compounds) * 10)
    score += min(35, len(targets) * 12)

    if extraction:
        score += 25

    return min(score, 100)


def _active_compound_score(candidate):
    compounds = candidate.get("Known_Active_Compounds", [])

    if not compounds:
        return 0

    score = 30 + len(compounds) * 12
    return min(score, 100)


def _target_score(candidate):
    targets = candidate.get("Known_Targets", [])

    if not targets:
        return 0

    score = 30 + len(targets) * 15
    return min(score, 100)


def _extraction_score(candidate, dosage_form):
    extraction = str(candidate.get("Extraction_Method", "")).lower()
    dosage_form = str(dosage_form).lower()

    if not extraction:
        return 20

    score = 60

    if dosage_form in extraction:
        score += 25

    if "infusion" in dosage_form and ("infusion" in extraction or "aqueous" in extraction):
        score += 25

    if "extract" in dosage_form and ("extract" in extraction or "hydroalcoholic" in extraction):
        score += 20

    if "essential oil" in dosage_form and ("essential oil" in extraction or "distillation" in extraction):
        score += 20

    return min(score, 100)


def _clinical_score(candidate):
    priority = candidate.get("Research_Priority", "Medium")

    if priority == "High":
        return 80
    if priority == "Medium":
        return 60
    return 35


def _safety_score(candidate):
    name = str(candidate.get("Scientific_Name", "")).lower()

    caution_plants = [
        "piper methysticum",
    ]

    if name in caution_plants:
        return 35

    return 70


def _novelty_score(candidate):
    ema = candidate.get("EMA_Status", "No")
    region = str(candidate.get("Region", "")).lower()

    score = 30

    if ema == "No":
        score += 35

    if any(x in region for x in ["china", "india", "asia", "pacific", "africa"]):
        score += 25

    return min(score, 100)


def _market_score(candidate):
    ema = candidate.get("EMA_Status", "No")
    priority = candidate.get("Research_Priority", "Medium")

    score = 45

    if ema == "Yes":
        score += 20

    if priority == "High":
        score += 20

    return min(score, 100)


def _commercial_score(candidate):
    extraction = str(candidate.get("Extraction_Method", "")).lower()
    ema = candidate.get("EMA_Status", "No")

    score = 45

    if extraction:
        score += 20

    if ema == "Yes":
        score += 20

    if "infusion" in extraction or "aqueous" in extraction:
        score += 10

    return min(score, 100)


def _final_weighted_score(row):
    return round(
        row["Clinical_Score"] * 0.25
        + row["Chemistry_Score"] * 0.20
        + row["Active_Compound_Score"] * 0.15
        + row["Target_Score"] * 0.10
        + row["Extraction_Score"] * 0.10
        + row["Regulatory_Score"] * 0.10
        + row["Safety_Score"] * 0.05
        + row["Novelty_Score"] * 0.05
        + row["Market_Score"] * 0.05
        + row["Commercial_Score"] * 0.05,
        1,
    )


def _candidate_status(score):
    if score >= 85:
        return "Product-ready candidate"
    if score >= 70:
        return "Strategic development candidate"
    if score >= 55:
        return "R&D candidate"
    if score >= 40:
        return "Early research candidate"
    return "Low priority"


def rank_global_candidates(
    indication,
    dosage_form,
    market,
    target_count=100,
):
    rows = []

    for candidate in GLOBAL_PLANT_CANDIDATES:
        if not _matches_indication(candidate, indication):
            continue

        regulatory = _regulatory_score(candidate, market)
        chemistry = _chemistry_score(candidate)
        active = _active_compound_score(candidate)
        target = _target_score(candidate)
        extraction = _extraction_score(candidate, dosage_form)
        clinical = _clinical_score(candidate)
        safety = _safety_score(candidate)
        novelty = _novelty_score(candidate)
        market_score = _market_score(candidate)
        commercial = _commercial_score(candidate)

        row = {
            "Scientific_Name": candidate.get("Scientific_Name", ""),
            "Common_Name": candidate.get("Common_Name", ""),
            "Region": candidate.get("Region", ""),
            "Known_Active_Compounds": ", ".join(candidate.get("Known_Active_Compounds", [])),
            "Known_Targets": ", ".join(candidate.get("Known_Targets", [])),
            "Plant_Part": candidate.get("Plant_Part", ""),
            "Extraction_Method": candidate.get("Extraction_Method", ""),
            "EMA_Status": candidate.get("EMA_Status", ""),
            "Clinical_Score": clinical,
            "Chemistry_Score": chemistry,
            "Active_Compound_Score": active,
            "Target_Score": target,
            "Extraction_Score": extraction,
            "Regulatory_Score": regulatory,
            "Safety_Score": safety,
            "Novelty_Score": novelty,
            "Market_Score": market_score,
            "Commercial_Score": commercial,
        }

        row["Global_Ranking_Score"] = _final_weighted_score(row)
        row["Candidate_Status"] = _candidate_status(row["Global_Ranking_Score"])

        rows.append(row)

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return (
        df.sort_values(
            by=[
                "Global_Ranking_Score",
                "Chemistry_Score",
                "Active_Compound_Score",
                "Regulatory_Score",
            ],
            ascending=[False, False, False, False],
        )
        .head(target_count)
        .reset_index(drop=True)
    )
