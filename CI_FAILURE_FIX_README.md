# CI failure fix

Fixes `test_final_recommendation_can_differ_for_scientifically_valid_reasons`.

Root cause: the Stage-5 NaN/list hardening normalized `None` to `[]` for the optional direct-outcome ID fields. In this engine those values have distinct semantics: `None` means a legacy response where direct-outcome IDs were not part of the schema and lineage must be reconstructed; `[]` means the adjudicator explicitly found no direct-outcome evidence. Collapsing the sentinel prevented positive/negative adjudications from reaching the negative-evidence cap.

Change: preserve `None` only for `Direct_Outcome_Evidence_IDs` and `Direct_Human_Outcome_Evidence_IDs`; continue normalizing NaN/scalar/list values safely for all evidence-ID fields.

No scoring weights, shortlist thresholds, or UI behavior were changed.
