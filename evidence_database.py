import pandas as pd

def load_evidence_database():
    data = [
        {
            "plant": "Melissa officinalis",
            "common_name": "Lemon balm",
            "product_type": "Herbal product",
            "dosage_form": "Infusion",
            "indication": "Sleep and relaxation",
            "market": "European Union",
            "ema_status": "Positive traditional-use fit",
            "who_status": "To be verified",
            "escop_status": "To be verified",
            "infusion_specific": "Yes",
            "safety_level": "Acceptable",
            "commercial_value": "High",
            "decision_class": "Priority candidate",
            "reason": "Strong EU traditional-use fit for stress and sleep support, suitable for infusion."
        },
        {
            "plant": "Valeriana officinalis",
            "common_name": "Valerian",
            "product_type": "Herbal product",
            "dosage_form": "Infusion",
            "indication": "Sleep and relaxation",
            "market": "European Union",
            "ema_status": "Positive traditional-use fit",
            "who_status": "To be verified",
            "escop_status": "To be verified",
            "infusion_specific": "Partial",
            "safety_level": "Caution",
            "commercial_value": "High",
            "decision_class": "Conditional candidate",
            "reason": "Strong sleep positioning, but much clinical evidence concerns extracts rather than infusion."
        },
        {
            "plant": "Passiflora incarnata",
            "common_name": "Passionflower",
            "product_type": "Herbal product",
            "dosage_form": "Infusion",
            "indication": "Sleep and relaxation",
            "market": "European Union",
            "ema_status": "Positive traditional-use fit",
            "who_status": "To be verified",
            "escop_status": "To be verified",
            "infusion_specific": "Yes",
            "safety_level": "Acceptable with caution",
            "commercial_value": "Medium",
            "decision_class": "Conditional candidate",
            "reason": "Good traditional-use fit, but clinical evidence strength is limited."
        },
    ]

    return pd.DataFrame(data)
