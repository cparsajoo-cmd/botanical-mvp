# Gold Corpus Coverage Audit — Cases 001–019

**Audit date:** 2026-08-07  
**Scope:** Gold Case / Gold Source / Benchmark coverage only. No production logic, scoring, safety, regulatory, or market rules were changed.

## Canonical case count

The canonical registry contains **18 active Gold Cases** after addition of Case 019. Case 002 remains abandoned. The superseded Case 008 indication-evidence implementation is not canonical and must remain archived; the active Case 008 is the preparation-specification case.

## Domain coverage

| Domain | Active cases | Count |
|---|---|---:|
| INDICATION_EVIDENCE | 001, 003, 004, 005, 009, 010, 011, 012, 019 | 9 |
| SAFETY | 006, 014 | 2 |
| PREPARATION_SPEC | 007, 008, 015 | 3 |
| IDENTITY_QUALITY | 013, 017 | 2 |
| REGULATORY_STATUS | 016, 018 | 2 |

All five ReferenceDomain values are represented.

## Governing-source coverage

| Source family | Cases | Status |
|---|---|---|
| EMA/HMPC | 001, 006, 007, 008, 009, 010, 012, 014, 015 | COVERED |
| WHO | **019** | **COVERED — new** |
| ESCOP | — | GAP |
| FDA-specific | — | GAP |
| National regulator | 016, 018 | COVERED |
| Systematic review | 003, 004, 005, 011 | COVERED |
| Taxonomic authority | 013, 017 | COVERED |

## Scientific-evidence coverage

- **Positive human evidence:** covered (009, 010, 011, 012; WHO clinical-data-supported use in 019 adds source diversity).
- **Negative human evidence:** covered (004).
- **Insufficient/missing scientific evidence:** covered (005).
- **Conditional/mixed evidence:** covered (003).
- **Meta-analysis:** already covered before Case 019 (003 and 011). Therefore another meta-analysis-only case was not selected merely to increase case count.
- **Conflicting evidence:** Case 005 documents a real later conflicting review, but the resolved Gold Case still contains one governing applicable reference. A true multi-reference same-rank conflict remains a structural coverage opportunity.
- **Standalone RCT Gold source:** GAP. RCTs occur inside reviews, but protocol v0.3 does not rank a standalone RCT source_type for INDICATION_EVIDENCE.
- **Observational-study Gold source:** GAP for the same ontology/precedence reason unless used as supporting, not governing, evidence.
- **Standalone null-human-evidence case:** GAP. Null findings exist within the literature, but there is no canonical governing case specifically built around a null human evidence source under the current source hierarchy.

## Safety / preparation / regulatory coverage

- Contraindication: 006.
- Drug interaction: 006, 014.
- Preparation-specific evidence: 007, 008, 015.
- Dose-specific regulatory evidence: 018.
- Regulatory prohibition: 016.
- Regulatory restriction: 018.
- Botanical identity / synonym handling: 013, 017.

## Retrieval / End-to-End coverage gaps

- Critical-source expectations exist for the corpus and missing critical retrieval is tested as a failure condition.
- **Real Source-Unavailable holdout case:** still GAP. Do not fabricate one; it requires a real source expected by the frozen benchmark that is demonstrably unavailable to the tested retrieval path.
- Known irrelevant and duplicate source sets are still sparse; retrieval precision cannot yet be characterized comprehensively from the corpus alone.

## Why Case 019 was selected

The previous corpus had no `WHO_MONOGRAPH` governing source. WHO is explicitly recognized by the existing `reference_precedence.py` hierarchy for INDICATION_EVIDENCE, so it can be added without an architecture change.

Case 019 uses the WHO Volume 1 **Radix Ginseng** monograph. The monograph explicitly defines Radix Ginseng as dried root of *Panax ginseng* C.A. Meyer and places the selected restorative/prophylactic use under **"Uses supported by clinical data"**. No single dose, preparation, route, or population was fabricated where the monograph did not provide one uniform value for the benchmark question.

## Remaining highest-value gaps

1. **ESCOP governing source**, if an independently verifiable ESCOP monograph is available.
2. **FDA-specific medicinal-product or botanical regulatory source**, only if it fits the current regulatory ontology without semantic stretching.
3. **True multi-reference conflict case** with two independently verified, applicable sources processed by the existing precedence logic.
4. **Null human evidence** that can be represented honestly under the current source hierarchy.
5. **Real source-unavailable retrieval case** from a frozen retrieval snapshot, not a synthetic outage.

The corpus should not grow merely by repeating already-covered EMA positive-indication or meta-analysis patterns.
