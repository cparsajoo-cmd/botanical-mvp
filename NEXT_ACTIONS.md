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
- **Priority:** Immediate (upgraded 2026-08-03 — threshold reached, see below)
- **Description:** Reassess TD-001 (Case 004's EMA-sourced preparation/population fields) once ~10–15 Gold Cases exist.
- **Dependencies:** None — **16 Gold Cases now exist (001, 003–017), which is at/above the stated ~10–15 threshold.** This item is no longer blocked and should move to the top of the queue.
- **Estimated effort:** UNKNOWN.
- **Current status:** **Due now.** Previously marked "not due yet" when the repository's own count (6) was stale; reconciled 2026-08-03 against the actual 16 case files on disk (see `BENCHMARK_PROGRESS.md` §2 and `PROJECT_STATUS.md` §11).
- **Owner:** UNKNOWN.
- **Acceptance criteria:** `TECHNICAL_DEBT.md` reviewed as a batch (per its own stated review policy), TD-001 either resolved, re-deferred with updated reasoning, or formally closed.

---

## Long-Term

### NA-007 — Extend Gold Case coverage to untested domains and states
- **Priority:** Long-term (domain gaps below closed 2026-08-03; remaining scope narrowed)
- **Description:** Originally: `ReferenceDomain.IDENTITY_QUALITY` and `REGULATORY_STATUS` entirely untested; `AssertionType` values beyond `SUPPORTS_INDICATION`/`CONTRAINDICATION`/`PREPARATION_SPECIFICATION` untested; `AssertionState.NOT_STATED` untested.
  - ✅ **CLOSED**: `IDENTITY_QUALITY` — covered by Case 013 (Echinacea purpurea) and Case 017 (Matricaria chamomilla).
  - ✅ **CLOSED**: `REGULATORY_STATUS` — covered by Case 016 (Piper methysticum).
  - ✅ **Partially closed**: `AssertionType` — `INTERACTION` (Case 014) and `IDENTITY_CONFIRMATION`/`PROHIBITION` (Cases 013/016/017) now exercised, in addition to the original three.
  - ⬜ **Still open**: `AssertionState.NOT_STATED` — untested across all 16 cases.
  - ⬜ **Still open**: no taxon tested across all 5 `ReferenceDomain` values (Ginkgo biloba closest, at 3 of 5).
- **Dependencies:** New Gold Case curation work (source screening → claim extraction → engine evidence → execution), following the same process documented for Cases 001–017.
- **Estimated effort:** UNKNOWN — no per-case effort estimate is recorded anywhere in-repo.
- **Current status:** Narrowed. Remaining scope is `AssertionState.NOT_STATED` coverage and additional `AssertionType` diversity, not full domains.
- **Owner:** UNKNOWN.
- **Acceptance criteria:** New Gold Case(s) built, locked, and reflected in `BENCHMARK_PROGRESS.md`.

### NA-010 — Remove ambiguity around the superseded Case 008 draft
- **Priority:** Short-term (newly identified 2026-08-03; partially resolved same day)
- **Description:** `gold_case_reference_grounded_008_ginkgo_biloba_indicationevidence.py` (non-canonical, domain INDICATION_EVIDENCE) was replaced by `gold_case_reference_grounded_008_ginkgo_biloba_preparation_spec.py` (canonical, domain PREPARATION_SPEC) per `CASES_008_009_010_012_CORRECTION_REPORT.md`, but the old file and its test `test_case_008_indicationevidence.py` remain at repository root with no in-file warning. This is a live import risk: any future code, test, or curator that references "Case 008" by filename guesswork could pick up the wrong one.
- **What was done (2026-08-03):** Verified with the repository's own `repo_dependency_audit.py` that neither file is production-active (the case file classifies as a legacy candidate; the test file classifies as test-only). Added an explicit "SUPERSEDED / NON-CANONICAL" warning to the top docstring of both files, pointing to the canonical replacement. Confirmed via `python3 -m py_compile` and `pytest test_case_008_indicationevidence.py` (12/12 passed) and `pytest test_case_008_ginkgo_biloba_preparation_spec.py` (5/5 passed) that this was a zero-risk, docstring-only change — no imports, classes, or test outcomes changed. Re-ran `repo_dependency_audit.py summary` before/after to confirm the production/test/legacy counts (90/142/131) were unaffected.
- **What was deliberately NOT done:** The superseded file was **not** added to `.github/legacy-files.txt`, because that list currently contains zero `test_*.py` entries — it appears to be a convention specifically for archiving dead *production* source modules, not test files, and adding a test file to it would be new, undiscussed behavior for the existing `archive-legacy.yml` workflow. The case file itself *could* be added (it is a legitimate legacy candidate per the audit tool), but was left out pending a decision on the test file, since archiving one without the other leaves the same ambiguity in a different form.
- **Remaining decision (owner: supervisor):** whether to (a) leave both files as-is with just the docstring warning, (b) add just the case file to `legacy-files.txt` and separately delete or repurpose the orphaned test, or (c) establish a new convention for archiving superseded test files and add both. No action taken on this until decided.
- **Current status:** Partially resolved — ambiguity risk mitigated via warning docstrings; final archival disposition still open.
- **Owner:** Hamid / supervisor (per repository convention, deletions and legacy-list changes require explicit sign-off).
- **Acceptance criteria:** Supervisor decision recorded; if archival is chosen, `archive-legacy.yml` run and `QUALITY_RECORDS_INDEX.json`'s `superseded_artifacts` entry updated to match.

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
