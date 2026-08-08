# Fresh Unseen Decision Holdout v3 — Frozen Result

## Status
This holdout was frozen before engine execution. No production rule was changed during scoring. After this run, these five cases are no longer considered unseen and must only be used for development/regression.

## Result
- Scored: 5
- Correct: 2
- Agreement: 40.0%
- Macro-F1: 0.5714
- Serious safety false negatives: 0
- Regulatory false negatives: 0
- False NO-GO: 0

| Case | Reference | Engine | Match |
|---|---|---|---|
| v3_001_ginger_cinv | EXPERT REVIEW REQUIRED | GO | no |
| v3_002_cranberry_ruti | GO | GO | yes |
| v3_003_peppermint_ibs | GO | GO | yes |
| v3_004_rhodiola_fatigue | EXPERT REVIEW REQUIRED | GO | no |
| v3_005_hawthorn_hf | GO WITH CAUTION | GO | no |

## Root-cause findings

### v3_001 Ginger / CINV
The evidence set contains a positive recent systematic review plus an older systematic review explicitly describing efficacy as debated/not definitive. The production decision remained GO. This identifies a semantic conflict-propagation gap: explicit uncertainty/debate language is not reliably converted into a governing conflict/review-required state.

### v3_004 Rhodiola / fatigue
The engine-side set contains a positive older review and a newer randomized study reporting only trivial-to-small effects. The final decision remained GO. This exposes a hierarchy/freshness problem: source-tier precedence can allow an old review to dominate materially newer evidence without a recency/staleness challenge.

### v3_005 Hawthorn / chronic heart failure
The engine-side set is predominantly positive and older, whereas the frozen independent 2026 reference supports adjunctive potential but explicitly calls for cautious interpretation because evidence is limited for some interventions and direct comparisons are scarce. The engine returned GO. This is primarily an evidence-set freshness/coverage limitation: caution cannot be inferred if the retrieved set does not contain the newer limitation signal.

## Interpretation
The retrieval diversification patch improved query architecture, but it does not by itself guarantee that the final evidence set is current, contradictory where appropriate, or semantically conflict-aware. The next remediation should therefore focus on general conflict semantics and evidence freshness, not plant-specific rules.
