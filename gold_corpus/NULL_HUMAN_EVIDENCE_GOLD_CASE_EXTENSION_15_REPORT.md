# Extension 15 — Standalone Null Human Evidence Gold Case

**Date:** 2026-08-07  
**Scope:** Gold Case / Gold Corpus metadata only. No production engine logic changed.

## Scientific gap closed

The uploaded corpus already contained null RCT records, but no active governing Gold Case represented a statistically null human-evidence result as the Ground Truth outcome.

Case 023 closes only that gap.

## Added Gold Case

**Case 023 — Momordica charantia L., fasting blood glucose**

Critical source:
- Laczkó-Zöld E, Csupor-Löffler B, Kolcsár E-B, et al.
- *The metabolic effect of Momordica charantia cannot be determined based on the available clinical evidence: a systematic review and meta-analysis of randomized clinical trials.*
- Front Nutr. 2024;10:1200801.
- PMID **38274207**
- PMCID **PMC10808600**
- DOI **10.3389/fnut.2023.1200801**
- PubMed: https://pubmed.ncbi.nlm.nih.gov/38274207/

For the fasting-blood-glucose change-score meta-analysis, the source reports no statistically significant effect versus placebo (MD -0.03; 95% CI -0.38 to 0.31).

## Scope control

The Gold Case is limited to the fasting-blood-glucose endpoint. It does not claim that every metabolic endpoint is null, and it does not infer a dose, preparation, plant part, route, or population that is not necessary for the bounded claim.

The repository has no dedicated `NULL` assertion state. Therefore the source is represented using the existing `SUPPORTS_INDICATION + ABSENT` Ground Truth semantics, while benchmark metadata explicitly records `scientific_result_kind = NULL_STATISTICAL_RESULT`. No production vocabulary or production classifier was changed.

## Duplicate control

Before inclusion, PMID **38274207** and DOI **10.3389/fnut.2023.1200801** were searched across the uploaded repository and were absent.

The PMID was **not** duplicated into a second corpus-extension JSON merely to increase the independent-record count. The independent corpus-record count therefore remains **181**; Gold Case coverage increases from **21 to 22 active cases**.

## Production leakage control

No production file was changed. In particular, this extension does not modify:
- `evidence_interpretation.py`
- source precedence
- applicability logic
- scoring
- safety logic
- regulatory logic
- retrieval ranking
- market logic

## Freeze implication

The standalone null-evidence coverage gap is now closed. This does **not** make the corpus globally freeze-ready: external expert review, locking, and broader frozen E2E snapshot coverage remain governance prerequisites.
