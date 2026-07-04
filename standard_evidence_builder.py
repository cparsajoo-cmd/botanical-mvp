def build_standard_evidence(record):
    selected_form = str(record.get("Dosage_Form", "")).strip().lower()
    selected_indication = str(record.get("Target_Indication", "")).strip().lower()

    detected_form = (
        str(record.get("Detected_Dosage_Forms", "")) or
        str(record.get("Detected_Dosage_Form", ""))
    ).strip()

    detected_indication = (
        str(record.get("Detected_Indications", "")) or
        str(record.get("Target_Indication_Detected", ""))
    ).strip()

    detected_form_lower = detected_form.lower()

    if selected_form and selected_form in detected_form_lower:
        direct = "Yes"
        reason = "Detected dosage form matches selected product dosage form."
    elif detected_form:
        direct = "No"
        reason = f"Detected dosage form differs: {detected_form}"
    else:
        direct = "Unknown"
        reason = "Dosage form not clearly detected."

    score = int(record.get("Evidence_Score", 0) or 0)

    standard = {
        "Plant": record.get("Scientific_Name", ""),
        "Study_Type": record.get("Evidence_Type", "Unknown"),
        "Study_Model": record.get("Study_Model", "Unknown"),
        "Dosage_Form_Detected": detected_form,
        "Target_Indication_Detected": detected_indication,
        "Population": record.get("LLM_Population", ""),
        "Sample_Size": record.get("LLM_Sample_Size", ""),
        "Comparator": record.get("LLM_Comparator", ""),
        "Primary_Outcome": record.get("LLM_Main_Outcome", ""),
        "Result_Direction": record.get("LLM_Result_Direction", ""),
        "Safety_Signal": record.get("LLM_Safety_Signal", ""),
        "Evidence_Level": record.get("Evidence_Level", "Unknown"),
        "Direct_For_Selected_Product": direct,
        "Directness_Reason": reason,
        "Evidence_Score": score,
    }

    record.update(standard)
    return record
