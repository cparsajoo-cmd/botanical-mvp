# Fresh Unseen Decision Holdout v4 — 10 Case Blind Run

Frozen: 2026-08-08

## Protocol

Ten botanical/indication cases not used in prior decision-remediation holdouts were selected. Reference labels were fixed from peer-reviewed publications before engine execution. For every case the reference PMID is distinct from every PMID in the engine-side frozen evidence snapshot. No production rule, threshold, classifier, retrieval behavior, or decision policy was changed after scoring began.

## Result

- Correct: 2 / 10
- Agreement: 20.0%
- Macro-F1: 0.148
- Serious safety false negatives: 0 (no NO-GO-SAFETY reference cases in this efficacy-focused set)
- Regulatory false negatives: 0 (no NO-GO-REGULATORY reference cases in this efficacy-focused set)
- False NO-GO: 0

This is an efficacy/uncertainty stress holdout, not a balanced six-class safety/regulatory benchmark. The result must not be represented as overall platform accuracy.

## Case results

| Case | Reference | Engine | Match |
|---|---|---|---|
| Hibiscus / mild-moderate hypertension | GO WITH CAUTION | GO WITH CAUTION | yes |
| Nigella / hypertension | GO WITH CAUTION | GO | no |
| Fennel / primary dysmenorrhea | GO | GO | yes |
| Sage / menopausal hot flashes | GO WITH CAUTION | GO | no |
| Artichoke / hyperlipidemia | GO WITH CAUTION | GO | no |
| Vitex / PMS | GO WITH CAUTION | GO | no |
| Flaxseed / hypertension | GO WITH CAUTION | GO | no |
| Fenugreek / T2DM glycemic control | GO WITH CAUTION | EXPERT REVIEW REQUIRED | no |
| Passiflora / anxiety | GO WITH CAUTION | GO | no |
| Silymarin / chronic liver support | EXPERT REVIEW REQUIRED | GO | no |

## Root-cause pattern

The dominant error is overconfident GO: six caution references and one expert-review reference were flattened to GO. This is not a recurrence of botanical identity transport or the legacy Decision_Class authority bug. Evidence reaches the candidate and Final_Decision_Status is being read.

The remaining generalization gap is semantic/calibration coverage in final-decision evidence resolution:

1. Caution language is incomplete. Phrases such as `more evidence is needed`, `modest`, `variability`, `remaining uncertainties`, and methodological limitations are not consistently converted to SUPPORTIVE_WITH_CAUTION.
2. Some positive clinical language is still not assigned a usable direction (`potentially effective`, `all included trials positive`, `majority ... reported reduced anxiety`).
3. A positive direction plus an equally ranked unclear/insufficient synthesis can still collapse to SUPPORTIVE instead of escalating uncertainty (Silymarin).
4. Endpoint-level partial null findings can become full conflict rather than cautious support (Fenugreek), showing that evidence aggregation is not yet endpoint-aware enough.

## Interpretation

The new retrieval changes did not solve the principal scientific-decision generalization problem. The next remediation should be a general Evidence Certainty / Limitation Semantics layer, tested on a separate development corpus, rather than adding plant-specific rules. v4 is now exposed and must be treated as regression/development data after this run.
