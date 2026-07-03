def parse_user_question(question):
    question_lower = question.lower()

    parsed = {
        "product_type": None,
        "dosage_form": None,
        "indication": None,
        "market": None,
    }

    # Product type
    if "herbal" in question_lower or "botanical" in question_lower:
        parsed["product_type"] = "Herbal product"

    # Dosage form
    if "tea" in question_lower or "infusion" in question_lower or "herbal tea" in question_lower:
        parsed["dosage_form"] = "Infusion"
    elif "capsule" in question_lower:
        parsed["dosage_form"] = "Capsule"
    elif "tablet" in question_lower:
        parsed["dosage_form"] = "Tablet"
    elif "cream" in question_lower:
        parsed["dosage_form"] = "Cream"
    elif "syrup" in question_lower:
        parsed["dosage_form"] = "Syrup"

    # Indication
    if "sleep" in question_lower or "bedtime" in question_lower or "relaxation" in question_lower:
        parsed["indication"] = "Sleep and relaxation"
    elif "constipation" in question_lower:
        parsed["indication"] = "Constipation"
    elif "cough" in question_lower:
        parsed["indication"] = "Cough"
    elif "digestive" in question_lower or "digestion" in question_lower:
        parsed["indication"] = "Digestive comfort"

    # Market
    if "eu" in question_lower or "europe" in question_lower or "european union" in question_lower:
        parsed["market"] = "European Union"
    elif "usa" in question_lower or "united states" in question_lower:
        parsed["market"] = "United States"
    elif "canada" in question_lower:
        parsed["market"] = "Canada"
    elif "iran" in question_lower:
        parsed["market"] = "Iran"

    return parsed
