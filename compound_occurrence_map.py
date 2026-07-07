"""
Curated compound -> plant occurrence knowledge base.

This is NOT clinical evidence. It is a fast, offline cross-reference used by
BotanicalRDCandidateEngine to seed the search for alternative botanical
sources of a given active compound, before/alongside live literature search.
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
