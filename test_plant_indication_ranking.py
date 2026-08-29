"""Regression tests for plant_indication_ranking.py (2026-08-29 chat
session) -- replaces alphabetical-of-a-deduped-set indication selection
(pages/Bulk evidence.py::_all_plants_with_indications) with frequency-based
ranking, so a plant's bulk evidence-gathering search queries target the
indications actually most associated with THAT plant, not whichever
indication strings happen to sort earliest alphabetically.
"""
import pytest

from plant_indication_ranking import rank_plant_indications


def test_ranks_by_frequency_not_alphabetically():
    # "Diabetes" and "Rheumatoid arthritis" are each cited twice; "AIDS/HIV"
    # (which would sort first alphabetically) is cited only once. Frequency
    # must win over alphabetical order.
    texts = [
        "AIDS/HIV; Diabetes",
        "Diabetes; Rheumatoid arthritis",
        "Rheumatoid arthritis",
    ]
    result = rank_plant_indications(texts, max_indications=5)
    assert result[0] in {"Diabetes", "Rheumatoid arthritis"}
    assert "AIDS/HIV" in result  # still included, just not first
    assert result.index("AIDS/HIV") > result.index("Diabetes")
    assert result.index("AIDS/HIV") > result.index("Rheumatoid arthritis")


def test_reproduces_the_production_incident_shape():
    """The exact failure mode found in production: many compound records
    each list the SAME broad, low-relevance indication set once, while the
    plant's own genuinely-frequent, specific indication is cited far more
    often across its records. The specific one must now win."""
    generic_bundle = "AIDS/HIV; BPH; Cancer; Dermatitis/Dermatoses; Diabetes"
    texts = [generic_bundle] * 3 + ["Rheumatoid arthritis; Autoimmune conditions"] * 8
    result = rank_plant_indications(texts, max_indications=5)
    assert result[0] == "Autoimmune conditions"
    assert result[1] == "Rheumatoid arthritis"


def test_ties_broken_alphabetically_for_determinism():
    texts = ["Zzz condition; Aaa condition"]
    result = rank_plant_indications(texts, max_indications=5)
    assert result == ["Aaa condition", "Zzz condition"]


def test_respects_max_indications_cap():
    texts = ["A; B; C; D; E; F"]
    result = rank_plant_indications(texts, max_indications=3)
    assert len(result) == 3


def test_blank_and_whitespace_entries_ignored():
    texts = ["", "   ", "Diabetes;  ; ;Cancer"]
    result = rank_plant_indications(texts, max_indications=5)
    assert set(result) == {"Diabetes", "Cancer"}


def test_empty_input_returns_empty_list():
    assert rank_plant_indications([], max_indications=5) == []
    assert rank_plant_indications(None, max_indications=5) == []


def test_zero_max_indications_returns_empty_list():
    assert rank_plant_indications(["Diabetes"], max_indications=0) == []


def test_single_indication_texts_without_semicolons():
    texts = ["Diabetes", "Diabetes", "Cancer"]
    result = rank_plant_indications(texts, max_indications=5)
    assert result[0] == "Diabetes"
    assert result[1] == "Cancer"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
