from evidence_classifier import classify_evidence


def build_standard_evidence(record):
    classified = classify_evidence(record)

    selected_form = str(record.get("Dosage_Form", "")).lower()
    detected_form = str(classified.get("Detected_Dosage_Forms", "")).lower()

    direct = "No"
    reason = "Dosage form not clearly matched."

    if selected_form and selected_form in detected_form:
        direct = "Yes"
        reason = "Detected dosage form matches selected product dosage form."
    elif detected_form:
        direct = "No"
        reason = f"Detected dosage form differs: {detected_form}"

    standard = {
        "Plant": classified.get("Scientific_Name", ""),
        "Study_Type": classified.get("Evidence_Type", "Unknown"),
        "Study_Model": classified.get("Study_Model", "Unknown"),
        "Dosage_Form_Detected": classified.get("Detected_Dosage_Forms", ""),
        "Target_Indication_Detected": classified.get("Detected_Indications", ""),
        "Population": classified.get("LLM_Population", ""),
        "Sample_Size": classified.get("LLM_Sample_Size", ""),
        "Comparator": classified.get("LLM_Comparator", ""),
        "Primary_Outcome": classified.get("LLM_Main_Outcome", ""),
        "Result_Direction": classified.get("LLM_Result_Direction", ""),
        "Safety_Signal": classified.get("LLM_Safety_Signal", ""),
        "Evidence_Level": classified.get("Evidence_Level", "Unknown"),
        "Direct_For_Selected_Product": direct,
        "Directness_Reason": reason,
        "Evidence_Score": classified.get("Evidence_Score", 0),
    }

    classified.update(standard)

    return classified
