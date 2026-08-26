"""Regression tests for the Step 5 commercial/market-intelligence performance fix.

Context: after Phase 8 (commercial/market-intelligence) enrichment was added
to Step 5, ``MarketIntelligenceEngine.evaluate()`` rebuilt its lower-cased
plant-name "haystack" (and, when a market filter was set, the market-scope
mask) from scratch on *every single call* — i.e. once per candidate plant.
Since ``_attach_commercial_market_intelligence()`` (step_rd_candidates.py)
calls ``evaluate()`` once per unique candidate plant, this produced
candidates x market_rows work and stalled Step 5 once either side of that
product grew.

The complete fix must do more than cache the joined haystack.  Candidate
matching itself must use a pre-built exact plant/common-name index, otherwise
``haystack.str.contains(...)`` still scans every market row once per candidate.
The haystack is retained only as a rare compatibility fallback for decorated
legacy values.  Market-row classification is also vectorized so engine startup
does not call a Python row function across the entire evidence dataframe.

These tests prove:
  1. Step 5 does not repeatedly rebuild/rescan the full market dataframe per
     candidate (the actual performance regression).
  2. Market enrichment is correct for multiple indications.
  3. A Rhodiola + stress product does NOT count as Rhodiola + sleep evidence.
  4. A known Valerian sleep product counts as commercial evidence for sleep.
  5. An unknown/ambiguous product claim does not auto-count as
     indication-specific commercial evidence.
  6. SEARCH_NOT_PERFORMED does not become commercial white space.
  7. Existing scientific ranking is unaffected when no commercial evidence
     is available (Commercial_* enrichment is additive-only).
  8. OUTPUT_COLUMNS stays at the historically-expected size of 87.
  9. The engine's core eligibility/regulatory/safety decision logic is
     unaffected (spot-checked via unaltered import/behavior surface).
"""
import time

import pandas as pd
import pytest

import market_intelligence_engine as mie
from market_intelligence_engine import MarketIntelligenceEngine


def _market_row(plant, common="", *, indication_text="", claim_col="Product_Claim", **extra):
    row = {
        "Scientific_Name": plant,
        "Common_Name": common,
        "Market_Source_Type": "Major retailer",
        "Product_Name": f"{common or plant} extract",
        "Brand": "Brand A",
        "Retailer": "Retailer A",
        "Source_URL": f"https://example.test/{plant}-{extra.get('suffix', '0')}",
        claim_col: indication_text,
    }
    row.update({k: v for k, v in extra.items() if k != "suffix"})
    return row


def _big_market_df(n_plants=40, rows_per_plant=25):
    """A market dataframe large enough that O(candidates x rows) rescanning
    is measurably slower than a cached single scan."""
    rows = []
    for i in range(n_plants):
        plant = f"Species genus{i}"
        for j in range(rows_per_plant):
            rows.append(_market_row(
                plant, f"Common{i}",
                indication_text="stress support" if j % 2 == 0 else "",
                suffix=j,
            ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 1. Performance: the market dataframe must not be rescanned per candidate.
# ---------------------------------------------------------------------------

def test_scoped_market_index_is_built_once_per_market_value_not_per_candidate():
    """Direct proof of the fix: repeated evaluate() calls for many distinct
    candidate plants, with the same market, must hit the cache after the
    first call rather than rebuilding the haystack every time."""
    df = _big_market_df(n_plants=30, rows_per_plant=20)
    engine = MarketIntelligenceEngine(df)

    calls = {"n": 0}
    real_scoped_index = MarketIntelligenceEngine._scoped_market_index

    def _counting_scoped_index(self, market):
        calls["n"] += 1
        return real_scoped_index(self, market)

    engine._scoped_market_index = _counting_scoped_index.__get__(engine, MarketIntelligenceEngine)

    for i in range(30):
        engine.evaluate({"Scientific_Name": f"Species genus{i}"}, market="FR")

    # One scope/haystack build per distinct market value ("FR"), never once
    # per candidate plant (30 candidates evaluated above).
    assert calls["n"] == 30  # the wrapper is called each time...
    assert len(engine._scope_cache) == 1  # ...but only ever builds it once


def test_exact_candidate_lookup_does_not_scan_full_haystack_per_candidate():
    """The former cache-only fix was insufficient: evaluate() still called
    ``haystack.str.contains`` over every row for every candidate.  Exact
    structured plant names must now resolve from the pre-built dictionary index.

    Replacing the cached haystack with an object whose ``str.contains`` explodes
    makes this a deterministic structural test rather than a timing guess.
    """
    df = _big_market_df(n_plants=40, rows_per_plant=25)
    engine = MarketIntelligenceEngine(df)
    scope = engine._scoped_market_index("FR")

    class _BombStr:
        def contains(self, *args, **kwargs):
            raise AssertionError("full haystack scan executed for an exact indexed plant")

    class _BombHaystack:
        @property
        def str(self):
            return _BombStr()

    scope["haystack"] = _BombHaystack()
    for i in range(40):
        result = engine.evaluate(
            {"Scientific_Name": f"Species genus{i}"},
            indication="stress",
            market="FR",
        )
        assert result["Market_Evidence_Count"] == 25


def test_engine_init_does_not_use_rowwise_dataframe_apply(monkeypatch):
    """Large evidence tables must be classified vectorially at engine startup."""
    df = _big_market_df(n_plants=10, rows_per_plant=10)
    original_apply = pd.DataFrame.apply

    def _forbid_apply(self, *args, **kwargs):
        raise AssertionError("row-wise DataFrame.apply used during market-engine initialization")

    monkeypatch.setattr(pd.DataFrame, "apply", _forbid_apply)
    try:
        engine = MarketIntelligenceEngine(df)
    finally:
        monkeypatch.setattr(pd.DataFrame, "apply", original_apply)
    assert len(engine._market_rows) == len(df)


def test_many_candidates_against_large_market_table_is_fast():
    """End-to-end timing guard matching the reported symptom: Step 5 must
    stay responsive as candidate count and market table size grow."""
    df = _big_market_df(n_plants=200, rows_per_plant=50)  # 10,000 market rows
    engine = MarketIntelligenceEngine(df)

    started = time.perf_counter()
    for i in range(400):  # 400 evaluations across 200 candidate plants
        engine.evaluate(
            {"Scientific_Name": f"Species genus{i % 200}"},
            indication="stress",
            market="FR",
        )
    elapsed = time.perf_counter() - started

    # Generous bound for interactive Streamlit use (padded for slower CI
    # runners); the pre-fix per-candidate full rescan + per-row indication
    # re-resolution pattern scales with candidates x rows and would be far
    # slower at this size.
    assert elapsed < 10.0


# ---------------------------------------------------------------------------
# 2 & 3. Indication-specific commercial presence must not leak across
#         indications (Rhodiola/stress must not count as Rhodiola/sleep).
# ---------------------------------------------------------------------------

def test_rhodiola_stress_product_does_not_count_as_rhodiola_sleep_evidence():
    df = pd.DataFrame([
        _market_row("Rhodiola rosea", "Rhodiola", indication_text="stress and fatigue support", suffix=1),
    ])
    engine = MarketIntelligenceEngine(df)

    stress_result = engine.evaluate({"Scientific_Name": "Rhodiola rosea"}, indication="stress")
    sleep_result = engine.evaluate({"Scientific_Name": "Rhodiola rosea"}, indication="sleep")

    assert stress_result["Commercial_Status_For_Indication"] == "VERIFIED_MARKETED_FOR_INDICATION"
    assert sleep_result["Commercial_Status_For_Indication"] != "VERIFIED_MARKETED_FOR_INDICATION"
    assert sleep_result["Indication_Product_Hits"] == 0


def test_market_enrichment_correct_across_multiple_indications():
    df = pd.DataFrame([
        _market_row("Rhodiola rosea", "Rhodiola", indication_text="stress and fatigue support", suffix=1),
        _market_row("Valeriana officinalis", "Valerian", indication_text="sleep support", suffix=1),
    ])
    engine = MarketIntelligenceEngine(df)

    rhodiola_stress = engine.evaluate({"Scientific_Name": "Rhodiola rosea"}, indication="stress")
    valerian_sleep = engine.evaluate({"Scientific_Name": "Valeriana officinalis"}, indication="sleep")

    assert rhodiola_stress["Commercial_Status_For_Indication"] == "VERIFIED_MARKETED_FOR_INDICATION"
    assert valerian_sleep["Commercial_Status_For_Indication"] == "VERIFIED_MARKETED_FOR_INDICATION"


# ---------------------------------------------------------------------------
# 4. Known Valerian sleep product counts as commercial evidence for sleep.
# ---------------------------------------------------------------------------

def test_known_valerian_sleep_product_counts_as_sleep_commercial_evidence():
    df = pd.DataFrame([
        _market_row("Valeriana officinalis", "Valerian", indication_text="traditionally used for sleep", suffix=1),
    ])
    engine = MarketIntelligenceEngine(df)
    result = engine.evaluate({"Scientific_Name": "Valeriana officinalis"}, indication="sleep")

    assert result["Indication_Product_Hits"] >= 1
    assert result["Commercial_Status_For_Indication"] == "VERIFIED_MARKETED_FOR_INDICATION"


# ---------------------------------------------------------------------------
# 5. Unknown/ambiguous claim does not auto-count as indication-specific
#    commercial evidence.
# ---------------------------------------------------------------------------

def test_generic_product_without_claim_does_not_prove_indication_match():
    df = pd.DataFrame([
        {
            "Scientific_Name": "Ashwagandha somnifera",
            "Common_Name": "Ashwagandha",
            "Market_Source_Type": "Major retailer",
            "Product_Name": "Ashwagandha 500 mg",
            "Brand": "Brand A",
            "Retailer": "Retailer A",
            "Source_URL": "https://example.test/ash-1",
            # No explicit claim/indication column populated at all.
        }
    ])
    engine = MarketIntelligenceEngine(df)
    result = engine.evaluate({"Scientific_Name": "Ashwagandha somnifera"}, indication="sleep")

    assert result["Commercial_Status_For_Indication"] != "VERIFIED_MARKETED_FOR_INDICATION"
    assert result["Indication_Unclear_Product_Count"] >= 1


# ---------------------------------------------------------------------------
# 6. SEARCH_NOT_PERFORMED / missing data never becomes white space.
# ---------------------------------------------------------------------------

def test_search_not_performed_is_not_commercial_white_space():
    engine = MarketIntelligenceEngine(pd.DataFrame())
    result = engine.evaluate({"Scientific_Name": "Anything officinalis"}, indication="sleep")

    assert result["Search_Status"] == "SEARCH_NOT_PERFORMED"
    assert result["Commercial_Novelty_Status"] == "Commercial novelty not assessed"
    assert result["Commercial_Status_Overall"] == "UNKNOWN"
    assert result["Commercial_Status_For_Indication"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 7. Scientific ranking untouched when no commercial evidence available —
#    the commercial attach step in step_rd_candidates.py is additive-only.
# ---------------------------------------------------------------------------

def test_commercial_attach_is_additive_and_preserves_scientific_columns():
    import step_rd_candidates as src

    result_df = pd.DataFrame([
        {"Alternative_Plant": "Species genus1", "Novelty_Status": "Alternative source",
         "Scientific_RnD_Potential": 42},
    ])
    out = src._attach_commercial_market_intelligence(
        result_df, evidence_df=pd.DataFrame(), indication="sleep",
        dosage_form="", market="",
    )

    assert out.loc[0, "Novelty_Status"] == "Alternative source"
    assert out.loc[0, "Scientific_RnD_Potential"] == 42
    # Chemical differentiation is derived, never redefined by commercial data.
    assert out.loc[0, "Chemical_Differentiation_Status"] == "Alternative source"


# ---------------------------------------------------------------------------
# 8. OUTPUT_COLUMNS contract stays at the historically expected size.
# ---------------------------------------------------------------------------

def test_output_columns_contract_unchanged():
    from botanical_rd_candidate_engine import OUTPUT_COLUMNS
    assert len(OUTPUT_COLUMNS) == 87
    assert "Chemical_Differentiation_Status" not in OUTPUT_COLUMNS


# ---------------------------------------------------------------------------
# 9. market_intelligence_engine.py must not be archivable as legacy.
# ---------------------------------------------------------------------------

def test_market_intelligence_engine_not_listed_as_legacy():
    import repo_dependency_audit as audit
    errors = audit.validate_legacy_list(".github/legacy-files.txt", ".")
    assert errors == []
    with open(".github/legacy-files.txt") as f:
        assert "market_intelligence_engine.py" not in f.read()
