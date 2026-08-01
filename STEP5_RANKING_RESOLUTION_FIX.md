# Step 5 ranking-resolution correction

Scope is deliberately limited to the authoritative plant-level ranking layer.
No evidence ingestion, normalization, validation, discovery, report, persistence,
or database logic was changed.

## Changes

1. **Indication relevance (max 35)** is no longer a binary 35-point award for
   every plant with any human signal. Within the same evidence stratum it now
   uses modest diminishing increments for independent direct sources and the
   breadth of indication-specific concepts. Evidence hierarchy and study depth
   remain in the separate Evidence Quality component.

2. **Safety & regulatory (max 15)** no longer treats `No explicit flag found`
   or `Not assessed` as proof that a candidate is clean. Missing information now
   receives a conservative neutral score. Explicit reassuring, adverse, and
   prohibitive evidence remains differentiated.

3. **Novelty & market (max 5)** ignores generated placeholders such as
   `Indication-derived candidate` and `Search not performed`. When no real
   market work has been performed, the output is honestly `Not assessed` rather
   than a fabricated differentiation.

4. **Reproducibility metadata** was bumped from
   `authoritative-plant-v1` to `authoritative-plant-v1.1`, because the
   authoritative plant-level scoring logic changed.

## Deliberately unchanged

- Candidate entry and indication-centric discovery
- Evidence collection and evidence-record attribution
- Evidence normalization and validation
- Compound-support cap (5 points)
- Scientific gates and shortlist thresholds
- Report generation and decision persistence
- Database schema and migrations

## Tests

Focused ranking, sensitivity, and metadata tests: `94 passed`.
The complete repository suite could not be collected in this container because
`streamlit` and `supabase` are not installed here; this is an environment
limitation rather than a failure in the changed modules.
