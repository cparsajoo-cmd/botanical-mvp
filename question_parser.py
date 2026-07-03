def parse_user_question(question):
    q = question.lower()

    parsed = {
        "product_type": "Herbal product",
        "dosage_form": None,
        "indication": None,
        "market": None,
    }

    if any(x in q for x in ["tea", "infusion", "herbal tea", "tisane"]):
        parsed["dosage_form"] = "Infusion"
    elif "capsule" in q:
        parsed["dosage_form"] = "Capsule"
    elif "tablet" in q:
        parsed["dosage_form"] = "Tablet"
    elif "cream" in q:
        parsed["dosage_form"] = "Cream"
    elif "syrup" in q:
        parsed["dosage_form"] = "Syrup"

    if any(x in q for x in ["sleep", "bedtime", "insomnia", "relaxation", "stress"]):
        parsed["indication"] = "Sleep and relaxation"
    elif "constipation" in q:
        parsed["indication"] = "Constipation"
    elif "cough" in q:
        parsed["indication"] = "Cough"
    elif any(x in q for x in ["digestive", "digestion", "stomach"]):
        parsed["indication"] = "Digestive comfort"

    if any(x in q for x in ["eu", "europe", "european union", "france"]):
        parsed["market"] = "European Union"
    elif any(x in q for x in ["usa", "united states", "america"]):
        parsed["market"] = "United States"
    elif "canada" in q:
        parsed["market"] = "Canada"
    elif "iran" in q:
        parsed["market"] = "Iran"

    return parsed
