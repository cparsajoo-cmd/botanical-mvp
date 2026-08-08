# Evidence Interpretation / Uncertainty Propagation Remediation

## Scope
This remediation targeted the remaining scientifically demonstrated mismatches in Cases 003, 005 and 011 after evidence transport/domain-routing repair. Case 023 remained reference-currency/adjudication only.

## Production changes
1. Final-decision-only review-conclusion interpretation now recognizes explicit conclusion language such as "insufficient evidence to support" and "appears efficacious/effective" without modifying the frozen scoring calibration in `evidence_interpretation.py`.
2. A governing systematic review that is supportive but explicitly mixed/inconsistent maps to `GO WITH CAUTION`, rather than unconditional GO or automatic expert-conflict escalation.
3. Same-rank positive vs null/negative systematic reviews remain `EXPERT REVIEW REQUIRED`; they are not averaged.
4. Direct botanical+indication records are no longer dropped merely because compound-specific evidence exists. Only plant records whose structured target indication matches the active question are added, avoiding whole-plant cross-indication pooling.
5. `final_status_from_engine_row()` recognizes scientific `Go with caution` decisions even when safety/regulatory eligibility itself is unrestricted.

## Regression outcomes on the historical 15-case set
This is not a new independent validation score; the set has already been used for diagnosis/remediation.

- Case 003: GO -> GO WITH CAUTION (corrected)
- Case 011: INSUFFICIENT EVIDENCE -> GO (corrected)
- Case 005: GO -> EXPERT REVIEW REQUIRED. The frozen snapshot contains two same-tier systematic reviews with opposing conclusions, so this is now a reference/adjudication conflict rather than a demonstrated engine failure.
- Case 023: remains EXPERT REVIEW REQUIRED for the same reason: newer same-tier evidence conflicts with the frozen reference.

Historical regression agreement therefore becomes 13/15, with the two remaining mismatches both requiring reference adjudication rather than further production tuning.

## Tests
Focused remediation/domain/decision tests: 12 passed.
The production import integrity test passes when run independently.
The broad suite progressed beyond 82% without a new remediation-related failure before the environment execution limit was reached. Known collection blockers remain missing `supabase` / `streamlit` dependencies. One historical Case 003 characterization test already failed on the pre-remediation baseline and is not caused by this patch.
