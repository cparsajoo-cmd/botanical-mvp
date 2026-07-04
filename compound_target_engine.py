COMPOUND_TARGET_DATABASE = {
    "Rosmarinic acid": {
        "Targets": ["GABAergic system", "COX-2", "NF-kB", "Nrf2"],
        "Mechanism": "Anti-inflammatory, antioxidant, possible neuromodulatory effects",
    },
    "Citral": {
        "Targets": ["GABAergic system", "TRP channels"],
        "Mechanism": "Sedative and anxiolytic-like effects; volatile oil activity",
    },
    "Luteolin": {
        "Targets": ["NF-kB", "COX-2", "IL-6", "TNF-alpha"],
        "Mechanism": "Anti-inflammatory flavonoid with neuroprotective potential",
    },
    "Vitexin": {
        "Targets": ["GABAergic system", "oxidative stress pathways"],
        "Mechanism": "Flavonoid-associated anxiolytic and antioxidant activity",
    },
    "Chrysin": {
        "Targets": ["benzodiazepine receptor", "GABA-A receptor"],
        "Mechanism": "Potential benzodiazepine-site modulation",
    },
    "Valerenic acid": {
        "Targets": ["GABA-A receptor"],
        "Mechanism": "Modulation of GABA-A receptor activity",
    },
    "Linalool": {
        "Targets": ["GABAergic system", "glutamate system", "calcium channels"],
        "Mechanism": "Sedative, anxiolytic, and CNS depressant-like activity",
    },
    "Linalyl acetate": {
        "Targets": ["GABAergic system", "autonomic nervous system"],
        "Mechanism": "Relaxant volatile compound activity",
    },
    "Apigenin": {
        "Targets": ["benzodiazepine receptor", "GABA-A receptor", "COX-2"],
        "Mechanism": "Flavonoid with anxiolytic-like and anti-inflammatory effects",
    },
    "Xanthohumol": {
        "Targets": ["NF-kB", "Nrf2", "estrogen receptors"],
        "Mechanism": "Prenylated chalcone with anti-inflammatory and antioxidant activity",
    },
    "Withanolides": {
        "Targets": ["HPA axis", "GABAergic system", "NF-kB"],
        "Mechanism": "Adaptogenic, anti-stress, anti-inflammatory activity",
    },
    "Jujubosides": {
        "Targets": ["GABAergic system", "serotonergic system"],
        "Mechanism": "Sedative and sleep-promoting saponins",
    },
}


def get_compound_target_info(compound):
    return COMPOUND_TARGET_DATABASE.get(
        compound,
        {
            "Targets": [],
            "Mechanism": "",
        },
    )
