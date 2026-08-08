-- Roll back dedicated LLM assertion provenance fields.
-- WARNING: dropping these columns deletes any backfilled LLM-derived values.

alter table if exists public.evidence_records
    drop column if exists llm_safety_signal;

alter table if exists public.evidence_records
    drop column if exists llm_result_direction;
