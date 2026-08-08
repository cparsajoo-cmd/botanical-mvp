# Reference-Grounded Scientific Validation — corrected protocol

The previous release-gate draft incorrectly required two independent human adjudicators even though this project is intentionally pursuing a source-grounded validation strategy without an external expert panel.

That requirement has been removed.

## What can be validated without external experts
The engine can be tested against decisions frozen from independent, traceable, high-authority reference evidence. The reference evidence must be selected and frozen before the engine run, and the evidence that defines the reference answer must not be supplied to the engine as its test input.

This supports a bounded claim of **reference-grounded validation on the frozen target benchmark/domain**.

It does **not** support the claims "human expert agreement", "clinical validation", or "regulatory approval".

## Final finite protocol
One 24-case balanced final holdout:
- 4 GO
- 4 GO WITH CAUTION
- 4 EXPERT REVIEW REQUIRED
- 4 NO GO SAFETY
- 4 NO GO REGULATORY
- 4 INSUFFICIENT EVIDENCE

Every case must have traceable independent reference provenance. Cases used to build or remediate engine 1.4.0 are excluded.

Release thresholds remain:
- accuracy >= 0.80
- macro-F1 >= 0.75
- GO precision >= 0.85
- CAUTION recall >= 0.75
- EXPERT REVIEW recall >= 0.70
- serious-safety false negatives = 0
- regulatory false negatives = 0
- insufficient-evidence miss rate <= 0.20

There is no human-adjudicator or inter-rater-agreement requirement in this protocol.

The next task is to populate and freeze the 24 genuinely new reference-grounded cases. No production rule should be changed while constructing that final benchmark.
