"""Frozen-snapshot End-to-End pilot over existing reference-grounded Gold Cases.

This is benchmark/test infrastructure only. It does not change production logic.
Snapshots contain source-derived retrieval records and a frozen candidate-discovery
pool. GoldCase remains the source of scientific truth; snapshots are retrieval inputs.
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from end_to_end_validation import (
    BenchmarkMode,
    BenchmarkVersions,
    FrozenSnapshotRetriever,
    GoldSourceExpectation,
    GoldSourceSet,
    RetrievedEvidence,
    SourceRole,
    ValidationQuestion,
    build_end_to_end_evaluation_run,
    run_end_to_end_case,
)
from gold_corpus.gold_source_sets import GOLD_SOURCE_SETS

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = Path(__file__).resolve().parent / "e2e_snapshots"
REGISTRY = ROOT / "gold_cases" / "gold_case_registry_corrected_2026-08-01.json"
PILOT_CASE_NUMBERS = (6, 16, 18, 19, 20, 21, 22)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_snapshot(case_number: int) -> dict:
    if case_number not in PILOT_CASE_NUMBERS:
        raise KeyError(f"Case {case_number} is not in the frozen E2E pilot set")
    return _load_json(SNAPSHOT_DIR / f"case_{case_number:03d}_baseline.json")


def _load_case_builder(case_number: int):
    registry = _load_json(REGISTRY)
    row = next(x for x in registry["active_cases"] if x["case_number"] == case_number)
    path = ROOT / "gold_cases" / row["file"]
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builders = [v for k, v in vars(module).items() if k.startswith("build_gold_case") and callable(v)]
    if len(builders) != 1:
        raise RuntimeError(f"Expected exactly one GoldCase builder in {path}")
    return builders[0]


def load_gold_case(case_number: int):
    return _load_case_builder(case_number)()


def snapshot_question(snapshot: dict) -> ValidationQuestion:
    return ValidationQuestion(**snapshot["question"])


def snapshot_records(snapshot: dict) -> list[RetrievedEvidence]:
    return [RetrievedEvidence(**row) for row in snapshot["records"]]


def frozen_candidate_discovery(snapshot: dict):
    pool = tuple(snapshot["candidate_pool"])

    def _discover(_question: ValidationQuestion) -> list[str]:
        return list(pool)

    return _discover


def run_baseline_case(case_number: int):
    snapshot = load_snapshot(case_number)
    case = load_gold_case(case_number)
    sources = GOLD_SOURCE_SETS[case.case_id]
    return run_end_to_end_case(
        case,
        snapshot_question(snapshot),
        sources,
        FrozenSnapshotRetriever(snapshot_records(snapshot)),
        frozen_candidate_discovery(snapshot),
        use_live_search=False,
    )


def run_critical_missed_scenario(case_number: int):
    snapshot = load_snapshot(case_number)
    case = load_gold_case(case_number)
    sources = GOLD_SOURCE_SETS[case.case_id]
    critical = sources.critical_ids()
    records = [r for r in snapshot_records(snapshot) if r.reference_id not in critical]
    return run_end_to_end_case(
        case,
        snapshot_question(snapshot),
        sources,
        FrozenSnapshotRetriever(records),
        frozen_candidate_discovery(snapshot),
        use_live_search=False,
    )


def run_source_unavailable_scenario(case_number: int):
    snapshot = load_snapshot(case_number)
    case = load_gold_case(case_number)
    sources = GOLD_SOURCE_SETS[case.case_id]
    critical = sources.critical_ids()
    records = [
        replace(r, source_available=False) if r.reference_id in critical else r
        for r in snapshot_records(snapshot)
    ]
    return run_end_to_end_case(
        case,
        snapshot_question(snapshot),
        sources,
        FrozenSnapshotRetriever(records),
        frozen_candidate_discovery(snapshot),
        use_live_search=False,
    )


def duplicate_records(records: Iterable[RetrievedEvidence]) -> list[RetrievedEvidence]:
    records = list(records)
    if not records:
        return records
    first = records[0]
    duplicate = replace(first, reference_id=f"{first.reference_id}__DUPLICATE_CAPTURE")
    return records + [duplicate]


def run_duplicate_scenario(case_number: int):
    snapshot = load_snapshot(case_number)
    case = load_gold_case(case_number)
    sources = GOLD_SOURCE_SETS[case.case_id]
    return run_end_to_end_case(
        case,
        snapshot_question(snapshot),
        sources,
        FrozenSnapshotRetriever(duplicate_records(snapshot_records(snapshot))),
        frozen_candidate_discovery(snapshot),
        use_live_search=False,
    )


def run_case020_irrelevant_source_scenario():
    """Use a real ESCOP Echinacea *root* monograph as an irrelevant retrieval
    for the Case 020 *flowering aerial parts* question.
    """
    case_number = 20
    snapshot = load_snapshot(case_number)
    case = load_gold_case(case_number)
    baseline_sources = GOLD_SOURCE_SETS[case.case_id]
    irrelevant_id = "ESCOP_2021_ECHINACEAE_PURPUREAE_RADIX"
    sources = GoldSourceSet(baseline_sources.sources + (
        GoldSourceExpectation(reference_id=irrelevant_id, role=SourceRole.IRRELEVANT, source_type="ESCOP_MONOGRAPH"),
    ))
    records = snapshot_records(snapshot) + [RetrievedEvidence(
        reference_id=irrelevant_id,
        scientific_name="Echinacea purpurea (L.) Moench",
        source_type="ESCOP_MONOGRAPH",
        source_title="Echinaceae purpureae radix (Purple Coneflower root)",
        source_url="https://www.escop.com/downloads/echinaceae-purpureae-radix-purple-coneflower-root-escop-2021/",
        target_indication="recurrent infections of the upper respiratory tract (common colds)",
        dosage_form="Oral",
        notes="ESCOP defines this separate monograph as the underground parts/root of Echinacea purpurea; Case 020 targets flowering aerial parts.",
        source_available=True,
    )]
    return run_end_to_end_case(
        case,
        snapshot_question(snapshot),
        sources,
        FrozenSnapshotRetriever(records),
        frozen_candidate_discovery(snapshot),
        use_live_search=False,
    )


def build_pilot_evaluation_run():
    cases = []
    candidate_map = {}
    record_map = {}
    for number in PILOT_CASE_NUMBERS:
        snapshot = load_snapshot(number)
        case = load_gold_case(number)
        cases.append((case, snapshot_question(snapshot), GOLD_SOURCE_SETS[case.case_id]))
        candidate_map[snapshot["question"]["question"]] = tuple(snapshot["candidate_pool"])
        record_map[snapshot["question"]["question"]] = tuple(snapshot_records(snapshot))

    def _discover(question: ValidationQuestion) -> list[str]:
        return list(candidate_map.get(question.question, ()))

    def _retrieve(question: ValidationQuestion, candidates: list[str]) -> list[RetrievedEvidence]:
        # Route only by the natural-language benchmark question, never by case_id
        # or expected output. Each frozen snapshot represents the captured output
        # of retrieval for that question at the snapshot date.
        records = record_map.get(question.question, ())
        return FrozenSnapshotRetriever(records)(question, candidates)

    versions = BenchmarkVersions(
        benchmark_version="gold-corpus-e2e-pilot/1",
        gold_corpus_version="0.3.0",
        scoring_model_version="production-current-unmodified",
        ruleset_version="production-current-unmodified",
        evidence_schema_version="production-current-unmodified",
        connector_versions={"frozen_snapshot": "source-derived-2026-08-07"},
    )
    return build_end_to_end_evaluation_run(
        cases=cases,
        retriever=_retrieve,
        versions=versions,
        mode=BenchmarkMode.FROZEN_SNAPSHOT,
        candidate_discovery=_discover,
        data_snapshot="gold-corpus-e2e-pilot-2026-08-07",
        config={"pilot_cases": list(PILOT_CASE_NUMBERS), "live_search": False},
        evaluation_run_id="gold-corpus-e2e-pilot-2026-08-07",
    )
