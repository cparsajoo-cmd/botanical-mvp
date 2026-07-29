# Validation Protocol — Reference-Grounded Validation Program

Status: **DRAFT — pending Hamid's final confirmation of this revision** (Persian v0.1 content approved subject to the three corrections below; this is that corrected revision, translated to English)
Version: v0.2 (Phase 3A.1)
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

- **H0 (null):** the engine's derived decision direction (`Decision_Class`/gate status) agrees with the locked `ResolvedExpectedOutcome`, per the two metrics already implemented in `evaluation_run.py` (`decision_direction_agreement`, `safety_serious_false_negative_rate`).
- **H1:** it does not.

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
- `build_evaluation_run()` runs without error and both metrics compute.
- The full existing test suite and `repo_dependency_audit.py validate` remain green (no regression).
- The case, protocol, and template are documented well enough for a third party to reproduce the entire process.

**Important methodological point:** "the engine agreed with the reference" is **not** itself a success criterion of the validation process. Agreement and disagreement are both scientifically valid, informative outcomes. Success means the process was executed rigorously and honestly — not that the engine "passed."

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

## 14. Change History

| Version | Date | Summary |
|---|---|---|
| v0.1 | 2026-07-29 | Initial draft (Persian) — objective, scope, ground truth/leakage rules, success/failure criteria, limitations, threats to validity |
| v0.2 | 2026-07-29 | Added Definitions/Glossary (Section 1); added this Change History (Section 14); translated to English; no substantive rule changed from v0.1 |

---

**Status of this document:** draft, pending Hamid's confirmation of this specific revision. Sections 3 (track selection), 6 (source-selection rule), and 10/11 (success/failure criteria) are the ones most worth a final check before use in Phase 3B.
