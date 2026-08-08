# Independent Holdout E2E Validation v1.0

Total prospective holdout cases: **15**. Scored without GoldCase evidence injection: **2**. Structurally blocked: **13**.

Executable-subset agreement: **1/2 = 50.0%**; Macro-F1: **0.667**.

## Scored cases

- refgrounded_001_melissa_officinalis_sleep: reference **GO**, engine **GO**, match=True.
- refgrounded_003_matricaria_chamomilla_sleep: reference **GO WITH CAUTION**, engine **GO**, match=False.

## Root-cause analysis

**Case 003 (Matricaria chamomilla, sleep):** reference GO WITH CAUTION, engine GO. The independent systematic review carries mixed/conditional efficacy across sleep endpoints, but the current final-decision policy only creates GO WITH CAUTION from safety/regulatory `ELIGIBLE_WITH_RESTRICTIONS`. A scientific conditional-support state therefore falls through to GO. Responsible path: `evidence_interpretation.py` -> `final_decision_policy.py` -> `botanical_rd_candidate_engine.py`. **No remediation was made in this holdout phase.**

## Structural blockers

- `CANDIDATE_DISCOVERY_ZERO_CANDIDATES` (5): refgrounded_004_ginkgo_biloba_cognitive, refgrounded_005_cimicifuga_racemosa_menopausal, refgrounded_009_melissa_officinalis_mental_stress, refgrounded_010_passiflora_incarnata_mental_stress, refgrounded_012_lavandula_angustifolia_sleep
- `QUESTION_SCHEMA_NOT_EXECUTABLE` (8): refgrounded_007_valeriana_officinalis_preparation_spec, refgrounded_008_ginkgo_biloba_preparation_spec, refgrounded_011_matricaria_chamomilla_indication_evidence, refgrounded_013_echinacea_purpurea_identity_quality, refgrounded_014_ginkgo_biloba_safety_interaction, refgrounded_015_hypericum_perforatum_preparation_spec, refgrounded_017_matricaria_chamomilla_identity_quality, refgrounded_023_momordica_charantia_null_fbg

These blockers are validation findings, not silently imputed inputs. Cases with no indication/dosage-form compatible question are not forced through an indication-driven engine, and cases whose indication is absent from production candidate discovery are not seeded with the Gold botanical.

## Next action based on data

Do **not** tune against this holdout. Preserve this result. The next engineering phase should address the demonstrated architectural blockers on development fixtures: broaden candidate discovery beyond the exact hard-coded indication map and define a domain-appropriate E2E path for preparation/identity/safety cases. Separately, reproduce the Case 003 scientific-caution loss on development data before changing final-decision policy.
