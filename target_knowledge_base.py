TARGET_COMPOUND_MAP = {
    "GABA pathway": [
        "Apigenin",
        "Linalool",
        "Valerenic acid",
        "Rosmarinic acid",
        "Magnolol",
        "Honokiol",
        "GABA",
    ],
    "GABA-A receptor": [
        "Apigenin",
        "Valerenic acid",
        "Linalool",
        "Honokiol",
        "Magnolol",
    ],
    "5-HT1A receptor": [
        "Linalool",
        "Apigenin",
        "Rosmarinic acid",
        "Hyperforin",
    ],
    "Melatonin pathway": [
        "Melatonin",
        "Tryptophan",
        "Serotonin",
    ],
    "Adenosine pathway": [
        "Apigenin",
        "Luteolin",
    ],
    "Acetylcholinesterase": [
        "Galantamine",
        "Huperzine A",
        "Berberine",
        "Rosmarinic acid",
        "Curcumin",
    ],
    "COX pathway": [
        "Curcumin",
        "Boswellic acids",
        "Quercetin",
        "Apigenin",
        "Luteolin",
        "Rosmarinic acid",
    ],
    "NF-kB pathway": [
        "Curcumin",
        "Boswellic acids",
        "Resveratrol",
        "Quercetin",
        "Withanolides",
        "Rosmarinic acid",
    ],
    "TRPV1 channel": [
        "Capsaicin",
        "Curcumin",
        "Gingerols",
    ],
    "Histamine H1 receptor": [
        "Quercetin",
        "Luteolin",
        "Apigenin",
    ],
}


COMPOUND_PLANT_MAP = {
    "Apigenin": [
        "Matricaria chamomilla",
        "Passiflora incarnata",
        "Petroselinum crispum",
        "Apium graveolens",
    ],
    "Linalool": [
        "Lavandula angustifolia",
        "Ocimum basilicum",
        "Coriandrum sativum",
        "Cinnamomum camphora",
    ],
    "Valerenic acid": [
        "Valeriana officinalis",
    ],
    "Rosmarinic acid": [
        "Melissa officinalis",
        "Rosmarinus officinalis",
        "Salvia officinalis",
        "Perilla frutescens",
        "Ocimum basilicum",
    ],
    "Magnolol": [
        "Magnolia officinalis",
    ],
    "Honokiol": [
        "Magnolia officinalis",
    ],
    "Galantamine": [
        "Galanthus nivalis",
        "Narcissus pseudonarcissus",
        "Leucojum aestivum",
    ],
    "Huperzine A": [
        "Huperzia serrata",
    ],
    "Berberine": [
        "Berberis vulgaris",
        "Coptis chinensis",
        "Hydrastis canadensis",
    ],
    "Curcumin": [
        "Curcuma longa",
    ],
    "Boswellic acids": [
        "Boswellia serrata",
        "Boswellia sacra",
    ],
    "Quercetin": [
        "Sophora japonica",
        "Allium cepa",
        "Camellia sinensis",
        "Ginkgo biloba",
    ],
    "Luteolin": [
        "Perilla frutescens",
        "Apium graveolens",
        "Thymus vulgaris",
    ],
    "Resveratrol": [
        "Polygonum cuspidatum",
        "Vitis vinifera",
    ],
    "Withanolides": [
        "Withania somnifera",
    ],
    "Capsaicin": [
        "Capsicum annuum",
        "Capsicum frutescens",
    ],
    "Gingerols": [
        "Zingiber officinale",
    ],
    "Hyperforin": [
        "Hypericum perforatum",
    ],
    "Melatonin": [
        "Hypericum perforatum",
        "Vitis vinifera",
        "Oryza sativa",
    ],
    "Tryptophan": [
        "Avena sativa",
        "Sesamum indicum",
        "Glycine max",
    ],
    "Serotonin": [
        "Musa paradisiaca",
        "Ananas comosus",
        "Urtica dioica",
    ],
    "GABA": [
        "Camellia sinensis",
        "Oryza sativa",
        "Glycine max",
    ],
}


def get_compounds_for_target(target):
    return TARGET_COMPOUND_MAP.get(target, [])


def get_plants_for_compound(compound):
    return COMPOUND_PLANT_MAP.get(compound, [])


def get_all_target_compound_plant_links():
    rows = []

    for target, compounds in TARGET_COMPOUND_MAP.items():
        for compound in compounds:
            plants = COMPOUND_PLANT_MAP.get(compound, [])

            for plant in plants:
                rows.append(
                    {
                        "Target": target,
                        "Compound": compound,
                        "Candidate_Plant": plant,
                        "Source": "Internal curated MVP knowledge base",
                    }
                )

    return rows
