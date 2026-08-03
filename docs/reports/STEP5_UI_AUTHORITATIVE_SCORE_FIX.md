# Step 5 UI authoritative-score display fix

This change is intentionally limited to the Streamlit display layer.

## What changed

- The main Scientific shortlist and Exploratory tables now display the authoritative plant-level `R&D_Opportunity_Score` (falling back to `Overall_Score`).
- The legacy `Scientific_Triage_Score` is no longer shown in the main UI table.
- The full downloadable plant-level CSV is unchanged and still contains all audit/legacy columns.
- Rows are shown in descending authoritative-score order.
- No discovery, evidence ingestion, normalization, validation, scoring, thresholds, Supabase, or report-generation logic was modified.

## Tests

`test_step5_authoritative_score_display.py` verifies that:

1. the legacy score is absent from the user-facing table;
2. the authoritative score is displayed and used for ordering;
3. `Overall_Score` is used as a backward-compatible fallback when the alias is absent.
