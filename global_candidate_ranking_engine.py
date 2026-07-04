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

    return False


def _regulatory_score(candidate, market):
    ema = candidate.get("EMA_Status", "No")

    if market in ["European Union", "France"]:
        return 20 if ema == "Yes" else 4

    return 10 if ema == "Yes" else 6


def _chemistry_score(candidate):
    compounds = candidate.get("Known_Active_Compounds", [])
    targets = candidate.get("Known_Targets", [])
    extraction = candidate.get("Extraction_Method", "")

    score = 0

    score += min(20, len(compounds) * 4)
    score += min(15, len(targets) * 5)

    if extraction:
        score += 10

    return min(score, 45)


def _research_priority_score(candidate):
    priority = candidate.get("Research_Priority", "Medium")

    if priority == "High":
        return 15
    if priority == "Medium":
        return 9
    return 4


def _novelty_score(candidate):
    ema = candidate.get("EMA_Status", "No")
    region = str(candidate.get("Region", "")).lower()

    score = 0

    if ema == "No":
        score += 8

    if any(x in region for x in ["china", "india", "asia", "pacific", "africa"]):
        score += 7

    return min(score, 15)


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
        research = _research_priority_score(candidate)
        novelty = _novelty_score(candidate)

        extraction_bonus = 5 if dosage_form.lower() in str(candidate.get("Extraction_Method", "")).lower() else 0

        final_score = regulatory + chemistry + research + novelty + extraction_bonus
        final_score = min(final_score, 100)

        if final_score >= 80:
            status = "Product-ready candidate"
        elif final_score >= 65:
            status = "Strategic development candidate"
        elif final_score >= 50:
            status = "R&D candidate"
        elif final_score >= 35:
            status = "Early research candidate"
        else:
            status = "Low priority"

        rows.append({
            "Scientific_Name": candidate.get("Scientific_Name", ""),
            "Common_Name": candidate.get("Common_Name", ""),
            "Region": candidate.get("Region", ""),
            "Known_Active_Compounds": ", ".join(candidate.get("Known_Active_Compounds", [])),
            "Known_Targets": ", ".join(candidate.get("Known_Targets", [])),
            "Plant_Part": candidate.get("Plant_Part", ""),
            "Extraction_Method": candidate.get("Extraction_Method", ""),
            "EMA_Status": candidate.get("EMA_Status", ""),
            "Regulatory_Score": regulatory,
            "Chemistry_Score": chemistry,
            "Research_Priority_Score": research,
            "Novelty_Score": novelty,
            "Extraction_Bonus": extraction_bonus,
            "Global_Ranking_Score": final_score,
            "Candidate_Status": status,
        })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return (
        df.sort_values(
            by=["Global_Ranking_Score", "Chemistry_Score", "Regulatory_Score"],
            ascending=[False, False, False],
        )
        .head(target_count)
        .reset_index(drop=True)
      )
