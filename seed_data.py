from schema import get_connection, init_schema

PLANTS = [
    ("Melissa officinalis", "Lemon balm", "Lamiaceae", "Europe", "Leaf"),
    ("Valeriana officinalis", "Valerian", "Caprifoliaceae", "Europe", "Root/rhizome"),
    ("Passiflora incarnata", "Passionflower", "Passifloraceae", "Americas", "Aerial parts"),
    ("Matricaria chamomilla", "Chamomile", "Asteraceae", "Europe", "Flower heads"),
    ("Lavandula angustifolia", "Lavender", "Lamiaceae", "Europe", "Flowering tops"),
    ("Humulus lupulus", "Hops", "Cannabaceae", "Europe", "Female inflorescences"),
    ("Tilia cordata", "Linden flower", "Malvaceae", "Europe", "Inflorescences"),
    ("Aloysia citriodora", "Lemon verbena", "Verbenaceae", "South America", "Leaf"),
    ("Eschscholzia californica", "California poppy", "Papaveraceae", "North America", "Aerial parts"),
    ("Mentha piperita", "Peppermint", "Lamiaceae", "Europe", "Leaf"),
    ("Curcuma longa", "Turmeric", "Zingiberaceae", "South Asia", "Rhizome"),
    ("Foeniculum vulgare", "Fennel", "Apiaceae", "Mediterranean", "Fruit"),
    ("Withania somnifera", "Ashwagandha", "Solanaceae", "South Asia", "Root"),
    ("Ziziphus jujuba", "Jujube", "Rhamnaceae", "East Asia", "Seed"),
]

PLANT_COMPOUNDS = {
    "Melissa officinalis": [
        ("Rosmarinic acid", "Phenolic acid", "Aqueous / hydroalcoholic extract"),
        ("Citral", "Monoterpene aldehyde", "Steam distillation"),
        ("Caffeic acid", "Phenolic acid", "Aqueous extract"),
        ("Luteolin", "Flavonoid", "Hydroalcoholic extract"),
        ("Apigenin", "Flavonoid", "Aqueous / hydroalcoholic extract"),
    ],
    "Valeriana officinalis": [
        ("Valerenic acid", "Sesquiterpenic acid", "Hydroalcoholic extract / dry extract"),
        ("Valepotriates", "Iridoid ester", "Hydroalcoholic extract"),
        ("Bornyl acetate", "Monoterpene ester", "Steam distillation"),
    ],
    "Passiflora incarnata": [
        ("Vitexin", "Flavonoid", "Aqueous / hydroalcoholic extract"),
        ("Isovitexin", "Flavonoid", "Aqueous extract"),
        ("Chrysin", "Flavonoid", "Hydroalcoholic extract"),
    ],
    "Matricaria chamomilla": [
        ("Apigenin", "Flavonoid", "Infusion / hydroalcoholic extract"),
        ("Bisabolol", "Sesquiterpene alcohol", "Steam distillation"),
        ("Luteolin", "Flavonoid", "Infusion"),
    ],
    "Lavandula angustifolia": [
        ("Linalool", "Monoterpene alcohol", "Steam distillation / essential oil"),
        ("Linalyl acetate", "Monoterpene ester", "Steam distillation / essential oil"),
    ],
    "Humulus lupulus": [
        ("Xanthohumol", "Prenylated chalcone", "Hydroalcoholic extract / CO2 extract"),
    ],
    "Tilia cordata": [
        ("Tiliroside", "Flavonoid glycoside", "Infusion / aqueous extract"),
        ("Quercetin", "Flavonoid", "Infusion"),
    ],
    "Aloysia citriodora": [
        ("Citral", "Monoterpene aldehyde", "Infusion / essential oil"),
        ("Verbascoside", "Phenylethanoid glycoside", "Aqueous extract"),
    ],
    "Eschscholzia californica": [
        ("Californidine", "Isoquinoline alkaloid", "Hydroalcoholic extract"),
        ("Protopine", "Isoquinoline alkaloid", "Hydroalcoholic extract"),
    ],
    "Mentha piperita": [
        ("Menthol", "Monoterpene", "Essential oil / infusion"),
        ("Menthone", "Monoterpene", "Essential oil"),
        ("Rosmarinic acid", "Phenolic acid", "Infusion"),
    ],
    "Curcuma longa": [
        ("Curcumin", "Diarylheptanoid", "Ethanolic extract / standardized extract"),
    ],
    "Foeniculum vulgare": [
        ("Anethole", "Phenylpropene", "Essential oil / infusion"),
        ("Fenchone", "Monoterpene ketone", "Essential oil"),
    ],
    "Withania somnifera": [
        ("Withanolides", "Steroidal lactone", "Hydroalcoholic extract / standardized extract"),
    ],
    "Ziziphus jujuba": [
        ("Jujubosides", "Saponin", "Aqueous / ethanolic extract"),
    ],
}

COMPOUND_TARGETS = {
    "Rosmarinic acid": ["GABAergic system", "COX-2", "NF-kB", "Nrf2"],
    "Citral": ["GABAergic system", "TRP channels"],
    "Luteolin": ["NF-kB", "COX-2"],
    "Vitexin": ["GABAergic system", "oxidative stress pathways"],
    "Chrysin": ["Benzodiazepine receptor", "GABA-A receptor"],
    "Valerenic acid": ["GABA-A receptor"],
    "Linalool": ["GABAergic system", "Glutamate system", "Calcium channels"],
    "Linalyl acetate": ["GABAergic system", "Autonomic nervous system"],
    "Apigenin": ["Benzodiazepine receptor", "GABA-A receptor", "COX-2"],
    "Xanthohumol": ["NF-kB", "Nrf2", "Estrogen receptors"],
    "Withanolides": ["HPA axis", "GABAergic system", "NF-kB"],
    "Jujubosides": ["GABAergic system", "Serotonergic system"],
    "Menthol": ["TRPM8", "Calcium channels"],
    "Anethole": ["Smooth muscle relaxation"],
    "Fenchone": ["Smooth muscle relaxation"],
    "Curcumin": ["NF-kB", "COX-2", "Nrf2", "AMPK"],
    "Bisabolol": ["COX-2", "Anti-inflammatory pathways"],
    "Tiliroside": ["Anti-inflammatory pathways"],
    "Quercetin": ["Anti-inflammatory pathways", "Oxidative stress pathways"],
    "Californidine": ["GABAergic system"],
    "Protopine": ["GABAergic system"],
    "Verbascoside": ["Antioxidant pathways"],
    "Bornyl acetate": ["GABAergic system"],
    "Isovitexin": ["Oxidative stress pathways"],
}

TARGET_DISEASES = {
    "Insomnia / sleep disturbance": {
        "GABA-A receptor": "established",
        "GABAergic system": "established",
        "Benzodiazepine receptor": "established",
        "HPA axis": "probable",
        "Serotonergic system": "probable",
        "Autonomic nervous system": "probable",
        "Glutamate system": "probable",
        "Calcium channels": "theoretical",
    },
    "Anxiety": {
        "GABA-A receptor": "established",
        "GABAergic system": "established",
        "Benzodiazepine receptor": "established",
        "HPA axis": "established",
        "Serotonergic system": "established",
    },
    "Digestive discomfort": {
        "Smooth muscle relaxation": "established",
        "TRPM8": "probable",
        "Anti-inflammatory pathways": "probable",
    },
}

SLEEP_TEA_EVIDENCE = {
    "Melissa officinalis": dict(
        study_type="Traditional use", preparation_form="infusion",
        outcome="Traditional use for mild mental stress and to aid sleep",
        ema_status="Traditional use (HMPC)", who_status="Listed", escop_status="Traditional use",
        safety="none", safety_desc="Generally acceptable for short-term traditional use",
        production_status="commercially produced", commercial="Very high",
    ),
    "Valeriana officinalis": dict(
        study_type="RCT (extract, not infusion)", preparation_form="extract",
        outcome="Multiple RCTs on hydroalcoholic extract for sleep; infusion-specific evidence limited",
        ema_status="Traditional use (HMPC)", who_status="Listed", escop_status="Traditional use",
        safety="mild", safety_desc="Sedation warning; caution with CNS depressants",
        production_status="commercially produced", commercial="High",
    ),
    "Passiflora incarnata": dict(
        study_type="RCT (infusion-specific)", preparation_form="infusion",
        outcome="Ngan & Conduit 2011: infusion-specific human RCT on sleep quality",
        ema_status="Traditional use (HMPC)", who_status="Listed", escop_status="Traditional use",
        safety="none", safety_desc="Generally acceptable; caution with sedatives",
        production_status="commercially produced", commercial="Medium-high",
    ),
    "Matricaria chamomilla": dict(
        study_type="Traditional use", preparation_form="infusion",
        outcome="Official EMA indication mainly gastrointestinal; sleep evidence weaker",
        ema_status="Well-established use (GI)", who_status="Listed", escop_status="Traditional use",
        safety="mild", safety_desc="Allergy risk in Asteraceae-sensitive users",
        production_status="commercially produced", commercial="Very high",
    ),
    "Lavandula angustifolia": dict(
        study_type="RCT (extract/oral capsule, not infusion)", preparation_form="extract",
        outcome="Silexan (oral lavender oil capsule) RCTs positive; not infusion-form evidence",
        ema_status="Traditional use (HMPC)", who_status="Listed", escop_status="Traditional use",
        safety="none", safety_desc="Generally acceptable as tea ingredient",
        production_status="commercially produced", commercial="High",
    ),
    "Humulus lupulus": dict(
        study_type="Traditional use", preparation_form="infusion",
        outcome="Traditional use for mild mental stress and to aid sleep, often combined with valerian",
        ema_status="Traditional use (HMPC)", who_status="Listed", escop_status="Traditional use",
        safety="mild", safety_desc="Sedative caution; taste may limit acceptance",
        production_status="commercially produced", commercial="Medium",
    ),
    "Tilia cordata": dict(
        study_type="Traditional use", preparation_form="infusion",
        outcome="Strong traditional infusion use; direct clinical sleep evidence limited",
        ema_status="Traditional use (regional)", who_status="Not listed", escop_status="Traditional use",
        safety="none", safety_desc="Generally acceptable for traditional infusion use",
        production_status="commercially produced", commercial="Medium-high",
    ),
    "Aloysia citriodora": dict(
        study_type="RCT (infusion-specific, null result)", preparation_form="infusion",
        outcome="Dedicated aqueous infusion RCT found no significant sleep effect; valid EU traditional-use sleep indication exists",
        ema_status="Traditional use (regional)", who_status="Not listed", escop_status="Not listed",
        safety="none", safety_desc="Generally used in herbal teas",
        production_status="commercially produced", commercial="Medium-high",
    ),
    "Eschscholzia californica": dict(
        study_type="Preclinical / limited human data", preparation_form="extract",
        outcome="Regulatory position and infusion-specific evidence not established in this dataset",
        ema_status="Not evaluated", who_status="Not listed", escop_status="Not listed",
        safety="moderate", safety_desc="Needs careful safety and regulatory review before use",
        production_status="R&D candidate", commercial="Medium",
    ),
}


def _get_id(cur, table, id_col, name_col, name_value):
    cur.execute(f"SELECT {id_col} FROM {table} WHERE {name_col} = ?", (name_value,))
    row = cur.fetchone()
    return row[0] if row else None


def seed_all():
    init_schema(reset=True)
    conn = get_connection()
    cur = conn.cursor()

    for sci, common, family, region, part in PLANTS:
        cur.execute(
            "INSERT OR IGNORE INTO plants (scientific_name, common_name, family, region, plant_part_used) "
            "VALUES (?, ?, ?, ?, ?)",
            (sci, common, family, region, part),
        )

    for disease in TARGET_DISEASES:
        cur.execute("INSERT OR IGNORE INTO diseases (disease_name) VALUES (?)", (disease,))

    all_targets = set()
    for targets in COMPOUND_TARGETS.values():
        all_targets.update(targets)
    for targets in TARGET_DISEASES.values():
        all_targets.update(targets.keys())
    for t in all_targets:
        cur.execute("INSERT OR IGNORE INTO targets (target_name) VALUES (?)", (t,))

    for plant_name, compounds in PLANT_COMPOUNDS.items():
        plant_id = _get_id(cur, "plants", "plant_id", "scientific_name", plant_name)
        for compound_name, compound_class, extraction_method in compounds:
            cur.execute(
                "INSERT OR IGNORE INTO compounds (compound_name, compound_class) VALUES (?, ?)",
                (compound_name, compound_class),
            )
            compound_id = _get_id(cur, "compounds", "compound_id", "compound_name", compound_name)
            cur.execute(
                "INSERT OR IGNORE INTO plant_compounds (plant_id, compound_id, extraction_method) "
                "VALUES (?, ?, ?)",
                (plant_id, compound_id, extraction_method),
            )

    for compound_name, targets in COMPOUND_TARGETS.items():
        compound_id = _get_id(cur, "compounds", "compound_id", "compound_name", compound_name)
        if compound_id is None:
            continue
        for target_name in targets:
            target_id = _get_id(cur, "targets", "target_id", "target_name", target_name)
            cur.execute(
                "INSERT OR IGNORE INTO compound_targets (compound_id, target_id) VALUES (?, ?)",
                (compound_id, target_id),
            )

    for disease_name, targets in TARGET_DISEASES.items():
        disease_id = _get_id(cur, "diseases", "disease_id", "disease_name", disease_name)
        for target_name, relevance in targets.items():
            target_id = _get_id(cur, "targets", "target_id", "target_name", target_name)
            cur.execute(
                "INSERT OR IGNORE INTO target_diseases (target_id, disease_id, relevance_level) "
                "VALUES (?, ?, ?)",
                (target_id, disease_id, relevance),
            )

    insomnia_id = _get_id(cur, "diseases", "disease_id", "disease_name", "Insomnia / sleep disturbance")
    for plant_name, ev in SLEEP_TEA_EVIDENCE.items():
        plant_id = _get_id(cur, "plants", "plant_id", "scientific_name", plant_name)

        cur.execute(
            "INSERT INTO clinical_evidence (plant_id, disease_id, study_type, preparation_form, outcome) "
            "VALUES (?, ?, ?, ?, ?)",
            (plant_id, insomnia_id, ev["study_type"], ev["preparation_form"], ev["outcome"]),
        )

        for agency, status_key in [("EMA", "ema_status"), ("WHO", "who_status"), ("ESCOP", "escop_status")]:
            cur.execute(
                "INSERT INTO regulatory_status (plant_id, agency, status) VALUES (?, ?, ?)",
                (plant_id, agency, ev[status_key]),
            )

        cur.execute(
            "INSERT INTO safety_profile (plant_id, severity, description) VALUES (?, ?, ?)",
            (plant_id, ev["safety"], ev["safety_desc"]),
        )

        cur.execute(
            "INSERT INTO market_information (plant_id, production_status, commercial_attractiveness) "
            "VALUES (?, ?, ?)",
            (plant_id, ev["production_status"], ev["commercial"]),
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    seed_all()
    print("Seed data loaded.")
