from knowledge_retrieval_engine import get_candidate_plants
from therapeutic_area_registry import lookup_therapeutic_area


def test_free_text_cognitive_indication_discovers_ginkgo_without_exact_map_entry():
    assert "Ginkgo biloba" in get_candidate_plants("Cognitive decline / Alzheimer's support")


def test_free_text_menopause_indication_discovers_cimicifuga_without_exact_map_entry():
    assert "Cimicifuga racemosa" in get_candidate_plants("Menopause support")


def test_free_text_sleep_variant_discovers_lavandula_without_exact_map_entry():
    assert "Lavandula angustifolia" in get_candidate_plants("Sleep disorders and temporary insomnia")


def test_noncontiguous_clinical_phrase_resolves_metabolic_family():
    area = lookup_therapeutic_area("reduction of fasting blood glucose")
    assert area is not None
    assert area.canonical_name == "Metabolic & blood sugar support"
    assert "Momordica charantia" in get_candidate_plants("reduction of fasting blood glucose")


def test_unknown_indication_does_not_fabricate_candidates():
    assert get_candidate_plants("completely unknown qzxv botanical indication") == []
