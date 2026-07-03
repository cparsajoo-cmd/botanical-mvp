import pandas as pd


def _text(value):
    if pd.isna(value):
        return ""
    return str(value).strip().lower()


def retrieve_knowledge(
    df,
    product_type,
    dosage_form,
    indication,
    market,
    evidence_strictness="Dosage-form specific only"
):
    result = df.copy()

    if "Product_Type" in result.columns:
        result = result[
            result["Product_Type"].astype(str).str.lower()
            == str(product_type).lower()
        ]

    if "Target_Indication" in result.columns:
        result = result[
            result["Target_Indication"].astype(str).str.lower()
            == str(indication).lower()
        ]

    if "Target_Market" in result.columns:
        result = result[
            result["Target_Market"].astype(str).str.lower()
            == str(market).lower()
        ]

    if evidence_strictness == "Dosage-form specific only":
        if "Dosage_Form" in result.columns:
            result = result[
                result["Dosage_Form"].astype(str).str.lower()
                == str(dosage_form).lower()
            ]

        if "Infusion_Evidence" in result.columns and str(dosage_form).lower() == "infusion":
            result = result[
                result["Infusion_Evidence"].astype(str).str.lower().isin(
                    ["direct", "yes", "supported"]
                )
            ]

    elif evidence_strictness == "Regulatory-first":
        if "Dosage_Form" in result.columns:
            result = result[
                result["Dosage_Form"].astype(str).str.lower()
                == str(dosage_form).lower()
            ]

        regulatory_cols = [
            col for col in ["EMA_Status", "WHO_Status", "ESCOP_Status"]
            if col in result.columns
        ]

        if regulatory_cols:
            mask = False
            for col in regulatory_cols:
                mask = mask | result[col].astype(str).str.lower().isin(
                    ["yes", "positive", "supported", "traditional use", "well-established use"]
                )
            result = result[mask]

    elif evidence_strictness == "Clinical-first":
        if "Clinical_Level" in result.columns:
            result = result[
                result["Clinical_Level"].astype(str).str.lower().isin(
                    ["strong", "moderate"]
                )
            ]

    elif evidence_strictness == "Flexible":
        pass

    return result
