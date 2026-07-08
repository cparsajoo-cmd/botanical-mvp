"""
Regulatory knowledge base.

LEVEL 1 — MARKET_REGULATORY_FRAMEWORKS: generic, market-level regulatory
context (which authority, which product pathways exist, key constraints).
This applies to every plant/product equally within a given market and is
safe to state as general regulatory knowledge.

LEVEL 2 — US_UK_PLANT_REGULATORY_STATUS: a manually curated, plant-specific
regulatory position for the US and UK markets only, for a set of
well-established botanicals. This is NOT a legal opinion or a guarantee
of any specific product's approval status — it reflects the general,
publicly-known regulatory category a plant falls into (e.g. whether it
has long-standing US dietary-supplement market history, or an existing
UK Traditional Herbal Registration route), so it should be verified
against the specific product/ingredient/supplier before being relied on
commercially.
"""

MARKET_REGULATORY_FRAMEWORKS = {
    "European Union": {
        "primary_authority": "EMA / HMPC (Committee on Herbal Medicinal Products)",
        "key_pathways": [
            "Traditional herbal medicinal product registration (Directive 2004/24/EC) — 30+ years of use, 15+ in the EU",
            "Well-established use marketing authorisation — for products with recognized efficacy/safety literature",
            "Food supplement (Directive 2002/46/EC) — no disease claims; only EU-authorized health claims allowed",
            "Novel Food authorisation (Regulation 2015/2283) — required if the plant/part lacks significant EU food-use history before 1997",
        ],
        "notes": "Disease-treatment claims are reserved for registered medicinal products. Food supplements may only use claims from the EU health claims register.",
    },
    "Germany": {
        "primary_authority": "BfArM; follows the EU HMPC framework, historically shaped by the Kommission E monographs",
        "key_pathways": [
            "Traditional herbal medicinal product registration (EU THMPD, as implemented by BfArM)",
            "Food supplement — general EU rules apply",
        ],
        "notes": "Germany's Kommission E monographs (1978–1994) predate and heavily influenced the current EU HMPC system.",
    },
    "France": {
        "primary_authority": "ANSM; follows the EU HMPC framework",
        "key_pathways": [
            "Traditional herbal medicinal product registration (EU THMPD)",
            "Food supplement — DGCCRF oversight, subject to France's own positive list of authorised plants (Décret 2008-841)",
        ],
        "notes": "France maintains a national positive list of plants authorised for food-supplement use, which can be more restrictive than the general EU list.",
    },
    "Italy": {
        "primary_authority": "Ministero della Salute / AIFA; follows the EU HMPC framework",
        "key_pathways": [
            "Traditional herbal medicinal product registration (EU THMPD)",
            "Food supplement — Ministry of Health 'herbal substances' positive list, updated periodically",
        ],
        "notes": "Italy keeps its own positive/negative list of botanicals allowed in food supplements.",
    },
    "Spain": {
        "primary_authority": "AEMPS; follows the EU HMPC framework",
        "key_pathways": [
            "Traditional herbal medicinal product registration (EU THMPD)",
            "Food supplement — subject to a national list of plants restricted to pharmacy-only sale",
        ],
        "notes": "Spain restricts a number of botanicals to pharmacy-only sale, which can affect market-entry strategy.",
    },
    "Netherlands": {
        "primary_authority": "CBG-MEB; follows the EU HMPC framework",
        "key_pathways": [
            "Traditional herbal medicinal product registration (EU THMPD)",
            "Food supplement — NVWA oversight",
        ],
        "notes": "The Netherlands has a relatively permissive food-supplement regime within the EU framework.",
    },
    "Poland": {
        "primary_authority": "URPL; follows the EU HMPC framework",
        "key_pathways": [
            "Traditional herbal medicinal product registration (EU THMPD)",
            "Food supplement — notification-based system via the Sanitary Inspectorate (GIS)",
        ],
        "notes": "Poland uses a straightforward notification system for food supplements.",
    },
    "United Kingdom": {
        "primary_authority": "MHRA",
        "key_pathways": [
            "Traditional Herbal Registration (THR) — UK-retained equivalent of the EU THMPD scheme, 30+ years traditional use, 15+ in EU/UK",
            "Food supplement — same general no-disease-claim principle as the EU",
        ],
        "notes": "Post-Brexit, the UK kept its own THR scheme in parallel with (but legally separate from) the EU framework. Most EU HMPC-monograph herbs already have THR-registered UK products.",
    },
    "Switzerland": {
        "primary_authority": "Swissmedic",
        "key_pathways": [
            "Simplified authorisation for complementary/herbal medicines",
            "Food supplement (FSVO/BLV rules) — closely mirrors the EU food-supplement framework",
        ],
        "notes": "Not an EU member, but its herbal/food-supplement rules are closely aligned with the EU framework.",
    },
    "Nordic countries (Sweden, Norway, Denmark, Finland)": {
        "primary_authority": "National medicines agencies (e.g. Läkemedelsverket in Sweden); EU/EEA HMPC framework applies (Norway via the EEA)",
        "key_pathways": [
            "Traditional herbal medicinal product registration (EU/EEA THMPD)",
            "Food supplement — national food agency oversight",
        ],
        "notes": "Some Nordic countries historically classify certain botanicals more strictly as medicines-only; verify per country before market entry.",
    },
    "Iran": {
        "primary_authority": "Iran Food and Drug Administration (FDO), Ministry of Health",
        "key_pathways": [
            "Traditional/herbal medicine registration, recognizing Iranian traditional (Persian) medicine pharmacopoeia",
            "Herbal food supplement registration",
        ],
        "notes": "Iran has a strong domestic Persian-medicine tradition (e.g. saffron, rose, licorice) with an established registration pathway for locally-recognized botanicals.",
    },
    "Middle East / GCC": {
        "primary_authority": "National regulators (e.g. SFDA in Saudi Arabia), generally within the GCC harmonised framework",
        "key_pathways": [
            "Herbal/traditional product registration via the national health authority",
            "Food supplement registration",
        ],
        "notes": "Requirements vary significantly by country; SFDA (Saudi Arabia) tends to be the reference/strictest regulator in the bloc.",
    },
    "Turkey": {
        "primary_authority": "TITCK (Turkish Medicines and Medical Devices Agency)",
        "key_pathways": [
            "Traditional herbal medicinal product registration (aligned with EU THMPD logic)",
            "Food supplement registration",
        ],
        "notes": "Turkey's herbal-medicine framework closely follows the EU traditional-use model.",
    },
    "United States": {
        "primary_authority": "FDA, under DSHEA (Dietary Supplement Health and Education Act, 1994)",
        "key_pathways": [
            "Dietary supplement — no pre-market approval; manufacturer self-affirms safety",
            "New Dietary Ingredient (NDI) notification — required if the ingredient was not marketed in the US before Oct 15, 1994",
            "Structure/function claims allowed with a mandatory disclaimer; disease claims require full drug approval (NDA)",
        ],
        "notes": "Most long-established European/Asian traditional herbs qualify as 'grandfathered' (pre-1994 market history) and don't require NDI notification — but this must be verified per ingredient/form/company.",
    },
    "Canada": {
        "primary_authority": "Health Canada — Natural and Non-prescription Health Products Directorate (NNHPD)",
        "key_pathways": [
            "Natural Health Product (NHP) licence — required for every herbal product, with a product-specific Natural Product Number (NPN)",
        ],
        "notes": "Canada requires pre-market licensing (NPN) for every herbal product, unlike the self-affirmed US DSHEA model — generally the most rigorous pre-market herbal framework in North America.",
    },
    "Brazil / Latin America": {
        "primary_authority": "ANVISA (Brazil) as regional reference; other countries follow national health ministries",
        "key_pathways": [
            "Traditional herbal medicine ('fitoterápico') registration — ANVISA maintains an official list of herbal medicines with simplified registration (RDC 26/2014)",
            "Food supplement registration",
        ],
        "notes": "Brazil's ANVISA list of recognized traditional herbal medicines is one of the more structured frameworks in Latin America; other countries vary widely.",
    },
    "China": {
        "primary_authority": "NMPA (National Medical Products Administration)",
        "key_pathways": [
            "Traditional Chinese Medicine (TCM) registration — requires listing in the Chinese Pharmacopoeia or NMPA-approved TCM standards",
            "Health food (保健食品) registration — for non-disease-claim products",
        ],
        "notes": "Import of finished herbal products faces some of the strictest registration requirements globally. TCM-listed species (e.g. Scutellaria, Ziziphus) have an established pathway; non-TCM Western herbs generally do not.",
    },
    "Japan": {
        "primary_authority": "MHLW / PMDA",
        "key_pathways": [
            "Kampo (traditional Japanese herbal medicine) — listed formulas covered under the Japanese Pharmacopoeia and NHI reimbursement",
            "Foods with Function Claims (FFC) / food supplement — for non-Kampo botanicals without disease claims",
        ],
        "notes": "The Kampo pathway applies mainly to classical multi-herb formulas of Chinese origin; single Western botanicals are usually positioned as food supplements instead.",
    },
    "South Korea": {
        "primary_authority": "MFDS (Ministry of Food and Drug Safety)",
        "key_pathways": [
            "Herbal medicine (Korean Pharmacopoeia-listed) registration",
            "Health Functional Food (HFF) registration — requires an MFDS-recognized functional ingredient",
        ],
        "notes": "HFF registration is the most common route for new-to-market botanicals without an existing pharmacopoeia listing.",
    },
    "India": {
        "primary_authority": "Ministry of AYUSH / CDSCO",
        "key_pathways": [
            "Ayurvedic, Siddha, Unani (ASU) drug licensing — for plants listed in classical Ayurvedic texts / the Ayurvedic Pharmacopoeia",
            "Nutraceutical / food supplement registration (FSSAI)",
        ],
        "notes": "Ayurveda-listed species (e.g. Withania, Curcuma, Bacopa) have an established ASU licensing pathway; non-Ayurvedic Western herbs are usually positioned as FSSAI nutraceuticals.",
    },
    "Southeast Asia (Vietnam / Thailand / Indonesia)": {
        "primary_authority": "National regulators per country (e.g. BPOM in Indonesia, Thai FDA, Vietnam MOH)",
        "key_pathways": [
            "Traditional medicine registration (varies by country)",
            "Food / health supplement registration",
        ],
        "notes": "Highly heterogeneous region — pathways, timelines, and requirements differ substantially by country.",
    },
    "Australia": {
        "primary_authority": "TGA (Therapeutic Goods Administration)",
        "key_pathways": [
            "Listed medicine (AUST L) — lower-risk herbal products with an indication from the TGA's permitted list",
            "Registered medicine (AUST R) — higher-risk or higher-claim products, requires a full evidence dossier",
        ],
        "notes": "The 'Listed' (AUST L) pathway is the standard route for most herbal supplement products in Australia.",
    },
    "New Zealand": {
        "primary_authority": "Ministry of Health (regime under long-term reform via the Therapeutic Products framework)",
        "key_pathways": [
            "Dietary supplement notification",
            "Natural health product framework (in transition)",
        ],
        "notes": "New Zealand's natural-health-product regulation has been under long-term reform; historically lighter-touch than Australia's TGA.",
    },
    "South Africa": {
        "primary_authority": "SAHPRA (South African Health Products Regulatory Authority)",
        "key_pathways": [
            "Complementary medicine registration",
            "Traditional African medicine — a separate, still-emerging regulatory track",
        ],
        "notes": "SAHPRA's complementary medicines framework is still maturing; requirements have evolved significantly in recent years.",
    },
    "Global / Multi-market": {
        "primary_authority": "N/A — multi-market strategy",
        "key_pathways": [
            "Requires a market-by-market regulatory assessment",
        ],
        "notes": "No single global pathway exists; each target market must be assessed individually before a multi-market launch.",
    },
}


# ------------------------------------------------------------------ #
# LEVEL 2 — curated, plant-specific general regulatory category for
# the US and UK markets, for a set of well-established botanicals.
# ------------------------------------------------------------------ #

US_UK_PLANT_REGULATORY_STATUS = {
    "Melissa officinalis": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Valeriana officinalis": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Passiflora incarnata": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Matricaria chamomilla": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC well-established-use monograph)",
    },
    "Lavandula angustifolia": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Humulus lupulus": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Tilia cordata": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "Mostly sold as food supplement; regional traditional-use monograph, not all EU/UK THR-registered",
    },
    "Withania somnifera": {
        "us_status": "Likely grandfathered (long Ayurvedic/US supplement history)",
        "uk_status": "Typically sold as food supplement only (no EU/UK HMPC monograph)",
    },
    "Echinacea purpurea": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Sambucus nigra": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Ginkgo biloba": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist for traditional circulation-support use",
    },
    "Panax ginseng": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "Typically sold as food supplement (limited EU/UK HMPC monograph coverage)",
    },
    "Rhodiola rosea": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "Typically sold as food supplement only (no EU/UK HMPC monograph)",
    },
    "Silybum marianum": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Cynara scolymus": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Hypericum perforatum": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Crocus sativus": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "Typically sold as food supplement only (no EU/UK HMPC monograph)",
    },
    "Curcuma longa": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "Typically sold as food supplement (no dedicated EU/UK HMPC monograph as of last review)",
    },
    "Camellia sinensis": {
        "us_status": "Likely grandfathered (long-standing food/beverage and supplement history)",
        "uk_status": "Typically sold as food supplement / food ingredient",
    },
    "Cinnamomum verum": {
        "us_status": "Likely grandfathered (long-standing food/spice and supplement history)",
        "uk_status": "Typically sold as food supplement / food ingredient",
    },
    "Zingiber officinale": {
        "us_status": "Likely grandfathered (long-standing food/spice and supplement history)",
        "uk_status": "THR-registered products exist for traditional digestive-comfort use",
    },
    "Allium sativum": {
        "us_status": "Likely grandfathered (long-standing food and supplement history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Crataegus monogyna": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Boswellia serrata": {
        "us_status": "Likely grandfathered (long-standing Ayurvedic/US supplement history)",
        "uk_status": "Typically sold as food supplement only (no EU/UK HMPC monograph)",
    },
    "Cimicifuga racemosa": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC well-established-use monograph)",
    },
    "Vitex agnus-castus": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Serenoa repens": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
    "Vaccinium macrocarpon": {
        "us_status": "Likely grandfathered (long-standing food and supplement history)",
        "uk_status": "THR-registered products exist for traditional urinary-comfort use",
    },
    "Vaccinium myrtillus": {
        "us_status": "Likely grandfathered (long pre-1994 US market history)",
        "uk_status": "THR-registered products exist (EU/UK HMPC traditional-use monograph)",
    },
}


def get_market_framework(market):
    return MARKET_REGULATORY_FRAMEWORKS.get(market)


def get_us_uk_status(scientific_name):
    return US_UK_PLANT_REGULATORY_STATUS.get(scientific_name)
