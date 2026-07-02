def analyze_evidence(df, product_type, dosage_form, indication, market):
    result = df[
        (df["product_type"] == product_type)
        & (df["dosage_form"] == dosage_form)
        & (df["indication"] == indication)
        & (df["market"] == market)
    ].copy()

    if result.empty:
        return result

    priority_order = {
        "Priority candidate": 1,
        "Conditional candidate": 2,
        "Combination candidate": 3,
        "Supportive ingredient": 4,
        "Evidence gap": 5,
        "Not recommended": 6,
    }

    result["rank"] = result["decision_class"].map(priority_order).fillna(99)
    result = result.sort_values(["rank", "commercial_value"])

    return result.drop(columns=["rank"])
