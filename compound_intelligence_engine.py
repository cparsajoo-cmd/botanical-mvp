import re
import pandas as pd


COMPOUND_KNOWLEDGE = {
    "Melissa officinalis": {
        "compounds": ["rosmarinic acid", "citral", "caffeic acid", "luteolin", "apigenin"],
        "targets": ["GABAergic system", "acetylcholinesterase", "antioxidant pathways"],
        "plant_part": "Leaf",
        "extraction": "Aqueous / hydroalcoholic extract",
    },
    "Valeriana officinalis": {
        "compounds": ["valerenic acid", "valepotriates", "bornyl acetate", "lignans"],
        "targets": ["GABA-A receptor", "adenosine system"],
        "plant_part": "Root / rhizome",
        "extraction": "Hydroalcoholic extract / dry extract",
    },
    "Passiflora incarnata": {
        "compounds": ["vitexin", "isovitexin", "orientin", "apigenin", "chrysin"],
        "targets": ["GABAergic system", "benzodiazepine receptor modulation"],
        "plant_part": "Aerial parts",
        "extraction": "Aqueous / hydroalcoholic extract",
    },
    "Lavandula angustifolia": {
        "compounds": ["linalool", "linalyl acetate", "lavandulol", "terpinen-4-ol"],
        "targets": ["GABAergic system", "serotonergic system", "calcium channels"],
        "plant_part": "Flowering tops / essential oil",
        "extraction": "Steam distillation / essential oil",
    },
    "Humulus lupulus": {
        "compounds": ["xanthohumol", "8-prenylnaringenin", "humulone", "lupulone"],
        "targets": ["GABAergic system", "estrogen receptors", "anti-inflammatory pathways"],
        "plant_part": "Female inflorescences",
        "extraction": "Hydroalcoholic extract / CO2 extract",
    },
    "Matricaria chamomilla": {
        "compounds": ["apigenin", "bisabolol", "chamazulene", "luteolin"],
        "targets": ["GABAergic system", "anti-inflammatory pathways", "COX/LOX modulation"],
        "plant_part": "Flower heads",
        "extraction": "Infusion / essential oil / hydroalcoholic extract",
    },
    "Tilia cordata": {
        "compounds": ["tiliroside", "quercetin", "kaempferol", "mucilage"],
        "targets": ["mild sedative pathways", "anti-inflammatory pathways"],
        "plant_part": "Inflorescences",
        "extraction": "Infusion / aqueous extract",
    },
    "Mentha piperita": {
        "compounds": ["menthol", "menthone", "rosmarinic acid", "menthyl acetate"],
        "targets": ["TRPM8", "calcium channels", "smooth muscle relaxation"],
        "plant_part": "Leaf / essential oil",
        "extraction": "Essential oil / dry extract / infusion",
    },
    "Curcuma longa": {
        "compounds": ["curcumin", "demethoxycurcumin", "bisdemethoxycurcumin", "turmerones"],
        "targets": ["NF-kB", "COX-2", "Nrf2", "AMPK"],
        "plant_part": "Rhizome",
        "extraction": "Ethanolic extract / standardized extract",
    },
    "Foeniculum vulgare": {
        "compounds": ["anethole", "fenchone", "estragole", "limonene"],
        "targets": ["smooth muscle relaxation", "carminative activity"],
        "plant_part": "Fruit",
        "extraction": "Essential oil / infusion",
    },
}


GLOBAL_COMPOUNDS = [
    "rosmarinic acid", "citral", "caffeic acid", "luteolin", "apigenin",
    "valerenic acid", "valepotriates", "bornyl acetate",
    "vitexin", "isovitexin", "orientin", "chrysin",
    "linalool", "linalyl acetate", "lavandulol",
    "xanthohumol", "8-prenylnaringenin", "humulone", "lupulone",
    "bisabolol", "chamazulene",
    "tiliroside", "quercetin", "kaempferol",
    "menthol", "menthone",
    "curcumin", "demethoxycurcumin", "bisdemethoxycurcumin", "turmerones",
    "anethole", "fenchone", "estragole", "limonene",
    "berberine", "egcg", "epigallocatechin gallate",
]


TARGET_KEYWORDS = {
    "GABAergic system": ["gaba", "gabaergic", "benzodiazepine"],
    "NF-kB": ["nf-kb", "nfkb", "nuclear factor kappa"],
    "COX-2": ["cox-2", "cyclooxygenase"],
    "Nrf2": ["nrf2"],
    "AMPK": ["ampk"],
    "TRPM8": ["trpm8"],
    "acetylcholinesterase": ["acetylcholinesterase", "ache"],
    "antioxidant pathways": ["antioxidant", "oxidative stress"],
    "anti-inflammatory pathways": ["anti-inflammatory", "inflammation"],
    "serotonergic system": ["serotonin", "serotonergic"],
}


def _txt(x):
    return "" if x is None else str(x)


def _combined_text(row):
    return " ".join([
        _txt(row.get("Scientific_Name", "")),
        _txt(row.get("Source_Title", "")),
        _txt(row.get("Notes", "")),
        _txt(row.get("Primary_Outcome", "")),
        _txt(row.get("Regulatory_Status", "")),
    ]).lower()


def detect_compounds(row):
    text = _combined_text(row)
    plant = _txt(row.get("Scientific_Name", "")).strip()

    compounds = []

    if plant in COMPOUND_KNOWLEDGE:
        compounds.extend(COMPOUND_KNOWLEDGE[plant]["compounds"])

    for compound in GLOBAL_COMPOUNDS:
        if compound.lower() in text:
            compounds.append(compound)

    compounds = sorted(set([c for c in compounds if c]))
    return compounds


def detect_targets(row):
    text = _combined_text(row)
    plant = _txt(row.get("Scientific_Name", "")).strip()

    targets = []

    if plant in COMPOUND_KNOWLEDGE:
        targets.extend(COMPOUND_KNOWLEDGE[plant]["targets"])

    for target, keys in TARGET_KEYWORDS.items():
        if any(k in text for k in keys):
            targets.append(target)

    targets = sorted(set([t for t in targets if t]))
    return targets


def infer_plant_part(row):
    plant = _txt(row.get("Scientific_Name", "")).strip()
    if plant in COMPOUND_KNOWLEDGE:
        return COMPOUND_KNOWLEDGE[plant]["plant_part"]

    text = _combined_text(row)
    for part in ["leaf", "root", "rhizome", "flower", "fruit", "seed", "bark", "aerial parts"]:
        if part in text:
            return part.title()

    return "Unknown"


def infer_extraction_method(row):
    plant = _txt(row.get("Scientific_Name", "")).strip()
    if plant in COMPOUND_KNOWLEDGE:
        return COMPOUND_KNOWLEDGE[plant]["extraction"]

    text = _combined_text(row)
    methods = []

    for method in [
        "aqueous extract", "hydroalcoholic extract", "ethanolic extract",
        "methanolic extract", "dry extract", "essential oil", "infusion",
        "decoction", "supercritical co2", "steam distillation"
    ]:
        if method in text:
            methods.append(method)

    return ", ".join(sorted(set(methods))) if methods else "Unknown"


def chemistry_score(row):
    compounds = detect_compounds(row)
    targets = detect_targets(row)
    extraction = infer_extraction_method(row)

    score = 0

    if compounds:
        score += min(35, 10 + len(compounds) * 5)

    if targets:
        score += min(35, 10 + len(targets) * 5)

    if extraction != "Unknown":
        score += 20

    if row.get("Source_Type", "") in ["PubChem", "ChEMBL", "ChEBI"]:
        score += 10

    return min(score, 100)


def apply_compound_intelligence(df):
    if df is None or df.empty:
        return df

    result = df.copy()

    result["Active_Compounds"] = result.apply(
        lambda row: ", ".join(detect_compounds(row)),
        axis=1,
    )

    result["Molecular_Targets"] = result.apply(
        lambda row: ", ".join(detect_targets(row)),
        axis=1,
    )

    result["Plant_Part"] = result.apply(infer_plant_part, axis=1)
    result["Extraction_Method"] = result.apply(infer_extraction_method, axis=1)
    result["Chemistry_Score"] = result.apply(chemistry_score, axis=1)

    return result
