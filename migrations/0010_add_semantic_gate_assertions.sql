-- Additive storage for record-level semantic safety/regulatory assertions.
-- Raw/source fields remain unchanged; this JSONB column stores model-derived
-- assertions with supporting spans and provenance for shadow evaluation.

alter table if exists public.evidence_records
    add column if not exists llm_gate_assertions jsonb;

comment on column public.evidence_records.llm_gate_assertions is
    'Record-level LLM semantic safety/regulatory assertions. Additive model output; never overwrites source evidence and is interpreted by deterministic gate policy.';
