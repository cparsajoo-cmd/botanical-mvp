"""
AI Discovery Engine
Step 1 - Question Understanding

Builds a therapeutic profile (targets / keywords / compound classes)
directly from seed_data.py (TARGET_DISEASES / COMPOUND_TARGETS /
PLANT_COMPOUNDS) instead of a separate hardcoded map, so every
indication offered in the Step 0 dropdown is automatically covered
here too, with a single source of truth.
"""

from seed_data import TARGET_DISEASES, COMPOUND_TARGETS, PLANT_COMPOUNDS


def _build_compound_class_index():
    index = {}
    for compounds in PLANT_COMPOUNDS.values():
        for compound_name, chem_class, _extraction in compounds:
            index[compound_name] = chem_class
    return index


_COMPOUND_CLASS_INDEX = _build_compound_class_index()


def understand_question(
    therapeutic_area,
    dosage_form,
    target_market,
):
    targets_dict = TARGET_DISEASES.get(therapeutic_area)

    if not targets_dict:
        return None

    targets = list(targets_dict.keys())

    compound_classes = sorted({
        _COMPOUND_CLASS_INDEX[compound]
        for compound, compound_targets in COMPOUND_TARGETS.items()
        if compound in _COMPOUND_CLASS_INDEX
        and any(target in targets for target in compound_targets)
    })

    keywords = sorted({
        word
        for target in targets
        for word in target.lower().replace("-", " ").replace("/", " ").split()
        if len(word) > 2
    } | {therapeutic_area.lower()})

    return {
        "therapeutic_area": therapeutic_area,
        "dosage_form": dosage_form,
        "target_market": target_market,
        "targets": targets,
        "keywords": keywords,
        "compound_classes": compound_classes or ["Not yet catalogued"],
    }
