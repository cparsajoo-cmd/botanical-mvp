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

    # PHASE 3 — outcome/safety-wording decoupling.
    #
    # Prior to Phase 3 this function added/subtracted points here based on
    # whether the evidence text sounded positive ("improved", "effective")
    # or negative ("no significant", "not effective") — see
    # PHASE3_SOURCE_AUTHORITY_AUDIT.md §2.1 for the direct-from-code
    # confirmation. That coupling is exactly what the Phase 3 brief
    # prohibits: a negative RCT must remain a high-quality RCT; whether a
    # study's OUTCOME was favorable is Evidence Direction's concern
    # (evidence_interpretation.classify_evidence_direction /
    # evidence_authority.direction_sign), never Evidence Quality's. This
    # module never reached production scoring (its only caller,
    # decision_engine.py, has no importer anywhere in the repository —
    # see the audit), but the bug is fixed here anyway per the brief's
    # explicit instruction, so no future caller inherits it.
    #
    # Outcome direction and safety-tolerability wording are therefore no
    # longer read into `quality_score` at all. `Evidence_Quality_Score`/
    # `_Class` below now reflect ONLY study-design/methodology signals
    # (hierarchy, blinding, control, sample size) — never outcome
    # polarity. A caller that also wants a direction-aware SIGNED
    # contribution should combine this quality score with
    # evidence_interpretation.classify_evidence_direction() /
    # evidence_authority.signed_evidence_contribution() itself, exactly
    # as candidate_shortlisting.py and botanical_rd_candidate_engine.py
    # already do for their own (separate, live) quality paths.
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
