# Pharmaceutical-grade Safety Engine Hardening — Zero Serious False Negative Audit

## Executive conclusion

The repository already contained a meaningful first-stage pharmaceutical safety hardening layer: structured SafetyAssertion objects, serious-interaction classification, conservative conflict retention, evidence authority/confidence, fail-closed handling for severe findings with unknown applicability, traceable evidence IDs, and ranking partition isolation. The current pass audited that implementation against the requested broader safety taxonomy and adversarial failure modes.

The principal remaining general false-negative risk was taxonomy incompleteness rather than the old Hypericum-specific interaction bug. Several high-consequence findings had no first-class structured assertion type and therefore depended on incidental legacy vocabulary. In addition, structured Population metadata was collected from EvidenceRecord rows but discarded before SafetyAssertion construction.

This pass closes those two concrete gaps and adds independent safety operating metrics. It does not claim that the engine has achieved literal zero false negatives; extraction is still deterministic/vocabulary-bounded and candidate-specific applicability remains incomplete.

## Risk register

### Critical

1. **High-consequence taxonomy gaps** — carcinogenicity, genotoxicity, reproductive toxicity, serious adverse events, fatal adverse events, major regulatory/boxed warnings, serotonergic toxicity, severe CNS depression, severe hypertension/hypotension, diabetes/hypoglycaemia interaction and geriatric restriction were not represented as dedicated SafetyAssertion types. A valid serious source could therefore fail to create a structured Severe SafetyFinding unless another legacy term happened to fire. **Remediated in this pass.**

2. **EvidenceRecord population metadata dropped before SafetyAssertion creation** — the engine collected `population` in `evidence_records_index` but did not pass it to `classify_safety_assertions()`. This could erase a critical applicability dimension. **Remediated in this pass.**

### High

3. **Candidate-specific applicability remains incomplete.** Production does not yet perform validated matching across plant part, preparation/extraction/DER, normalized dose/exposure, duration, route, indication and target population. Severe findings with unknown scope are correctly kept out of normal ranking via `EXPERT_REVIEW_REQUIRED`, but this is not regulator-grade applicability adjudication. **Open.**

4. **Dose dependency is carried as raw metadata, not normalized semantics.** Threshold-dependent and exposure-dependent toxicity cannot yet be reliably distinguished from unconditional risk. **Open.**

5. **Extraction remains deterministic and vocabulary-bounded.** Novel prose, tables, scanned labels, indirect causal language, or previously unseen terminology can still be missed. **Open.**

6. **Formal causality assessment is incomplete.** Source authority/confidence is represented, but Bradford-Hill/WHO-UMC-style causality, dechallenge/rechallenge, exposure-response and temporal relationship are not represented as a validated structured policy. **Open.**

### Medium

7. **Formal conflict synthesis is incomplete.** Conflicting reassuring/risk assertions are retained conservatively, but there is no formal recency/document-status/source-precedence synthesis model. **Open.**

8. **Regulatory provenance needs document lifecycle semantics.** Regulator identity is represented, but label vs safety communication vs assessment report, effective date, withdrawn/superseded status and jurisdictional precedence are not fully normalized. **Open.**

9. **Moderate findings can remain normally rankable.** This is not a serious-false-negative path when severity is classified correctly, but a future policy may require some moderate classes to route to expert review based on population/context. **Open policy decision.**

### Low

10. Legacy hard-term vocabulary remains for backward compatibility alongside structured assertions. It is no longer the sole safety decision path, but duplicated safety concepts increase maintenance burden. **Open cleanup; not a current serious-FN blocker.**

## Taxonomy coverage after this pass

Dedicated structured coverage now includes: contraindication; serious/moderate drug interaction; pregnancy; lactation; pediatric; geriatric; hepatic impairment; renal impairment; QT prolongation; bleeding risk; hypertension; hypotension; diabetes/hypoglycaemia interaction; CNS depression; serotonergic toxicity; organ toxicity (including hepatotoxicity/nephrotoxicity/cardiotoxicity/neurotoxicity); allergy; photosensitivity; carcinogenicity; genotoxicity; reproductive toxicity; narrow therapeutic index interaction; CYP induction; CYP inhibition; P-gp interaction; major regulatory/boxed safety warning; serious adverse event; fatal adverse event; precaution/warning; and reassurance/conflict evidence.

Mechanism-only CYP/P-gp signals remain explicitly non-blocking unless a clinical risk relationship is asserted, which protects against false-positive escalation.

## Severity architecture

The hardened path is:

`EvidenceRecord -> sentence-level structured SafetyAssertion -> polarity + safety type + severity + authority/confidence + evidence/context metadata -> SafetyFinding -> EligibilityDecision -> RankingPartition -> Final decision/explainability`

Explicit contraindications and high-consequence safety outcomes are assigned SERIOUS semantically, without requiring a plant-specific rule or a high-risk-drug whitelist. Source authority changes confidence rather than silently downgrading a serious semantic assertion. Severe findings with unconfirmed scope/relevance resolve to `EXPERT_REVIEW_REQUIRED` and are excluded from normal ranking; confirmed relevant severe findings can resolve to hard safety no-go under the existing eligibility decision table.

## Context applicability

The assertion object currently carries preparation, dose metadata, route, affected population and provenance. This pass additionally wires structured EvidenceRecord population metadata into assertions. Plant-part and candidate-context matching are still not validated end-to-end; therefore unknown applicability stays fail-closed for Severe findings instead of being guessed as applicable or irrelevant.

## Fail-open audit

- Missing evidence text -> `DataCompleteness.INCOMPLETE`, not normal eligibility.
- Severe safety + unknown scope/relevance -> `EXPERT_REVIEW_REQUIRED`, not normal ranking.
- Conflicting reassurance + serious risk -> serious risk retained; reassurance cannot overwrite it.
- Multi-compound merge -> structured assertions and eligibility are recomputed across all subrows; dangerous lower-scoring subrows cannot be masked by the selected best row.
- Mechanism-only CYP/P-gp -> non-blocking by design until clinical risk is asserted.

The remaining fail-open risk is primarily **failure to extract a serious assertion at all**, not post-extraction gate compensation.

## Explainability / traceability

For structured safety findings the existing implementation can expose the causal chain:

`Evidence_Record_ID -> source sentence -> assertion type/polarity -> severity -> source authority/confidence -> severity rule -> SafetyFinding -> eligibility gate -> decision/ranking partition`.

Bidirectional trace at row level is supported through evidence IDs and serialized `Safety_Assertions`. A full graph-level reverse index across persisted historical decisions remains outside this pass.

## Adversarial regression tests added

`test_pharmaceutical_safety_zero_fn.py` was written failing-first and covers fatal adverse events, serious adverse events, carcinogenicity, genotoxicity, reproductive toxicity, serotonergic toxicity, severe CNS depression, severe hypertension/hypotension, diabetes interaction, geriatric contraindication, major regulatory/boxed warning, non-normal-ranking behavior for serious risk, and preservation of structured population metadata.

`test_safety_metrics.py` was written failing-first and covers all newly requested validation metrics.

## Safety metrics

A pure validation module `safety_metrics.py` now computes:

- Serious Safety Recall
- Serious Safety Precision
- False Negative Rate
- False Positive Rate
- NO_GO Precision
- NO_GO Recall
- Expert Review Rate
- Unknown Safety Rate

It does not alter production ranking or gate behavior.

## Test results

- New regression tests: **7 passed** (`6 taxonomy/context + 1 metrics`).
- Broad targeted safety/eligibility/interaction/severity/Case006/Case014/E2E suite: **219 passed, 3 xfailed**.
- Broad repository suite excluding 12 modules that cannot collect because exact project `supabase`/`streamlit` dependencies are unavailable in this sandbox: **2661 passed, 3 xfailed, 1 failed**.
- The single broad-suite failure is `test_production_dependency_integrity.py::test_app_py_and_direct_production_modules_are_import_resolvable`, failing while importing `app.py` with `ValueError: not enough values to unpack (expected 2, got 0)`. The repository's prior safety report already identifies this test as environment-sensitive when `app.py` is imported outside its normal Streamlit runtime. It is not caused by the safety changes.
- Unfiltered collection: **12 collection errors**, all due to missing `supabase` or `streamlit` packages. Attempting to install the exact pinned versions from this sandbox failed because the package index is unavailable.

## Can we claim Zero Serious Safety False Negative?

**Not literally.** We can defensibly say the engine is materially closer to a zero-serious-FN operating posture *for recognized structured safety evidence*: once a serious assertion is recognized, it cannot silently enter normal ranking merely because efficacy/market/scientific score is high or because scope is unknown.

A literal or regulator-grade zero-FN claim is still blocked by extraction recall, structured context applicability (plant part/preparation/DER/dose/duration/route/indication/population), formal causality, document lifecycle/source precedence and the limited size of independently curated serious-safety gold cases. The correct current description is **pharmaceutical-grade-oriented, fail-closed for recognized serious safety assertions, with remaining extraction/applicability validation blockers**.
