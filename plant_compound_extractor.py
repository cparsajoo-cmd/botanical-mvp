import re

from plant_compound_database import save_plant_compound_record


COMPOUND_PATTERNS = {
    "Rosmarinic acid": {
        "compound_class": "Phenolic acid",
        "target": "GABAergic system; COX-2; NF-kB; Nrf2",
        "mechanism": "Anti-inflammatory, antioxidant, possible neuromodulatory effects",
    },
    "Citral": {
        "compound_class": "Monoterpene aldehyde",
        "target": "GABAergic system; TRP channels",
        "mechanism": "Sedative and anxiolytic-like volatile oil activity",
    },
    "Luteolin": {
        "compound_class": "Flavonoid",
        "target": "NF-kB; COX-2; IL-6; TNF-alpha",
        "mechanism": "Anti-inflammatory flavonoid with neuroprotective potential",
    },
    "Vitexin": {
        "compound_class": "Flavonoid",
        "target": "GABAergic system; oxidative stress pathways",
        "mechanism": "Flavonoid-associated anxiolytic and antioxidant activity",
    },
    "Chrysin": {
        "compound_class": "Flavonoid",
        "target": "benzodiazepine receptor; GABA-A receptor",
        "mechanism": "Potential benzodiazepine-site modulation",
    },
    "Valerenic acid": {
        "compound_class": "Sesquiterpenic acid",
        "target": "GABA-A receptor",
        "mechanism": "Modulation of GABA-A receptor activity",
    },
    "Linalool": {
        "compound_class": "Monoterpene alcohol",
        "target": "GABAergic system; glutamate system; calcium channels",
        "mechanism": "Sedative, anxiolytic, and CNS depressant-like activity",
    },
    "Linalyl acetate": {
        "compound_class": "Monoterpene ester",
        "target": "GABAergic system; autonomic nervous system",
        "mechanism": "Relaxant volatile compound activity",
    },
    "Apigenin": {
        "compound_class": "Flavonoid",
        "target": "benzodiazepine receptor; GABA-A receptor; COX-2",
        "mechanism": "Flavonoid with anxiolytic-like and anti-inflammatory effects",
    },
    "Xanthohumol": {
        "compound_class": "Prenylated chalcone",
        "target": "NF-kB; Nrf2; estrogen receptors",
        "mechanism": "Prenylated chalcone with anti-inflammatory and antioxidant activity",
    },
    "Withanolides": {
        "compound_class": "Steroidal lactones",
        "target": "HPA axis; GABAergic system; NF-kB",
        "mechanism": "Adaptogenic, anti-stress, anti-inflammatory activity",
    },
    "Jujubosides": {
        "compound_class": "Saponins",
        "target": "GABAergic system; serotonergic system",
        "mechanism": "Sedative and sleep-promoting saponins",
    },
    "Baicalin": {
        "compound_class": "Flavonoid glycoside",
        "target": "GABAergic system; NF-kB; COX-2",
        "mechanism": "Anti-inflammatory and neuroactive flavonoid activity",
    },
    "Baicalein": {
        "compound_class": "Flavonoid",
        "target": "GABAergic system; NF-kB; oxidative stress pathways",
        "mechanism": "Neuroprotective and anti-inflammatory activity",
    },
    "Wogonin": {
        "compound_class": "Flavonoid",
        "target": "GABA-A receptor; NF-kB",
        "mechanism": "Potential anxiolytic-like and anti-inflammatory activity",
    },
    "Kavalactones": {
        "compound_class": "Lactones",
        "target": "GABAergic system; sodium channels; monoamine oxidase",
        "mechanism": "Anxiolytic and CNS depressant-like activity",
    },
}


EXTRACTION_KEYWORDS = [
    "aqueous extract",
    "hydroalcoholic extract",
    "hydroethanolic extract",
    "ethanolic extract",
    "methanolic extract",
    "dry extract",
    "essential oil",
    "infusion",
    "decoction",
    "steam distillation",
    "supercritical CO2",
    "CO2 extract",
]


PLANT_PART_KEYWORDS = [
    "leaf",
    "leaves",
    "root",
    "rhizome",
    "aerial parts",
    "flower",
    "flowering tops",
    "seed",
    "fruit",
    "bark",
    "inflorescences",
]


def _clean_text(text):
    if text is None:
        return ""
    return str(text)


def _find_extraction_method(text):
    lower = text.lower()
    found = []

    for method in EXTRACTION_KEYWORDS:
        if method.lower() in lower:
            found.append(method)

    return "; ".join(sorted(set(found)))


def _find_plant_part(text):
    lower = text.lower()
    found = []

    for part in PLANT_PART_KEYWORDS:
        if part.lower() in lower:
            found.append(part)

    return "; ".join(sorted(set(found)))


def extract_plant_compounds_from_text(
    scientific_name,
    text,
    indication="",
    dosage_form="",
    market="",
    reference_title="",
    reference_url="",
    source="",
    source_year="",
    save=True,
):
    text = _clean_text(text)
    lower_text = text.lower()

    extracted_records = []

    extraction_method = _find_extraction_method(text)
    plant_part = _find_plant_part(text)

    for compound_name, meta in COMPOUND_PATTERNS.items():
        pattern = re.escape(compound_name.lower())

        if re.search(pattern, lower_text):
            confidence = 80

            if extraction_method:
                confidence += 5

            if plant_part:
                confidence += 5

            confidence = min(confidence, 100)

            record = {
                "scientific_name": scientific_name,
                "common_name": "",
                "compound_name": compound_name,
                "compound_class": meta.get("compound_class", ""),
                "plant_part": plant_part,
                "concentration": "",
                "unit": "",
                "extraction_method": extraction_method,
                "solvent": "",
                "yield_percent": "",
                "target": meta.get("target", ""),
                "mechanism": meta.get("mechanism", ""),
                "bioavailability": "",
                "toxicity": "",
                "safety_note": "",
                "indication": indication,
                "dosage_form": dosage_form,
                "market": market,
                "evidence_level": "",
                "confidence_score": confidence,
                "reference_title": reference_title,
                "reference_url": reference_url,
                "source": source,
                "source_year": source_year,
            }

            if save:
                try:
                    save_plant_compound_record(record)
                except Exception:
                    pass

            extracted_records.append(record)

    return extracted_records
