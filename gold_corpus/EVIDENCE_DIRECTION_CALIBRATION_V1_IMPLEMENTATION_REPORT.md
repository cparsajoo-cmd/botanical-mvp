# Evidence Direction Calibration V1 — Implementation Report

Date: 2026-08-07

## Scope

This is a bounded calibration of the existing free-text evidence-direction classifier.

Changed production file:
- `evidence_interpretation.py`

Not changed:
- Gold Case truth
- source precedence
- scoring weights
- safety rules
- regulatory rules
- market logic

## Calibration governance

The 24-record Calibration V1 set was frozen before this production change.
No PMID, benchmark text, or truth label was changed to improve the result.

A separate External Validation V2 set was then curated from 8 different PubMed
records, with zero PMID overlap with Calibration V1.

## Production change

The existing bounded phrase matcher was extended with generic clinical-outcome
constructions only. No plant-, indication-, PMID-, or Gold-Case-specific rule was added.

Added coverage includes generic forms such as:
- statistically significant change / greater reduction
- significantly reduced / greater improvement
- clinically effective
- no statistically significant effect / not significantly different
- no more effective than placebo / did not improve
- does not demonstrate beneficial effects
- contrast-driven mixed findings when positive and null/negative cues coexist

Negation handling was also strengthened for constructions using "neither" / "nor".

## Results

Pre-calibration frozen V1:
- 3/24 = 12.5%

Post-calibration Calibration V1:
- 21/24 = 87.5%

Original frozen 12-record set after calibration:
- 11/12 = 91.7%

Independent Extension 01 after calibration:
- 10/12 = 83.3%

External Validation V2 (8 new PubMed records, disjoint PMIDs):
- 7/8 = 87.5%

## Remaining error

External Validation V2 still misses one mixed-result example. Therefore this is
not claimed to be perfect or clinically validated. It is a measured improvement
of one bounded text-classification component.

## Regression

Targeted regression covering Gold Cases, Gold Corpus, E2E validation, and Phase-1
evidence-direction behavior:
- 248 passed
- 0 failed

## Scientific interpretation

The external 87.5% result is evidence that the calibration generalizes beyond the
24 records used for calibration, but it is not a claim of overall platform accuracy
or clinical validation.

## Post-calibration evaluation status clarification

Because Calibration V1 directly informed the generic production phrase-matcher changes described in this report, its post-change 21/24 score is a **calibration/training-set measurement**, not an independent holdout-validation estimate. It must not be used as headline evidence of out-of-sample performance.

External Validation V2 remains the disjoint post-calibration evaluation set currently available. Any future benchmark intended to estimate generalization must use records not consulted during rule design or calibration. This clarification changes benchmark governance/documentation only; no production code is changed here.
