# Evidence Conflict + Freshness Handling

## Scope
This remediation addresses two root causes demonstrated by Fresh Holdout v3 without adding botanical-specific decision rules:

1. Governing review text that explicitly says the evidence is debated/conflicting/not definitive was previously flattened into an automatic GO.
2. A positive systematic review could remain authoritative even when a directly relevant clinical trial published after that review reported a null/negative direction.

## Changes
- Added final-decision-only detection of explicit controversy language (`matter of debate`, `conflicting evidence`, `not definitive`, etc.). Such a governing source now produces `CONFLICT` and therefore `EXPERT REVIEW REQUIRED`.
- Added publication-year propagation from PubMed XML -> evidence collection -> frozen validation records -> engine evidence records.
- Added a narrow freshness safeguard: a directly relevant clinical trial published after the newest governing review can challenge a supportive review when the newer study is null/negative. The lower-tier study does not replace the review; it triggers expert review because the older synthesis cannot contain later contradictory evidence.
- No freshness conflict is invented when publication year is missing.
- An older lower-tier trial does not override a newer positive systematic review.

## Fresh Holdout v3 regression
This set is no longer independent validation and is used only as regression.

- Ginger: GO -> EXPERT REVIEW REQUIRED (fixed)
- Cranberry: GO -> GO (preserved)
- Peppermint: GO -> GO (preserved)
- Rhodiola: GO -> EXPERT REVIEW REQUIRED (fixed after publication-year metadata was propagated)
- Hawthorn: remains GO vs reference GO WITH CAUTION. This was intentionally not patched because the frozen engine evidence set does not contain the newer cautionary evidence needed to justify caution.

Regression agreement therefore moves from 2/5 to 4/5, but this number is not an independent validation metric.

## Tests
- Focused decision/validation suite: 54 passed, 0 failed.
- Conflict/freshness + publication-year + retrieval tests: 12 passed, 0 failed (with local Supabase dependency stub only for import collection).

## Scientific interpretation
The remaining Hawthorn mismatch is an evidence-set coverage problem, not a decision-semantics problem. A decision engine cannot infer caution from evidence it never retrieved.
