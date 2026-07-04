import pandas as pd

from compound_database import PLANT_COMPOUND_DATABASE
from compound_target_engine import get_compound_target_info


def _score_extraction(feasibility):
    feasibility = str(feasibility).lower()

    if feasibility == "high":
        return 90
    if feasibility == "medium":
        return 65
    if feasibility == "low":
        return 35
    return 50


def _score_novelty(novelty):
    novelty = str(novelty).lower()

    if novelty == "high":
        return 90
    if novelty == "medium":
        return 65
    if novelty == "low":
        return 35
    return 50


def _score_target_match(targets, indication):
    indication = str(indication).lower()
    targets_text = " ".join(targets).lower()

    score = 40

    if "sleep" in indication or "relaxation" in indication or "anxiety" in indication:
        if "gaba" in targets_text:
            score += 35
        if "benzodiazepine" in targets_text:
            score += 25
        if "serotonergic" in targets_text:
            score += 15

    if "inflammation" in indication or "skin inflammation" in indication:
        if "nf-kb" in targets_text or "cox-2" in targets_text:
            score += 35
        if "tnf" in targets_text or "il-6" in targets_text:
            score += 20

    if "digestive" in indication or "ibs" in indication:
        if "trp" in targets_text or "calcium" in targets_text:
            score += 25

    return min(score, 100)


def _score_compound_class(compound_class):
    compound_class = str(compound_class).lower()

    if any(x in compound_class for x in ["flavonoid", "phenolic", "saponin", "terpene", "lactone"]):
        return 80

    if any(x in compound_class for x in ["alkaloid", "glycoside"]):
        return 70

    return 55


def _final_compound_score(row):
    return round(
        row["Target_Match_Score"] * 0.30
        + row["Extraction_Score"] * 0.20
        + row["Novelty_Score"] * 0.20
        + row["Compound_Class_Score"] * 0.15
        + row["Standardization_Score"] * 0.15,
        1,
    )


def _rd_potential(score):
    if score >= 85:
        return "High R&D potential"
    if score >= 70:
        return "Promising R&D candidate"
    if score >= 55:
        return "Exploratory candidate"
    return "Low priority"


def build_plant_compound_ranking(indication, selected_plants=None):
    rows = []

    selected_set = None
    if selected_plants:
        selected_set = set([str(x) for x in selected_plants])

    for item in PLANT_COMPOUND_DATABASE:
        plant = item.get("Scientific_Name", "")

        if selected_set and plant not in selected_set:
            continue

        compound = item.get("Compound", "")
        target_info = get_compound_target_info(compound)
        targets = target_info.get("Targets", [])
        mechanism = target_info.get("Mechanism", "")

        row = {
            "Scientific_Name": plant,
            "Compound": compound,
            "Compound_Class": item.get("Compound_Class", ""),
            "Plant_Part": item.get("Plant_Part", ""),
            "Extraction_Method": item.get("Extraction_Method", ""),
            "Extraction_Feasibility": item.get("Extraction_Feasibility", ""),
            "Standardization_Marker": item.get("Standardization_Marker", ""),
            "Novelty_Level": item.get("Novelty_Level", ""),
            "Targets": ", ".join(targets),
            "Mechanism": mechanism,
        }

        row["Target_Match_Score"] = _score_target_match(targets, indication)
        row["Extraction_Score"] = _score_extraction(row["Extraction_Feasibility"])
        row["Novelty_Score"] = _score_novelty(row["Novelty_Level"])
        row["Compound_Class_Score"] = _score_compound_class(row["Compound_Class"])
        row["Standardization_Score"] = 85 if row["Standardization_Marker"] else 40

        row["Compound_Final_Score"] = _final_compound_score(row)
        row["R&D_Potential"] = _rd_potential(row["Compound_Final_Score"])

        rows.append(row)

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return (
        df.sort_values(
            by=["Compound_Final_Score", "Target_Match_Score", "Novelty_Score"],
            ascending=[False, False, False],
        )
        .reset_index(drop=True)
      )
