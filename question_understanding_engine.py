# question_understanding_engine.py

from typing import Dict, List, Any


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _prettify_if_lowercase(raw: str) -> str:
    """Only title-cases input that looks like unformatted free text
    (all-lowercase). A value that already has any uppercase (an
    already-canonical value like "Cognitive decline / Alzheimer's
    support", or an acronym like "GCC") is passed through unchanged —
    blindly calling .title() on those mangles apostrophes
    ("Alzheimer's" -> "Alzheimer'S") and acronyms ("GCC" -> "Gcc").
    This surfaced as a real bug once this module was actually wired
    into the live pipeline for the first time (it was previously
    unreachable, so nothing had ever exercised this path with a
    real mixed-case value)."""
    if not raw:
        return raw
    return raw.title() if raw == raw.lower() else raw


def normalize_market(market: str) -> str:
    market_raw = normalize_text(market)
    market = market_raw.lower()

    market_map = {
        "eu": "European Union",
        "europe": "European Union",
        "european union": "European Union",
        "france": "France",
        "usa": "United States",
        "us": "United States",
        "united states": "United States",
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
        "canada": "Canada",
        "global": "Global"
    }

    return market_map.get(market, _prettify_if_lowercase(market_raw) or "Not specified")


def infer_route(dosage_form: str) -> str:
    dosage_form = normalize_text(dosage_form).lower()

    if any(term in dosage_form for term in ["tea", "infusion", "capsule", "tablet", "syrup", "drops"]):
        return "Oral"

    if any(term in dosage_form for term in ["nasal", "spray"]):
        return "Intranasal"

    if any(term in dosage_form for term in ["cream", "gel", "ointment", "lotion"]):
        return "Topical"

    if any(term in dosage_form for term in ["inhalation", "vapor", "aromatherapy"]):
        return "Inhalation"

    return "Not specified"


def normalize_dosage_form(dosage_form: str) -> str:
    dosage_form_raw = normalize_text(dosage_form)
    dosage_form = dosage_form_raw.lower()

    dosage_map = {
        "tea": "Herbal Infusion",
        "herbal tea": "Herbal Infusion",
        "infusion": "Herbal Infusion",
        "tisane": "Herbal Infusion",
        "capsule": "Capsule",
        "capsules": "Capsule",
        "tablet": "Tablet",
        "tablets": "Tablet",
        "nasal spray": "Nasal Spray",
        "spray": "Spray",
        "cream": "Cream",
        "gel": "Gel",
        "ointment": "Ointment",
        "syrup": "Syrup",
        "drops": "Drops"
    }

    return dosage_map.get(dosage_form, _prettify_if_lowercase(dosage_form_raw) or "Not specified")


def normalize_indication(indication: str) -> str:
    indication_raw = normalize_text(indication)
    indication = indication_raw.lower()

    indication_map = {
        "sleep": "Sleep Support",
        "insomnia": "Insomnia",
        "stress": "Stress",
        "anxiety": "Anxiety",
        "relaxation": "Relaxation",
        "constipation": "Constipation",
        "allergic rhinitis": "Allergic Rhinitis",
        "rhinitis": "Rhinitis",
        "cough": "Cough",
        "digestion": "Digestive Support",
        "menopause": "Menopausal Symptoms"
    }

    return indication_map.get(indication, _prettify_if_lowercase(indication_raw) or "Not specified")


def infer_product_type(dosage_form: str, indication: str) -> str:
    dosage_form_l = normalize_text(dosage_form).lower()
    indication_l = normalize_text(indication).lower()

    if any(term in dosage_form_l for term in ["tea", "infusion", "tisane"]):
        return "Botanical Food Product"

    if any(term in dosage_form_l for term in ["capsule", "tablet", "drops", "syrup"]):
        return "Botanical Food Supplement"

    if any(term in dosage_form_l for term in ["nasal spray", "cream", "ointment"]):
        return "Botanical Medicinal Product Candidate"

    if any(term in indication_l for term in ["allergic rhinitis", "insomnia", "constipation"]):
        return "Botanical Medicinal Product Candidate"

    return "Botanical Product"


def infer_regulatory_focus(market: str, dosage_form: str, indication: str) -> List[str]:
    market_l = normalize_text(market).lower()
    dosage_l = normalize_text(dosage_form).lower()
    indication_l = normalize_text(indication).lower()

    focus = []

    if market_l in ["eu", "europe", "european union", "france"]:
        focus.append("EU Regulatory Framework")
        focus.append("EMA-HMPC Monographs")

    if any(term in dosage_l for term in ["tea", "infusion", "tisane"]):
        focus.append("Traditional Herbal Infusion Use")

    if any(term in dosage_l for term in ["capsule", "tablet", "drops"]):
        focus.append("Food Supplement / Herbal Medicinal Borderline")

    if any(term in dosage_l for term in ["nasal", "spray", "cream", "ointment"]):
        focus.append("Herbal Medicinal Product Assessment")

    if any(term in indication_l for term in ["insomnia", "allergic rhinitis", "constipation"]):
        focus.append("Therapeutic Claim Risk Assessment")

    return list(dict.fromkeys(focus))


def infer_evidence_requirements(dosage_form: str, indication: str) -> List[str]:
    dosage_l = normalize_text(dosage_form).lower()
    indication_l = normalize_text(indication).lower()

    requirements = [
        "EMA-HMPC",
        "WHO Monographs",
        "ESCOP Monographs",
        "Clinical Evidence",
        "Safety Evidence"
    ]

    if any(term in dosage_l for term in ["tea", "infusion", "tisane"]):
        requirements.append("Infusion-Specific Evidence")

    if any(term in dosage_l for term in ["nasal", "spray"]):
        requirements.append("Local Tolerance Evidence")
        requirements.append("Route-Specific Safety Evidence")

    if any(term in indication_l for term in ["sleep", "insomnia", "anxiety", "stress"]):
        requirements.append("Human Clinical Evidence for CNS-Related Claims")

    if any(term in indication_l for term in ["allergic rhinitis", "rhinitis"]):
        requirements.append("Evidence for Anti-Allergic / Anti-Inflammatory Activity")

    return list(dict.fromkeys(requirements))


def standardize_project_definition(form_input: Dict[str, Any]) -> Dict[str, Any]:
    product = normalize_text(form_input.get("product"))
    dosage_form_raw = normalize_text(form_input.get("dosage_form"))
    indication_raw = normalize_text(form_input.get("indication"))
    market_raw = normalize_text(form_input.get("market"))
    population = normalize_text(form_input.get("population")) or "Adults"
    constraints = form_input.get("constraints", [])
    commercial_goal = normalize_text(form_input.get("commercial_goal")) or "New Product Development"

    dosage_form = normalize_dosage_form(dosage_form_raw)
    indication = normalize_indication(indication_raw)
    market = normalize_market(market_raw)
    route = infer_route(dosage_form)
    product_type = infer_product_type(dosage_form, indication)

    standardized_project = {
        "product": product or "Not specified",
        "product_type": product_type,
        "dosage_form": dosage_form,
        "route": route,
        "target_indication": indication,
        "target_population": population,
        "target_market": market,
        "commercial_goal": commercial_goal,
        "constraints": constraints if isinstance(constraints, list) else [constraints],
        "regulatory_focus": infer_regulatory_focus(market_raw, dosage_form, indication),
        "evidence_requirements": infer_evidence_requirements(dosage_form, indication),
        "module_status": {
            "module": "Module 2 - Question Understanding Engine",
            "status": "Completed",
            "output": "Standardized Project Definition JSON"
        }
    }

    return standardized_project
