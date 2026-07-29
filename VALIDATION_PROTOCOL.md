# Validation Protocol — Reference-Grounded Validation Program

Status: **DRAFT — pending Hamid's final confirmation of this revision** (v0.3 adopts the Prospective Claim-to-Decision Mapping implementation into the protocol; see Section 14 and Section 15's Change History)
Version: v0.3 (Phase 4 — Evaluation Layer)
Track: `GoldCase` / Reference-Grounded Validation (v4). The `ValidationCaseProtocol`/`ExpertPanel` track is explicitly out of scope for this protocol — see Section 3.

This document is written once and governs every future case (case 1 through case N). Case-specific decisions (which plant, which document) do not belong here — they are filled into `VALIDATION_CASE_TEMPLATE.md`, under the rules defined here.

---

## 1. Definitions

Terms as used specifically in this repository, not generic definitions.

- **Ground Truth** — the final, resolved, reference-grounded conclusion for one case/domain/assertion. In this program: `GoldCase.resolved_outcomes` (`list[ResolvedExpectedOutcome]`), computed by `resolve_expected_outcomes()` from the case's `ReferenceClaim`s via `reference_precedence.py`'s domain hierarchies. Never hand-typed. Never derived from engine output.
- **Reference Claim** — one specific, source-locatable assertion extracted from an authoritative document. Modeled as `ReferenceClaim` (domain, assertion_type, assertion_state, severity, source_reference_id, source_locator, evidence_text, extraction_confidence). The atomic unit of Ground Truth before precedence resolution.
- **Reference Source** — the document a Reference Claim was extracted from. Modeled as `ReferenceDescriptor` (reference_id, source_type, version, scope fields). Must use a `source_type` from the Permitted Sources table (Section 6) to participate in precedence resolution.
- **Curator** — the person who reads a real Reference Source and transcribes its claims into `ReferenceClaim` objects, and who separately supplies `EngineEvidenceInput` values. In this program both roles are currently performed by the same person (Hamid) — the ordering discipline in the Leakage Rules (Section 9) exists precisely because curator and evidence-supplier are not organizationally separate people.
- **Reviewer** — a person who checks a curator's work against the Reference Source without having produced it themselves. Distinct from Curator. Not currently a first-class field on `GoldCase` (see the Case Template's known-gaps section) — recorded, if at all, via `FieldProvenance.curator` (`ReviewerRole`) or external documentation.
- **Validation Case** — one instance of `GoldCase`: the complete, lockable unit tying together a `ValidationUnit`, references with claims, resolved outcomes, and engine evidence for one Scientific Question (Section 4).
- **Evidence** — always one of two distinct things in this program, never conflated: (a) reference-truth evidence — a `ReferenceClaim`'s `evidence_text`, read only by the evaluator to compute Ground Truth; (b) Engine Evidence (below). A case's `GoldCaseReference.claims` never reaches the engine directly.
- **Engine Evidence** — the only evidence the real production engine (`BotanicalRDCandidateEngine`) ever receives for a case. Modeled as `EngineEvidenceInput` (a frozen, four-field dataclass: `scientific_name`, `target_indication`, `notes`, `compound_activity_targets`), passed via `GoldCase.engine_evidence`. Structurally incapable of holding a `ReferenceClaim` or `ResolvedExpectedOutcome` — see `engine_evidence_input.py`'s own module docstring.
- **Leakage** — any pathway, structural or procedural, by which a case's Ground Truth (or knowledge of it) could influence the Engine Evidence supplied to the engine, or by which the engine's own output could influence Ground Truth after the fact. Tracked structurally via `dataset_split.LeakageControl`/`assess_leakage()`, and procedurally via Section 9.
- **Holdout** — a case whose `DatasetSplit` is `LOCKED_HOLDOUT`: locked, leakage-assessed as `VALID_FOR_HOLDOUT`, and eligible for inclusion in an `EvaluationRun`. Distinct from `DEVELOPMENT`/`VALIDATION` split cases, which may still be actively curated.
- **Reference-Grounded** — `GoldCaseKind.REFERENCE_GROUNDED`: a case whose Ground Truth is built from a real, cited, authoritative Reference Source, as opposed to `GoldCaseKind.SYNTHETIC` (invented content used only to exercise pipeline mechanics). This program produces Reference-Grounded cases exclusively.

## 2. Validation Objective

Determine whether the mechanisms locked down in Phase 2 (`ReferenceClaim → precedence resolution → ResolvedExpectedOutcome → GoldCase locking → EvaluationRun`) produce a decision, when run on **real** (not synthetic) evidence, that agrees with the documented conclusion of an authoritative reference source — using the existing, unmodified pipeline, with no change to `botanical_rd_candidate_engine.py`.

This is not a general scientific proof of engine accuracy. It is a controlled exercise asking: "when the engine is given evidence that correctly represents a documented fact, does it reach the same conclusion?"

## 3. Validation Scope

**In scope:**
- The `GoldCase` track only. The `ValidationCaseProtocol`/`ExpertPanel` track is excluded because the mechanism to compare its output against a live panel's judgment does not yet exist — a Phase 3A decision, not a permanent technical limitation.
- Exactly one `ReferenceDomain` per case (never all five at once).
- `ValidationScope.PROVIDED_EVIDENCE` only — already enforced in code (`EvaluationRun.__post_init__` raises on `END_TO_END`). This program tests interpretation/gates/decision-translation, never the engine's own retrieval.
- `GoldCaseKind.REFERENCE_GROUNDED` cases only.

**Out of scope:**
- Any change to the central engine or its scoring/ranking logic.
- Retrieval/end-to-end validation (`ValidationScope.END_TO_END` — explicitly reserved in code for a future Corpus/Retrieval Validation phase).
- Building the `ExpertPanel`-vs-platform-output comparison mechanism.
- Inferring Ground Truth from engine output, in any form.

## 4. Scientific Question — Standard Template

Every case has exactly one Scientific Question, in this fixed form:

> "Does the reference-grounded resolved outcome (`ResolvedExpectedOutcome`) for `<taxon>` in domain `<domain>` (`<assertion_type>`), under a specified `<population>`/`<route>`/`<preparation>`/`<jurisdiction>`, agree with the decision the engine produces when given equivalent, independently curator-supplied evidence?"

Each case targets exactly one primary assertion (`AssertionType`) and one domain — never several claims bundled into one case.

## 5. Hypothesis — General Form

- **H0 (null):** the engine's derived decision direction (`Decision_Class`/gate status) agrees with the locked `ResolvedExpectedOutcome`, per whichever of the two metrics already implemented in `evaluation_run.py` (`decision_direction_agreement`, `safety_serious_false_negative_rate`) is applicable to the given case (see Section 14 for `decision_direction_agreement` eligibility, and Section 10 for both metrics' applicability conditions) — not every case activates both.
- **H1:** for the metric(s) applicable to this case, it does not.

**Explicitly recorded:** a single case's result (N=1) is one observation, not a generalizable statistical conclusion. Statistical power only emerges at larger N (Section 12).

## 6. Permitted Sources

The actual ranking table, taken directly from `reference_precedence.py`'s `_DOMAIN_HIERARCHIES` / `_SAFETY_FALLBACK_RANK`:

| Domain | Rank order (highest to lowest) |
|---|---|
| Identity/Quality | PHARMACOPOEIA, EMA_HMPC, WHO_MONOGRAPH, TAXONOMIC_AUTHORITY |
| Indication/Evidence | SYSTEMATIC_REVIEW, EMA_HMPC, WHO_MONOGRAPH, ESCOP_MONOGRAPH, COMMISSION_E |
| Safety | No direct rank list — severity decides first; used only to break ties: EMA_HMPC, WHO_MONOGRAPH, ESCOP_MONOGRAPH, COMMISSION_E |
| Regulatory status | NATIONAL_REGULATORY, EMA_HMPC, OTHER_NATIONAL_REGULATORY |
| Preparation spec | EMA_HMPC, PHARMACOPOEIA, WHO_MONOGRAPH, ESCOP_MONOGRAPH |

**Source-selection rule (criterion → conclusion, not the reverse):** for the first case, prefer a source that (a) appears in the chosen domain's hierarchy, (b) ranks as high as possible within it, (c) has a real, accessible document for the chosen candidate. **Mechanically applying this rule to the table above** — not a prior preference — is what makes `EMA_HMPC` stand out, since it is the only source_type present in all five hierarchies. This is the rule's output, to be re-checked once a domain and a real candidate/document are actually chosen, not assumed in advance.

**Known gap:** `FDA` is not currently in any hierarchy — only the generic `NATIONAL_REGULATORY`/`OTHER_NATIONAL_REGULATORY` buckets exist. If an FDA-specific source is required, that is a separate protocol decision (adding a new value = a code change = out of scope for Phase 3A).

## 7. Non-Permitted Sources

- Any `source_type` outside the table above — the code resolves it to `INSUFFICIENT_METADATA`, so the case cannot lock.
- Secondary/tertiary sources: blogs, unreferenced wikis, marketing material, AI-generated summaries, non-peer-reviewed preprints — unless explicitly added by a later decision.
- The platform's own retrieval or output used as a "reference" — the same principle as `ValidationCaseProtocol`'s `ReferenceEvidenceCorpus.built_independently_of_platform`, extended here even though `ReferenceDescriptor` has no equivalent explicit flag.

## 8. Ground Truth Rules

- Every claim must come from a `ReferenceClaim` with a `source_locator` traceable to a specific section/page of a permitted source.
- `evidence_text.transformation_type` may only be `VERBATIM`, `NORMALIZED_TERMINOLOGY`, or `TRANSLATED`. **`SUMMARIZED_BY_CURATOR` is forbidden for non-SYNTHETIC cases in the code itself** (`gold_case.is_lockable()`, check 6) — verbatim excerpt, translation, or terminology normalization only, never a curator's paraphrase (mine or yours).
- Resolution must reach `ResolutionStatus.SELECTED` through the real logic in `reference_precedence.py` — never forced by hand.
- The target `curation_status` must be stated explicitly for each case (Case Template, Section 9).

## 9. Leakage Rules

1. **Mandatory ordering:** extract and record the `ReferenceClaim` from the real source first → then, separately, with an explicit independence note, decide `EngineEvidenceInput.notes`/`compound_activity_targets` → only then run the engine.
2. If the engine is run earlier for any reason, `LeakageControl.engine_output_observed_before_finalization=True` must be recorded honestly; the case remains usable, but the fact is never hidden.
3. The reason for selecting the case itself must be documented **before** seeing engine output.
4. Claude/AI must not use knowledge of the engine's internal vocabulary (e.g. `HARD_SAFETY_TERMS`) to help select which case or claim to use.
5. Every case must pass `dataset_split.assess_leakage()` with result `VALID_FOR_HOLDOUT` before it can be locked or used.

## 10. Success Criteria

- The case locks (`is_lockable() == True`) for genuine reasons, not by working around the rules.
- `assess_leakage()` returns `VALID_FOR_HOLDOUT`.
- `build_evaluation_run()` runs without error.
- **Metric applicability, not blanket computation, is what's required:**
  - `decision_direction_agreement` is `MetricStatus.COMPUTED` when the case is `AgreementEligibility.ELIGIBLE` (Section 14.3). For a `NOT_ELIGIBLE` case, exclusion from that metric's denominator, together with the specific `AgreementIneligibilityReason` recorded in `EvaluationRun.agreement_eligibility` (Section 14.7), is valid, expected behavior — not a defect.
  - `safety_serious_false_negative_rate` is `MetricStatus.COMPUTED` only when at least one `SELECTED` `SAFETY`/`SERIOUS`/`PRESENT` resolved outcome exists for the case(s) in the run. A case with no such outcome (e.g. most `INDICATION_EVIDENCE`-domain cases) correctly produces a structurally zero denominator and `MetricStatus.NOT_COMPUTABLE` for this metric — **this is not a validation failure.**
  - What *is* required: no metric applicable to the case set may be silently omitted from `EvaluationRun.results`, and no case eligible for a given metric may be silently excluded from it without an explicit, recorded reason.
- The full existing test suite and `repo_dependency_audit.py validate` remain green (no regression).
- The case, protocol, and template are documented well enough for a third party to reproduce the entire process.

**Important methodological point:** "the engine agreed with the reference" is **not** itself a success criterion of the validation process. Agreement and disagreement are both scientifically valid, informative outcomes. Success means the process was executed rigorously and honestly — not that the engine "passed," and not that every metric returned a numeric value regardless of whether it structurally applied to the case.

## 11. Failure Criteria

- The case fails to lock (an incomplete element) → a curation-completeness failure, not a validation failure; the case returns to DRAFT.
- Leakage is detected (`QUARANTINED`/`INVALID_FOR_HOLDOUT`) → the case is invalid for this program and must be excluded or rebuilt.
- Ground Truth traces to a non-permitted source, or to curator-summarized text → invalid; must be rebuilt with a verbatim excerpt.
- Any attempt — deliberate or accidental — to shape `EngineEvidenceInput` with knowledge of `ResolvedExpectedOutcome` or the engine's internal vocabulary → invalidates the case regardless of its numeric result.

## 12. Limitations

- N=1 (or small N) carries no statistical power; it only demonstrates pipeline correctness on one real fact pattern.
- Only `PROVIDED_EVIDENCE` scope — retrieval capability is never tested.
- Only one `ReferenceDomain` per case — cross-domain interaction is never tested.
- Ground Truth reflects one authoritative source's stated position — it does not itself resolve genuine scientific controversy in the underlying literature (`reference_precedence.py`'s tie-breaking rules are a documented convention, not a claim of absolute scientific truth).
- No live expert panel exists in this track, by design — a documented judgment call, not "expert-validated" in the `ValidationCaseProtocol`/Appendix-A sense.

## 13. Threats to Validity

- **Selection bias** — choosing a case that is too easy or too edge-case. Mitigated by documenting the selection rationale before viewing engine output.
- **Extraction bias** — a curator's reading of the source document is itself an interpretive act. Mitigated by the VERBATIM/NORMALIZED/TRANSLATED restriction and the mandatory `source_locator`.
- **Confirmation leakage** — unconsciously shaping engine evidence to match the expected result. Mitigated by the ordering rule in Section 9.
- **Construct validity of the metrics** — only two metrics are implemented (`decision_direction_agreement`, `safety_serious_false_negative_rate`); gate-level agreement, top-k inclusion, and GRADE calibration are not implemented. A case could appear "in agreement" on these two metrics while disagreeing on dimensions they don't capture — this must be disclosed, never hidden.
- **Reactivity** — the very fact that this case is being built to demonstrate the pipeline works could unconsciously bias case selection toward a favorable outcome.

## 14. Prospective Claim-to-Decision Mapping

Formally adopts the implementation in `agreement_eligibility.py` (Phases 1–2) and `evaluation_run.py` (Phase 3), built from the "Prospective Claim-to-Decision Mapping Proposal" design document and its accepted revisions. This section governs how `GoldCase.resolved_outcomes` (claim-level Ground Truth) may be compared against the engine's candidate-level output for the `decision_direction_agreement` metric — a question the original v0.2 protocol left open, and which Case 003 showed cannot be answered ad hoc without risking post-outcome specification.

**14.1 Domain policy.** `ReferenceDomain.INDICATION_EVIDENCE` is presently the **only** domain eligible for whole-case `decision_direction_agreement` (`agreement_eligibility._ELIGIBLE_DOMAINS`). This is **current protocol policy, tied to the current Engine version's decision semantics — not a permanent architectural limit.** `SAFETY`, `IDENTITY_QUALITY`, and `REGULATORY_STATUS` map to their corresponding engine gates individually, not to the whole-case decision; `PREPARATION_SPEC` currently maps to nothing. If a future Engine version changes how these domains factor into its candidate-level decision, this policy may be revised without redesigning the mapping architecture itself.

**14.2 AssertionState → DecisionDirection mapping** (`agreement_eligibility.map_assertion_state_to_direction()`):

| AssertionState | Maps to | Basis |
|---|---|---|
| `PRESENT` | `DecisionDirection.POSITIVE` | Unconditional |
| `ABSENT` | `DecisionDirection.NEGATIVE` | Unconditional |
| `NOT_STATED` | *(none — not eligible)* | The source never addressed the question; nothing to map |
| `INSUFFICIENT` | *(none — not eligible)* | Same reasoning as `NOT_STATED` |
| `CONDITIONAL` | *(none — unresolved)* | **Deliberately unresolved under the currently adopted policy** (`ADOPTED_CONDITIONAL_POLICY = ConditionalMappingPolicy.UNRESOLVED`). Two other options (mapping to `HOLD`, or a case-specific override) remain implemented and available via an explicit override argument, but neither is adopted. This is an intentional, documented open question — not an oversight — kept open until more Reference-Grounded cases have been completed and there is empirical basis to decide among the three options. Do not resolve this by editing a single case; it is a protocol-level decision.

**14.3 Eligibility requirements** (`agreement_eligibility.assess_agreement_eligibility()`), all four required:
1. Exactly one `SELECTED` resolved outcome exists in a currently eligible domain (14.1). Zero such outcomes, or more than one (ambiguous), makes the case `NOT_ELIGIBLE`.
2. That outcome's `AssertionState` maps to a `DecisionDirection` under 14.2.
3. `GoldCase.expected_output.expected_decision_direction` is set (prospectively — see 14.6).
4. That set value is **exactly equal** to the mapped direction from step 2.

**14.4 Mapping mismatch.** If requirement 4 fails — a manually supplied `expected_decision_direction` disagrees with what the mapping in 14.2 produces from Ground Truth — the case is recorded `NOT_ELIGIBLE`, reason `EXPECTED_OUTPUT_MAPPING_MISMATCH`. **This must never be silently repaired (by overwriting either value) and never silently scored using the manually supplied value instead of the mapped one.** A mismatch is treated as a real inconsistency requiring curator attention, not an implementation detail to route around.

**14.5 Derivation behavior** (`agreement_eligibility.derive_expected_output_from_resolved_outcomes()`), for populating `expected_decision_direction` from Ground Truth:
- If the existing value is `None` and a direction is derivable (14.2/14.3): populate it, returning a new `ExpectedOutput`.
- If the existing value already equals the derived direction: return the existing object **unchanged** — never a needless replacement.
- If the existing value **conflicts** with the derived direction: raise `ExpectedOutputDirectionConflictError` explicitly. **Never silently overwrite an existing conflicting value, and never silently keep it while treating derivation as having succeeded.**

**14.6 Prospective-order requirement.** `ExpectedOutput.expected_decision_direction` **must be set and frozen before `EngineEvidenceInput` is introduced for a case** — the same ordering discipline as Leakage Rule 9.1, extended to the expected-outcome side rather than only the evidence side. Defining or adjusting the expected direction after the engine's actual output has already been observed is post-outcome specification and invalidates any resulting agreement measurement, regardless of whether the eligibility checks in 14.3 otherwise pass. **The current implementation cannot verify this ordering programmatically** — nothing in the data model timestamps when a field was set, and adding such tracking was explicitly out of scope for this phase; there is no `AgreementIneligibilityReason` for an ordering violation, and none should be invented to paper over this gap. This remains a **required curation/process control**, enforced the same way Leakage Rule 9.1 already is: by documented construction order and reviewer attention, not by a runtime check.

*On Case 003, precisely:* Case 003's actual, programmatic `NOT_ELIGIBLE` reason is `ASSERTION_STATE_UNMAPPED` — its resolved outcome is `CONDITIONAL`, and `CONDITIONAL` has no mapping under the currently adopted `UNRESOLVED` policy (14.2). This is entirely independent of construction order; Case 003 would be `ASSERTION_STATE_UNMAPPED` even if its `ExpectedOutput` had been set with perfect prospective timing. Case 003 is cited here only as a *worked illustration* of why 14.6's ordering discipline matters in practice — during its curation, an `ExpectedOutput.expected_decision_direction` was drafted, then engine evidence was drafted and revised, then the readiness/agreement questions were worked through iteratively; had a direction been assigned prospectively and then left unexamined through that process, its correctness would have depended entirely on curator discipline, not on anything the code could check. That is the general risk 14.6 exists to name — it is not, and must not be read as, Case 003's actual disqualifying condition.

**14.7 Evaluation reporting.** `build_evaluation_run()` must compute and record an explicit `AgreementEligibilityResult` (`EvaluationRun.agreement_eligibility`, keyed by `case_id`) for **every** case that executes successfully — both `ELIGIBLE` and `NOT_ELIGIBLE`, each with its specific reason. **No executable case may be silently omitted from this record.** Only `ELIGIBLE` cases contribute to the `decision_direction_agreement` numerator/denominator; `NOT_ELIGIBLE` cases are excluded from that metric but still appear, by name and reason, in `agreement_eligibility`. This does not change `safety_serious_false_negative_rate`, which was never derived from `expected_output`/`DecisionDirection` and is unaffected by this section.

## 15. Change History

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-07-29 | Initial draft (Persian) — objective, scope, ground truth/leakage rules, success/failure criteria, limitations, threats to validity |
| v0.2 | 2026-07-29 | Added Definitions/Glossary (Section 1); added this Change History (Section 14); translated to English; no substantive rule changed from v0.1 |
| v0.3 | 2026-07-29 | Added Section 14, Prospective Claim-to-Decision Mapping — formally adopts `agreement_eligibility.py`/`evaluation_run.py`'s domain policy, AssertionState mapping (CONDITIONAL left unresolved), eligibility requirements, mapping-mismatch handling, derivation behavior, the prospective-order requirement (documented as a process control, not programmatically enforced), and mandatory per-case eligibility reporting. No prior section's rules changed; Change History renumbered to Section 15. Clarification pass (same version): corrected Section 10's success criteria from "both metrics compute" to metric-applicability-aware criteria (Section 5 hypothesis wording aligned accordingly); corrected Section 14.6 to separate Case 003's actual programmatic ineligibility reason (`ASSERTION_STATE_UNMAPPED`, unrelated to construction order) from its use as a worked illustration of the ordering principle; simplified 14.1's rationale and bound it explicitly to the current Engine version. |

---

**Status of this document:** draft, pending Hamid's confirmation of this specific revision. Sections 3 (track selection), 6 (source-selection rule), 10/11 (success/failure criteria), and 14 (Prospective Claim-to-Decision Mapping — newly adopted, especially the still-open CONDITIONAL question in 14.2) are the ones most worth a final check before use in Phase 4/Case 004.
