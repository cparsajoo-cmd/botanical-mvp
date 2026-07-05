"""
AI Discovery Engine
Step 1 - Question Understanding
"""

THERAPEUTIC_MAP = {

    "Sleep and relaxation": {

        "targets": [
            "GABA-A receptor",
            "Melatonin receptor",
            "5-HT1A receptor",
            "Orexin receptor",
            "Histamine receptor"
        ],

        "keywords": [
            "sleep",
            "insomnia",
            "sedative",
            "anxiolytic",
            "sleep quality",
            "sleep disorder",
            "GABA",
            "melatonin"
        ],

        "compound_classes": [
            "Flavonoids",
            "Terpenes",
            "Phenolic acids",
            "Alkaloids",
            "Lignans",
            "Saponins"
        ]
    },

    "Stress": {

        "targets": [
            "Cortisol",
            "GABA-A receptor",
            "5-HT1A receptor"
        ],

        "keywords": [
            "stress",
            "adaptogen",
            "cortisol",
            "relaxation"
        ],

        "compound_classes": [
            "Withanolides",
            "Flavonoids",
            "Terpenes"
        ]
    },

    "Inflammation": {

        "targets": [
            "COX-2",
            "NF-kB",
            "TNF-alpha",
            "IL-6"
        ],

        "keywords": [
            "anti-inflammatory",
            "inflammation",
            "cytokines"
        ],

        "compound_classes": [
            "Polyphenols",
            "Flavonoids",
            "Terpenes"
        ]
    }

}


def understand_question(
    therapeutic_area,
    dosage_form,
    target_market
):

    profile = THERAPEUTIC_MAP.get(therapeutic_area)

    if profile is None:
        return None

    return {

        "therapeutic_area": therapeutic_area,

        "dosage_form": dosage_form,

        "target_market": target_market,

        "targets": profile["targets"],

        "keywords": profile["keywords"],

        "compound_classes": profile["compound_classes"]

    }
