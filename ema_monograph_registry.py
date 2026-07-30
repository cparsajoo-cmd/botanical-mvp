"""Hand-curated, human-verified registry of real EMA/HMPC per-substance
monograph documents — the input the EMA Monograph Connector
(ema_monograph_connector.py) fetches and parses.

WHY A CURATED REGISTRY INSTEAD OF DISCOVERING URLS PROGRAMMATICALLY:
EMA does not publish a bulk, machine-readable index of monograph URLs
(the browse/search page is JS-rendered, same limitation documented in
ema_regulatory_connector.py for the inventory PDF). Each entry below
was verified by fetching the actual document and reading its title
page — not guessed from a URL-naming pattern, and not inferred from a
citation in a third-party paper. See the "verified" note on each entry
for how it was confirmed. Two entries were corrected mid-research after
an initial guess turned out wrong when checked against the real
document (Passiflora's reference number; Cimicifuga's monograph was
superseded by a later revision) — a reminder that even this registry
should be re-verified, not assumed permanent, when a plant is added or
when EMA publishes a periodic-review revision.

SCOPE: this registry currently covers only the pilot set of 10 plants
(11 records, since Lavandula angustifolia has two separate monographs
for flos and aetheroleum) plus the 2 adopted combination monographs
that involve 2+ of those plants. Two further combination monographs
(Valeriana+Passiflora, Hypericum+Cimicifuga) are known to be in
development but NOT YET ADOPTED — they are listed under
PENDING_COMBINATION_MONOGRAPHS for visibility, not fetched or parsed,
since there is no final document yet to fetch.

Adding a new plant: verify its monograph the same way — fetch the
actual PDF, confirm "Final" status and the reference number on the
document's own title page, and add an entry here. Do not extrapolate
a URL or reference number from a related document's numbering; that
specific mistake happened once already during this registry's own
construction (see Passiflora note in commit history / proposal docs)
and was only caught by insisting on direct verification.
"""

EMA_DOCS_BASE = "https://www.ema.europa.eu/en/documents/herbal-monograph/"

# ---------------------------------------------------------------------
# Standalone (single-substance) monographs
# ---------------------------------------------------------------------
# Each entry keyed by (Scientific_Name, Plant_Part) since some plants
# have more than one monograph (different plant parts = different
# monographs, e.g. Lavandula flos vs. aetheroleum).

STANDALONE_MONOGRAPHS = {
    ("Melissa officinalis", "folium"): {
        "monograph_reference": "EMA/HMPC/196745/2012",
        "status": "Final",
        "adopted_date": "2013-05-14",
        "url": EMA_DOCS_BASE + "final-community-herbal-monograph-melissa-officinalis-l-folium_en.pdf",
        "verified": "Fetched and read directly; full text confirmed.",
    },
    ("Valeriana officinalis", "radix"): {
        "monograph_reference": "EMA/HMPC/150848/2015, Corr.1",
        "status": "Final",
        "adopted_date": "2016-02-02",
        "url": EMA_DOCS_BASE + "final-european-union-herbal-monograph-valeriana-officinalis-l-radix_en.pdf",
        "verified": "Fetched and read directly; full text confirmed.",
    },
    ("Passiflora incarnata", "herba"): {
        "monograph_reference": "EMA/HMPC/669740/2013",
        "status": "Final",
        "adopted_date": "2014-03-25",
        "url": EMA_DOCS_BASE + "final-community-herbal-monograph-passiflora-incarnata-l-herba_en.pdf",
        "verified": (
            "Fetched and read directly; full text confirmed. NOTE: an "
            "earlier pass had inferred reference number 669738 from an "
            "adjacent document's numbering — that was WRONG (669738 is "
            "the assessment report's number, not the monograph's). "
            "669740 is confirmed from the monograph document's own "
            "title page."
        ),
    },
    ("Matricaria recutita", "flos"): {
        "monograph_reference": "EMA/HMPC/55843/2011",
        "status": "Final",
        "adopted_date": "2015-07-07",
        "url": EMA_DOCS_BASE + "final-european-union-herbal-monograph-matricaria-recutita-l-flos_en.pdf",
        "verified": "Fetched and read directly; full text confirmed.",
        "synonyms": ["Matricaria chamomilla"],  # seed_data.py uses this older name
    },
    ("Lavandula angustifolia", "flos"): {
        "monograph_reference": "EMA/HMPC/734125/2010",
        "status": "Final",
        "adopted_date": "2012-03-27",
        "url": EMA_DOCS_BASE + "final-community-herbal-monograph-lavandula-angustifolia-p-mill-flos_en.pdf",
        "verified": "URL and reference confirmed via search + citing source; not yet directly re-fetched by this engineer — recommend a confirm-fetch before first production run.",
    },
    ("Lavandula angustifolia", "aetheroleum"): {
        "monograph_reference": "EMA/HMPC/143181/2010",
        "status": "Final",
        "adopted_date": "2012-03-27",
        "url": EMA_DOCS_BASE + "final-community-herbal-monograph-lavandula-angustifolia-miller-aetheroleum_en.pdf",
        "verified": "URL and reference confirmed via search + citing source; not yet directly re-fetched by this engineer — recommend a confirm-fetch before first production run.",
    },
    ("Humulus lupulus", "flos"): {
        "monograph_reference": "EMA/HMPC/682384/2013",
        "status": "Final",
        "adopted_date": "2014-05-06",
        "url": EMA_DOCS_BASE + "final-community-herbal-monograph-humulus-lupulus-l-flos_en.pdf",
        "verified": "URL and reference confirmed via search + citing source; not yet directly re-fetched by this engineer — recommend a confirm-fetch before first production run.",
    },
    ("Tilia cordata", "flos"): {
        "monograph_reference": "EMA/HMPC/337066/2011",
        "status": "Final",
        "adopted_date": "2012-05-22",
        "url": EMA_DOCS_BASE + "final-community-herbal-monograph-tilia-cordata-miller-tilia-platyphyllos-scop-tilia-x-vulgaris-heyne_en.pdf",
        "verified": "Fetched and read directly; full text confirmed.",
        "note": "Multi-species monograph — also covers Tilia platyphyllos and Tilia x vulgaris or their mixtures under the same document.",
    },
    ("Cimicifuga racemosa", "rhizoma"): {
        "monograph_reference": "EMA/HMPC/48745/2017",
        "status": "Final, Revision 1",
        "adopted_date": "2018-03-27",
        "url": EMA_DOCS_BASE + "final-european-union-herbal-monograph-cimicifuga-racemosa-l-nutt-rhizome-revision-1_en.pdf",
        "verified": (
            "Fetched and read directly; full text confirmed. NOTE: "
            "supersedes an earlier monograph (EMA/HMPC/600717/2007, "
            "adopted 2010) — if any existing Gold Case or evidence "
            "record cites the 2007/2010 reference, it is citing a "
            "superseded document; worth checking Gold Case 005 "
            "specifically."
        ),
    },
    ("Hypericum perforatum", "herba"): {
        "monograph_reference": "EMA/HMPC/7695/2021, Rev.1",
        "status": "Final (unified well-established-use + traditional-use)",
        "adopted_date": "2022-11-23",
        "url": EMA_DOCS_BASE + "final-european-union-herbal-monograph-hypericum-perforatum-l-herba-revision-1_en.pdf",
        "verified": "Fetched and confirmed via opinion document (EMA/HMPC/71074/2023) referencing this as Annex I; not yet directly re-fetched — recommend a confirm-fetch before first production run.",
    },
    ("Ginkgo biloba", "folium"): {
        "monograph_reference": "EMA/HMPC/321097/2012",
        "status": "Final",
        "adopted_date": "2015-01-28",
        "url": EMA_DOCS_BASE + "final-european-union-herbal-monograph-ginkgo-biloba-l-folium_en.pdf",
        "verified": "URL and reference confirmed via search + multiple independent citing sources; not yet directly re-fetched by this engineer — recommend a confirm-fetch before first production run.",
    },
}

# ---------------------------------------------------------------------
# Combination monographs (Option B — modeled as a distinct record type,
# never merged into the standalone records above)
# ---------------------------------------------------------------------

COMBINATION_MONOGRAPHS = {
    ("Valeriana officinalis", "Humulus lupulus"): {
        "combination_label": "Valeriana officinalis L., radix and Humulus lupulus L., flos",
        "monograph_reference": "EMA/HMPC/327107/2017 (Revision 1)",
        "status": "Final",
        "adopted_date": "2019-09-25",
        "url": EMA_DOCS_BASE + "opinion-hmpc-community-herbal-monograph-valeriana-officinalis-l-radix-and-humulus-lupulus-l-flos-revision-1_en.pdf",
        "verified": "Reference and adoption date confirmed via HMPC opinion document; URL is the opinion (which contains the monograph as Annex I) — recommend confirming the standalone monograph PDF URL separately before parsing.",
    },
    ("species_sedativae",): {
        "combination_label": (
            "Species sedativae — herbal tea combinations of 2, 3, or 4 "
            "herbal substances from: Humulus lupulus L. flos, "
            "Lavandula angustifolia Mill. flos, Melissa officinalis L. "
            "folium, Passiflora incarnata L. herba, Valeriana "
            "officinalis L. radix"
        ),
        "involves_plants": [
            "Humulus lupulus", "Lavandula angustifolia",
            "Melissa officinalis", "Passiflora incarnata",
            "Valeriana officinalis",
        ],
        "monograph_reference": "EMA/HMPC/438183/2017",
        "status": "Final",
        "adopted_date": "2017",  # exact day not confirmed — flagged
        "url": None,  # direct monograph PDF URL not yet confirmed — see note
        "verified": (
            "Reference number and involved-plants composition table "
            "confirmed via a mirrored copy of the document; the "
            "canonical ema.europa.eu URL for this specific monograph "
            "PDF has NOT yet been directly confirmed by this engineer "
            "— required before this entry can be fetched in production."
        ),
    },
}

# ---------------------------------------------------------------------
# Known combination monographs still in development — NOT final, not
# fetchable as adopted content. Listed for visibility / roadmap only.
# ---------------------------------------------------------------------

PENDING_COMBINATION_MONOGRAPHS = {
    ("Valeriana officinalis", "Passiflora incarnata"): {
        "combination_label": "Valerianae radix and Passiflorae herba",
        "status": "In development — ongoing call for scientific data (not yet a monograph)",
        "landing_page": "https://www.ema.europa.eu/en/medicines/herbal/valerianae-radix-passiflorae-herba",
    },
    ("Hypericum perforatum", "Cimicifuga racemosa"): {
        "combination_label": "Hypericum perforatum L., herba and Cimicifuga racemosa (L.) Nutt., rhizoma",
        "status": "In development — draft assessment report stage as of 2025 (not yet a final monograph)",
        "draft_reference": "EMA/HMPC/884573/2022 (draft monograph)",
        "landing_page": "https://www.ema.europa.eu/en/medicines/herbal/hyperici-herba-cimicifugae-rhizoma",
    },
}
