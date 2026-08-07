# Gold Corpus Coverage Audit — Cases 001–020

**Audit date:** 2026-08-07  
**Scope:** Gold Case / Gold Source / Benchmark coverage only. No production logic, scoring, safety, regulatory, or market rules were changed.

## Canonical case count

The canonical registry contains **19 active Gold Cases** after addition of Case 020. Case 002 remains abandoned. The superseded Case 008 indication-evidence implementation is not canonical; the active Case 008 is the preparation-specification case.

## Domain coverage

| Domain | Active cases | Count |
|---|---|---:|
| INDICATION_EVIDENCE | 001, 003, 004, 005, 009, 010, 011, 012, 019, 020 | 10 |
| SAFETY | 006, 014 | 2 |
| PREPARATION_SPEC | 007, 008, 015 | 3 |
| IDENTITY_QUALITY | 013, 017 | 2 |
| REGULATORY_STATUS | 016, 018 | 2 |

All five `ReferenceDomain` values are represented.

## Governing-source coverage

| Source family | Cases | Status |
|---|---|---|
| EMA/HMPC | 001, 006, 007, 008, 009, 010, 012, 014, 015 | COVERED |
| WHO | 019 | COVERED |
| ESCOP | **020** | **COVERED — new** |
| FDA-specific | — | GAP |
| National regulator | 016, 018 | COVERED |
| Systematic review | 003, 004, 005, 011 | COVERED |
| Taxonomic authority | 013, 017 | COVERED |

## Scientific-evidence coverage

- **Positive human evidence:** covered by several EMA/HMPC cases, systematic-review evidence in 011, WHO clinical-data-supported use in 019, and an ESCOP therapeutic-indication monograph in 020.
- **Negative human evidence:** covered (004).
- **Insufficient/missing scientific evidence:** covered (005).
- **Conditional/mixed evidence:** covered (003).
- **Meta-analysis:** covered (003 and 011). No duplicate meta-analysis-only case was added.
- **Conflicting evidence:** Case 005 documents a real later conflicting review, but the resolved Gold Case still contains one governing applicable reference. A true multi-reference same-rank conflict remains a structural gap.
- **Standalone RCT Gold source:** GAP. RCTs occur inside reviews, but protocol v0.3 does not rank a standalone RCT source type for `INDICATION_EVIDENCE`.
- **Observational-study Gold source:** GAP under the current governing-source ontology.
- **Standalone null-human-evidence case:** GAP.

## Why Case 020 was selected

The previous corpus had no `ESCOP_MONOGRAPH` governing source, while ESCOP is already recognized by the existing `reference_precedence.py` hierarchy for `INDICATION_EVIDENCE`. Therefore this gap could be closed without modifying architecture.

Case 020 uses the official ESCOP public page for **Echinaceae purpureae herba (Purple Coneflower Herb)**, published in 2021. The public summary explicitly defines the herbal drug as the flowering aerial parts of *Echinacea purpurea* (L.) Moench and explicitly lists recurrent infections of the upper respiratory tract (common colds) among the therapeutic indications.

The case deliberately does **not** infer preparation, dose, route, duration, or population from the paywalled full monograph. Only source text visible on the official public ESCOP page is used for Ground Truth.

## Retrieval / End-to-End coverage gaps

- Critical-source expectations exist for the corpus and missing critical retrieval is tested as a failure condition.
- **Real Source-Unavailable holdout case:** still GAP. Do not fabricate one; it requires a real frozen retrieval snapshot in which an expected critical source is genuinely unavailable.
- Known irrelevant and duplicate source sets remain sparse.

## Remaining highest-value gaps

1. **FDA-specific source**, only if a real FDA determination fits the existing ontology without semantic stretching.
2. **True multi-reference conflict case** with independently verified, applicable references processed by existing precedence logic.
3. **Null human evidence** that can be represented honestly under current source hierarchy.
4. **Real source-unavailable retrieval case** from a frozen retrieval snapshot.
5. **Standalone RCT/observational supporting-source expectations**, if added as supporting rather than governing evidence without changing precedence rules.

The corpus should not grow merely by repeating already-covered EMA positive-indication, WHO, ESCOP, or meta-analysis patterns.
