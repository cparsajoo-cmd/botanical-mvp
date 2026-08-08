# General Evidence Direction Remediation Report

## Scope
This phase remediates the proven general-language evidence-direction gap exposed by fresh holdout v2. No botanical-specific or indication-specific lookup was added.

## Production change
`evidence_interpretation.py` was extended with bounded, polarity-aware clinical outcome patterns for:
- significant beneficial/anxiolytic/therapeutic effects;
- improvement of disease-qualified symptoms/outcomes;
- present-tense significant reduction/improvement language;
- clinically beneficial hedged language such as `may be beneficial`;
- substantial reduction in clinical symptom burden;
- common liver-injury marker reduction language.

Explicit adverse-effect wording and negated/null wording remain protected from positive classification.

## Fresh-holdout-v2 regression direction result
Before remediation, all five engine-side evidence texts were `unclear`.
After remediation:
- v2_001 Lavender/anxiety -> positive
- v2_002 Boswellia/OA -> positive
- v2_003 Silymarin/liver -> positive
- v2_004 Garlic/BP -> positive
- v2_005 Elderberry/respiratory -> positive

This v2 set is now a development/regression set and is not an independent validation set.

## Important downstream finding
Correcting Evidence_Direction alone does not make all final decisions match the frozen v2 references. Several rows still end as `INSUFFICIENT EVIDENCE` because the candidate-level evidence layer marks a single systematic-review source as `Partial Evidence` / `POSITIVE BUT INSUFFICIENT` when there is no independent corroborating publication. That is a distinct downstream evidence-sufficiency/corroboration policy issue and was not changed in this phase.

## Regression
Focused and dependent tests: 189 passed, 0 failed.

## Next data-driven target
Audit whether the current independent-corroboration requirement is scientifically appropriate when the governing evidence is already a high-quality systematic review/meta-analysis, and determine whether review-level synthesis is being incorrectly treated like a single primary study.
