# Benchmark Progress — Reference-Grounded Validation Gold Cases

Tracks the `GoldCase`/Reference-Grounded Validation benchmark specifically. Do not confuse this with `benchmark_cases/smoke_cases.json`, a separate, synthetic, mechanics-only regression fixture set — both are described below, kept clearly distinguished per the repository's own framing.

---

## 1. Target Benchmark Size

**UNKNOWN / not specified in-repo.** No document states an overall target number of Gold Cases. The only numeric target found anywhere in the repository is `TECHNICAL_DEBT.md`'s TD-001 batch-review threshold of "~10–15 cases" — that is a threshold for reassessing deferred technical debt, not a stated final benchmark size, and should not be treated as one.

## 2. Current Number of Implemented Cases

**6 Reference-Grounded Gold Cases**, case IDs 001, 003, 004, 005, 006, 007. There is no Case 002 (see Section 5).

| Case | File | Taxon | Domain | Assertion Type | Assertion State | Governing Source |
|---|---|---|---|---|---|---|
| 001 | `gold_case_reference_grounded_001_melissa_officinalis.py` | Melissa officinalis | Indication/Evidence | Supports indication (sleep) | PRESENT | EMA_HMPC |
| 003 | `gold_case_reference_grounded_003_matricaria_chamomilla.py` | Matricaria chamomilla | Indication/Evidence | Supports indication (sleep) | CONDITIONAL | SYSTEMATIC_REVIEW (Kazemi et al. 2024) |
| 004 | `gold_case_reference_grounded_004_ginkgo_biloba.py` | Ginkgo biloba | Indication/Evidence | Supports indication (cognitive impairment) | ABSENT | SYSTEMATIC_REVIEW (Cochrane) |
| 005 | `gold_case_reference_grounded_005_cimicifuga_racemosa.py` | Cimicifuga racemosa | Indication/Evidence | Supports indication (menopausal symptoms) | INSUFFICIENT | SYSTEMATIC_REVIEW |
| 006 | `gold_case_reference_grounded_006_hypericum_perforatum_safety_interaction.py` | Hypericum perforatum | Safety | Contraindication (CYP3A4/CYP2B6/CYP2C9/CYP2C19 or P-glycoprotein-affected products) | PRESENT | EMA_HMPC (EMA/HMPC/7695/2021) |
| 007 | `gold_case_reference_grounded_007_valeriana_officinalis_preparation_spec.py` | Valeriana officinalis | Preparation Spec | Preparation specification (dry extract, DER 3–7.4:1, ethanol 40–70% V/V) | PRESENT | EMA_HMPC (EMA/HMPC/150846/2015) |

Companion "engine evidence run" files exist for Cases 003 and 006 (`case_003_engine_evidence_run.py`, `case_006_engine_evidence_run.py`), which is where those two cases' `EngineEvidenceInput` is constructed and the real engine is actually executed, per the repository's "Leakage Rule 9.1" file-separation convention. Case 007 (Preparation Spec) has **no** engine-evidence-run file — confirmed intentional: `PREPARATION_SPEC` is not currently eligible for whole-case decision-direction agreement (Protocol §14.1), and `test_case_007_preparation_specification.py` includes a test explicitly confirming engine evidence remains empty for this case (`test_engine_evidence_remains_empty_no_expected_direction`). Whether Cases 001/004/005 have their own engine-evidence-run step (inline or in a still-unidentified separate file) was **not independently re-verified for each file individually** in this documentation pass — treat as PENDING for those three cases specifically.

## 3. Frozen Cases

See `PROJECT_STATUS.md` §12 and `DECISIONS.md`. Cases 001, 003, 004, 005, and 006 each describe their own Ground Truth construction file as not to be edited once complete (informally, in each file's own docstring — e.g., Case 003's file states of itself: "is frozen"). No single repository-wide "frozen" flag or registry was found. A full, field-by-field freeze-status inventory was not completed in this pass — see `NEXT_ACTIONS.md` (NA item under "Immediate"/"Short-term" candidates for a future pass, not currently listed as it wasn't explicit enough in-repo to assign a priority).

## 4. Cases Under Review

**Case 006 (Hypericum perforatum)** went through a documented two-pass review process before being built: an initial source-suitability screening (`case_006_source_suitability_screening.md`, itself marked "Status: DRAFT screening only. No Gold Case, test, or Engine Evidence created" at the time it was written) followed by a same-rank-source verification pass, both "supervisor-approved before this file was written" per the Case 006 gold-case file's own docstring. No case is currently marked as "under review" as of this snapshot — Case 006's screening-stage document remains in the repo as a historical record of that process, not as a currently-open review.

## 5. Abandoned Cases

**Case 002 (Passiflora)** — the only confirmed abandoned/skipped case number. Documented reason: "Access-Blocked" (`Prospective_Claim_to_Decision_Mapping_Proposal.md`, referencing it in passing). No dedicated abandonment record with fuller reasoning was found in this repository snapshot.

## 6. Coverage by Botanical

6 distinct taxa, one Gold Case each: Melissa officinalis, Matricaria chamomilla, Ginkgo biloba, Cimicifuga racemosa, Hypericum perforatum, Valeriana officinalis. No taxon currently has more than one Gold Case.

## 7. Coverage by Indication

- Sleep: 2 cases (001 Melissa officinalis, 003 Matricaria chamomilla)
- Cognitive impairment: 1 case (004 Ginkgo biloba)
- Menopausal symptoms: 1 case (005 Cimicifuga racemosa)
- Not indication-dependent: 1 case (007 Valeriana officinalis — `validation_unit.indication: None`, per the case file's own docstring, since `PREPARATION_SPEC` claims are not indication-dependent)
- Safety/interaction (not an indication per se): 1 case (006 Hypericum perforatum — contraindication with specific drug classes, not an indication claim)

## 8. Coverage by Evidence Type / Governing Source Type

- EMA_HMPC: 3 cases (001, 006, 007)
- SYSTEMATIC_REVIEW: 3 cases (003, 004, 005)

No case in the current set is governed by WHO_MONOGRAPH, ESCOP_MONOGRAPH, COMMISSION_E, PHARMACOPOEIA, TAXONOMIC_AUTHORITY, NATIONAL_REGULATORY, or OTHER_NATIONAL_REGULATORY as its primary/selected reference — those source types appear in the Permitted Sources hierarchy (`VALIDATION_PROTOCOL.md` §6) but have not yet been exercised as a case's *governing* (selected) source, per the cases currently built. (`WHO_MONOGRAPH`, `ESCOP_MONOGRAPH`, `COMMISSION_E` did appear as unverified same-rank competing sources considered, but not used, during Case 006's screening — see `case_006_source_suitability_screening.md`.)

## 9. Coverage Gaps

Per `case_006_source_suitability_screening.md` (Section 1, written before Cases 006/007 existed) plus this pass's own review of Cases 006/007:
- `ReferenceDomain.IDENTITY_QUALITY` — no case yet.
- `ReferenceDomain.REGULATORY_STATUS` — no case yet.
- `AssertionType` values other than `SUPPORTS_INDICATION`, `CONTRAINDICATION`, and `PREPARATION_SPECIFICATION` — untested.
- `AssertionState.NOT_STATED` — untested (all 6 cases use PRESENT, ABSENT, CONDITIONAL, or INSUFFICIENT).
- `FDA` as a source type is not present in any `reference_precedence.py` domain hierarchy at all — only the generic `NATIONAL_REGULATORY`/`OTHER_NATIONAL_REGULATORY` buckets exist (`VALIDATION_PROTOCOL.md` §6, "Known gap"). Adding an FDA-specific source type would itself be a code change, out of scope for case curation alone.

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
