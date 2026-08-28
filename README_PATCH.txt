General scientific outcome-specificity + human-evidence coherence patch v4

Production files to overwrite:
- evidence_adjudication_engine.py
- candidate_shortlisting.py
- step_rd_candidates.py

What it fixes generically:
1. Human-study classification recognizes explicit clinical/RCT/review design descriptors even when Population is blank.
2. A human record can be indication-relevant without being an indication-specific efficacy outcome. AI evidence-strength calibration now counts only DIRECT + HUMAN + outcome-specific records.
3. Direct_Indication_Evidence_Count now requires an indication-specific reported outcome in the primary scientific evidence tier.
4. A row labelled Direct human/clinical with zero outcome-specific direct evidence cannot remain GO/GO WITH CAUTION; it is routed to EXPERT REVIEW REQUIRED and marked with CONTRADICTION_NO_OUTCOME_SPECIFIC_DIRECT_EVIDENCE.
5. No indication-, plant-, or dosage-form-specific rules were added.

Validation in local dependency-stubbed test environment:
- py_compile passed for modified production files.
- 84 focused regression tests passed, including existing adjudication, calibration, shortlist, Stage-6 gate, scientific-integrity tests and 4 new generic tests.
- Full GitHub CI remains authoritative because the local runtime lacks the production Streamlit/OpenAI/Supabase dependencies.
