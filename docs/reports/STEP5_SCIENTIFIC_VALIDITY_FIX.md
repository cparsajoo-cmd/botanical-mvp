# Step 5 scientific-validity correction

This patch is limited to indication-centric Step 5 discovery and plant-level shortlisting.
It does not modify ingestion, Supabase schema, normalization, validation, reports, UI,
or compound-substitution mode.

## Changes

1. **Result direction is preserved per evidence record.**
   Positive, null/no-effect, harmful, mixed, and unreported outcomes are no longer
   treated as equivalent.
2. **Null or adverse human evidence cannot create a Go recommendation.**
   If no positive result exists and human records report no effect or harm, the
   candidate becomes Exploratory and its indication/evidence scores are reduced.
3. **Mixed results receive a transparent consistency discount.**
4. **Preparation applicability is record-specific.**
   Evidence from a capsule/standardized extract is not treated as directly applicable
   to an infusion/tea request. Explicit mismatches are excluded for the selected
   product form; unknown preparation remains unknown.
5. **Safety and interaction data are propagated from evidence records.**
   Missing safety data is not interpreted as clean safety.
6. **Go is now gated.**
   It requires all of: a high authoritative score, predominantly positive outcomes,
   compatible preparation, and explicit reassuring safety evidence. Otherwise the
   candidate remains Investigate even if scientifically shortlisted.
7. **Reproducibility version bumped** to `authoritative-plant-v1.2`.

## New output fields

- `Result_Direction` (raw record-level output)
- `Preparation_Applicability` (raw record-level output)
- `Outcome_Consistency` (plant-level summary)
- `Positive_Result_Count`
- `Null_Negative_Result_Count`
- `Unreported_Result_Count`
