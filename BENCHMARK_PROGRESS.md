# Benchmark Progress — Reference-Grounded Validation Gold Cases

Tracks the `GoldCase`/Reference-Grounded Validation benchmark specifically. Do not confuse this with `benchmark_cases/smoke_cases.json`, a separate, synthetic, mechanics-only regression fixture set — both are described below, kept clearly distinguished per the repository's own framing.

---

## 1. Target Benchmark Size

**UNKNOWN / not specified in-repo.** No document states an overall target number of Gold Cases. The only numeric target found anywhere in the repository is `TECHNICAL_DEBT.md`'s TD-001 batch-review threshold of "~10–15 cases" — that is a threshold for reassessing deferred technical debt, not a stated final benchmark size, and should not be treated as one.

## 2. Current Number of Implemented Cases

**Reconciled 2026-08-03** (previous count of 6 was stale — it predated Cases 008–017). **16 Reference-Grounded Gold Cases are canonical**, case IDs 001, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012, 013, 014, 015, 016, 017. There is no Case 002 (see Section 5). Case 008 additionally has a **superseded, non-canonical file** still on disk — see the note under the table.

| Case | File | Taxon | Domain | Assertion Type | Assertion State | Governing Source |
|---|---|---|---|---|---|---|
| 001 | `gold_case_reference_grounded_001_melissa_officinalis.py` | Melissa officinalis | Indication/Evidence | Supports indication (sleep) | PRESENT | EMA_HMPC |
| 003 | `gold_case_reference_grounded_003_matricaria_chamomilla.py` | Matricaria chamomilla | Indication/Evidence | Supports indication (sleep) | CONDITIONAL | SYSTEMATIC_REVIEW (Kazemi et al. 2024) |
| 004 | `gold_case_reference_grounded_004_ginkgo_biloba.py` | Ginkgo biloba | Indication/Evidence | Supports indication (cognitive impairment) | ABSENT | SYSTEMATIC_REVIEW (Cochrane) |
| 005 | `gold_case_reference_grounded_005_cimicifuga_racemosa.py` | Cimicifuga racemosa | Indication/Evidence | Supports indication (menopausal symptoms) | INSUFFICIENT | SYSTEMATIC_REVIEW |
| 006 | `gold_case_reference_grounded_006_hypericum_perforatum_safety_interaction.py` | Hypericum perforatum | Safety | Contraindication (CYP3A4/CYP2B6/CYP2C9/CYP2C19 or P-glycoprotein-affected products) | PRESENT | EMA_HMPC (EMA/HMPC/7695/2021) |
| 007 | `gold_case_reference_grounded_007_valeriana_officinalis_preparation_spec.py` | Valeriana officinalis | Preparation Spec | Preparation specification (dry extract, DER 3–7.4:1, ethanol 40–70% V/V) | PRESENT | EMA_HMPC (EMA/HMPC/150846/2015) |
| 008 | `gold_case_reference_grounded_008_ginkgo_biloba_preparation_spec.py` | Ginkgo biloba (folium) | Preparation Spec | Preparation specification (dry extract, DER 35–67:1, acetone 60% w/w) | PRESENT | EMA_HMPC (EMA/HMPC/321097/2012) |
| 009 | `gold_case_reference_grounded_009_melissa_officinalis_mental_stress.py` | Melissa officinalis (folium) | Indication/Evidence | Supports indication (mental stress) | PRESENT | EMA_HMPC (EMA/HMPC/310761/2013) |
| 010 | `gold_case_reference_grounded_010_passiflora_incarnata_mental_stress.py` | Passiflora incarnata (herba) | Indication/Evidence | Supports indication (mental stress) | PRESENT | EMA_HMPC (EMA/275240/2014) |
| 011 | `gold_case_reference_grounded_011_matricaria_chamomilla_indication_evidence.py` | Matricaria chamomilla (flower) | Indication/Evidence | Supports indication (generalized anxiety disorder) | PRESENT | SYSTEMATIC_REVIEW (Hieu et al. 2019, PMID 31006899) |
| 012 | `gold_case_reference_grounded_012_lavandula_angustifolia_sleep.py` | Lavandula angustifolia (aetheroleum) | Indication/Evidence | Supports indication (sleep) | PRESENT | EMA_HMPC (EMA/HMPC/530968/2012) |
| 013 | `gold_case_reference_grounded_013_echinacea_purpurea_identity_quality.py` | Echinacea purpurea | Identity/Quality | Identity confirmation | PRESENT | TAXONOMIC_AUTHORITY (Kew POWO) |
| 014 | `gold_case_reference_grounded_014_ginkgo_biloba_safety_interaction.py` | Ginkgo biloba (folium) | Safety | Interaction (dabigatran etexilate), severity MODERATE | PRESENT | EMA_HMPC (EMA/HMPC/321097/2012) |
| 015 | `gold_case_reference_grounded_015_hypericum_perforatum_preparation_spec.py` | Hypericum perforatum (herba) | Preparation Spec | Preparation specification (dry extract, DER 3–7:1, methanol 80% V/V) | PRESENT | EMA_HMPC (EMA/HMPC/7695/2021) |
| 016 | `gold_case_reference_grounded_016_piper_methysticum_regulatory_prohibition.py` | Piper methysticum | Regulatory Status | Prohibition (UK medicinal-product sale/supply/import) | PRESENT | NATIONAL_REGULATORY (UK MHRA, SI 2002/3170) |
| 017 | `gold_case_reference_grounded_017_matricaria_chamomilla_identity_quality.py` | Matricaria chamomilla | Identity/Quality | Identity confirmation | PRESENT | TAXONOMIC_AUTHORITY (Kew POWO) |

**Superseded, non-canonical artifact (do not use or count):** the earlier hard-coded INDICATION_EVIDENCE draft of Case 008 and its old test are archived under `gold_cases/archive/superseded_case_008/`. They are retained only for audit history and are outside the active Case namespace. The canonical Case 008 is the PREPARATION_SPEC file listed above.

Companion "engine evidence run" files exist for Cases 003 and 006 (`case_003_engine_evidence_run.py`, `case_006_engine_evidence_run.py`), which is where those two cases' `EngineEvidenceInput` is constructed and the real engine is actually executed, per the repository's "Leakage Rule 9.1" file-separation convention. Cases 007–017 (all Preparation Spec, Identity/Quality, and Regulatory Status cases, plus Cases 008–012/014's Indication/Evidence and Safety claims) have **no** engine-evidence-run file and explicitly declare `engine_evidence_attached: false` in their quality records — confirmed intentional per Protocol §14.1 for non-eligible domains, but for the Indication/Evidence and Safety cases among 009–012/014 this means no whole-case engine-agreement run has been attached yet even though the domain itself would be eligible. Whether Cases 001/004/005 have their own engine-evidence-run step (inline or in a still-unidentified separate file) was **not independently re-verified for each file individually** — treat as PENDING for those three cases specifically.

## 3. Frozen Cases

See `PROJECT_STATUS.md` §12 and `DECISIONS.md`. Cases 001, 003, 004, 005, and 006 each describe their own Ground Truth construction file as not to be edited once complete (informally, in each file's own docstring — e.g., Case 003's file states of itself: "is frozen"). No single repository-wide "frozen" flag or registry was found. A full, field-by-field freeze-status inventory was not completed in this pass — see `NEXT_ACTIONS.md` (NA item under "Immediate"/"Short-term" candidates for a future pass, not currently listed as it wasn't explicit enough in-repo to assign a priority).

## 4. Cases Under Review

**Case 006 (Hypericum perforatum)** went through a documented two-pass review process before being built: an initial source-suitability screening (`case_006_source_suitability_screening.md`, itself marked "Status: DRAFT screening only. No Gold Case, test, or Engine Evidence created" at the time it was written) followed by a same-rank-source verification pass, both "supervisor-approved before this file was written" per the Case 006 gold-case file's own docstring. No case is currently marked as "under review" as of this snapshot — Case 006's screening-stage document remains in the repo as a historical record of that process, not as a currently-open review.

## 5. Abandoned Cases

**Case 002 (Passiflora)** — the only confirmed abandoned/skipped case number. Documented reason: "Access-Blocked" (`Prospective_Claim_to_Decision_Mapping_Proposal.md`, referencing it in passing). No dedicated abandonment record with fuller reasoning was found in this repository snapshot.

## 6. Coverage by Botanical

**Reconciled 2026-08-03.** 11 distinct taxa across 16 cases. Two taxa now have more than one Gold Case:
- Ginkgo biloba: 3 cases (004 — indication/cognitive, ABSENT; 008 — preparation spec; 014 — safety/interaction)
- Matricaria chamomilla: 3 cases (003 — indication/sleep, CONDITIONAL; 011 — indication/GAD, PRESENT; 017 — identity/quality)
- Hypericum perforatum: 2 cases (006 — safety/contraindication; 015 — preparation spec)
- Single-case taxa: Melissa officinalis (001, 009 — actually 2, see below), Cimicifuga racemosa (005), Valeriana officinalis (007), Passiflora incarnata (010), Lavandula angustifolia (012), Echinacea purpurea (013), Piper methysticum (016)

Correction: Melissa officinalis also has 2 cases (001 — indication/sleep; 009 — indication/mental stress), not 1.

## 7. Coverage by Indication

- Sleep: 3 cases (001 Melissa officinalis, 003 Matricaria chamomilla, 012 Lavandula angustifolia)
- Cognitive impairment: 1 case (004 Ginkgo biloba)
- Menopausal symptoms: 1 case (005 Cimicifuga racemosa)
- Mental stress: 2 cases (009 Melissa officinalis, 010 Passiflora incarnata)
- Generalized anxiety disorder: 1 case (011 Matricaria chamomilla)
- Not indication-dependent: 4 cases (007, 008, 015 — Preparation Spec claims; 013, 016, 017 — Identity/Quality and Regulatory Status claims, `validation_unit.indication: None` in each)
- Safety/interaction (not an indication per se): 2 cases (006 Hypericum perforatum — contraindication; 014 Ginkgo biloba — dabigatran interaction)

## 8. Coverage by Evidence Type / Governing Source Type

- EMA_HMPC: 9 cases (001, 006, 007, 008, 009, 010, 012, 014, 015)
- SYSTEMATIC_REVIEW: 4 cases (003, 004, 005, 011)
- TAXONOMIC_AUTHORITY: 2 cases (013, 017 — both Kew Plants of the World Online)
- NATIONAL_REGULATORY: 1 case (016 — UK MHRA)

No case in the current set is governed by WHO_MONOGRAPH, ESCOP_MONOGRAPH, COMMISSION_E, or PHARMACOPOEIA as its primary/selected reference — those source types appear in the Permitted Sources hierarchy (`VALIDATION_PROTOCOL.md` §6) but have not yet been exercised as a case's *governing* (selected) source. (`WHO_MONOGRAPH`, `ESCOP_MONOGRAPH`, `COMMISSION_E` did appear as unverified same-rank competing sources considered, but not used, during Case 006's screening — see `case_006_source_suitability_screening.md`.)

## 9. Coverage Gaps

**Reconciled 2026-08-03 — the two domain gaps below are now CLOSED:**
- ~~`ReferenceDomain.IDENTITY_QUALITY` — no case yet~~ → **closed** by Cases 013 (Echinacea purpurea) and 017 (Matricaria chamomilla).
- ~~`ReferenceDomain.REGULATORY_STATUS` — no case yet~~ → **closed** by Case 016 (Piper methysticum, UK MHRA prohibition).

**Still open:**
- `AssertionType` values beyond `SUPPORTS_INDICATION`, `CONTRAINDICATION`, `PREPARATION_SPECIFICATION`, `IDENTITY_CONFIRMATION`, `INTERACTION`, and `PROHIBITION` — remain untested (these six are now exercised across the 16 cases).
- `AssertionState.NOT_STATED` — still untested; all 16 cases use PRESENT, ABSENT, CONDITIONAL, or INSUFFICIENT.
- `FDA` as a source type is not present in any `reference_precedence.py` domain hierarchy at all — only the generic `NATIONAL_REGULATORY`/`OTHER_NATIONAL_REGULATORY` buckets exist (`VALIDATION_PROTOCOL.md` §6, "Known gap"). Adding an FDA-specific source type would itself be a code change, out of scope for case curation alone.
- No taxon has been tested across all 5 `ReferenceDomain` values yet — Ginkgo biloba is the closest, with 3 of 5 (Indication/Evidence, Preparation Spec, Safety).

## 10. Validation Statistics

- `decision_direction_agreement`: computed only for `AgreementEligibility.ELIGIBLE` cases. Case 003 is confirmed `NOT_ELIGIBLE` (reason: `ASSERTION_STATE_UNMAPPED`, its resolved outcome being `CONDITIONAL`). Eligibility status for Cases 001, 004, 005, 006, 007 individually was **not independently re-run/re-verified in this documentation pass** — PENDING. (004's ABSENT and 005's INSUFFICIENT states have documented mappings: ABSENT → NEGATIVE is unconditional per Protocol §14.2's table; INSUFFICIENT has *(none — not eligible)* per that same table, meaning 005 is very likely `NOT_ELIGIBLE` for this metric by the same mapping logic that makes 003 ineligible — this inference was not run against the actual code in this pass and should be verified, not assumed, before being treated as fact.)
- `safety_serious_false_negative_rate`: computed only when at least one `SELECTED` `SAFETY`/`SERIOUS`/`PRESENT` resolved outcome exists in the case set. As of `case_006_source_suitability_screening.md`'s own writing (before Case 006 existed), this had presumably never left `NOT_COMPUTABLE`. Case 006 (Safety/PRESENT) may have changed this — **not independently re-verified in this pass; see `NEXT_ACTIONS.md` NA-004.**
- No other metrics are implemented. `VALIDATION_PROTOCOL.md` §13 states explicitly that gate-level agreement, top-k inclusion, and GRADE calibration are not implemented.

## 11. Lessons Learned

Documented explicitly in-repo (not inferred):
- Case 003 demonstrated that "the pipeline can execute correctly and still produce an output that cannot be scored" — this motivated the entire Prospective Claim-to-Decision Mapping proposal, later adopted as Protocol §14 (`Prospective_Claim_to_Decision_Mapping_Proposal.md`, "Origin").
- Defining `ExpectedOutput`/`DecisionDirection` *after* seeing engine output is explicitly named as a temptation to avoid — "post-outcome specification... would make every future agreement metric suspect" (same document).
- `ARCHITECTURE.md`'s own account of the legacy-file archival near-miss: a static, one-time-generated list of "safe to archive" files silently went stale once a later session wired one of those files into production. The lesson recorded in-repo: "copying a snippet out of this file is exactly how the original snapshot went stale (it was never re-run after being pasted here once)" — always re-run the actual tool (`repo_dependency_audit.py`), never trust a previously-pasted result.

## 12. Next Candidate Cases

No specific next-candidate-case list exists in this repository snapshot. The only forward-looking case-selection guidance found is the coverage-gap list in Section 9 above (Identity/Quality and Regulatory Status domains, non-PRESENT/ABSENT/CONDITIONAL/INSUFFICIENT-only AssertionType coverage, `NOT_STATED` AssertionState) — these are documented gaps, not a committed roadmap. Do not present them as a decided next-case plan; see `NEXT_ACTIONS.md` NA-007.

---

## Appendix: `benchmark_cases/smoke_cases.json` (separate from the Gold Case benchmark)

This file contains **synthetic** smoke-test cases, explicitly self-described in-file as "NOT a real historical decision, NOT expert-curated" — each case's `expected` block was produced by running that exact case through the engine and capturing its current output, making these a mechanics/regression lock, not a scientific validation claim. They exercise engine code paths (e.g., the hard-safety auto-exclusion path, the generic no-evidence/`NOT_EVALUABLE` gate path) rather than testing agreement with an authoritative reference. They are exercised by `benchmark_harness.py`/`test_benchmark_harness.py`, not by the Gold Case pipeline. Do not count these toward Gold Case statistics above.
