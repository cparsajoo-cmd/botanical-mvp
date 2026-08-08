# Scientific Safety Audit — Pharmaceutical-grade Safety Engine Hardening

## Scope audited

Reviewed the production path around `interaction_severity_classifier.py`, `severity_assignment_policy.py`, `botanical_rd_candidate_engine.py`, `eligibility_gate.py`, `evidence_authority.py`, evidence interpretation/record transport, SafetyFinding, gate logic, regulatory finding logic, explainability/causal traceability, Gold Case safety regressions, E2E-facing execution, and safety/interaction/regulatory tests.

## Critical pre-change false-negative path proven

The previous interaction classifier assigned an explicit contraindication to `MODERATE_INTERACTION` when no member of the narrow `HighRiskInteractionDrugClass` whitelist was detected. This meant clinically explicit contraindications such as population contraindications (for example pregnancy) were not semantically SERIOUS unless a recognized high-risk interacting drug class was also present. The behavior was generic and therefore not limited to Case 006 or Hypericum.

A second fail-open path existed in multi-compound row merging: `Safety_Flags` were merged across sub-rows, but the structured Phase-4 eligibility fields were not recomputed from all sub-row safety assertions. A lower-scoring compound-specific safety signal could therefore be visible in merged text while authoritative eligibility fields remained inherited from the highest-scoring sub-row.

## Implemented architecture

A new `safety_assertion_engine.py` introduces a structured assertion layer:

`EvidenceRecord -> source sentence -> SafetyAssertion -> semantic severity -> SafetyFinding -> EligibilityDecision`.

Raw keywords are extraction aids only. The gate consumes structured assertion severity. Assertions retain assertion type, polarity, severity, confidence/evidence strength, affected population, affected drug classes, preparation, dose metadata, route, authority, authority score, evidence record id, source URL, exact source sentence, matched language, severity-rule version, classifier version, and reason.

The taxonomy now explicitly represents:

- contraindication
- serious drug interaction
- moderate interaction
- precaution
- warning
- pregnancy
- lactation
- pediatric restriction
- hepatic impairment
- renal impairment
- QT prolongation
- bleeding risk
- CYP induction
- CYP inhibition
- P-gp interaction
- organ toxicity
- photosensitivity
- allergic risk
- narrow-therapeutic-index interaction
- reassurance / explicit absence-of-risk evidence

Explicit contraindication language is SERIOUS without requiring a drug-class whitelist. Mechanism-only CYP/P-gp signals remain non-blocking unless a clinical risk relationship is asserted. Protective organ-toxicity contexts are excluded from causal toxicity escalation.

## Evidence conflict

Positive risk assertions and explicit reassurance assertions are retained simultaneously. `Safety_Evidence_Conflict` is set when both exist. A reassuring record cannot overwrite a serious risk record. Serious risk remains conservative and routes to the appropriate safety gate while the conflict is exposed for expert review.

## Confidence and authority

Safety confidence is separate from decision severity: `High`, `Moderate`, `Low`, `Insufficient`.

Authority changes confidence, not the semantic meaning of an explicit source assertion. The shared authority classifier was extended so FDA, Health Canada, TGA, clinical guidelines, EMA, WHO, ESCOP, systematic reviews, RCTs, case reports, commercial sources, blogs, and unknown sources are not collapsed to the same weight.

This avoids the unsafe pattern where a low-authority assertion is silently treated as high-certainty, while also avoiding the opposite unsafe pattern where a serious assertion becomes “safe” merely because its source is weak. Weak serious evidence remains visible and review-requiring.

## Explainability and traceability

Each structured safety gate can now expose:

`Evidence_Record_ID -> source sentence -> assertion type/polarity -> severity -> authority/confidence -> severity rule -> eligibility gate -> decision`.

New output fields:

- `Safety_Assertions`
- `Safety_Decision_Confidence`
- `Safety_Evidence_Conflict`
- `Safety_Severity_Rule`

`decision_explainability.py` carries the assertion trace into the eligibility gate explanation and records the severity rule as an applied rule.

## Multi-compound merge hardening

Merged candidate rows now aggregate all structured safety assertions across sub-rows and recompute:

- Eligibility_Status
- Hard_No_Go
- Eligible_For_Normal_Ranking
- Ranking_Partition
- Score_Validity
- Gate_Type / Gate_Reason / Gate_Evidence_IDs
- Safety and regulatory evidence ids
- Safety confidence/conflict/severity/rule/scope/relevance
- Regulatory status/scope/relevance
- Data_Completeness
- Requires_Expert_Review

This closes the “safe best sub-row masks dangerous lower-scoring sub-row” eligibility inconsistency.

## Regression results

Pre-change targeted Safety baseline: **102 passed**.

Post-change broad Safety/Severity/Eligibility/Interaction/Regulatory/Authority suite (excluding one Supabase-bound persistence test unavailable in this sandbox): **378 passed, 3 xfailed**.

Post-change broad repository suite runnable without unavailable third-party runtime dependencies: **2651 passed, 3 xfailed**.

Full unfiltered pytest collection cannot run in this sandbox because `supabase` and `streamlit` are not installed; 12 dependency-bound test modules fail during collection for that environmental reason. The production dependency integrity test is also environment-sensitive when importing `app.py` without Streamlit.

## Remaining weaknesses / blockers

The engine is materially safer, but I would **not** call it fully Pharmaceutical-grade yet.

### Blocker 1 — candidate-specific applicability is still incomplete

Assertions now carry preparation, dose metadata, route, and population, but the live production pipeline still does not perform a validated structured match between those assertion dimensions and the candidate context. Consequently, a severe risk with unknown scope resolves to `EXPERT_REVIEW_REQUIRED`, not a fabricated automatic `NO_GO_SAFETY`. This is fail-closed for ranking, but it is still insufficient for regulator-grade applicability adjudication.

### Blocker 2 — dose dependency is not yet semantically parsed

The assertion schema stores dose information, but does not reliably distinguish unconditional risk from threshold-dependent, exposure-dependent, or dose-specific risk. A pharmaceutical-grade implementation needs normalized dose/exposure units plus explicit conditionality logic.

### Blocker 3 — route/preparation equivalence requires controlled normalization

Raw preparation/route metadata are carried into assertions, but equivalence/mismatch (e.g. oral extract vs topical preparation; standardized extract vs infusion) is not yet resolved by a dedicated validated safety applicability policy.

### Blocker 4 — conflict resolution is conservative but not a formal evidence-synthesis model

Conflict is surfaced and serious evidence is never overwritten, which fixes the unsafe behavior. However, the engine does not yet perform formal source-precedence + recency + study-quality + population/preparation applicability synthesis to resolve contradictory safety claims into a regulator-style adjudication.

### Blocker 5 — coverage remains vocabulary-bounded

The system is now `keyword -> structured assertion -> decision`, not `keyword -> NO_GO`, but extraction remains deterministic vocabulary/pattern based. Novel phrasing, tables, label structure, or highly indirect safety language can still be missed. This should eventually be supplemented by validated structured extraction with abstention and human review, not by expanding an uncontrolled keyword list.

### Blocker 6 — authority taxonomy is improved but not jurisdiction/context complete

FDA, Health Canada, TGA, EMA, WHO, ESCOP and clinical guidelines are now distinguished, but regulator-grade source precedence should also encode document type/status (label, safety communication, monograph, assessment report, withdrawn/superseded document), jurisdiction, version/effective date, and supersession relationships.

## Reviewer answer

Could a *recognized structured serious safety assertion* still silently enter normal ranking? Under the hardened path, it should not: serious assertions become severe SafetyFindings and, when scope is unknown, are routed to `EXPERT_REVIEW_REQUIRED`, which is outside normal ranking; when applicability is confirmed, existing eligibility logic can hard-stop them.

Could the system still *fail to recognize* a real serious safety risk because extraction/applicability is incomplete? **Yes.** The remaining blockers above are why the engine should be described as **pharmaceutical-grade-oriented / hardened**, not yet fully Pharmaceutical-grade.
