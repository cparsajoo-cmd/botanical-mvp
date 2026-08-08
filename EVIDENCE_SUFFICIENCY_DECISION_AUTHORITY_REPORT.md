# Evidence Sufficiency / Final Decision Authority Remediation

## Scope
This phase audited the hypothesis that a single systematic review/meta-analysis was being rejected solely because it lacked a second independent publication.

## Proven root cause
The hypothesis was not supported by the structured final-decision policy. `resolve_scientific_evidence()` + `decide_final()` can return GO from one supportive top-tier systematic review/meta-analysis when safety/regulatory eligibility passes.

The actual defect was a dual-source-of-truth problem:
- the structured six-class `FinalDecision` could be GO;
- legacy `Decision_Class` could simultaneously remain `Low priority / insufficient data` because it is score-tier oriented;
- benchmark/consumers that inferred final status from legacy `Decision_Class` therefore converted a genuine structured GO into `INSUFFICIENT EVIDENCE`.

## Remediation
1. Added `Final_Decision_Status` to engine output as the authoritative six-class decision field.
2. `final_status_from_engine_row()` now reads `Final_Decision_Status` first and falls back to legacy parsing only for older rows/artifacts.
3. Multi-compound merge explicitly recomputes/preserves the same structured final status.
4. Legacy `Decision_Class` remains available for backward compatibility; it is no longer the source of truth for six-class validation.

## Regression evidence
Focused/related regression: 277 passed, 0 failed.
Structured-decision authority tests: 4 passed, 0 failed.

## Development-set observation (not independent validation)
After this correction, fresh-holdout-v2 cases previously used for diagnosis changed as follows:
- Lavender/anxiety: INSUFFICIENT -> GO (matches reference)
- Boswellia/OA: INSUFFICIENT -> GO (matches reference)
- Silymarin/liver: GO (reference is GO WITH CAUTION)
- Garlic/BP: GO (reference is GO WITH CAUTION)
- Elderberry/respiratory: GO (reference is INSUFFICIENT)

These five cases are no longer an unseen holdout. They are diagnostic/regression cases only.

## Next proven gap
The remaining failures are not corroboration-count failures. They are nuance/uncertainty propagation failures: supportive evidence carrying limitations/uncertainty is being collapsed to unconditional positive, while weak/uncertain evidence can also be interpreted as positive. This requires a separate Evidence Uncertainty Semantics audit before any new rule is written.
