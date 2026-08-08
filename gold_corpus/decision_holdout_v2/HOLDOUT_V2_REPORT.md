# Fresh Decision Holdout v2 — 2026-08-08

## Design
Five new botanical/indication questions were frozen before engine execution. Reference labels use a different publication from the engine-side snapshot, and the listed PMIDs were not present in the repository before this holdout was created. This is a decision-generalization holdout; it does not claim to validate live internet retrieval because the engine was run against independently captured evidence snapshots.

## Results
- Scored: 5/5
- Correct: 1/5
- Agreement: **20.0%**
- Macro-F1: **0.3333**
- Serious-safety false negatives: 0
- Regulatory false negatives: 0
- False NO-GO: 0

| Case | Reference | Engine | Match |
|---|---|---|---|
| Lavender / anxiety | GO | INSUFFICIENT EVIDENCE | No |
| Boswellia / joint/OA | GO | INSUFFICIENT EVIDENCE | No |
| Silymarin / liver/NAFLD | GO WITH CAUTION | INSUFFICIENT EVIDENCE | No |
| Garlic / cardiovascular/BP | GO WITH CAUTION | INSUFFICIENT EVIDENCE | No |
| Elderberry / respiratory | INSUFFICIENT EVIDENCE | INSUFFICIENT EVIDENCE | Yes |

## Root cause
The dominant failure is **Evidence Direction Interpretation**, not candidate discovery or taxonomic transport. The evidence records reach the correct candidate and are recognized as systematic-review/meta-analysis level, but phrases such as `significant anxiolytic effects`, `improved osteoarthritis symptoms`, and `significantly reduces biochemical and transaminase levels` are still normalized to `Evidence_Direction=unclear` in several cases. The final scientific policy therefore falls through to INSUFFICIENT EVIDENCE.

No production rule was changed after viewing this holdout. These five cases are now development/regression material and must not be reused as a future unseen validation set.

## Reference adjudication closure
Cases 005 and 023 from Holdout v1 were adjudicated to EXPERT REVIEW REQUIRED because newer same-domain evidence conflicts with their older single-source benchmark labels. The original source-grounded GoldCase files remain unchanged; only a dated validation overlay supersedes the final benchmark label. With that adjudication, the old 15-case set is 15/15 as a regression suite. This is **not** an independent validation score.
