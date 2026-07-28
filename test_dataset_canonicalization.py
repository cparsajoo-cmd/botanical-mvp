"""Tests for dataset_canonicalization.py (Validation Architecture v3, Phase 1)."""

from dataset_canonicalization import canonicalize_dataset, canonicalize_gold_case, hash_dataset
from dataset_split import DatasetSplit
from gold_case import GoldCase, RiskStratum, ExpectedOutput, DecisionDirection
from validation_unit import ValidationUnit


def _case(case_id, taxon="X", synonyms=None):
    return GoldCase(
        case_id=case_id,
        validation_unit=ValidationUnit(taxon=taxon, taxon_synonyms=synonyms or []),
        risk_strata=[RiskStratum.CLEAN_BASELINE],
    )


def test_hash_is_deterministic_across_repeated_calls():
    cases = [_case("c1"), _case("c2")]
    assert hash_dataset(cases) == hash_dataset(cases)


def test_hash_is_order_independent():
    a = _case("case_a")
    b = _case("case_b")
    assert hash_dataset([a, b]) == hash_dataset([b, a])


def test_hash_changes_when_taxon_changes():
    h1 = hash_dataset([_case("c1", taxon="Valeriana officinalis")])
    h2 = hash_dataset([_case("c1", taxon="Matricaria chamomilla")])
    assert h1 != h2


def test_hash_unaffected_by_taxon_synonyms():
    h1 = hash_dataset([_case("c1", taxon="X", synonyms=[])])
    h2 = hash_dataset([_case("c1", taxon="X", synonyms=["X synonym A", "X synonym B"])])
    assert h1 == h2


def test_hash_changes_when_a_case_is_added():
    h1 = hash_dataset([_case("c1")])
    h2 = hash_dataset([_case("c1"), _case("c2")])
    assert h1 != h2


def test_hash_changes_when_risk_strata_change():
    c1 = _case("c1")
    c2 = _case("c1")
    c2.risk_strata = [RiskStratum.SAFETY_SERIOUS]
    assert hash_dataset([c1]) != hash_dataset([c2])


def test_hash_changes_when_dataset_split_changes():
    c1 = _case("c1")
    c1.dataset_split = DatasetSplit.DEVELOPMENT
    c2 = _case("c1")
    c2.dataset_split = DatasetSplit.LOCKED_HOLDOUT
    assert hash_dataset([c1]) != hash_dataset([c2])


def test_canonicalize_gold_case_returns_a_plain_dict():
    result = canonicalize_gold_case(_case("c1"))
    assert isinstance(result, dict)
    assert result["case_id"] == "c1"


def test_canonicalize_gold_case_excludes_taxon_synonyms():
    result = canonicalize_gold_case(_case("c1", synonyms=["syn1"]))
    assert "taxon_synonyms" not in result["validation_unit"]


def test_canonicalize_dataset_is_valid_json_string():
    import json
    text = canonicalize_dataset([_case("c1"), _case("c2")])
    parsed = json.loads(text)
    assert isinstance(parsed, list)
    assert len(parsed) == 2


def test_hash_is_a_hex_sha256_digest():
    h = hash_dataset([_case("c1")])
    assert len(h) == 64
    int(h, 16)  # raises ValueError if not valid hex


def test_empty_dataset_hashes_consistently():
    assert hash_dataset([]) == hash_dataset([])
