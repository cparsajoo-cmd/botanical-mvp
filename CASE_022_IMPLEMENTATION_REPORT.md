# Case 022 Implementation Report

## Purpose
First active cross-rank reference-precedence Gold Case for INDICATION_EVIDENCE.

## Case
- Taxon: Valeriana officinalis L.
- Plant part: radix
- Domain: INDICATION_EVIDENCE
- Subject: insomnia

## Critical references
1. Stevinson C, Ernst E. Valerian for insomnia: a systematic review of randomized clinical trials. Sleep Med. 2000;1(2):91-99. PMID 10767649. DOI 10.1016/S1389-9457(99)00015-5.
   - Source type: SYSTEMATIC_REVIEW
   - Verdict: INSUFFICIENT / inconclusive
2. EMA/HMPC/150848/2015. European Union herbal monograph on Valeriana officinalis L., radix. Adopted 2 February 2016.
   - Source type: EMA_HMPC
   - Verdict: PRESENT / supports relief of sleep disorders

## Expected precedence behavior
Existing hierarchy: SYSTEMATIC_REVIEW > EMA_HMPC for INDICATION_EVIDENCE.
Both references are applicable, but the systematic review must be selected despite being older.
Expected resolution: SELECTED, selected_reference_id = PUBMED_10767649_STEVINSON_ERNST_2000_VALERIAN_INSOMNIA_SR, assertion_state = INSUFFICIENT.

This is not a same-rank REFERENCE_CONFLICT case.

## E2E critical-source behavior
Both references are explicitly CRITICAL for this benchmark. Missing either one must trigger CRITICAL_SOURCE_MISSED because cross-rank precedence cannot be evaluated if only one source is retrieved.

## Scope discipline
No dose or preparation was invented. The benchmark question is narrowed to insomnia, the clinical overlap between the systematic review and EMA sleep-disorder use.

## Tests
- Case 022 dedicated tests: 8/8 passed
- Case 022 + Gold Corpus + Phase 7: 42 passed
- Canonical Gold Cases + Gold Corpus + Phase 7 regression: 159 passed
- Production logic modified: NO
