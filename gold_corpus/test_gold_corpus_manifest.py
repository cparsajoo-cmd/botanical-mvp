from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from end_to_end_validation import FrozenSnapshotRetriever, RetrievedEvidence, ValidationQuestion, run_end_to_end_case
from gold_corpus.gold_source_sets import GOLD_SOURCE_SETS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((Path(__file__).with_name("gold_corpus_manifest.json")).read_text())
REGISTRY = json.loads((ROOT / "gold_cases" / "gold_case_registry_corrected_2026-08-01.json").read_text())


def _case_by_number(number: int):
    item = next(x for x in REGISTRY["active_cases"] if x["case_number"] == number)
    path = ROOT / "gold_cases" / item["file"]
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(module)
    builder = next(v for k, v in vars(module).items() if k.startswith("build_gold_case") and callable(v))
    return builder()


def test_manifest_has_exactly_all_active_registry_cases():
    assert MANIFEST["active_case_count"] == len(REGISTRY["active_cases"])
    assert {c["case_number"] for c in MANIFEST["cases"]} == {x["case_number"] for x in REGISTRY["active_cases"]}


def test_every_case_has_required_scientific_corpus_fields():
    required = {
        "case_id", "question", "indication", "botanical_identity", "scientific_name", "plant_part",
        "preparation", "dose", "critical_sources", "supporting_sources", "known_irrelevant_sources",
        "known_duplicate_sources", "expected_evidence_direction", "expected_study_design",
        "expected_applicability", "expected_safety_status", "expected_regulatory_status",
        "expected_decision_direction", "expected_prohibited_decisions", "reference_rationale", "reviewer", "review_date",
    }
    for case in MANIFEST["cases"]:
        assert required <= set(case)
        assert case["question"].strip()
        assert case["reference_rationale"].strip()
        assert case["critical_sources"], case["case_id"]


def test_critical_sources_match_ground_truth_resolution():
    for case_meta in MANIFEST["cases"]:
        case = _case_by_number(case_meta["case_number"])
        assert len(case.resolved_outcomes) == 1
        outcome = case.resolved_outcomes[0]
        manifest_ids = {s["reference_id"] for s in case_meta["critical_sources"]}
        if outcome.selected_reference_id is not None:
            assert manifest_ids == {outcome.selected_reference_id}
        else:
            assert outcome.conflicting_reference_ids
            assert manifest_ids == set(outcome.conflicting_reference_ids)


def test_all_active_cases_have_gold_source_sets():
    ids = {c["case_id"] for c in MANIFEST["cases"]}
    assert set(GOLD_SOURCE_SETS) == ids
    assert all(gs.critical_ids() for gs in GOLD_SOURCE_SETS.values())


def test_missing_real_critical_source_fails_end_to_end_case():
    case = _case_by_number(1)
    meta = next(c for c in MANIFEST["cases"] if c["case_number"] == 1)
    q = ValidationQuestion(meta["question"], meta["indication"] or "", "capsule", meta["jurisdiction"] or "EU")
    result = run_end_to_end_case(
        case, q, GOLD_SOURCE_SETS[case.case_id], FrozenSnapshotRetriever([]),
        candidate_discovery=lambda _q: [case.validation_unit.taxon],
    )
    assert any(f.code == "CRITICAL_SOURCE_MISSED" for f in result.failures)


def test_critical_source_retrieval_clears_critical_miss_for_case_1():
    case = _case_by_number(1)
    meta = next(c for c in MANIFEST["cases"] if c["case_number"] == 1)
    src = meta["critical_sources"][0]
    rec = RetrievedEvidence(
        reference_id=src["reference_id"], scientific_name=case.validation_unit.taxon,
        notes="Traditional herbal medicinal product for relief of mild symptoms of mental stress and to aid sleep.",
        source_type=src["source_type"], target_indication=meta["indication"] or "",
    )
    q = ValidationQuestion(meta["question"], meta["indication"] or "", "capsule", meta["jurisdiction"] or "EU")
    result = run_end_to_end_case(
        case, q, GOLD_SOURCE_SETS[case.case_id], FrozenSnapshotRetriever([rec]),
        candidate_discovery=lambda _q: [case.validation_unit.taxon],
    )
    assert not any(f.code == "CRITICAL_SOURCE_MISSED" for f in result.failures)
    assert result.source_counts["critical_retrieved"] == 1


def test_case_21_is_real_multi_reference_conflict():
    case = _case_by_number(21)
    meta = next(c for c in MANIFEST["cases"] if c["case_number"] == 21)
    outcome = case.resolved_outcomes[0]
    assert outcome.resolution_status.value == "Reference conflict"
    assert outcome.selected_reference_id is None
    assert len(outcome.conflicting_reference_ids) == 2
    assert len(meta["critical_sources"]) == 2
    assert meta["expected_evidence_direction"] == "conflicting"
    assert meta["expected_decision_direction"]["value"] is None


def test_case_21_requires_both_conflicting_critical_sources_for_e2e_retrieval():
    case = _case_by_number(21)
    meta = next(c for c in MANIFEST["cases"] if c["case_number"] == 21)
    sources = meta["critical_sources"]
    assert len(sources) == 2
    first = sources[0]
    rec = RetrievedEvidence(
        reference_id=first["reference_id"],
        scientific_name=case.validation_unit.taxon,
        notes="One of two critical same-rank systematic reviews.",
        source_type=first["source_type"],
        target_indication=meta["indication"] or "",
    )
    q = ValidationQuestion(meta["question"], meta["indication"] or "", "unspecified", meta["jurisdiction"] or "International")
    result = run_end_to_end_case(
        case, q, GOLD_SOURCE_SETS[case.case_id], FrozenSnapshotRetriever([rec]),
        candidate_discovery=lambda _q: [case.validation_unit.taxon],
    )
    assert any(f.code == "CRITICAL_SOURCE_MISSED" for f in result.failures)
    assert result.source_counts["critical_retrieved"] == 1
