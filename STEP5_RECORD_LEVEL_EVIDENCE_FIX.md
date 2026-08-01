# Step 5 record-level evidence depth fix

## Root cause

Indication discovery concatenated every evidence source for a plant into one synthetic row. The strongest hierarchy phrase found anywhere in that combined text was assigned to the whole plant, while `Candidate_Specific_Empirical_Row_Count` remained 1. This caused many botanicals with very different evidence bases to receive identical evidence-quality scores.

## Changes

- Emit one raw candidate row per independent evidence record.
- Preserve each record's own source ID, source URL, study type, hierarchy, result direction and Phase-5 validation summary.
- Treat ClinicalTrials.gov registry/protocol records without reported results as non-efficacy evidence.
- Require empirical support before direct indication text can receive direct-relevance credit.
- Compute evidence quality from the record-level hierarchy mix, independent-source depth, study-design diversity and result consistency.
- Deduplicate repeated source identifiers before scoring.
- Keep chemistry capped as supporting metadata only.

## Tests

Focused regression suite: 36 passed.

The full repository suite could not be collected in this local environment because the `supabase` package is not installed. This is an environment limitation; the focused discovery and shortlisting tests pass.
