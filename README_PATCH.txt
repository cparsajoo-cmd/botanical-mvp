General scientific evidence-lineage fix v7

Production files:
- indication_candidate_discovery.py
- candidate_shortlisting.py
- evidence_adjudication_engine.py
- step_rd_candidates.py

Regression test:
- test_general_evidence_transport_and_ai_alignment_v7.py

Root causes fixed:
1) Source-derived outcome/study/evidence text used to establish relevance was not transported into Stage-5 output.
2) Canonical Stage-5 human/outcome flags were created in triage_audit_df but downstream AI was mistakenly given result_df, so AI never saw those canonical flags.
3) Direct_Indication_Evidence_Count had been conflated with the stricter outcome-specific evidence subset, causing all direct counts to collapse to zero when optional structured outcome fields were absent.
4) Empty priority-table UI incorrectly reported AI unavailable even when adjudication had run on unresolved candidates.

Semantics:
- Direct_Indication_Evidence_Count = independent primary-tier direct indication records.
- Outcome_Specific_Direct_Evidence_Count = stricter primary-tier subset with indication-specific reported outcome/source-result context.
- Outcome_Specific_Human_Evidence_Count = human subset of the above.
- All downstream AI consumes processed triage_audit_df when available.

No indication-specific or plant-specific rule was added.
