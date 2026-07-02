def analyze_evidence(df, product_type, dosage_form, indication, market):
    result = df[
        (df["Product_Type"] == product_type)
        & (df["Dosage_Form"] == dosage_form)
        & (df["Target_Indication"] == indication)
        & (df["Target_Market"] == market)
    ].copy()

    if result.empty:
        return result

    result = result.sort_values(
        by=["Evidence_Score"],
        ascending=False
    )

    return result
