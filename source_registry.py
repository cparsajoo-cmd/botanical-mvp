SOURCE_REGISTRY = [
    # Tier 1 — Scientific literature
    {
        "name": "PubMed",
        "category": "Scientific literature",
        "priority": 1,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 1.0,
    },
    {
        "name": "Europe PMC",
        "category": "Scientific literature",
        "priority": 1,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.95,
    },
    {
        "name": "Semantic Scholar",
        "category": "Scientific literature",
        "priority": 2,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.85,
    },
    {
        "name": "OpenAlex",
        "category": "Scientific literature",
        "priority": 2,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.8,
    },
    {
        "name": "CrossRef",
        "category": "Scientific literature",
        "priority": 3,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.7,
    },

    # Tier 1 — Clinical
    {
        "name": "ClinicalTrials.gov",
        "category": "Clinical trials",
        "priority": 1,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 1.0,
    },

    # Tier 1 — Regulatory
    {
        "name": "EMA/WHO/ESCOP Regulatory",
        "category": "Regulatory",
        "priority": 1,
        "enabled": True,
        "max_results": 1,
        "authority_weight": 1.0,
    },
    {
        "name": "FDA Labels",
        "category": "Regulatory/Safety",
        "priority": 2,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.9,
    },

    # Safety
    {
        "name": "LiverTox",
        "category": "Safety",
        "priority": 1,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 1.0,
    },
    {
        "name": "DailyMed",
        "category": "Safety/Labels",
        "priority": 2,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.85,
    },
    {
        "name": "OpenFDA FAERS",
        "category": "Pharmacovigilance",
        "priority": 2,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.85,
    },

    # Chemistry and mechanism
    {
        "name": "PubChem",
        "category": "Chemistry",
        "priority": 1,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.95,
    },
    {
        "name": "ChEMBL",
        "category": "Mechanism/Bioactivity",
        "priority": 1,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.95,
    },
    {
        "name": "ChEBI",
        "category": "Chemical ontology",
        "priority": 2,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.85,
    },

    # Patent / commercial
    {
        "name": "Patent Landscape",
        "category": "Patent/Commercial",
        "priority": 2,
        "enabled": True,
        "max_results": 5,
        "authority_weight": 0.7,
    },
]


def get_enabled_sources():
    return [s for s in SOURCE_REGISTRY if s.get("enabled")]


def get_source_names():
    return [s["name"] for s in get_enabled_sources()]


def get_source_config(name):
    for source in SOURCE_REGISTRY:
        if source["name"] == name:
            return source
    return None
