# Evidence Uncertainty Semantics Remediation

## Scope
This phase changes only the semantic handling of uncertainty that is explicitly present in scientific evidence text. It does not add plant-specific rules and does not infer uncertainty that the engine never retrieved.

## Changes
- Explicit cautious-support wording such as `may be beneficial`, `requires confirmation`, and `further high-quality trials` now resolves to `SUPPORTIVE_WITH_CAUTION` rather than unconditional `SUPPORTIVE`.
- Explicit firm-uncertainty wording such as `evidence remains uncertain` and `insufficient for firm conclusions` resolves to `INSUFFICIENT` even when the same sentence mentions a possible benefit.
- Unhedged positive evidence remains `SUPPORTIVE`.
- Negative/null evidence is not promoted to caution merely because authors call for more studies.

## Regression result on the previously exposed v2 cases
These cases are regression cases only, not an independent validation set.

- Lavender/anxiety: GO -> GO (unchanged, correct)
- Boswellia/OA: GO -> GO (unchanged, correct)
- Silymarin/liver: GO -> GO (reference: GO WITH CAUTION; unresolved here because the engine-side snapshot contains no uncertainty wording)
- Garlic/BP: GO -> GO WITH CAUTION (fixed by explicit `may be beneficial` semantics)
- Elderberry/respiratory: GO -> GO (reference: INSUFFICIENT; unresolved here because the engine-side snapshot is strongly positive and contains no uncertainty wording)

Regression agreement on these already-exposed cases changed from 2/5 after decision-authority reconciliation to 3/5. This is not a new holdout score.

## Tests
101 focused/related tests passed, 0 failed.

## Remaining root cause
The two remaining mismatches cannot be solved honestly by uncertainty semantics because the engine snapshots do not contain the uncertainty/contradiction present in the reference evidence. The next root cause is retrieval evidence-set completeness/representativeness: the engine must retrieve enough high-rank evidence to expose conflicting or uncertainty-bearing conclusions before the decision layer can reason over them.
