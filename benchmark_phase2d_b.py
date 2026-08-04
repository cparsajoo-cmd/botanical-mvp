"""Phase 2D-B benchmark — before (Phase 2D-A unbounded build, simulated
inline since that code was removed) vs after (current, Option B)
performance for 100 / 1,000 / 2,000 unique synthetic plants.

Deterministic: _eu_regulatory_status() is monkeypatched to a cheap
synthetic stand-in that mimics real per-call cost (a small amount of
string work) without any network access, so results do not depend on
network conditions or the live EMA inventory.

Run with: python3 benchmark_phase2d_b.py
"""

import time
import types

import pandas as pd

import botanical_rd_candidate_engine as eng
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine


def make_engine(rows):
    background = [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    df = pd.DataFrame(list(rows) + background)
    return BotanicalRDCandidateEngine(
        plant_compounds_df=df,
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=pd.DataFrame(),
        use_live_search=False,
    )


def make_rows(n_unique_plants):
    rows = [
        dict(scientific_name="Referencia herbosa", compound_name="Sharedcompoundia",
             indication="Test indication", target="Testtarget",
             common_name="", plant_part="", extraction_method=""),
    ]
    rows += [
        dict(scientific_name=f"Syntheticplant{i} speciosa", compound_name="Sharedcompoundia",
             indication="", target="Testtarget",
             common_name="", plant_part="", extraction_method="")
        for i in range(n_unique_plants)
    ]
    return rows


def fake_eu_regulatory_status(plant):
    # Cheap synthetic stand-in for the real per-call cost of
    # _eu_regulatory_status() -> search_regulatory_sources_real() ->
    # _classify_inventory_match() + classify_ema_hmpc_signal() after
    # _get_inventory() is warm (lru_cache) — a handful of string
    # operations, not network I/O.
    text = f"Not in HMPC inventory for {plant} (as of 2021 snapshot)"
    _ = any(p in text.lower() for p in ("not found", "not listed", "no match"))
    return {
        "EMA_HMPC_Status": "Not found in HMPC inventory",
        "EMA_HMPC_Detail": text,
        "EMA_Source": "EMA HMPC — Inventory of herbal substances for assessment",
        "EMA_HMPC_Match_Category": "searched_not_found",
    }


def run_after(n_unique_plants):
    """Current (Phase 2D-B) behavior: default run(), no monkeypatch of
    run() itself — just observe how many times the real
    _eu_regulatory_status would have been called via a counting wrapper."""
    rows = make_rows(n_unique_plants)
    engine = make_engine(rows)
    engine.use_live_search = False

    call_count = {"n": 0}
    original = engine._eu_regulatory_status

    def counting_wrapper(plant):
        call_count["n"] += 1
        return fake_eu_regulatory_status(plant)

    engine._eu_regulatory_status = counting_wrapper

    start = time.perf_counter()
    result_df = engine.run(indication="Test indication", dosage_form="tea", market="EU")
    elapsed = time.perf_counter() - start

    return {
        "calls": call_count["n"],
        "elapsed_s": elapsed,
        "result_rows": len(result_df),
        "market_status_values": sorted(result_df["Market_Status"].unique().tolist()),
    }


def run_before_simulated(n_unique_plants):
    """Simulates Phase 2D-A's removed unbounded cache-build code
    directly (that exact code no longer exists in the file — this
    reproduces it inline for a fair before/after comparison), timing
    ONLY that block, against the same synthetic plant set and the same
    fake_eu_regulatory_status stand-in used in run_after()."""
    rows = make_rows(n_unique_plants)
    engine = make_engine(rows)
    engine.use_live_search = False

    all_candidates = engine._candidate_frame()
    unique_alt_plants = set(
        p for p in all_candidates["Scientific_Name"].tolist() if p
    )

    call_count = {"n": 0}

    def counting_wrapper(plant):
        call_count["n"] += 1
        return fake_eu_regulatory_status(plant)

    start = time.perf_counter()
    _ = {plant: counting_wrapper(plant) for plant in unique_alt_plants}
    elapsed = time.perf_counter() - start

    return {"calls": call_count["n"], "elapsed_s": elapsed}


if __name__ == "__main__":
    print(f"{'N unique plants':>16} | {'BEFORE calls':>13} | {'BEFORE time (s)':>16} | {'AFTER calls':>12} | {'AFTER time (s)':>15}")
    print("-" * 90)
    for n in (100, 1000, 2000):
        before = run_before_simulated(n)
        after = run_after(n)
        print(
            f"{n:>16} | {before['calls']:>13} | {before['elapsed_s']:>16.4f} | "
            f"{after['calls']:>12} | {after['elapsed_s']:>15.4f}"
        )
        print(f"    after: result_rows={after['result_rows']}, Market_Status values={after['market_status_values']}")
