# Gold Corpus Frozen-Snapshot End-to-End Pilot Report

**Date:** 2026-08-07  
**Pilot cases:** 006, 016, 018, 019, 020, 021, 022  
**Production logic modified:** No

## What was built

Seven frozen baseline retrieval snapshots were added under `gold_corpus/e2e_snapshots/`. Each snapshot contains a source-derived retrieval record for every pre-declared critical reference plus a frozen candidate-discovery pool. The runner uses the existing `end_to_end_validation.py` and real `BotanicalRDCandidateEngine`.

## Verification sources

- Case 006 — EMA/HMPC/7695/2021, Hypericum perforatum herba.
- Cases 016/018 — current MHRA banned/restricted herbal ingredients guidance.
- Case 019 — WHO Monographs on Selected Medicinal Plants, Vol. 1, Radix Ginseng.
- Case 020 — official ESCOP public Echinaceae purpureae herba summary.
- Case 021 — PubMed PMID 9820264 and Cochrane CD001423.
- Case 022 — PubMed PMID 10767649 and EMA Valerianae radix monograph page.

## Frozen baseline results

- Critical-source retrieval recall: **9/9 = 100%**.
- Retrieval recall over labelled relevant sources: **9/9 = 100%**.
- Duplicate retrieval rate: **0** in baseline.
- Known irrelevant retrieval rate: **0** in baseline.
- Evidence-direction accuracy: **1/9 = 11.1%**. Eight records were interpreted as `unclear` where the GoldSource expectation was positive/negative.
- Serious-safety false-negative: **1/1** in Case 006: critical EMA contraindication retrieved, safety gate did not fail.
- Regulatory gate: Case 016 prohibition and Case 018 restriction were detected.

## Perturbation tests

The following were tested without altering scientific Gold Cases:

1. Remove every critical source from each snapshot → `CRITICAL_SOURCE_MISSED` for all seven cases.
2. Mark every critical source unavailable → `SOURCE_UNAVAILABLE` and critical-source miss for all seven cases.
3. Duplicate a real Serenoa systematic-review record with the same DOI/article identity → deduplication count increases.
4. Add the real ESCOP *Echinacea purpurea* root monograph to the flowering-aerial-parts Case 020 scenario → counted as known irrelevant retrieval.

## Scientific/benchmark interpretation

The pilot demonstrates that the retrieval-failure plumbing is usable with real critical references. It also reveals two nontrivial calibration issues: the free-text evidence-direction classifier does not map most real monograph/regulatory wording into the corpus expectation vocabulary, and the serious Hypericum safety source remains a safety-gate false negative. No tuning was performed.

Because `positive` in GoldSource expectations is currently used both for efficacy-positive evidence and for affirmative safety/regulatory assertions, the direction-accuracy metric should not yet be presented as a standalone scientific accuracy estimate across mixed domains.

## Test result

`pytest -q gold_cases gold_corpus/test_gold_corpus_manifest.py gold_corpus/test_e2e_snapshot_pilot.py test_phase7_end_to_end_validation.py`

**165 passed, 0 failed.**
