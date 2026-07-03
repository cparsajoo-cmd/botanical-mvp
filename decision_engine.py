def analyze_evidence(df, product_type, dosage_form, indication, market, min_score=0):
    result = df[
        (df["Product_Type"] == product_type)
        & (df["Dosage_Form"] == dosage_form)
        & (df["Target_Indication"] == indication)
        & (df["Target_Market"] == market)
        & (df["Evidence_Score"] >= min_score)
    ].copy()

    if result.empty:
        return result

    return result.sort_values(by="Evidence_Score", ascending=False)
