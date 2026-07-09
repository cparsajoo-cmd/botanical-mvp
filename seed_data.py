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

    ("Scutellaria baicalensis", "Baikal skullcap", "Lamiaceae", "East Asia", "Root"),
    ("Gynostemma pentaphyllum", "Jiaogulan", "Cucurbitaceae", "East Asia", "Aerial parts"),
    ("Piper methysticum", "Kava", "Piperaceae", "Pacific Islands", "Root/rhizome"),
    ("Centella asiatica", "Gotu kola", "Apiaceae", "South Asia", "Aerial parts"),
    ("Bacopa monnieri", "Bacopa", "Plantaginaceae", "South Asia", "Aerial parts"),
    ("Ginkgo biloba", "Ginkgo", "Ginkgoaceae", "East Asia", "Leaf"),
    ("Panax ginseng", "Asian ginseng", "Araliaceae", "East Asia", "Root"),
    ("Rhodiola rosea", "Rhodiola", "Crassulaceae", "Northern Europe / Asia", "Root/rhizome"),
    ("Crocus sativus", "Saffron", "Iridaceae", "Iran / Mediterranean", "Stigma"),
    ("Hypericum perforatum", "St John's wort", "Hypericaceae", "Europe", "Flowering tops"),

    ("Nigella sativa", "Black seed", "Ranunculaceae", "Middle East / Iran", "Seed"),
    ("Althaea officinalis", "Marshmallow", "Malvaceae", "Europe / Western Asia", "Root/leaf"),
    ("Thymus vulgaris", "Thyme", "Lamiaceae", "Mediterranean", "Leaf/flowering tops"),
    ("Salvia officinalis", "Sage", "Lamiaceae", "Mediterranean", "Leaf"),
    ("Glycyrrhiza glabra", "Licorice", "Fabaceae", "Middle East / Europe", "Root"),
    ("Plantago lanceolata", "Ribwort plantain", "Plantaginaceae", "Europe", "Leaf"),

    ("Echinacea purpurea", "Purple coneflower", "Asteraceae", "North America", "Root/aerial parts"),
    ("Sambucus nigra", "Elder", "Adoxaceae", "Europe", "Flower/fruit"),
    ("Urtica dioica", "Nettle", "Urticaceae", "Europe / Asia", "Leaf/root"),
    ("Silybum marianum", "Milk thistle", "Asteraceae", "Mediterranean", "Fruit"),
    ("Cynara scolymus", "Artichoke", "Asteraceae", "Mediterranean", "Leaf"),
    ("Taraxacum officinale", "Dandelion", "Asteraceae", "Europe / Asia", "Root/leaf"),

    ("Camellia sinensis", "Green tea", "Theaceae", "East Asia", "Leaf"),
    ("Berberis vulgaris", "Barberry", "Berberidaceae", "Iran / Europe", "Root bark/fruit"),
    ("Cinnamomum verum", "Ceylon cinnamon", "Lauraceae", "South Asia", "Bark"),
    ("Zingiber officinale", "Ginger", "Zingiberaceae", "South Asia", "Rhizome"),
    ("Allium sativum", "Garlic", "Amaryllidaceae", "Central Asia", "Bulb"),
    ("Vaccinium myrtillus", "Bilberry", "Ericaceae", "Europe", "Fruit/leaf"),

    ("Rosa damascena", "Damask rose", "Rosaceae", "Iran / Middle East", "Petal"),
    ("Coriandrum sativum", "Coriander", "Apiaceae", "Mediterranean / Middle East", "Fruit/leaf"),
    ("Carum carvi", "Caraway", "Apiaceae", "Europe / Western Asia", "Fruit"),
    ("Trigonella foenum-graecum", "Fenugreek", "Fabaceae", "Middle East / South Asia", "Seed"),
    ("Ocimum basilicum", "Basil", "Lamiaceae", "Mediterranean / Asia", "Leaf"),
    ("Moringa oleifera", "Moringa", "Moringaceae", "South Asia / Africa", "Leaf/seed"),

    ("Crataegus monogyna", "Hawthorn", "Rosaceae", "Europe", "Flower/leaf/berry"),
    ("Boswellia serrata", "Frankincense", "Burseraceae", "South Asia / Middle East", "Resin"),
    ("Cimicifuga racemosa", "Black cohosh", "Ranunculaceae", "North America", "Root/rhizome"),
    ("Vitex agnus-castus", "Chaste tree", "Lamiaceae", "Mediterranean", "Fruit"),
    ("Serenoa repens", "Saw palmetto", "Arecaceae", "North America", "Fruit"),
    ("Vaccinium macrocarpon", "Cranberry", "Ericaceae", "North America", "Fruit"),
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
        ("Humulone", "Bitter acid", "CO2 extract"),
        ("Lupulone", "Bitter acid", "CO2 extract"),
    ],
    "Tilia cordata": [
        ("Tiliroside", "Flavonoid glycoside", "Infusion / aqueous extract"),
        ("Quercetin", "Flavonoid", "Infusion"),
        ("Kaempferol", "Flavonoid", "Infusion"),
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
        ("Turmerones", "Sesquiterpenes", "Essential oil / extract"),
    ],
    "Foeniculum vulgare": [
        ("Anethole", "Phenylpropene", "Essential oil / infusion"),
        ("Fenchone", "Monoterpene ketone", "Essential oil"),
    ],
    "Withania somnifera": [
        ("Withanolides", "Steroidal lactone", "Hydroalcoholic extract / standardized extract"),
        ("Withaferin A", "Steroidal lactone", "Hydroalcoholic extract"),
    ],
    "Ziziphus jujuba": [
        ("Jujubosides", "Saponin", "Aqueous / ethanolic extract"),
        ("Spinosin", "Flavonoid glycoside", "Aqueous / ethanolic extract"),
    ],

    "Scutellaria baicalensis": [
        ("Baicalin", "Flavonoid glycoside", "Aqueous / ethanolic extract"),
        ("Baicalein", "Flavonoid", "Ethanolic extract"),
        ("Wogonin", "Flavonoid", "Ethanolic extract"),
    ],
    "Gynostemma pentaphyllum": [
        ("Gypenosides", "Saponins", "Aqueous / ethanolic extract"),
        ("Quercetin", "Flavonoid", "Aqueous extract"),
    ],
    "Piper methysticum": [
        ("Kavalactones", "Lactones", "Aqueous / organic solvent extract"),
        ("Kavain", "Kavalactone", "Organic solvent extract"),
        ("Yangonin", "Kavalactone", "Organic solvent extract"),
    ],
    "Centella asiatica": [
        ("Asiaticoside", "Triterpenoid saponin", "Hydroalcoholic extract"),
        ("Madecassoside", "Triterpenoid saponin", "Hydroalcoholic extract"),
    ],
    "Bacopa monnieri": [
        ("Bacosides", "Triterpenoid saponins", "Hydroalcoholic extract"),
    ],
    "Ginkgo biloba": [
        ("Ginkgolides", "Terpene lactones", "Standardized extract"),
        ("Bilobalide", "Sesquiterpene lactone", "Standardized extract"),
        ("Quercetin", "Flavonoid", "Standardized extract"),
    ],
    "Panax ginseng": [
        ("Ginsenosides", "Triterpenoid saponins", "Standardized extract"),
    ],
    "Rhodiola rosea": [
        ("Rosavins", "Phenylpropanoids", "Hydroalcoholic extract"),
        ("Salidroside", "Phenylethanoid glycoside", "Hydroalcoholic extract"),
    ],
    "Crocus sativus": [
        ("Crocin", "Carotenoid glycoside", "Aqueous extract"),
        ("Safranal", "Monoterpene aldehyde", "Aqueous / volatile fraction"),
    ],
    "Hypericum perforatum": [
        ("Hypericin", "Naphthodianthrone", "Hydroalcoholic extract"),
        ("Hyperforin", "Phloroglucinol", "Hydroalcoholic extract"),
    ],

    "Nigella sativa": [
        ("Thymoquinone", "Quinone", "Fixed oil / seed extract"),
    ],
    "Althaea officinalis": [
        ("Mucilage", "Polysaccharides", "Aqueous extract / infusion"),
    ],
    "Thymus vulgaris": [
        ("Thymol", "Phenolic monoterpene", "Essential oil / infusion"),
        ("Carvacrol", "Phenolic monoterpene", "Essential oil"),
    ],
    "Salvia officinalis": [
        ("Rosmarinic acid", "Phenolic acid", "Infusion / hydroalcoholic extract"),
        ("Thujone", "Monoterpene ketone", "Essential oil"),
    ],
    "Glycyrrhiza glabra": [
        ("Glycyrrhizin", "Triterpenoid saponin", "Aqueous extract"),
    ],
    "Plantago lanceolata": [
        ("Aucubin", "Iridoid glycoside", "Aqueous extract"),
        ("Mucilage", "Polysaccharides", "Infusion"),
    ],
    "Echinacea purpurea": [
        ("Cichoric acid", "Phenolic acid", "Hydroalcoholic extract"),
        ("Alkamides", "Fatty acid amides", "Hydroalcoholic extract"),
    ],
    "Sambucus nigra": [
        ("Anthocyanins", "Flavonoids", "Aqueous extract"),
        ("Rutin", "Flavonoid glycoside", "Aqueous extract"),
    ],
    "Urtica dioica": [
        ("Chlorogenic acid", "Phenolic acid", "Aqueous extract"),
        ("Lignans", "Polyphenols", "Hydroalcoholic extract"),
    ],
    "Silybum marianum": [
        ("Silymarin", "Flavonolignan complex", "Standardized extract"),
        ("Silibinin", "Flavonolignan", "Standardized extract"),
    ],
    "Cynara scolymus": [
        ("Cynarin", "Caffeoylquinic acid", "Aqueous / hydroalcoholic extract"),
        ("Chlorogenic acid", "Phenolic acid", "Aqueous extract"),
    ],
    "Taraxacum officinale": [
        ("Taraxasterol", "Triterpene", "Hydroalcoholic extract"),
        ("Inulin", "Polysaccharide", "Aqueous extract"),
    ],

    "Camellia sinensis": [
        ("EGCG", "Catechin", "Aqueous extract / infusion"),
        ("Caffeine", "Methylxanthine", "Aqueous extract"),
    ],
    "Berberis vulgaris": [
        ("Berberine", "Isoquinoline alkaloid", "Hydroalcoholic extract"),
    ],
    "Cinnamomum verum": [
        ("Cinnamaldehyde", "Phenylpropanoid aldehyde", "Essential oil / aqueous extract"),
    ],
    "Zingiber officinale": [
        ("Gingerols", "Phenolic ketones", "Ethanolic extract"),
        ("Shogaols", "Phenolic ketones", "Ethanolic extract"),
    ],
    "Allium sativum": [
        ("Allicin", "Organosulfur compound", "Fresh extract"),
    ],
    "Vaccinium myrtillus": [
        ("Anthocyanins", "Flavonoids", "Aqueous extract"),
    ],
    "Rosa damascena": [
        ("Citronellol", "Monoterpene alcohol", "Steam distillation"),
        ("Geraniol", "Monoterpene alcohol", "Steam distillation"),
    ],
    "Coriandrum sativum": [
        ("Linalool", "Monoterpene alcohol", "Essential oil"),
    ],
    "Carum carvi": [
        ("Carvone", "Monoterpene ketone", "Essential oil"),
    ],
    "Trigonella foenum-graecum": [
        ("Diosgenin", "Steroidal sapogenin", "Hydroalcoholic extract"),
        ("4-hydroxyisoleucine", "Amino acid derivative", "Aqueous extract"),
    ],
    "Ocimum basilicum": [
        ("Linalool", "Monoterpene alcohol", "Essential oil"),
        ("Eugenol", "Phenylpropanoid", "Essential oil"),
    ],
    "Moringa oleifera": [
        ("Isothiocyanates", "Sulfur compounds", "Aqueous / ethanolic extract"),
        ("Quercetin", "Flavonoid", "Aqueous extract"),
    ],
    "Crataegus monogyna": [
        ("Hyperoside", "Flavonoid glycoside", "Hydroalcoholic extract"),
        ("Procyanidins", "Oligomeric flavonoid", "Hydroalcoholic extract"),
        ("Vitexin", "Flavonoid", "Hydroalcoholic extract"),
    ],
    "Boswellia serrata": [
        ("Boswellic acids", "Triterpenic acid", "Resin extract / hydroalcoholic extract"),
    ],
    "Cimicifuga racemosa": [
        ("Triterpene glycosides", "Triterpenoid saponin", "Hydroalcoholic extract"),
    ],
    "Vitex agnus-castus": [
        ("Agnuside", "Iridoid glycoside", "Hydroalcoholic extract"),
    ],
    "Serenoa repens": [
        ("Fatty acid sterols", "Fatty acid / phytosterol", "Lipophilic (CO2 or hexane) extract"),
    ],
    "Vaccinium macrocarpon": [
        ("Proanthocyanidins", "Oligomeric flavonoid", "Aqueous / hydroalcoholic extract"),
    ],
}

COMPOUND_TARGETS = {
    "Rosmarinic acid": ["GABAergic system", "COX-2", "NF-kB", "Nrf2", "Acetylcholinesterase"],
    "Citral": ["GABAergic system", "TRP channels"],
    "Caffeic acid": ["Antioxidant pathways", "NF-kB"],
    "Luteolin": ["NF-kB", "COX-2", "IL-6", "TNF-alpha", "Histamine H1 receptor", "Mast cell stabilization"],
    "Apigenin": ["Benzodiazepine receptor", "GABA-A receptor", "COX-2"],
    "Valerenic acid": ["GABA-A receptor"],
    "Valepotriates": ["GABAergic system"],
    "Bornyl acetate": ["GABAergic system"],
    "Vitexin": ["GABAergic system", "Oxidative stress pathways"],
    "Isovitexin": ["Oxidative stress pathways"],
    "Chrysin": ["Benzodiazepine receptor", "GABA-A receptor"],
    "Bisabolol": ["COX-2", "Anti-inflammatory pathways"],
    "Linalool": ["GABAergic system", "Glutamate system", "Calcium channels"],
    "Linalyl acetate": ["GABAergic system", "Autonomic nervous system"],
    "Xanthohumol": ["NF-kB", "Nrf2", "Estrogen receptors"],
    "Humulone": ["Anti-inflammatory pathways"],
    "Lupulone": ["Anti-inflammatory pathways"],
    "Tiliroside": ["Anti-inflammatory pathways"],
    "Quercetin": ["Anti-inflammatory pathways", "Oxidative stress pathways", "Histamine H1 receptor", "Mast cell stabilization"],
    "Kaempferol": ["Anti-inflammatory pathways"],
    "Verbascoside": ["Antioxidant pathways"],
    "Californidine": ["GABAergic system"],
    "Protopine": ["GABAergic system"],
    "Menthol": ["TRPM8", "Calcium channels"],
    "Menthone": ["TRPM8"],
    "Curcumin": ["NF-kB", "COX-2", "Nrf2", "AMPK", "Acetylcholinesterase"],
    "Turmerones": ["Anti-inflammatory pathways"],
    "Anethole": ["Smooth muscle relaxation"],
    "Fenchone": ["Smooth muscle relaxation"],
    "Withanolides": ["HPA axis", "GABAergic system", "NF-kB"],
    "Withaferin A": ["NF-kB", "Anti-inflammatory pathways"],
    "Jujubosides": ["GABAergic system", "Serotonergic system"],
    "Spinosin": ["GABAergic system", "Serotonergic system"],

    "Baicalin": ["GABAergic system", "NF-kB", "COX-2"],
    "Baicalein": ["GABAergic system", "NF-kB", "Oxidative stress pathways"],
    "Wogonin": ["GABA-A receptor", "NF-kB"],
    "Gypenosides": ["AMPK", "Anti-inflammatory pathways", "Oxidative stress pathways"],
    "Kavalactones": ["GABAergic system", "Sodium channels", "Monoamine oxidase"],
    "Kavain": ["GABAergic system"],
    "Yangonin": ["CB1 receptor", "GABAergic system"],
    "Asiaticoside": ["Collagen synthesis", "Anti-inflammatory pathways", "Amyloid-beta aggregation"],
    "Madecassoside": ["Collagen synthesis", "NF-kB"],
    "Bacosides": ["Cholinergic system", "Antioxidant pathways"],
    "Ginkgolides": ["Platelet activating factor", "Neurovascular pathways"],
    "Bilobalide": ["Neuroprotective pathways"],
    "Ginsenosides": ["HPA axis", "AMPK", "Immune modulation"],
    "Rosavins": ["HPA axis", "Monoamine system"],
    "Salidroside": ["HPA axis", "Nrf2", "Anti-fatigue pathways"],
    "Crocin": ["Serotonergic system", "Antioxidant pathways"],
    "Safranal": ["GABAergic system", "Serotonergic system"],
    "Hypericin": ["Monoamine system"],
    "Hyperforin": ["Monoamine reuptake modulation"],

    "Thymoquinone": ["NF-kB", "Nrf2", "Anti-inflammatory pathways"],
    "Mucilage": ["Demulcent effect", "Mucosal protection", "Bulk laxative effect", "Salivary/oral mucosa protection"],
    "Thymol": ["Antimicrobial pathways", "Smooth muscle relaxation", "Expectorant pathways"],
    "Carvacrol": ["Antimicrobial pathways", "Anti-inflammatory pathways", "Expectorant pathways"],
    "Thujone": ["GABA-A receptor"],
    "Glycyrrhizin": ["Anti-inflammatory pathways", "Cortisol metabolism", "Expectorant pathways"],
    "Aucubin": ["Anti-inflammatory pathways"],
    "Cichoric acid": ["Immune modulation"],
    "Alkamides": ["CB2 receptor", "Immune modulation"],
    "Anthocyanins": ["Antioxidant pathways", "Microvascular pathways"],
    "Rutin": ["Antioxidant pathways"],
    "Chlorogenic acid": ["AMPK", "Antioxidant pathways"],
    "Lignans": ["Hormonal pathways"],
    "Silymarin": ["Hepatoprotective pathways", "Nrf2"],
    "Silibinin": ["Hepatoprotective pathways", "Nrf2"],
    "Cynarin": ["Bile flow", "Digestive support"],
    "Taraxasterol": ["Anti-inflammatory pathways"],
    "Inulin": ["Prebiotic effect", "Gut microbiota"],

    "EGCG": ["AMPK", "Antioxidant pathways", "Anti-inflammatory pathways"],
    "Caffeine": ["Adenosine receptor"],
    "Berberine": ["AMPK", "PPAR-gamma", "Gut microbiota", "Acetylcholinesterase"],
    "Cinnamaldehyde": ["Insulin signaling", "Anti-inflammatory pathways"],
    "Gingerols": ["COX-2", "TRPV1", "Anti-inflammatory pathways"],
    "Shogaols": ["TRPV1", "Anti-inflammatory pathways"],
    "Allicin": ["Cardiometabolic pathways"],
    "Citronellol": ["GABAergic system"],
    "Geraniol": ["GABAergic system", "Anti-inflammatory pathways"],
    "Carvone": ["Smooth muscle relaxation"],
    "Diosgenin": ["Metabolic pathways"],
    "4-hydroxyisoleucine": ["Insulin secretion"],
    "Eugenol": ["Anti-inflammatory pathways"],
    "Isothiocyanates": ["Nrf2", "Detoxification pathways"],

    "Hyperoside": ["Microvascular pathways", "Cardiometabolic pathways"],
    "Procyanidins": ["Microvascular pathways", "Cardiometabolic pathways", "Antioxidant pathways"],
    "Boswellic acids": ["Anti-inflammatory pathways", "COX-2"],
    "Triterpene glycosides": ["Hormonal pathways", "Serotonergic system"],
    "Agnuside": ["Hormonal pathways", "Dopaminergic system"],
    "Fatty acid sterols": ["Hormonal pathways", "Anti-inflammatory pathways"],
    "Proanthocyanidins": ["Antimicrobial pathways", "Microvascular pathways"],
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
        "Adenosine receptor": "probable",
    },
    "Anxiety": {
        "GABA-A receptor": "established",
        "GABAergic system": "established",
        "Benzodiazepine receptor": "established",
        "HPA axis": "established",
        "Serotonergic system": "established",
        "Monoamine system": "probable",
    },
    "Digestive discomfort": {
        "Smooth muscle relaxation": "established",
        "TRPM8": "probable",
        "Anti-inflammatory pathways": "probable",
        "Mucosal protection": "probable",
        "Bile flow": "probable",
        "Gut microbiota": "probable",
    },
    "Skin inflammation": {
        "NF-kB": "established",
        "COX-2": "established",
        "TNF-alpha": "probable",
        "IL-6": "probable",
        "Collagen synthesis": "probable",
        "Anti-inflammatory pathways": "established",
    },
    "Cognitive support": {
        "Cholinergic system": "established",
        "Neuroprotective pathways": "probable",
        "Neurovascular pathways": "probable",
        "Oxidative stress pathways": "probable",
        "Antioxidant pathways": "probable",
    },
    "Anti-inflammatory": {
        "NF-kB": "established",
        "COX-2": "established",
        "Nrf2": "probable",
        "TNF-alpha": "probable",
        "IL-6": "probable",
        "Anti-inflammatory pathways": "established",
    },
    "Metabolic health": {
        "AMPK": "established",
        "PPAR-gamma": "probable",
        "Insulin signaling": "probable",
        "Insulin secretion": "probable",
        "Gut microbiota": "probable",
    },

    # --- Aliases / additions so every option in step_inputs.py's
    # "Target indication" dropdown has direct, non-fuzzy coverage. ---

    "Sleep and relaxation": {
        "GABA-A receptor": "established",
        "GABAergic system": "established",
        "Benzodiazepine receptor": "established",
        "HPA axis": "probable",
        "Serotonergic system": "probable",
        "Autonomic nervous system": "probable",
        "Glutamate system": "probable",
        "Adenosine receptor": "probable",
    },
    "Stress": {
        "HPA axis": "established",
        "Cortisol metabolism": "established",
        "GABAergic system": "probable",
        "Monoamine system": "probable",
        "Anti-fatigue pathways": "probable",
    },
    "Inflammation": {
        "NF-kB": "established",
        "COX-2": "established",
        "Nrf2": "probable",
        "TNF-alpha": "probable",
        "IL-6": "probable",
        "Anti-inflammatory pathways": "established",
    },
    "Constipation": {
        "Bulk laxative effect": "established",
        "Gut microbiota": "probable",
        "Prebiotic effect": "probable",
        "Smooth muscle relaxation": "theoretical",
    },
    "Cough": {
        "Expectorant pathways": "established",
        "Demulcent effect": "established",
        "Mucosal protection": "probable",
        "Antimicrobial pathways": "probable",
    },
    "Digestive comfort": {
        "Smooth muscle relaxation": "established",
        "Bile flow": "probable",
        "Digestive support": "probable",
        "Gut microbiota": "probable",
        "Mucosal protection": "probable",
    },
    "Dry mouth": {
        "Salivary/oral mucosa protection": "established",
        "Demulcent effect": "established",
        "Mucosal protection": "probable",
    },
    "Allergic rhinitis": {
        "Histamine H1 receptor": "established",
        "Mast cell stabilization": "established",
        "Anti-inflammatory pathways": "probable",
    },
    "IBS": {
        "Gut microbiota": "established",
        "Smooth muscle relaxation": "established",
        "Prebiotic effect": "probable",
        "Serotonergic system": "probable",
        "Digestive support": "probable",
    },
    "Wound healing": {
        "Collagen synthesis": "established",
        "Anti-inflammatory pathways": "probable",
        "Antimicrobial pathways": "probable",
    },
    "Cognitive decline / Alzheimer's support": {
        "Cholinergic system": "established",
        "Acetylcholinesterase": "established",
        "Amyloid-beta aggregation": "probable",
        "Oxidative stress pathways": "established",
        "Neuroprotective pathways": "probable",
        "Antioxidant pathways": "probable",
    },

    "Immune support": {
        "Immune modulation": "established",
        "Antioxidant pathways": "probable",
        "CB2 receptor": "theoretical",
    },
    "Cardiovascular / circulation": {
        "Cardiometabolic pathways": "established",
        "Microvascular pathways": "probable",
        "Platelet activating factor": "probable",
        "Neurovascular pathways": "theoretical",
    },
    "Liver support / detox": {
        "Hepatoprotective pathways": "established",
        "Bile flow": "probable",
        "Detoxification pathways": "probable",
        "Nrf2": "theoretical",
    },
    "Joint & muscle comfort": {
        "Anti-inflammatory pathways": "established",
        "COX-2": "probable",
        "TRPV1": "probable",
        "NF-kB": "theoretical",
    },
    "Energy / fatigue": {
        "HPA axis": "established",
        "Anti-fatigue pathways": "probable",
        "Adenosine receptor": "probable",
        "AMPK": "theoretical",
    },
    "Metabolic & blood sugar support": {
        "AMPK": "established",
        "Insulin signaling": "probable",
        "Insulin secretion": "probable",
        "PPAR-gamma": "theoretical",
    },
    "Weight management": {
        "AMPK": "probable",
        "Adenosine receptor": "probable",
        "Gut microbiota": "theoretical",
        "Cardiometabolic pathways": "theoretical",
    },
    "Menopause support": {
        "Estrogen receptors": "probable",
        "Hormonal pathways": "probable",
        "Serotonergic system": "theoretical",
        "HPA axis": "theoretical",
    },
    "Menstrual / PMS support": {
        "Hormonal pathways": "probable",
        "Dopaminergic system": "probable",
        "Smooth muscle relaxation": "probable",
        "GABAergic system": "theoretical",
    },
    "Prostate / men's health": {
        "Hormonal pathways": "probable",
        "Anti-inflammatory pathways": "probable",
        "COX-2": "theoretical",
    },
    "Urinary tract health": {
        "Antimicrobial pathways": "established",
        "Microvascular pathways": "probable",
        "Diuretic effect": "theoretical",
    },
    "Cold & flu / respiratory": {
        "Immune modulation": "established",
        "Antimicrobial pathways": "probable",
        "Expectorant pathways": "probable",
        "Antioxidant pathways": "theoretical",
    },
    "Headache / mood support": {
        "Monoamine system": "established",
        "Serotonergic system": "probable",
        "GABAergic system": "probable",
        "HPA axis": "theoretical",
    },
    "Hair, skin & nail beauty-from-within": {
        "Collagen synthesis": "established",
        "Antioxidant pathways": "probable",
        "Anti-inflammatory pathways": "theoretical",
    },
    "Eye health": {
        "Antioxidant pathways": "probable",
        "Microvascular pathways": "probable",
        "Neuroprotective pathways": "theoretical",
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
        outcome="Silexan oral lavender oil capsule RCTs positive; not infusion-form evidence",
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
    "Withania somnifera": dict(
        study_type="Human supportive evidence", preparation_form="extract",
        outcome="Human supportive evidence for stress and sleep-related outcomes; EU traditional herbal status not established",
        ema_status="Not evaluated", who_status="Not listed", escop_status="Not listed",
        safety="moderate", safety_desc="Requires regulatory and safety review for EU product development",
        production_status="commercially produced", commercial="Very high",
    ),
    "Ziziphus jujuba": dict(
        study_type="Preclinical / traditional East Asian use", preparation_form="extract",
        outcome="Traditional use and preclinical sleep-promoting evidence; EU regulatory pathway requires review",
        ema_status="Not evaluated", who_status="Not listed", escop_status="Not listed",
        safety="mild", safety_desc="Generally used traditionally; EU safety/regulatory assessment required",
        production_status="R&D candidate", commercial="Medium",
    ),
    "Scutellaria baicalensis": dict(
        study_type="Preclinical / mechanistic evidence", preparation_form="extract",
        outcome="Strong flavonoid chemistry and GABA/inflammation targets; EU regulatory status limited",
        ema_status="Not evaluated", who_status="Not listed", escop_status="Not listed",
        safety="moderate", safety_desc="Requires safety and quality review",
        production_status="R&D candidate", commercial="Medium-high",
    ),
    "Crocus sativus": dict(
        study_type="Human supportive evidence", preparation_form="extract",
        outcome="Human supportive evidence for mood-related endpoints; sleep indication requires targeted review",
        ema_status="Not evaluated", who_status="Not listed", escop_status="Not listed",
        safety="mild", safety_desc="Dose and pregnancy safety need review",
        production_status="commercially produced", commercial="High",
    ),
    "Piper methysticum": dict(
        study_type="Clinical (multiple RCTs, meta-analysis) + contested EU regulatory history",
        preparation_form="extract (ethanolic/acetonic) — not aqueous infusion",
        outcome=(
            "Witte et al. 2005 meta-analysis and RCTs (Sarris et al. 2009 KADSS; "
            "Sarris et al. 2013 GAD trial) show anxiolytic efficacy vs placebo for "
            "kavalactone extracts. EMA/HMPC assessed Piper methysticum rhizoma but "
            "did NOT adopt an EU herbal monograph (2016-2019 assessment), citing "
            "insufficient efficacy data for the specific extracts reviewed."
        ),
        ema_status="No EU HMPC monograph adopted (rejected/withdrawn)",
        who_status="WHO monograph exists (Vol. 2, 2004)",
        escop_status="ESCOP monograph: positive, for anxiety/tension/restlessness",
        safety="serious",
        safety_desc=(
            "Hepatotoxicity concerns led to bans on kava products in Germany "
            "(2002, reinstated 2019) and restrictions in other markets; German "
            "courts have contested the ban's evidentiary basis. Not usable as an "
            "EU herbal medicinal product without national-level exception; "
            "requires dedicated regulatory and safety review before any product "
            "development."
        ),
        production_status="commercially produced (where legally permitted; banned/restricted in several EU markets)",
        commercial="Medium (regulatory-restricted)",
    ),
    "Crataegus monogyna": dict(
        study_type="EU HMPC traditional-use monograph + Ph. Eur. monograph",
        preparation_form="leaf/flower preparations (infusion, tincture, dry extract)",
        outcome=(
            "The EU herbal monograph on Crataegus monogyna/C. laevigata leaf and "
            "flower explicitly lists 'relief of mild symptoms of mental stress and "
            "to aid sleep' as an accepted traditional-use indication, alongside "
            "relief of temporary nervous cardiac complaints."
        ),
        ema_status="Traditional use (HMPC) — explicit sleep/mental-stress indication",
        who_status="Not confirmed in this review",
        escop_status="Traditional use (cardiac focus; ESCOP monograph exists)",
        safety="mild",
        safety_desc=(
            "Target organ is the heart; caution advised for people on cardiac "
            "medication or with serious cardiovascular disease. Reported adverse "
            "reactions include nausea, palpitations, and dizziness."
        ),
        production_status="commercially produced", commercial="Medium-high",
    ),
    "Gynostemma pentaphyllum": dict(
        study_type="Clinical (single RCT, human, anxiety-specific)",
        preparation_form="extract (ethanolic) — not infusion-specific",
        outcome=(
            "Huyen et al. 2018 (PubMed 30599899): randomized, double-blind, "
            "placebo-controlled trial in 72 healthy Korean adults with chronic "
            "psychological stress found ethanol extract of G. pentaphyllum leaves "
            "(200mg twice daily) reduced anxiety-proneness (STAI) vs placebo."
        ),
        ema_status="Not evaluated (no EU HMPC monograph; Chinese-origin herb)",
        who_status="Not listed", escop_status="Not listed",
        safety="none",
        safety_desc=(
            "Generally well tolerated in the available trial, though safety data "
            "is limited to one study. May require Novel Food authorisation for EU "
            "food-supplement use, since it lacks significant pre-1997 EU food-use "
            "history."
        ),
        production_status="R&D candidate", commercial="Medium",
    ),
}


def _get_id(cur, table, id_col, name_col, name_value):
    cur.execute(f"SELECT {id_col} FROM {table} WHERE {name_col} = ?", (name_value,))
    row = cur.fetchone()
    return row[0] if row else None



def build_standard_seed_records():
    """
    Return the local seed database in a normalized record format used by the
    R&D candidate engine. This does not replace the existing seed tables; it
    gives the engine one clean view of plant -> compound -> target ->
    indication -> evidence/safety/regulatory information.
    """
    compound_to_targets = {
        str(compound).strip(): list(targets)
        for compound, targets in COMPOUND_TARGETS.items()
    }

    target_to_indications = {}
    for indication, targets in TARGET_DISEASES.items():
        for target, relevance in targets.items():
            target_to_indications.setdefault(str(target).strip(), []).append({
                "indication": indication,
                "relevance_level": relevance,
            })

    evidence_by_plant = SLEEP_TEA_EVIDENCE

    records = []
    for plant, compounds in PLANT_COMPOUNDS.items():
        sleep_evidence = evidence_by_plant.get(plant, {})
        for compound_name, compound_class, extraction_method in compounds:
            targets = compound_to_targets.get(compound_name, [])
            indications = []
            for target in targets:
                indications.extend(target_to_indications.get(target, []))

            records.append({
                "plant": plant,
                "compound": compound_name,
                "compound_class": compound_class,
                "targets": targets,
                "indications": indications,
                "extraction_method": extraction_method,
                "evidence_level": sleep_evidence.get(
                    "study_type", "Not curated yet"
                ),
                "safety_notes": sleep_evidence.get(
                    "safety_desc", "Not curated yet"
                ),
                "regulatory_notes": {
                    "EMA": sleep_evidence.get("ema_status", "Not curated yet"),
                    "WHO": sleep_evidence.get("who_status", "Not curated yet"),
                    "ESCOP": sleep_evidence.get("escop_status", "Not curated yet"),
                },
            })

    return records

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

    for target in all_targets:
        cur.execute("INSERT OR IGNORE INTO targets (target_name) VALUES (?)", (target,))

    for plant_name, compounds in PLANT_COMPOUNDS.items():
        plant_id = _get_id(cur, "plants", "plant_id", "scientific_name", plant_name)

        if plant_id is None:
            continue

        for compound_name, compound_class, extraction_method in compounds:
            cur.execute(
                "INSERT OR IGNORE INTO compounds (compound_name, compound_class) VALUES (?, ?)",
                (compound_name, compound_class),
            )

            compound_id = _get_id(cur, "compounds", "compound_id", "compound_name", compound_name)

            if compound_id is None:
                continue

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

            if target_id is None:
                continue

            cur.execute(
                "INSERT OR IGNORE INTO compound_targets (compound_id, target_id) VALUES (?, ?)",
                (compound_id, target_id),
            )

    for disease_name, targets in TARGET_DISEASES.items():
        disease_id = _get_id(cur, "diseases", "disease_id", "disease_name", disease_name)

        if disease_id is None:
            continue

        for target_name, relevance in targets.items():
            target_id = _get_id(cur, "targets", "target_id", "target_name", target_name)

            if target_id is None:
                continue

            cur.execute(
                "INSERT OR IGNORE INTO target_diseases (target_id, disease_id, relevance_level) "
                "VALUES (?, ?, ?)",
                (target_id, disease_id, relevance),
            )

    insomnia_id = _get_id(cur, "diseases", "disease_id", "disease_name", "Insomnia / sleep disturbance")

    if insomnia_id is not None:
        for plant_name, ev in SLEEP_TEA_EVIDENCE.items():
            plant_id = _get_id(cur, "plants", "plant_id", "scientific_name", plant_name)

            if plant_id is None:
                continue

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
