# Technical Debt — Reference-Grounded Validation Program

Deferred items only. Recorded here specifically so they are not forgotten
and not re-litigated one at a time — reviewed together as a batch after a
larger set of Gold Cases has been completed (targeted: after ~10-15 cases).
Nothing in this file is an open task for the current case; adding an entry
here is explicitly the alternative to acting on it now.

Each entry: which case surfaced it, what the issue is, why it wasn't fixed
immediately, and what should be reassessed later.

---

## TD-001 — Preparation/population fields sourced from EMA, not independently derived from the governing systematic review

**Surfaced by:** Case 004 (Ginkgo biloba)

**Issue:** In Case 004, `ReferenceDescriptor.preparation`/`.population` (and the matching `ValidationUnit` fields) were taken from the EMA/HMPC monograph's own posology, not independently derived from what the governing Cochrane systematic review's included MCI trials actually used. This does not affect Ground Truth (`assertion_state`, `evidence_text`, `selected_reference_id` are 100% Cochrane-sourced) but does mean `applicability_check()`'s `preparation: pass` currently reflects "matches what EMA prescribes," not "matches what the governing SR's own trials studied."

**Why not fixed immediately (original entry):** Explicitly deferred per project decision — reassess only after a larger set of Gold Cases has been completed, not case-by-case.

---

**BATCH REASSESSMENT — 2026-08-03** (triggered at 16 Gold Cases, above the ~10–15 target stated above):

1. **The specific remediation this entry speculated about has already been built and applied.** `field_provenance.py` (`FieldProvenance`/`VerificationStatus`) exists and is wired into `GoldCase.case_provenance`. Verified by reading each file directly: **all five** cases with a preparation/population source that differs from the governing claim's own source — Cases 001, 003, 004, 005, and 006, not just Case 004 — each carry an explicit `FieldProvenance` entry whose `supported_field` states in plain language which document the preparation/population actually came from (e.g., Case 004's own entry: *"the EMA monograph's own well-established-use posology, not the governing Ground Truth claim itself"*; Case 005's: *"one of THREE EMA well-established-use preparations, arbitrarily selected"*; Case 003's: *"disclosed heterogeneity, not resolved"*).
2. **Verified this gap does not recur in Cases 007–017.** Grepped every case built after Case 006 for `FieldProvenance(` usage: Cases 009, 010, 011, 012, 013, 015, 017 use it zero times because their preparation/population and their governing claim come from the *same* single document (no split to disclose). Cases 014 and 016 use it once each, but that one usage documents the resolved outcome itself (a Safety/Interaction and a Regulatory/Prohibition claim respectively), not a preparation/population source split — neither of those two cases has a TD-001-type gap either. **Conclusion: TD-001 is fully confined to Cases 001/003/004/005/006 and has not spread to any of the 11 cases built since.**
3. **What is still genuinely open (see TD-002 below):** every one of the 5 `FieldProvenance` disclosures above is stored with `verification_status=VerificationStatus.UNVERIFIED` and `curator=None`. The mechanism discloses the sourcing gap; no human has yet reviewed or signed off on any of the five. Nothing in the codebase currently *requires* this review to happen, or blocks a case from staying `UNVERIFIED` indefinitely.
4. **The original protocol-level question remains unresolved and is NOT a coding task:** should `preparation`/`population` on a `ReferenceDescriptor` be required, as a matter of standing protocol, to come from the *governing* source specifically — even when that source is a systematic review without a single standardized posology — rather than from whichever accessible regulatory document happens to describe the taxon? The `FieldProvenance` mechanism makes the *current* practice honest and inspectable; it does not decide whether the current practice is the *right* one. This decision is Hamid's per the repository's standing review structure (same as the `CONDITIONAL` mapping policy in NA-005).

**Status: mechanism-remediated, disclosed, unverified. Downgraded from "unaddressed technical debt" to "known, disclosed, pending human verification + one open protocol question."** Recommend closing TD-001 as originally worded and tracking the two residual items as TD-002 (below) and as an addition to NA-005's Hamid-decision queue.

---

## TD-002 — FieldProvenance disclosures exist but are unverified, and nothing enforces their use going forward

**Surfaced by:** TD-001's 2026-08-03 batch reassessment (above), not a new case.

**Issue:** Two gaps in the `field_provenance.py` mechanism as actually used:
1. All 5 existing `case_provenance` entries (Cases 001, 003, 004, 005, 006) are `VerificationStatus.UNVERIFIED` with `curator=None`. The disclosure exists but has never been reviewed by a second person.
2. No completeness check (test or runtime gate) verifies that a case whose `validation_unit.preparation`/`.population` comes from a document *other than* the governing claim's own source actually carries a matching `FieldProvenance` entry. A future case could reintroduce the exact situation TD-001 described and nothing would flag it — the discipline is currently manual/convention-based only (visible by grepping for `FieldProvenance(`, as this reassessment did by hand).

**Why not fixed now:** Genuinely new finding from this reassessment pass, not yet triaged by the project owner. Recorded here rather than acted on, per this file's own stated policy.

**What to reassess later:** (a) Whether to schedule an explicit curator-verification pass over the 5 existing `UNVERIFIED` entries (this is a review task, not a coding task). (b) Whether to add a repository-enforced check — e.g., a pytest fixture or a field on `GoldCase` itself — that fails when `validation_unit.preparation`/`.population`'s source document differs from `resolved_outcomes[...].source_reference_id` and no corresponding `FieldProvenance` entry exists in `case_provenance`. This second item, if adopted, would close the class of bug TD-001 originally represented at the tooling level rather than relying on someone remembering to grep for it, as this pass just did.

---
