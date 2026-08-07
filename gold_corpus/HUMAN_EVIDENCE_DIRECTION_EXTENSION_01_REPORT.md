# Human Evidence Direction Benchmark — Extension 01

Date: 2026-08-07

This is an add-only **direction-only** benchmark extension. It does not modify Gold Cases or production logic.

## Source integrity

All 12 records correspond to real PubMed records verified before inclusion.
Three mixed records use curator-written summaries and are explicitly labeled
`curated_summary_from_abstract`; they are not presented as verbatim quotations.

## Composition

- Positive: 3
- Null: 2
- Negative: 4
- Mixed: 3
- Total: 12

## Baseline against the existing direction classifier

- Direction: 1/12 = 8.3%

By expected direction:
- Positive: 0/3
- Null: 1/2
- Negative: 0/4
- Mixed: 0/3

## Important scope note

This extension intentionally does **not** score study-design classification.
The frozen inputs are result/conclusion excerpts, and most do not contain the
design wording needed to fairly test a study-design classifier. Publication type
is retained as source metadata only.

No production phrases or scoring rules were changed in response to these results.

## Why this extension exists

The first frozen benchmark exposed weak negative and mixed classification.
This extension adds independent real records rather than tuning on the first set.

## Next step

Combine the original frozen benchmark with this independent extension for a
larger calibration set. Any production change should occur only in a separate,
explicitly authorized calibration phase and must be evaluated against both
frozen sets without changing their truth labels.
