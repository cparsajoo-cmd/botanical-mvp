# Decisions Log — Botanical R&D Decision Intelligence Platform

Records project decisions actually documented inside this repository. Nothing here is invented — each entry cites the file it was reconstructed from. Where a decision's date, alternatives, or full reasoning are not recorded in-repo, that is marked UNKNOWN rather than filled in. Never delete an entry; superseded decisions are marked as such, not removed.

---

### D-001 — Reference-Grounded Validation is the active track; ValidationCaseProtocol/ExpertPanel is out of scope

- **Date:** UNKNOWN (not dated in-repo beyond "Phase 3A")
- **Context:** Two validation tracks exist in the codebase: `GoldCase`/Reference-Grounded Validation, and `ValidationCaseProtocol`/`ExpertPanel`.
- **Decision:** The current protocol (`VALIDATION_PROTOCOL.md`) governs the `GoldCase` track only.
- **Reason:** "The mechanism to compare its output against a live panel's judgment does not yet exist."
- **Alternatives considered:** UNKNOWN (not documented).
- **Consequences:** `validation_case_protocol.py`, `user_roles.py`, `expert_sign_off.py` remain in the repository but are not exercised by the current protocol.
- **Status:** Active. Documented explicitly as "a Phase 3A decision, not a permanent technical limitation" (`VALIDATION_PROTOCOL.md` §3).

---

### D-002 — Only `ValidationScope.PROVIDED_EVIDENCE` is tested; retrieval/end-to-end validation is out of scope

- **Date:** UNKNOWN
- **Context:** The engine's own retrieval capability is a separate concern from its interpretation/gating/decision logic.
- **Decision:** This program tests interpretation/gates/decision-translation only, never the engine's own retrieval. Enforced in code (`EvaluationRun.__post_init__` raises on `END_TO_END`).
- **Reason:** Keeps the validation question answerable and controlled: "when the engine is given evidence that correctly represents a documented fact, does it reach the same conclusion?"
- **Alternatives considered:** UNKNOWN.
- **Consequences:** A future "Corpus/Retrieval Validation phase" is explicitly reserved but not started.
- **Status:** Active (`VALIDATION_PROTOCOL.md` §3).

---

### D-003 — `SUMMARIZED_BY_CURATOR` forbidden as Ground Truth evidence transformation for non-synthetic cases

- **Date:** UNKNOWN
- **Context:** `ReferenceClaim.evidence_text.transformation_type` needed rules to prevent curator paraphrase from silently becoming Ground Truth.
- **Decision:** Only `VERBATIM`, `NORMALIZED_TERMINOLOGY`, or `TRANSLATED` are permitted for non-`SYNTHETIC` cases. Enforced in code, not just documentation (`gold_case.is_lockable()`, check 6).
- **Reason:** Prevent a curator's paraphrase from being mistaken for a verbatim reference-truth excerpt.
- **Alternatives considered:** UNKNOWN.
- **Consequences:** Any case attempting to lock with `SUMMARIZED_BY_CURATOR` text fails to lock.
- **Status:** Active (`VALIDATION_PROTOCOL.md` §8).

---

### D-004 — Leakage ordering rule: extract Ground Truth first, decide Engine Evidence second, run engine last

- **Date:** UNKNOWN
- **Context:** Curator and evidence-supplier roles are currently the same person (Hamid), creating leakage risk between Ground Truth and Engine Evidence.
- **Decision:** Mandatory ordering — real-source `ReferenceClaim` extraction, then independent `EngineEvidenceInput` decisions, then engine execution. If violated, `LeakageControl.engine_output_observed_before_finalization=True` must be recorded honestly rather than hidden.
- **Reason:** "the ordering discipline in the Leakage Rules exists precisely because curator and evidence-supplier are not organizationally separate people."
- **Alternatives considered:** UNKNOWN.
- **Consequences:** Every case must pass `dataset_split.assess_leakage()` with result `VALID_FOR_HOLDOUT` before it can be locked or used.
- **Status:** Active (`VALIDATION_PROTOCOL.md` §9).

---

### D-005 — `EngineEvidenceInput` is a frozen, four-field shape, structurally incapable of holding Ground Truth

- **Date:** UNKNOWN
- **Context:** Need a hard structural (not just procedural) guarantee that a case's Ground Truth can never reach the engine.
- **Decision:** `EngineEvidenceInput` is a frozen dataclass with exactly four fields (`scientific_name`, `target_indication`, `notes`, `compound_activity_targets`) — structurally unable to hold a `ReferenceClaim` or `ResolvedExpectedOutcome`.
- **Reason:** Makes leakage-prevention a property of the type system, not only of curator discipline.
- **Alternatives considered:** UNKNOWN.
- **Consequences:** `gold_case_execution.execute_gold_case_against_engine()` reads only `GoldCase.engine_evidence`, never `.references[].claims`.
- **Status:** Active, locked (`gold_case.py` docstring; `engine_evidence_input.py`).

---

### D-006 — CONDITIONAL AssertionState left deliberately UNRESOLVED for decision-direction mapping

- **Date:** 2026-07-29 (per `VALIDATION_PROTOCOL.md` v0.3 Change History)
- **Context:** Case 003 (Matricaria chamomilla) produced a `CONDITIONAL` resolved outcome with no principled way to map it to `DecisionDirection`.
- **Decision:** `ADOPTED_CONDITIONAL_POLICY = ConditionalMappingPolicy.UNRESOLVED` — `CONDITIONAL` maps to nothing (case is `NOT_ELIGIBLE` for whole-case agreement) rather than being force-mapped to `HOLD` or a case-specific override.
- **Reason:** Kept open "until more Reference-Grounded cases have been completed and there is empirical basis to decide among the three options."
- **Alternatives considered:** Mapping `CONDITIONAL` to `HOLD`; a case-specific override argument. Both remain implemented in code but not adopted.
- **Consequences:** Case 003 is `NOT_ELIGIBLE` for `decision_direction_agreement` (reason: `ASSERTION_STATE_UNMAPPED`).
- **Status:** Active, explicitly open — "This is an intentional, documented open question — not an oversight — ... Do not resolve this by editing a single case; it is a protocol-level decision." (`VALIDATION_PROTOCOL.md` §14.2)

---

### D-007 — `ReferenceDomain.INDICATION_EVIDENCE` is the only domain currently eligible for whole-case `decision_direction_agreement`

- **Date:** 2026-07-29 (v0.3 adoption)
- **Context:** Not every Ground Truth domain has a natural mapping to the engine's single candidate-level decision.
- **Decision:** Only `INDICATION_EVIDENCE` maps to the whole-case decision. `SAFETY`, `IDENTITY_QUALITY`, `REGULATORY_STATUS` map to their corresponding individual engine gates, not the whole-case decision. `PREPARATION_SPEC` currently maps to nothing.
- **Reason:** Tied to "the current Engine version's decision semantics."
- **Alternatives considered:** UNKNOWN (proposal document discusses domain-by-domain eligibility rationale; full alternative-option list not itemized in-repo as rejected options for this specific sub-decision).
- **Consequences:** Case 007 (Preparation Spec) has no whole-case agreement metric applicable to it by design, not by omission.
- **Status:** Active — "current protocol policy... not a permanent architectural limit" (`VALIDATION_PROTOCOL.md` §14.1).

---

### D-008 — Mapping mismatches between manually supplied and derived `expected_decision_direction` are never silently repaired

- **Date:** 2026-07-29 (v0.3 adoption)
- **Context:** A case's manually supplied `expected_decision_direction` could, in principle, disagree with what Ground Truth actually maps to.
- **Decision:** On mismatch, record `NOT_ELIGIBLE` with reason `EXPECTED_OUTPUT_MAPPING_MISMATCH`. Never overwrite either value; never silently score using the manual value.
- **Reason:** "A mismatch is treated as a real inconsistency requiring curator attention, not an implementation detail to route around."
- **Alternatives considered:** UNKNOWN.
- **Consequences:** Requires explicit curator resolution before such a case can contribute to the agreement metric.
- **Status:** Active (`VALIDATION_PROTOCOL.md` §14.4).

---

### D-009 — Prospective-order requirement for `expected_decision_direction`: process control only, not code-enforced

- **Date:** 2026-07-29 (v0.3 adoption)
- **Context:** `expected_decision_direction` must be set before `EngineEvidenceInput` is introduced, to avoid post-outcome specification — but nothing in the data model timestamps when a field was set.
- **Decision:** This ordering is required by documented construction order and reviewer attention, not by a runtime check. Adding such tracking was explicitly ruled out of scope for this phase; no `AgreementIneligibilityReason` was invented to paper over the gap.
- **Reason:** No timestamp-tracking mechanism exists, and building one was out of scope.
- **Alternatives considered:** UNKNOWN (implied: adding field-level timestamps — explicitly rejected as out of scope).
- **Consequences:** Ordering discipline currently depends entirely on curator/reviewer process, same as Leakage Rule 9.1.
- **Status:** Active, explicitly acknowledged as an enforcement gap (`VALIDATION_PROTOCOL.md` §14.6).

---

### D-010 — Fabricated regulatory-status stub disabled, not deleted

- **Date:** UNKNOWN (Sprint 5, Phase A)
- **Context:** `regulatory_connector.py`'s `REGULATORY_DB` held hand-typed, never-independently-verified `"Yes"/"No"` regulatory-status values for 4 plants, indistinguishable in shape from genuine connector output.
- **Decision:** Disabled via `_LEGACY_STUB_ENABLED = False` rather than removed. `REGULATORY_DB` remains as historical reference; `search_regulatory_sources()` now always calls the real EMA connector.
- **Reason:** "Per the explicit instruction not to simply delete files." Re-enabling requires a deliberate, commented flag change, not a silent revert.
- **Alternatives considered:** Deletion (rejected per standing instruction not to delete files).
- **Consequences:** No plant can produce a fabricated "Regulatory monograph exists" status going forward; only genuine EMA_HMPC inventory matches (and the disjoint legacy literal, for backward compatibility with already-stored data) do.
- **Status:** Active (`ARCHITECTURE.md`, Sprint 5).

---

### D-011 — Legacy files identified for archival are NOT yet moved; archival requires an explicit, re-validated CI run

- **Date:** UNKNOWN (Phase 7)
- **Context:** An earlier version of `ARCHITECTURE.md` incorrectly claimed 67 legacy files had already been moved to `archive/` — they had not been. A subsequent audit also caught that `question_understanding_engine.py` had been wired into production after the original legacy list was generated, and would have been wrongly archived had the (stale) list been trusted.
- **Decision:** Do not restate archival as done from intent alone. `repo_dependency_audit.py` (a reusable, re-runnable tool) plus `test_production_dependency_integrity.py` (a pytest-enforced check) plus `archive-legacy.yml` (which validates the list as its first CI step) now structurally close this gap. 65 files (see Section discrepancy note in `REPOSITORY_STRUCTURE.md`) are confirmed unreachable from production and ready to archive, but archival itself has not been triggered.
- **Reason:** A previously stale, silently-trusted list nearly caused a production-breaking archival.
- **Alternatives considered:** UNKNOWN.
- **Consequences:** `archive/` directory does not exist yet in this repository. Running the GitHub Action "Archive legacy files (Phase 7)" is the one explicitly documented not-yet-done action.
- **Status:** Active/pending execution (`ARCHITECTURE.md`, "Legacy files" section).

---

### D-012 — Explicit evidence-to-gate causal attribution deferred; candidate-level traceability is the current stopping point

- **Date:** UNKNOWN (Tasks 10–13)
- **Context:** It would be desirable to know exactly which evidence record drove a specific gate's PASSED/FAILED status.
- **Decision:** Not implemented in this phase. `gate_results` + `Applicability_Summary.evidence_record_ids` (candidate-level, not evidence-record-level) is the current, intentional stopping point.
- **Reason:** See the architecture note directly above `BotanicalRDCandidateEngine._evaluate_gates()` in `botanical_rd_candidate_engine.py` (full reasoning lives in code comments, not duplicated here).
- **Alternatives considered:** UNKNOWN (full reasoning is in the referenced code comment, not reproduced in `ARCHITECTURE.md` itself).
- **Consequences:** Explainability at the individual-evidence level is not currently available; only candidate-level traceability is.
- **Status:** Active/deferred (`ARCHITECTURE.md`, "Tasks 10–13").

---

### D-013 — TD-001: EMA-sourced preparation/population fields for Case 004 deferred for batch reassessment

- **Date:** UNKNOWN (surfaced by Case 004)
- **Context:** Case 004 (Ginkgo biloba)'s `preparation`/`population` fields were taken from the EMA/HMPC monograph's posology rather than independently derived from the governing Cochrane systematic review's own trial data.
- **Decision:** Not fixed now; recorded as TD-001, to be reassessed as a batch after ~10–15 Gold Cases exist (currently 6).
- **Reason:** Explicit project decision to review technical debt in batches, not case-by-case, to avoid re-litigating one item at a time.
- **Alternatives considered:** UNKNOWN.
- **Consequences:** Does not affect Ground Truth itself (100% Cochrane-sourced); does affect what `applicability_check()`'s `preparation: pass` currently certifies.
- **Status:** Deferred, open (`TECHNICAL_DEBT.md`, TD-001).

---

### D-014 — Sprint 4 implemented by extending `structured_rationale.py`, not by creating new engine files

- **Date:** UNKNOWN (Sprint 4)
- **Context:** `evidence_conflict_reasoning()` already computed most of what Sprint 4 needed.
- **Decision:** Extend `structured_rationale.py` in place (`classify_evidence_consistency()`, `classify_dominant_evidence_pattern()`, `build_possible_explanations()`, `detect_research_gaps()`, `build_evidence_conflict_structured()`).
- **Reason:** Avoids duplicating logic that already existed.
- **Alternatives considered:** Creating `conflict_engine.py`/`consistency_engine.py` — explicitly rejected.
- **Consequences:** All Sprint 4 output lives alongside the existing evidence-conflict-reasoning code; verified not to change `Evidence_Confidence`, `R&D_Opportunity_Score`, or `Decision_Class_AH` (`test_sprint4_addition_does_not_change_scores_or_ranking`).
- **Status:** Active (`ARCHITECTURE.md`, "Sprint 4").

---

### D-015 — Sprint 4 explanation categories restricted to 7 structurally-supportable causes; species/target/mechanism explanations explicitly rejected

- **Date:** UNKNOWN (Sprint 4)
- **Context:** `possible_explanations` needed a bounded, honest vocabulary rather than open-ended causal claims.
- **Decision:** Only 7 categories permitted (Population, Dose, Extraction/preparation, Study design, Endpoint, Study quality, Evidence level differences), each backed by a real keyword-hint match or a structural check.
- **Reason:** "Species, target, mechanism, and publication-specific explanations are explicitly rejected... because no comparable structured field exists to honestly support them — adding them would be a fabricated causal claim, not a detected pattern."
- **Alternatives considered:** Broader explanation categories (rejected — see `REJECTED_EXPLANATION_CATEGORIES`).
- **Consequences:** Sprint 4 output is conservative by design; some real-world explanatory patterns are simply not surfaced.
- **Status:** Active (`ARCHITECTURE.md`, "Sprint 4").

---

### D-016 — Telemetry (Sprint 6A.2) and evidence (`evidence_records`) kept as strictly separate concerns

- **Date:** UNKNOWN (Sprint 6A.2)
- **Context:** Risk of conflating "how collection ran" with "what collection found."
- **Decision:** `telemetry_persistence.py` writes only to its own `connector_telemetry` table, never to `evidence_records`/`sources`.
- **Reason:** "Mixing them would make neither cleanly queryable."
- **Alternatives considered:** UNKNOWN.
- **Consequences:** Telemetry failures never affect evidence collection or recommendation logic (`persist_connector_telemetry()` never raises; verified by `test_persistence_failure_returns_gracefully_never_raises`).
- **Status:** Active (`ARCHITECTURE.md`, "Sprint 6A.2").

---

### D-017 — Reference-Grounded Validation Phase 2 capability is limited to structured safety-target inputs; natural-text hard-safety extraction is explicitly not implemented or validated

- **Date:** UNKNOWN
- **Context:** Open architectural question (also tracked in prior chat-based project memory) about whether feeding structured activity targets into the Hard Safety Gate is architecturally acceptable, and whether free text should ever be able to trigger it.
- **Decision:** Hard-safety-gate behavior is validated only for structured, preclassified inputs (`EngineEvidenceInput.compound_activity_targets` → `plant_compounds_df["target"]` → `_hard_safety_gate()`). `SAFETY_TERMS` (soft, free-text-scanned) and `HARD_SAFETY_TERMS` (hard-stop-triggering) remain disjoint vocabularies by design; no code path derives `compound_activity_targets` from `ReferenceClaim`/`ResolvedExpectedOutcome`/`expected_output`.
- **Reason:** Keeps the accepted validation scope honest: "Reference-grounded, provided-evidence validation," not natural-text safety extraction.
- **Alternatives considered:** UNKNOWN.
- **Consequences:** A hazard word typed into free-text `notes` alone cannot trigger the hard-safety gate.
- **Status:** Active, locked by `test_gold_case_execution.py`'s Structured Safety-Target Gate Validation pair and `test_structural_leakage_boundary.py`'s v4 correction #2 tests (`ARCHITECTURE.md`, "Reference-Grounded Validation v4 — Phase 2 capability statement").

---

## Superseded Decisions

None identified in this repository snapshot as of this documentation pass. If a future decision supersedes one of the above, add a note here and mark the original entry's Status as "Superseded by D-0XX" rather than deleting it.
