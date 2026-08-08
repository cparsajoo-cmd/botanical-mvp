# Final Fresh Decision Holdout v5 — Blind Run

Frozen and run: 2026-08-08

## Protocol
Ten new cases were selected after the v4 remediation. Reference labels were frozen before engine execution. Reference PMIDs are distinct from engine-side PMIDs. No production rule, classifier, threshold, retrieval behavior, or decision policy was changed during scoring.

## Result
- Correct: 3 / 10
- Agreement: 30.0%
- Macro-F1: 0.525
- Serious safety false negatives: 0
- NO-GO-SAFETY recall in this set: 2 / 2
- False NO-GO: 1 (Kava: reference EXPERT REVIEW REQUIRED, engine NO GO SAFETY)
- Regulatory class was not represented, so this run is not a complete six-class freeze benchmark.

## Case results
| Case | Reference | Engine | Match |
|---|---|---|---|
| Curcuma / knee OA | GO WITH CAUTION | GO | no |
| Ashwagandha / stress-anxiety | GO WITH CAUTION | GO | no |
| Cinnamon / T2DM | GO WITH CAUTION | GO | no |
| Serenoa / BPH-LUTS | INSUFFICIENT EVIDENCE | GO | no |
| Psyllium / constipation | GO | GO | yes |
| Aristolochia / oral use | NO GO SAFETY | NO GO SAFETY | yes |
| Comfrey / oral use | NO GO SAFETY | NO GO SAFETY | yes |
| Saffron / depression | GO WITH CAUTION | GO | no |
| Pelargonium / ARI | GO WITH CAUTION | GO | no |
| Kava / anxiety | EXPERT REVIEW REQUIRED | NO GO SAFETY | no |

## Interpretation
The engine is not ready to freeze as Scientific Decision Engine v1.0. Safety hard-stop behavior generalized in the two serious-safety cases, but efficacy/certainty calibration did not generalize: all five GO-WITH-CAUTION references were flattened to GO, and the Serenoa null-efficacy case was also overcalled as GO.

This v5 set is now exposed and must not be reused as an unseen final benchmark after remediation.
