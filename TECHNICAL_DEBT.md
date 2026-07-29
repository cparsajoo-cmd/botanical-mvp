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

**Why not fixed now:** Explicitly deferred per project decision — reassess only after a larger set of Gold Cases has been completed, not case-by-case.

**What to reassess later:** Whether `preparation`/`population` on a `ReferenceDescriptor` should, as a matter of protocol, be derived from the *governing* source specifically (even when that source is a systematic review that doesn't itself specify a single standardized preparation/dose the way a monograph does), rather than from whichever accessible regulatory document happens to describe the taxon. May also inform whether this deserves a named field-provenance flag (e.g., distinguishing "posology sourced from governing claim" vs. "posology sourced from a secondary regulatory document") rather than being detectable only by reading `FieldProvenance.document_id` by hand.

---
