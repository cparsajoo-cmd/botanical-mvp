# Canonical Scientific Assertion Pipeline — Engine 1.6.0

## Root cause
The project had multiple competing scientific-direction authorities:
- source/connector Result_Direction
- LLM_Result_Direction
- legacy Evidence_Direction
- evidence_interpretation text heuristics
- final_decision_policy's second text interpretation

Final body-of-evidence resolution ignored the structured direction fields and re-read prose. Strong evidence could therefore reach the correct hierarchy but still become `unclear` because a new wording was absent from one of the regex vocabularies.

A second instance of the same architecture existed in Safety: Safety_Signal reached the record but was reinterpreted by the free-text safety vocabulary rather than used as an already-structured assertion.

Regulatory structured fields also existed but were not included in the record-level assertion text passed to the regulatory gate.

## Architecture change
New single precedence for efficacy direction:
1. source/connector `Result_Direction`
2. `LLM_Result_Direction`
3. legacy `Evidence_Direction` compatibility value
4. raw-text classifier fallback for legacy records only

`evidence_body_assessment.py` now consumes this canonical record direction instead of always invoking the text classifier.

## Standardization activation
`evidence_standardizer.py` no longer treats a reliable Evidence_Level as a reason to skip result-direction extraction. If Result_Direction is absent and the optional structured extractor is available, extraction runs; reliable connector fields such as Evidence_Level are never overwritten.

The LLM safety output is now explicitly constrained to:
- Serious
- Moderate
- Reassuring
- None
- Unknown

Structured Safety_Signal values are normalized into the SafetyAssertion contract directly. They no longer have to be rediscovered by hazard regex.

## Regulatory transport
Record-level `Regulatory_Status`, `Novel_Food_Status`, and `Regulatory_Evidence` are now transported to the authoritative regulatory barrier/gate path. Candidate context supplied to regulatory applicability now includes indication, dosage form and market.

## Scientific invariant
Final Decision must consume structured assertions when present. Raw prose interpretation is a legacy fallback, not a competing source of truth.

## Version
Decision Engine 1.5.2 -> 1.6.0.

## Tests
Focused scientific-decision / evidence / safety / regulatory / E2E regression:
188 passed, 0 failed.

Historical exposed regression sets were not modified:
- v3: 60%
- v4: 90%
- v5: 80%

Those numbers remain regression-only and are not new validation estimates.

## Remaining explicit data-contract gap
The repository does not currently carry a distinct structured field for regulatory authorization state such as:
`authorized / not_authorized / pending / terminated / unknown`.

Therefore Engine 1.6.0 can consume existing Regulatory_Status / Novel_Food_Status / Regulatory_Evidence, but it must not infer "authorization not granted" solely from absence of an authorization field. A future regulatory data-contract phase should add that state from authoritative connector data rather than another prose regex.

## Next step
Do not patch historical holdouts. Merge 1.6.0, let CI run the full dependency-complete suite, then perform one genuinely new frozen reference-grounded validation on records generated through the canonical standardization path (so Result_Direction is present when structured extraction is available).
