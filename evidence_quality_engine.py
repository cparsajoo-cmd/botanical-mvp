def _txt(x):
    return "" if x is None else str(x).strip()


def _lower(x):
    return _txt(x).lower()


def _num(x):
    try:
        return float(x or 0)
    except Exception:
        return 0


def _combined_text(row):
    parts = [
        row.get("Source_Title", ""),
        row.get("Notes", ""),
        row.get("Study_Type", ""),
        row.get("Evidence_Type", ""),
        row.get("Evidence_Level", ""),
        row.get("Study_Model", ""),
        row.get("Population", ""),
        row.get("Sample_Size", ""),
        row.get("Primary_Outcome", ""),
        row.get("Safety_Signal", ""),
    ]
    return " ".join([_txt(p) for p in parts]).lower()


def assess_evidence_quality(row):
    text = _combined_text(row)

    quality_score = 0
    quality_flags = []

    # Study hierarchy
    if "meta-analysis" in text or "meta analysis" in text:
        quality_score += 25
        quality_flags.append("Meta-analysis")

    elif "systematic review" in text:
        quality_score += 20
        quality_flags.append("Systematic review")

    elif "randomized" in text or "randomised" in text or "rct" in text:
        quality_score += 18
        quality_flags.append("Randomized study")

    elif "clinical trial" in text or "patients" in text or "subjects" in text:
        quality_score += 12
        quality_flags.append("Clinical study")

    elif "animal" in text or "rat" in text or "mouse" in text or "mice" in text:
        quality_score += 5
        quality_flags.append("Animal study")

    elif "in vitro" in text or "cell line" in text:
        quality_score += 3
        quality_flags.append("In vitro study")

    # Design quality
    if "double blind" in text or "double-blind" in text:
        quality_score += 10
        quality_flags.append("Double blind")

    if "placebo" in text:
        quality_score += 8
        quality_flags.append("Placebo-controlled")

    if "controlled" in text:
        quality_score += 6
        quality_flags.append("Controlled")

    # Sample size
    sample_size = _num(row.get("Sample_Size"))

    if sample_size >= 200:
        quality_score += 10
        quality_flags.append("Large sample size")

    elif sample_size >= 100:
        quality_score += 7
        quality_flags.append("Moderate sample size")

    elif sample_size >= 30:
        quality_score += 4
        quality_flags.append("Small clinical sample")

    # Outcome direction
    outcome_text = (
        _lower(row.get("Result_Direction")) + " " +
        _lower(row.get("Primary_Outcome")) + " " +
        text
    )

    if any(x in outcome_text for x in ["significant improvement", "improved", "effective", "efficacy", "positive"]):
        quality_score += 10
        quality_flags.append("Positive outcome signal")

    elif any(x in outcome_text for x in ["no significant", "not effective", "negative"]):
        quality_score -= 10
        quality_flags.append("Negative or non-significant outcome")

    # Safety
    if any(x in text for x in ["well tolerated", "safe", "no serious adverse"]):
        quality_score += 6
        quality_flags.append("Good safety signal")

    elif any(x in text for x in ["adverse event", "contraindicated", "warning", "caution"]):
        quality_score -= 5
        quality_flags.append("Safety caution")

    quality_score = max(0, min(int(quality_score), 100))

    if quality_score >= 75:
        quality_class = "High quality"
    elif quality_score >= 50:
        quality_class = "Moderate quality"
    elif quality_score >= 25:
        quality_class = "Low quality"
    else:
        quality_class = "Very low quality"

    return {
        "Evidence_Quality_Score": quality_score,
        "Evidence_Quality_Class": quality_class,
        "Evidence_Quality_Flags": " | ".join(quality_flags),
    }


def apply_evidence_quality(df):
    if df is None or df.empty:
        return df

    result = df.copy()

    quality_rows = result.apply(assess_evidence_quality, axis=1)

    result["Evidence_Quality_Score"] = quality_rows.apply(lambda x: x["Evidence_Quality_Score"])
    result["Evidence_Quality_Class"] = quality_rows.apply(lambda x: x["Evidence_Quality_Class"])
    result["Evidence_Quality_Flags"] = quality_rows.apply(lambda x: x["Evidence_Quality_Flags"])

    return result
