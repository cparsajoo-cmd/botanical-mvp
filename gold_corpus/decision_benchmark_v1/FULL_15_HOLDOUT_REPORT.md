# Full Independent Holdout E2E Validation — 15/15

Frozen prospective holdout: **15 cases**. Scored: **15/15**. Pending: **0**.

Final-decision agreement: **5/15 = 33.3%**. Macro-F1: **0.303**.

Serious-safety false negatives: **0**; regulatory false negatives: **0**; false NO-GO: **0**; expert-review overuse: **1**; insufficient-evidence misses: **2**.

## Case results

- refgrounded_001_melissa_officinalis_sleep: reference **GO**; engine **GO** — **PASS**.
- refgrounded_003_matricaria_chamomilla_sleep: reference **GO WITH CAUTION**; engine **GO** — **MISMATCH**.
- refgrounded_004_ginkgo_biloba_cognitive: reference **INSUFFICIENT EVIDENCE**; engine **INSUFFICIENT EVIDENCE** — **PASS**.
- refgrounded_005_cimicifuga_racemosa_menopausal: reference **INSUFFICIENT EVIDENCE**; engine **GO** — **MISMATCH**.
- refgrounded_007_valeriana_officinalis_preparation_spec: reference **EXPERT REVIEW REQUIRED**; engine **INSUFFICIENT EVIDENCE** — **MISMATCH**.
- refgrounded_008_ginkgo_biloba_preparation_spec: reference **EXPERT REVIEW REQUIRED**; engine **INSUFFICIENT EVIDENCE** — **MISMATCH**.
- refgrounded_009_melissa_officinalis_mental_stress: reference **GO**; engine **GO** — **PASS**.
- refgrounded_010_passiflora_incarnata_mental_stress: reference **GO**; engine **GO** — **PASS**.
- refgrounded_011_matricaria_chamomilla_indication_evidence: reference **GO**; engine **INSUFFICIENT EVIDENCE** — **MISMATCH**.
- refgrounded_012_lavandula_angustifolia_sleep: reference **GO**; engine **GO** — **PASS**.
- refgrounded_013_echinacea_purpurea_identity_quality: reference **EXPERT REVIEW REQUIRED**; engine **INSUFFICIENT EVIDENCE** — **MISMATCH**.
- refgrounded_014_ginkgo_biloba_safety_interaction: reference **EXPERT REVIEW REQUIRED**; engine **INSUFFICIENT EVIDENCE** — **MISMATCH**.
- refgrounded_015_hypericum_perforatum_preparation_spec: reference **EXPERT REVIEW REQUIRED**; engine **INSUFFICIENT EVIDENCE** — **MISMATCH**.
- refgrounded_017_matricaria_chamomilla_identity_quality: reference **EXPERT REVIEW REQUIRED**; engine **INSUFFICIENT EVIDENCE** — **MISMATCH**.
- refgrounded_023_momordica_charantia_null_fbg: reference **INSUFFICIENT EVIDENCE**; engine **EXPERT REVIEW REQUIRED** — **MISMATCH**.

## Root-cause analysis

### refgrounded_003_matricaria_chamomilla_sleep

Reference: **GO WITH CAUTION**; engine: **GO**.

Responsible stage: **Evidence Interpretation -> Final Decision**. Modules: `evidence_interpretation.py, final_decision_policy.py, botanical_rd_candidate_engine.py`.

The governing chamomile review is positive for some sleep endpoints but explicitly non-supportive for others. Production collapses this conditional efficacy pattern to positive/eligible and has no scientific-evidence route to GO WITH CAUTION; that class is currently emitted from safety/regulatory restrictions only.

### refgrounded_005_cimicifuga_racemosa_menopausal

Reference: **INSUFFICIENT EVIDENCE**; engine: **GO**.

Responsible stage: **Evidence Interpretation -> Final Decision**. Modules: `evidence_interpretation.py, final_decision_policy.py`.

Two independently retrieved systematic reviews are not converted into a governing negative/null or conflict state. The phrase "insufficient evidence to support" is classified unclear, and unresolved scientific evidence falls through to GO once eligibility passes. This converts uncertainty into a positive final decision.

### refgrounded_007_valeriana_officinalis_preparation_spec

Reference: **EXPERT REVIEW REQUIRED**; engine: **INSUFFICIENT EVIDENCE**.

Responsible stage: **Evidence Transport / Botanical Identity Matching**. Modules: `botanical_rd_candidate_engine.py`.

The retrieved EMA record is indexed under the binomial scientific name while the named candidate retains the botanical author suffix. The evidence index uses literal normalized strings rather than the engine taxon-matching logic, so the preparation record is not attached to the candidate. The row therefore reports no direct evidence and becomes INSUFFICIENT EVIDENCE instead of expert review.

### refgrounded_008_ginkgo_biloba_preparation_spec

Reference: **EXPERT REVIEW REQUIRED**; engine: **INSUFFICIENT EVIDENCE**.

Responsible stage: **Evidence Transport / Botanical Identity Matching**. Modules: `botanical_rd_candidate_engine.py`.

The Ginkgo EMA preparation record is present in the snapshot but is lost at candidate evidence indexing because botanical-author variants are not canonicalized consistently between evidence rows and named candidates.

### refgrounded_011_matricaria_chamomilla_indication_evidence

Reference: **GO**; engine: **INSUFFICIENT EVIDENCE**.

Responsible stage: **Evidence Interpretation**. Modules: `evidence_interpretation.py, botanical_rd_candidate_engine.py`.

The systematic review conclusion that chamomile appears efficacious and safe for GAD is left unclear by the calibrated phrase classifier, while the clinical-trial sentence containing a positive symptom result plus a non-significant relapse endpoint becomes mixed. The aggregate therefore loses the high-level supportive conclusion and falls to INSUFFICIENT EVIDENCE.

### refgrounded_013_echinacea_purpurea_identity_quality

Reference: **EXPERT REVIEW REQUIRED**; engine: **INSUFFICIENT EVIDENCE**.

Responsible stage: **Evidence Transport / Domain Routing**. Modules: `botanical_rd_candidate_engine.py, final_decision_policy.py`.

The Kew identity record is independently retrieved, but the production evidence path is indication-centric and the botanical-name variant does not attach to the candidate evidence index. Identity/quality evidence therefore does not become a domain-level reviewable decision state.

### refgrounded_014_ginkgo_biloba_safety_interaction

Reference: **EXPERT REVIEW REQUIRED**; engine: **INSUFFICIENT EVIDENCE**.

Responsible stage: **Evidence Transport -> Safety**. Modules: `botanical_rd_candidate_engine.py, eligibility_gate.py`.

The EMA dabigatran caution is in the frozen input but never reaches candidate safety text because the evidence record and candidate use different taxonomic-name forms. Safety_Severity remains none and the row is marked incomplete for missing safety/regulatory evidence rather than being routed to expert review.

### refgrounded_015_hypericum_perforatum_preparation_spec

Reference: **EXPERT REVIEW REQUIRED**; engine: **INSUFFICIENT EVIDENCE**.

Responsible stage: **Evidence Transport / Botanical Identity Matching**. Modules: `botanical_rd_candidate_engine.py`.

The independently retrieved EMA preparation specification is not attached to the named Hypericum candidate because evidence indexing and candidate matching do not share one canonical botanical-identity key.

### refgrounded_017_matricaria_chamomilla_identity_quality

Reference: **EXPERT REVIEW REQUIRED**; engine: **INSUFFICIENT EVIDENCE**.

Responsible stage: **Evidence Transport / Domain Routing**. Modules: `botanical_rd_candidate_engine.py, final_decision_policy.py`.

The Kew accepted-species evidence is present but identity/quality evidence is not transported into a first-class final-decision domain for this named-botanical E2E path; taxonomic author variation also prevents normal candidate evidence attachment.

### refgrounded_023_momordica_charantia_null_fbg

Reference: **INSUFFICIENT EVIDENCE**; engine: **EXPERT REVIEW REQUIRED**.

Responsible stage: **Reference Currency / Evidence Conflict**. Modules: `gold_corpus/decision_benchmark_v1, final_decision_policy.py`.

Independent retrieval found a 2024 null/insufficient systematic review and a newer 2025 meta-analysis reporting significant FBG reduction. Production correctly recognizes equally ranked opposing directions as conflict and requests expert review. The frozen Gold reference still expects INSUFFICIENT EVIDENCE from the older evidence state, so this mismatch is primarily a benchmark/reference-currency issue rather than a demonstrated engine error.

## What the data says to fix next

The largest repeated failure is **evidence transport/domain routing for named-botanical preparation, identity and safety questions** (Cases 007, 008, 013, 014, 015, 017). The next repeated issue is **scientific evidence interpretation/final-decision propagation** (Cases 003, 005, 011). Case 023 should first trigger **Gold/reference refresh adjudication**, because newer independently retrieved evidence creates a genuine same-tier conflict. No holdout-driven production remediation was applied in this run.
