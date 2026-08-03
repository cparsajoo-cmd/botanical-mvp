# Evidence records connection fix

Changed `indication_candidate_discovery.py` so indication-centric discovery:

- reads persisted `engine.evidence_records_df` in addition to session and scientific evidence frames;
- includes structured indication/outcome/result fields when constructing evidence text;
- keeps human-readable source locators in `Evidence_Source`;
- keeps stable evidence identifiers in `Source_Record_IDs`;
- deduplicates identical evidence records across active evidence frames.

Regression coverage:

- `test_indication_evidence_records_connection.py`
- updated `test_indication_no_leakage.py`

Focused result: 38 relevant tests passed.

The complete repository suite could not be collected in this container because the optional `supabase` and `streamlit` packages are not installed here. This is an environment limitation; focused tests for the modified discovery path passed.
