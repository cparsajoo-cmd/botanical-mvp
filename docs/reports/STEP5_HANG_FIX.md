# Step 5 hang fix

The previous evidence-record connection fix made indication discovery scan every evidence row once for every candidate plant. With thousands of catalogue plants and persisted evidence rows, this produced quadratic work and left Streamlit on “Discovering and scoring R&D candidates…”.

This correction:

- builds a plant-keyed evidence index once per discovery run;
- performs constant-time exact plant lookups in the candidate loop;
- preserves a lightweight alias fallback without rescanning evidence rows;
- loads `evidence_records` with joined `plants` and `sources`, because the raw table contains foreign keys rather than the scientific name needed for attribution;
- caches the joined evidence table in `step_rd_candidates.py` and passes it into the cached engine;
- keeps source URLs and evidence record IDs separate.

Upload the three production files to the project root, reboot the Streamlit app, and rerun Step 5.
