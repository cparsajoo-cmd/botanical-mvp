import pandas as pd


def _text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def apply_evidence_filters(df, dosage_form, evidence_strictness):
    result = df.copy()

    result["Evidence_Filter_Status"] = "Accepted"
    result["Evidence_Filter_Reason"] = ""

    if evidence_strictness == "Flexible":
        return result

    if evidence_strictness == "Dosage-form specific only":
        if dosage_form.lower() == "infusion":
            if "Infusion_Evidence" in result.columns:
                direct_mask = result["Infusion_Evidence"].apply(
                    lambda x: _text(x) in ["direct", "yes", "supported"]
                )

                result.loc[~direct_mask, "Evidence_Filter_Status"] = "Evidence gap"
                result.loc[
                    ~direct_mask,
                    "Evidence_Filter_Reason"
                ] = "Direct infusion-specific evidence not found."

        if "Dosage_Form" in result.columns:
            form_mask = result["Dosage_Form"].astype(str).str.lower() == dosage_form.lower()

            result.loc[~form_mask, "Evidence_Filter_Status"] = "Excluded"
            result.loc[
                ~form_mask,
                "Evidence_Filter_Reason"
            ] = "Evidence belongs to another dosage form."

    if evidence_strictness == "Regulatory-first":
        regulatory_cols = [
            c for c in ["EMA_Status", "WHO_Status", "ESCOP_Status"]
            if c in result.columns
        ]

        if regulatory_cols:
            regulatory_mask = False

            for col in regulatory_cols:
                regulatory_mask = regulatory_mask | result[col].apply(
                    lambda x: _text(x) in [
                        "yes",
                        "positive",
                        "supported",
                        "traditional use",
                        "well-established use"
                    ]
                )

            result.loc[~regulatory_mask, "Evidence_Filter_Status"] = "Evidence gap"
            result.loc[
                ~regulatory_mask,
                "Evidence_Filter_Reason"
            ] = "No strong regulatory support found."

    if evidence_strictness == "Clinical-first":
        if "Clinical_Level" in result.columns:
            clinical_mask = result["Clinical_Level"].apply(
                lambda x: _text(x) in ["strong", "moderate"]
            )

            result.loc[~clinical_mask, "Evidence_Filter_Status"] = "Evidence gap"
            result.loc[
                ~clinical_mask,
                "Evidence_Filter_Reason"
            ] = "Clinical evidence is weak or missing."

    return result
