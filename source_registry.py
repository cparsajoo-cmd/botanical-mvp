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
        # Legacy internal connector key retained for compatibility with stored
        # telemetry/tests.  Production implementation queries EMA/HMPC only;
        # WHO and ESCOP are NOT independently queried by this connector.
        "name": "EMA/WHO/ESCOP Regulatory",
        "display_name": "EMA/HMPC Regulatory",
        "verified_scope": "EMA/HMPC inventory only; WHO/ESCOP not independently queried",
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


# Task 6 — pilot-scope evidence coverage. A single elevated ceiling,
# used only for explicitly pilot-scoped collection sessions (see
# multi_source_collector.collect_multi_source_evidence's
# max_results_override parameter and research_engine.py's pilot_mode
# parameter) — 3x the per-source default of 5 above. Chosen as a
# documented multiplier of the existing default, not an independently
# invented number: materially fuller coverage than the default
# exploratory-session cap, while still bounded (not "unlimited"), so a
# pilot session's connector calls stay within the kind of volume this
# repository's connectors have actually been exercised at. If a real
# pilot's rate-limit behavior at this volume needs adjusting, that is
# a deliberately separate, later change — not invented here.
PILOT_MAX_RESULTS = 15


def get_source_display_name(name):
    config = get_source_config(name)
    if config:
        return config.get("display_name") or config.get("name") or str(name)
    return str(name)


def get_source_verified_scope(name):
    config = get_source_config(name)
    return (config or {}).get("verified_scope", "")
