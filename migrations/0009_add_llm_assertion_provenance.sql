-- Preserve assertion provenance for model-extracted evidence fields.
--
-- result_direction and safety_signal are source/connector-authoritative fields.
-- Outputs produced by llm_extractor.py must never be written into them because
-- canonical_scientific_assertion.py intentionally gives source assertions
-- higher precedence than LLM-derived assertions.

alter table if exists public.evidence_records
    add column if not exists llm_result_direction text;

alter table if exists public.evidence_records
    add column if not exists llm_safety_signal text;

comment on column public.evidence_records.llm_result_direction is
    'Structured result direction extracted by an LLM; distinct from source/connector result_direction.';

comment on column public.evidence_records.llm_safety_signal is
    'Structured safety signal extracted by an LLM; distinct from source/connector safety_signal.';
