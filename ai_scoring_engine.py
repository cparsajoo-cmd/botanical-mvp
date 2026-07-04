import pandas as pd


def score_record(row):

    score = 0
    reasons = []

    publication_type = str(row.get("publication_type", "")).lower()
    title = str(row.get("title", "")).lower()
    abstract = str(row.get("abstract", "")).lower()

    text = publication_type + " " + title + " " + abstract

    # -------------------------
    # Human evidence
    # -------------------------

    if "randomized" in text:
        score += 30
        reasons.append("Randomized trial")

    elif "clinical trial" in text:
        score += 25
        reasons.append("Clinical trial")

    elif "human" in text:
        score += 20
        reasons.append("Human study")

    # -------------------------
    # Meta-analysis
    # -------------------------

    if "meta-analysis" in text:
        score += 35
        reasons.append("Meta-analysis")

    if "systematic review" in text:
        score += 25
        reasons.append("Systematic review")

    # -------------------------
    # Animal
    # -------------------------

    if "mouse" in text or "mice" in text:
        score += 8
        reasons.append("Mouse study")

    if "rat" in text:
        score += 8
        reasons.append("Rat study")

    # -------------------------
    # In vitro
    # -------------------------

    if "in vitro" in text:
        score += 5
        reasons.append("In vitro")

    # -------------------------
    # Safety
    # -------------------------

    if "safety" in text:
        score += 8
        reasons.append("Safety")

    if "adverse event" in text:
        score += 6
        reasons.append("Adverse events")

    # -------------------------
    # Dosage form
    # -------------------------

    dosage = str(row.get("dosage_form", "")).lower()

    if dosage != "":

        if dosage in text:
            score += 15
            reasons.append("Dosage-form match")

    # -------------------------
    # Indication
    # -------------------------

    indication = str(row.get("indication", "")).lower()

    if indication != "":

        if indication in text:
            score += 15
            reasons.append("Indication match")

    if score > 100:
        score = 100

    return score, reasons


def score_dataframe(df):

    scores = []
    reasons = []

    for _, row in df.iterrows():

        s, r = score_record(row)

        scores.append(s)
        reasons.append(", ".join(r))

    df = df.copy()

    df["ai_score"] = scores
    df["ai_reason"] = reasons

    return df
