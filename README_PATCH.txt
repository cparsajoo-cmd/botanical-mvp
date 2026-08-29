Scientific Directness / Evidence Qualification v11

General, indication-agnostic fix. No plant-, disease-, sleep-, diabetes-, or dosage-form-specific production rules.

Production files to overwrite:
- indication_candidate_discovery.py
- evidence_adjudication_engine.py
- candidate_shortlisting.py
- step_rd_candidates.py

Core fixes:
1. Requested query context persisted in Target_Indication can no longer re-enter main Stage-5 scoring as source evidence.
2. Structured AI adjudication explicitly identifies direct indication-outcome evidence IDs and the direct-human subset.
3. Mechanistic/background/disease-context evidence cannot manufacture efficacy direction or human-evidence strength.
4. Final Priority status requires AI-verified direct outcome evidence when schema-v2 adjudication is available.
5. AI output remains downgrade/cap only; safety/regulatory hard stops remain authoritative.

Validation in local sandbox:
- py_compile passed for all four production files.
- 160 focused/general scientific regression tests passed.
- Full-suite smoke reached 2,220 passed + 3 xfailed before stopping on a local Streamlit stub limitation (stub lacked set_page_config), not a repository-code failure.
