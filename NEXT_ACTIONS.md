# Next Actions — Botanical R&D Decision Intelligence Platform

Actionable work only. Completed items live in `PROJECT_STATUS.md`, not here. Every item below is grounded in something explicitly documented in-repo as not-yet-done; nothing here is a speculative "you might also want to..." suggestion.

---

## Immediate

### NA-001 — Confirm VALIDATION_PROTOCOL.md v0.3
- **Priority:** Immediate
- **Description:** `VALIDATION_PROTOCOL.md` is explicitly marked "DRAFT — pending Hamid's final confirmation of this revision." The document itself names the sections most worth a final check: Section 3 (track selection), Section 6 (source-selection rule), Sections 10/11 (success/failure criteria), and Section 14 (Prospective Claim-to-Decision Mapping — especially the still-open `CONDITIONAL` question in 14.2).
- **Dependencies:** None.
- **Estimated effort:** UNKNOWN (review-only task; not a coding task).
- **Current status:** Open.
- **Owner:** Hamid (per the document's own status line).
- **Acceptance criteria:** Document status line updated from "DRAFT — pending confirmation" to a confirmed/approved status, or specific revisions requested.

### NA-002 — Run the legacy-file archival workflow
- **Priority:** Immediate
- **Description:** `.github/workflows/archive-legacy.yml` ("Archive legacy files (Phase 7)") exists, is documented as ready, and validates its own file list before moving anything — but has not been triggered. 65 files are listed in `.github/legacy-files.txt` (note: `ARCHITECTURE.md`'s prose states "66 files" — this count was not reconciled in this documentation pass; see `REPOSITORY_STRUCTURE.md`).
- **Dependencies:** None — the workflow is described as self-validating (`repo_dependency_audit.py validate` runs first and fails the job if anything listed is actually reachable from production).
- **Estimated effort:** UNKNOWN (CI trigger + manual post-run verification).
- **Current status:** Not started.
- **Owner:** UNKNOWN (whoever has Actions-tab access).
- **Acceptance criteria** (from `ARCHITECTURE.md` directly): `archive/` exists and contains the archived files; `archive/ARCHIVED_FILES.md` was generated; `pytest -q` still passes; `ARCHITECTURE.md`'s "Legacy files" section is updated to say "moved" only once independently confirmed true.

---

## Short-Term

### NA-003 — Reconcile 65-vs-66 legacy file count discrepancy
- **Priority:** Short-term
- **Description:** `ARCHITECTURE.md`'s prose states 66 legacy files were confirmed; `.github/legacy-files.txt` (as present in this snapshot) contains 65 lines. Not reconciled during this documentation pass, per the instruction not to modify `ARCHITECTURE.md`'s frozen content.
- **Dependencies:** None.
- **Estimated effort:** Small (re-run `repo_dependency_audit.py summary`/`validate` and compare counts).
- **Current status:** Open, newly identified in this documentation pass.
- **Owner:** UNKNOWN.
- **Acceptance criteria:** Either the file list or the prose count is corrected to match a freshly re-run `repo_dependency_audit.py` result.

### NA-004 — Verify whether Case 006's SAFETY/PRESENT outcome changed `safety_serious_false_negative_rate` computability
- **Priority:** Short-term
- **Description:** `case_006_source_suitability_screening.md` states that, as of its own writing, no case had produced a `SELECTED` `SAFETY`/`SERIOUS`/`PRESENT` outcome — meaning the metric had presumably never left `NOT_COMPUTABLE`. Case 006 itself (built after that screening doc) is a Safety/Contraindication/PRESENT case. Whether this actually changed the metric's computability was not independently re-verified in this documentation pass.
- **Dependencies:** None — requires re-running `evaluation_run.py`'s `build_evaluation_run()` against a case set including Case 006.
- **Estimated effort:** Small.
- **Current status:** Open, newly identified in this documentation pass.
- **Owner:** UNKNOWN.
- **Acceptance criteria:** `BENCHMARK_PROGRESS.md`'s validation-statistics section updated with a verified answer instead of "PENDING."

---

## Medium-Term

### NA-005 — Resolve the CONDITIONAL → DecisionDirection mapping policy
- **Priority:** Medium-term (explicitly deferred by design, not urgent)
- **Description:** `ConditionalMappingPolicy.UNRESOLVED` is the currently adopted policy for mapping `AssertionState.CONDITIONAL` to a `DecisionDirection`. Two alternative policies (`HOLD` mapping, case-specific override) are implemented but not adopted. The protocol states this should be resolved only once more Reference-Grounded cases exist, giving an empirical basis to choose among the three options — and explicitly warns against resolving it by editing a single case.
- **Dependencies:** More completed Gold Cases (no specific numeric threshold stated for this decision, unlike TD-001's ~10–15).
- **Estimated effort:** UNKNOWN — protocol-level decision, not a coding task.
- **Current status:** Open, deliberately deferred.
- **Owner:** Hamid (protocol-level decisions are his to make per the repository's stated review structure).
- **Acceptance criteria:** `VALIDATION_PROTOCOL.md` §14.2 updated with an adopted (not just implemented) policy, plus a version bump and Change History entry.

### NA-006 — TD-001 batch technical-debt review
- **Priority:** Medium-term
- **Description:** Reassess TD-001 (Case 004's EMA-sourced preparation/population fields) once ~10–15 Gold Cases exist. Currently 6 exist.
- **Dependencies:** ~4–9 additional Gold Cases (relative to the current 6, to reach the stated 10–15 target).
- **Estimated effort:** UNKNOWN.
- **Current status:** Not due yet — threshold not reached.
- **Owner:** UNKNOWN.
- **Acceptance criteria:** `TECHNICAL_DEBT.md` reviewed as a batch (per its own stated review policy), TD-001 either resolved, re-deferred with updated reasoning, or formally closed.

---

## Long-Term

### NA-007 — Extend Gold Case coverage to untested domains and states
- **Priority:** Long-term
- **Description:** `case_006_source_suitability_screening.md` documents these coverage gaps as of its writing: `ReferenceDomain.IDENTITY_QUALITY` and `REGULATORY_STATUS` entirely untested (Case 006 has since covered `SAFETY` and Case 007 has since covered `PREPARATION_SPEC`, narrowing but not closing this gap); `AssertionType` values beyond `SUPPORTS_INDICATION`/`CONTRAINDICATION`/`PREPARATION_SPECIFICATION` untested; `AssertionState.NOT_STATED` untested.
- **Dependencies:** New Gold Case curation work (source screening → claim extraction → engine evidence → execution), following the same process documented for Cases 001–007.
- **Estimated effort:** UNKNOWN — no per-case effort estimate is recorded anywhere in-repo.
- **Current status:** Not started for the remaining gaps (IDENTITY_QUALITY, REGULATORY_STATUS, NOT_STATED, and most AssertionType values).
- **Owner:** UNKNOWN.
- **Acceptance criteria:** New Gold Case(s) built, locked, and reflected in `BENCHMARK_PROGRESS.md`.

### NA-008 — Corpus/Retrieval Validation phase (END_TO_END scope)
- **Priority:** Long-term
- **Description:** `ValidationScope.END_TO_END` is explicitly reserved in code for a future phase testing the engine's own retrieval, not just its interpretation of provided evidence.
- **Dependencies:** UNKNOWN — no design document for this phase exists in this repository snapshot (unlike the Prospective Claim-to-Decision Mapping, which had its own proposal document before adoption).
- **Estimated effort:** UNKNOWN.
- **Current status:** Not started; reserved only.
- **Owner:** UNKNOWN.
- **Acceptance criteria:** UNKNOWN — no acceptance criteria exist yet because no design work has been recorded.

### NA-009 — ExpertPanel comparison mechanism
- **Priority:** Long-term
- **Description:** Building the mechanism to compare `ValidationCaseProtocol`/`ExpertPanel` output against a live expert panel's judgment — explicitly named as the reason that track is currently out of scope.
- **Dependencies:** UNKNOWN.
- **Estimated effort:** UNKNOWN.
- **Current status:** Not started.
- **Owner:** UNKNOWN.
- **Acceptance criteria:** UNKNOWN.

---

## Explicitly Not a Task Right Now

For clarity, the following are documented in-repo as deliberately deferred and should **not** be picked up as ad hoc work without a protocol-level decision first:
- Editing any single Gold Case to resolve the `CONDITIONAL` mapping question (explicitly prohibited — see NA-005 and Decision D-006 in `DECISIONS.md`).
- Re-enabling the legacy fabricated regulatory stub (`_LEGACY_STUB_ENABLED`) without a deliberate, commented flag change and review.
- Removing the local SQLite layer (`schema.py`/`botanical_platform.db`) — flagged as worth removing "in a future pass," not scheduled.
