"""
Curated compound -> plant occurrence knowledge base.

This is NOT clinical evidence. It is a fast, offline cross-reference used by
BotanicalRDCandidateEngine to seed the search for alternative botanical
sources of a given active compound, before/alongside live literature search.

Single source of truth: previously duplicated between
botanical_brain_engine.COMPOUND_PLANT_MAP and
target_knowledge_base.COMPOUND_PLANT_MAP. Both files are removed; this is
the merged, deduplicated replacement.
"""

COMPOUND_PLANT_MAP = {
    "huperzine a": ["Huperzia serrata"],
    "galantamine": ["Galanthus nivalis", "Leucojum aestivum", "Narcissus pseudonarcissus"],
    "berberine": ["Berberis vulgaris", "Coptis chinensis", "Hydrastis canadensis"],
    "rosmarinic acid": ["Melissa officinalis", "Rosmarinus officinalis", "Salvia officinalis", "Perilla frutescens", "Ocimum basilicum"],
    "apigenin": ["Matricaria chamomilla", "Passiflora incarnata", "Petroselinum crispum", "Apium graveolens"],
    "luteolin": ["Salvia officinalis", "Perilla frutescens", "Apium graveolens", "Thymus vulgaris"],
    "quercetin": ["Sophora japonica", "Allium cepa", "Camellia sinensis", "Ginkgo biloba"],
    "curcumin": ["Curcuma longa"],
    "boswellic acid": ["Boswellia serrata", "Boswellia sacra"],
    "boswellic acids": ["Boswellia serrata", "Boswellia sacra"],
    "withanolides": ["Withania somnifera"],
    "valerenic acid": ["Valeriana officinalis"],
    "linalool": ["Lavandula angustifolia", "Ocimum basilicum", "Coriandrum sativum"],
    "chrysin": ["Passiflora incarnata"],
    "honokiol": ["Magnolia officinalis"],
    "magnolol": ["Magnolia officinalis"],
    "capsaicin": ["Capsicum annuum", "Capsicum frutescens"],
    "gingerol": ["Zingiber officinale"],
    "gingerols": ["Zingiber officinale"],
    "resveratrol": ["Polygonum cuspidatum", "Vitis vinifera"],
    "caffeic acid": ["Coffea arabica", "Rosmarinus officinalis", "Salvia officinalis"],
    "chlorogenic acid": ["Coffea arabica", "Lonicera japonica", "Cynara scolymus"],
    "silymarin": ["Silybum marianum"],
    "silybin": ["Silybum marianum"],
    "rutin": ["Sophora japonica", "Fagopyrum esculentum"],
    "hyperforin": ["Hypericum perforatum"],
    "hypericin": ["Hypericum perforatum"],
    "ginkgolide": ["Ginkgo biloba"],
    "bilobalide": ["Ginkgo biloba"],
    "oleuropein": ["Olea europaea"],
    "carnosic acid": ["Rosmarinus officinalis", "Salvia officinalis"],
    "carnosol": ["Rosmarinus officinalis", "Salvia officinalis"],
    "thymol": ["Thymus vulgaris", "Origanum vulgare"],
    "carvacrol": ["Origanum vulgare", "Thymus vulgaris"],
    "menthol": ["Mentha piperita"],
    "eugenol": ["Syzygium aromaticum", "Ocimum gratissimum"],
    "allicin": ["Allium sativum"],
    "sennoside": ["Senna alexandrina"],
    "sennosides": ["Senna alexandrina"],
    "glycyrrhizin": ["Glycyrrhiza glabra"],
    "glycyrrhetinic acid": ["Glycyrrhiza glabra"],
    "baicalin": ["Scutellaria baicalensis"],
    "baicalein": ["Scutellaria baicalensis"],
    "wogonin": ["Scutellaria baicalensis"],
    "ellagic acid": ["Punica granatum", "Rubus idaeus"],
    "punicalagin": ["Punica granatum"],
    "catechin": ["Camellia sinensis"],
    "epigallocatechin gallate": ["Camellia sinensis"],
    "egcg": ["Camellia sinensis"],
    "vitexin": ["Passiflora incarnata", "Crataegus monogyna"],
    "isovitexin": ["Passiflora incarnata"],
    "bisabolol": ["Matricaria chamomilla"],
    "xanthohumol": ["Humulus lupulus"],
    "kavalactones": ["Piper methysticum"],
    "bacosides": ["Bacopa monnieri"],
    "ginsenosides": ["Panax ginseng"],
    "salidroside": ["Rhodiola rosea"],
    "crocin": ["Crocus sativus"],
    "safranal": ["Crocus sativus"],
    "asiaticoside": ["Centella asiatica"],
    "madecassoside": ["Centella asiatica"],
}


def get_alternative_plants(compound: str):
    """Return curated candidate plants known to contain `compound`."""
    if not compound:
        return []
    return COMPOUND_PLANT_MAP.get(compound.strip().lower(), [])


# Region/origin for plants that appear as alternative candidates but are NOT
# in seed_data.PLANTS (which already carries region for the 48 seed plants).
# Used only to answer "does another region/country have the same compound?".
REGION_FALLBACK_MAP = {
    "Allium cepa": "Central Asia",
    "Apium graveolens": "Mediterranean",
    "Boswellia sacra": "Middle East / Horn of Africa",
    "Boswellia serrata": "South Asia",
    "Capsicum annuum": "Latin America",
    "Capsicum frutescens": "Latin America",
    "Coffea arabica": "East Africa / Latin America",
    "Coptis chinensis": "China",
    "Crataegus monogyna": "Europe",
    "Fagopyrum esculentum": "East Asia",
    "Galanthus nivalis": "Europe",
    "Huperzia serrata": "China",
    "Hydrastis canadensis": "North America",
    "Leucojum aestivum": "Europe",
    "Lonicera japonica": "China",
    "Magnolia officinalis": "China",
    "Narcissus pseudonarcissus": "Europe",
    "Ocimum gratissimum": "Africa / South Asia",
    "Olea europaea": "Mediterranean",
    "Origanum vulgare": "Mediterranean",
    "Perilla frutescens": "China / South Asia",
    "Petroselinum crispum": "Mediterranean",
    "Polygonum cuspidatum": "China",
    "Punica granatum": "Middle East / Iran",
    "Rosmarinus officinalis": "Mediterranean",
    "Rubus idaeus": "Europe",
    "Senna alexandrina": "Middle East / Africa",
    "Sophora japonica": "China",
    "Syzygium aromaticum": "South Asia",
    "Vitis vinifera": "Mediterranean / Iran",
}


def get_region(plant_name: str):
    """Region/origin for a plant, checking seed_data first, then the
    fallback map above. Returns 'Region not catalogued' if unknown."""
    from seed_data import PLANTS as _SEED_PLANTS
    for sci_name, _common, _family, region, _part in _SEED_PLANTS:
        if sci_name.strip().lower() == plant_name.strip().lower():
            return region
    for name, region in REGION_FALLBACK_MAP.items():
        if name.strip().lower() == plant_name.strip().lower():
            return region
    return "Region not catalogued"
