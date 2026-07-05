import pandas as pd

from plant_compound_database import load_plant_compound_database
from compound_profile_database import load_compound_profiles


def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def _txt(x):
    if x is None:
        return ""
    return str(x).strip()


def _score_target_relevance(target_text, indication):
    target_text = _txt(target_text).lower()
    indication = _txt(indication).lower()

    score = 20

    if any(x in indication for x in ["sleep", "relaxation", "anxiety", "stress"]):
        keywords = [
            "gaba",
            "gaba-a",
            "benzodiazepine",
            "serotonergic",
            "hpa axis",
            "melatonin",
            "adenosine",
            "orexin",
        ]
        score += sum(15 for k in keywords if k in target_text)

    elif any(x in indication for x in ["inflammation", "skin inflammation", "wound"]):
        keywords = [
            "nf-kb",
            "cox-2",
            "tnf",
            "tnf-alpha",
            "il-6",
            "nrf2",
            "inflammatory",
        ]
        score += sum(15 for k in keywords if k in target_text)

    elif any(x in indication for x in ["digestive", "ibs", "constipation"]):
        keywords = [
            "trp",
            "calcium",
            "serotonergic",
            "motility",
            "anti-inflammatory",
        ]
        score += sum(15 for k in keywords if k in target_text)

    else:
        if target_text:
            score += 30

    return min(score, 100)


def _score_extraction_method(extraction_text, dosage_form):
    extraction_text = _txt(extraction_text).lower()
    dosage_form = _txt(dosage_form).lower()

    if not extraction_text:
        return 25

    score = 45

    if "infusion" in dosage_form:
        if "infusion" in extraction_text:
            score += 35
        if "aqueous" in extraction_text or "water" in extraction_text:
            score += 30
        if "hydroalcoholic" in extraction_text or "hydroethanolic" in extraction_text:
            score += 15

    elif "extract" in dosage_form or "capsule" in dosage_form or "tablet" in dosage_form:
        if "extract" in extraction_text:
            score += 30
        if "hydroalcoholic" in extraction_text or "hydroethanolic" in extraction_text:
            score += 30
        if "ethanolic" in extraction_text or "methanolic" in extraction_text:
            score += 20
        if "dry extract" in extraction_text:
            score += 25

    elif "essential oil" in dosage_form:
        if "essential oil" in extraction_text:
            score += 35
        if "steam distillation" in extraction_text or "distillation" in extraction_text:
            score += 35

    else:
        if any(x in extraction_text for x in ["aqueous", "ethanolic", "hydroalcoholic", "extract", "infusion", "essential oil"]):
            score += 30

    return min(score, 100)


def _profile_score(row):
    score = 0

    activity = _num(row.get("activity_score", 0))
    score += min(activity, 100) * 0.45

    bioavailability = _txt(row.get("bioavailability", "")).lower()
    if bioavailability == "high":
        score += 20
    elif bioavailability == "medium":
        score += 13
    elif bioavailability == "low":
        score += 6

    toxicity = _txt(row.get("toxicity", "")).lower()
    if toxicity == "low":
        score += 15
    elif toxicity == "medium":
        score += 7
    elif toxicity == "high":
        score -= 10

    commercial = _txt(row.get("commercial_interest", "")).lower()
    if commercial == "very high":
        score += 20
    elif commercial == "high":
        score += 15
    elif commercial == "medium":
        score += 8

    return min(round(score, 1), 100)


def build_compound_scores(indication="", dosage_form=""):
    compounds_raw = load_plant_compound_database()
    compounds_df = pd.DataFrame(compounds_raw)

    if compounds_df.empty:
        return pd.DataFrame()

    profiles_df = load_compound_profiles()

    if not profiles_df.empty:
        compounds_df["compound_name_key"] = compounds_df["compound_name"].fillna("").astype(str).str.lower().str.strip()
        profiles_df["compound_name_key"] = profiles_df["compound_name"].fillna("").astype(str).str.lower().str.strip()

        compounds_df = compounds_df.merge(
            profiles_df,
            on="compound_name_key",
            how="left",
            suffixes=("", "_profile"),
        )

    required = [
        "scientific_name",
        "compound_name",
        "compound_class",
        "target",
        "mechanism",
        "extraction_method",
        "confidence_score",
        "source",
        "reference_url",
    ]

    for col in required:
        if col not in compounds_df.columns:
            compounds_df[col] = ""

    rows = []

    for plant, group in compounds_df.groupby("scientific_name", dropna=False):
        plant = _txt(plant)
        if not plant:
            continue

        unique_compounds = (
            group["compound_name"]
            .dropna()
            .astype(str)
            .str.strip()
        )
        unique_compounds = sorted(set([x for x in unique_compounds if x and x.lower() != "nan"]))

        compound_count = len(unique_compounds)

        high_conf_count = 0
        if "confidence_score" in group.columns:
            high_conf_count = int((group["confidence_score"].apply(_num) >= 70).sum())

        active_score = min(100, 20 + compound_count * 10 + high_conf_count * 5)

        target_text = " ; ".join(
            group["target"].fillna("").astype(str).tolist()
        )

        if "major_target" in group.columns:
            target_text += " ; " + " ; ".join(
                group["major_target"].fillna("").astype(str).tolist()
            )

        target_score = _score_target_relevance(target_text, indication)

        extraction_text = " ; ".join(
            group["extraction_method"].fillna("").astype(str).tolist()
        )

        extraction_score = _score_extraction_method(extraction_text, dosage_form)

        profile_scores = []
        for _, r in group.iterrows():
            profile_scores.append(_profile_score(r))

        compound_evidence_score = round(sum(profile_scores) / len(profile_scores), 1) if profile_scores else 40

        chemistry_score = round(
            active_score * 0.40
            + target_score * 0.30
            + extraction_score * 0.20
            + compound_evidence_score * 0.10,
            1,
        )

        best_compounds = ", ".join(unique_compounds[:10])

        targets = []
        for txt in target_text.replace(";", ",").split(","):
            t = txt.strip()
            if t and t.lower() != "nan":
                targets.append(t)
        best_targets = ", ".join(sorted(set(targets))[:10])

        extractions = []
        for txt in extraction_text.replace(";", ",").split(","):
            e = txt.strip()
            if e and e.lower() != "nan":
                extractions.append(e)
        best_extractions = ", ".join(sorted(set(extractions))[:10])

        high_value_count = int(sum(1 for s in profile_scores if s >= 75))

        rows.append(
            {
                "Scientific_Name": plant,
                "Compound_Count": compound_count,
                "High_Value_Compound_Count": high_value_count,
                "Best_Compounds": best_compounds,
                "Best_Targets": best_targets,
                "Best_Extraction_Methods": best_extractions,
                "Active_Compound_Score": round(active_score, 1),
                "Target_Score": round(target_score, 1),
                "Extraction_Score": round(extraction_score, 1),
                "Compound_Evidence_Score": round(compound_evidence_score, 1),
                "Chemistry_Score": round(chemistry_score, 1),
            }
        )

    return pd.DataFrame(rows)
