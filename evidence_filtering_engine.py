import pandas as pd


def apply_evidence_filters(
    df,
    dosage_form,
    evidence_strictness="Dosage-form specific only",
):
    if df is None or df.empty:
        return pd.DataFrame()

    result = df.copy()

    if "Evidence_Filter_Status" not in result.columns:
        result["Evidence_Filter_Status"] = "Accepted"

    if "Evidence_Filter_Reason" not in result.columns:
        result["Evidence_Filter_Reason"] = ""

    if "Dosage_Form" not in result.columns:
        result["Dosage_Form"] = ""

    if "Infusion_Evidence" not in result.columns:
        result["Infusion_Evidence"] = ""

    # Flexible: accept all retrieved records
    if evidence_strictness == "Flexible":
        result["Evidence_Filter_Status"] = "Accepted"
        result["Evidence_Filter_Reason"] = "Flexible evidence mode."
        return result.reset_index(drop=True)

    # Clinical-first: accept all retrieved clinical records
    if evidence_strictness == "Clinical-first":
        result["Evidence_Filter_Status"] = "Accepted"
        result["Evidence_Filter_Reason"] = "Clinical-first mode."
        return result.reset_index(drop=True)

    # Regulatory-first: accept retrieved records, because filtering happened upstream
    if evidence_strictness == "Regulatory-first":
        result["Evidence_Filter_Status"] = "Accepted"
        result["Evidence_Filter_Reason"] = "Regulatory-first mode."
        return result.reset_index(drop=True)

    # Dosage-form specific only:
    # Accept direct form matches OR records collected online for that project.
    dosage_match = (
        result["Dosage_Form"]
        .astype(str)
        .str.lower()
        .str.strip()
        == str(dosage_form).lower().strip()
    )

    direct_evidence = (
        result["Infusion_Evidence"]
        .astype(str)
        .str.lower()
        .str.strip()
        .isin(["direct", "dosage-form specific", "yes"])
    )

    empty_dosage = result["Dosage_Form"].astype(str).str.strip() == ""

    accepted = dosage_match | direct_evidence | empty_dosage

    result["Evidence_Filter_Status"] = accepted.map(
        {True: "Accepted", False: "Rejected"}
    )

    result["Evidence_Filter_Reason"] = accepted.map(
        {
            True: "Accepted as dosage-form relevant or online project evidence.",
            False: "Rejected because dosage form does not match selected product.",
        }
    )

    return result[result["Evidence_Filter_Status"] == "Accepted"].reset_index(drop=True)
