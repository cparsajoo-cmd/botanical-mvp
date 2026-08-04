"""Phase 2E benchmark — old order (safety_aggregate before the relevance
gate, called for every candidate plant) vs new order (safety_aggregate
after the relevance gate, called only for retained plants).

The OLD call count is derived analytically (it is, by construction, one
call per candidate plant — every plant reached that line before the
relevance check existed at that point) rather than re-executed, since
that code path no longer exists in the file. The NEW call count and
elapsed time are measured directly by running the real, current
discover_indication_candidates() with an instrumented (real logic,
counted) _aggregate_plant_safety.

Deterministic; no live network access.
Run with: python3 benchmark_phase2e.py
"""

import time
import unittest.mock as mock

import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
import indication_candidate_discovery as icd


def make_dataset(n_relevant, n_irrelevant):
    plant_rows = []
    evidence_rows = []
    for i in range(n_relevant):
        name = f"Relevantia{i} speciosa"
        plant_rows.append(dict(
            scientific_name=name, compound_name="Compoundia",
            indication="Cough", target="Testtarget",
            common_name="", plant_part="", extraction_method="",
        ))
        evidence_rows.append(dict(
            scientific_name=name,
            text=f"A clinical study on Cough treatment with {name}.",
            source="TestSource", record_id=f"rel{i}",
            target_indication="Cough",
        ))
    for i in range(n_irrelevant):
        name = f"Irrelevantia{i} nullius"
        plant_rows.append(dict(
            scientific_name=name, compound_name="Compoundia",
            indication="", target="",
            common_name="", plant_part="", extraction_method="",
        ))
        evidence_rows.append(dict(
            scientific_name=name,
            text=f"Text about {name} completely unrelated to any indication.",
            source="TestSource", record_id=f"irr{i}",
            target_indication="",
        ))
    return plant_rows, evidence_rows


def make_engine(plant_rows, evidence_rows):
    return BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(plant_rows),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=pd.DataFrame(evidence_rows),
        use_live_search=False,
    )


def run_new_order(n_relevant, n_irrelevant):
    plant_rows, evidence_rows = make_dataset(n_relevant, n_irrelevant)
    engine = make_engine(plant_rows, evidence_rows)

    real_aggregate = icd._aggregate_plant_safety
    call_count = {"n": 0}

    def counting_wrapper(records, plant):
        call_count["n"] += 1
        return real_aggregate(records, plant)

    with mock.patch.object(icd, "_aggregate_plant_safety", side_effect=counting_wrapper):
        start = time.perf_counter()
        out = icd.discover_indication_candidates(
            engine, indication="Cough", dosage_form="Infusion", market="EU"
        )
        elapsed = time.perf_counter() - start

    return {
        "calls": call_count["n"],
        "elapsed_s": elapsed,
        "output_rows": len(out),
    }


if __name__ == "__main__":
    print(f"{'plants (rel+irrel)':>22} | {'OLD calls (analytical)':>24} | {'NEW calls (measured)':>21} | {'reduction':>10} | {'NEW elapsed (s)':>16} | {'output rows':>12}")
    print("-" * 120)
    for n_relevant, n_irrelevant in ((10, 90), (100, 900), (200, 1800)):
        total_plants = n_relevant + n_irrelevant
        result = run_new_order(n_relevant, n_irrelevant)
        old_calls = total_plants  # analytical: old order called it once per candidate plant, unconditionally
        reduction_pct = 100.0 * (old_calls - result["calls"]) / old_calls
        print(
            f"{f'{total_plants} ({n_relevant}+{n_irrelevant})':>22} | {old_calls:>24} | "
            f"{result['calls']:>21} | {reduction_pct:>9.1f}% | {result['elapsed_s']:>16.3f} | {result['output_rows']:>12}"
        )
