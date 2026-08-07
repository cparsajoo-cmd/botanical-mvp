# Case 021 Implementation Report

## Purpose
First active Gold Case whose resolved Ground Truth itself contains two applicable,
equally ranked systematic reviews with opposing verdicts and therefore resolves
to `REFERENCE_CONFLICT`.

## Botanical / question
- Taxon: Serenoa repens
- Plant part: berry (ValidationUnit; older review leaves part unspecified)
- Domain: INDICATION_EVIDENCE
- Assertion: SUPPORTS_INDICATION
- Subject: lower urinary tract symptoms due to benign prostatic enlargement

## Critical sources
1. Wilt TJ et al. JAMA. 1998;280(18):1604-1609.
   PMID 9820264. DOI 10.1001/jama.280.18.1604.
   Direction: positive.
2. Franco JVA et al. Cochrane Database Syst Rev. 2023;6:CD001423.
   DOI 10.1002/14651858.CD001423.pub4.
   Direction: negative / little-to-no benefit.

## Ground Truth behavior
- Both references: SYSTEMATIC_REVIEW
- Both independently applicable
- Same assertion identity
- Opposing assertion states: PRESENT vs ABSENT
- Resolution: REFERENCE_CONFLICT
- selected_reference_id: None
- Both sources are CRITICAL in the Gold Corpus

## Scope discipline
No preparation, dose, route, or duration was invented.

## Tests
- Case 021 dedicated tests: 8/8 passed
- Canonical Gold Cases + Gold Corpus/Phase 7 targeted regression: 149 passed
- Production engine/scoring/safety/regulatory/market logic: unchanged
