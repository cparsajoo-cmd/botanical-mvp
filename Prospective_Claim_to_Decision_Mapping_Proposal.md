# Prospective Claim-to-Decision Mapping Proposal

**Status:** Design document for review. Analysis only — no production code, no protocol document, and no Gold Case has been modified as part of producing this document.

**Origin:** Case 003 (Matricaria chamomilla, Kazemi et al. 2024 governing systematic review) reached a technically valid, fully-executed end-to-end pipeline run — Ground Truth resolved, Evidence transported correctly, all four engine gates PASSED, a real candidate-level decision produced — and then had no principled way to say whether that output *agreed* with Ground Truth. Not because the engine failed, and not because the Evidence was inadequate, but because the protocol never defined, in advance, what "agreement" would even mean for a `CONDITIONAL` claim compared against a `Decision_Class` string. That gap is the subject of this document.

---

## 1. Objectives and motivation

**Objective:** define, once, prospectively, and before any case's Engine Evidence is collected, exactly how a Ground-Truth claim's resolved state maps (or explicitly does not map) onto the engine's candidate-level decision output — so that `decision_direction_agreement` can be computed honestly, and so that a case which *cannot* be honestly mapped is labeled `NOT_ELIGIBLE` rather than silently skipped or retrofitted after the fact.

**Motivation, concretely:**
- Case 003 demonstrated that the pipeline can execute correctly and still produce an output that cannot be scored — this is a real, recurring category of outcome, not a one-off.
- The temptation this proposal exists to close off: defining `ExpectedOutput`/`DecisionDirection` *after* seeing "Strong R&D candidate" is post-outcome specification. It would make every future agreement metric suspect, because no one downstream could tell which cases had a real prospective prediction and which had a retrofitted one.
- Without a documented mapping, every future case reaching real execution recreates Case 003's exact problem, one at a time, ad hoc.
- The five Ground Truth domains, the five `AssertionState` values, and the engine's four gates already exist and are stable (frozen, in the case of the domains and states). What's missing is the *bridge* between them — not new vocabulary, a new mapping.

---

## 2. Separation of claim-level vs. candidate-level taxonomies

These are genuinely different objects, and the proposal treats them as such rather than trying to collapse one into the other:

| | Claim-level (Ground Truth) | Candidate-level (Engine output) |
|---|---|---|
| Owned by | `ResolvedExpectedOutcome` | `Decision_Class` / `Decision_Class_AH` / `Gate_Results` |
| Granularity | One `(domain, assertion_type, subject)` identity | One taxon vs. one anchor, aggregated across all matched compounds |
| Vocabulary | `AssertionState` (PRESENT / ABSENT / NOT_STATED / CONDITIONAL / INSUFFICIENT) | A small set of engine-defined decision-class strings, derived from four gate outcomes plus a numeric score |
| What it answers | "What does the authoritative literature say about *this one, narrow claim*?" | "Given everything the engine could evaluate, how strong an R&D candidate is *this whole taxon*?" |
| Stability | Frozen once `resolve_expected_outcomes()` runs | Can vary run to run with different Evidence, even for the same claim |

Case 003's finding, restated in this vocabulary: a `CONDITIONAL` claim-level state is a statement about the *shape* of one piece of evidence (partially positive, partially negative, on one narrow question). "Strong R&D candidate" is a statement about the *aggregate* of four independent gates plus a score. Neither is reducible to the other without an explicit, declared rule — which is exactly what this proposal supplies.

---

## 3. Which Ground Truth domains are eligible for candidate-level mapping

Not symmetric across the five domains — each has a different natural home:

- **`INDICATION_EVIDENCE`** — maps most directly to candidate-level `DecisionDirection`, since it's the domain the `minimum_evidence` gate and the overall opportunity score are most obviously "about." Primary candidate for full `decision_direction_agreement` eligibility.
- **`SAFETY`** — maps to the `safety` gate specifically, not necessarily to overall `Decision_Class`. A case could have a clean safety Ground Truth and still land as "Early-stage candidate" for unrelated evidence-volume reasons — collapsing these into one metric would blur two different questions. Proposed: gate-level agreement, not candidate-level, is the default for SAFETY.
- **`IDENTITY_QUALITY`** — maps to the `identity` gate only. Not a candidate-level decision question at all.
- **`REGULATORY_STATUS`** — maps to the `regulatory` gate only.
- **`PREPARATION_SPEC`** — does not map to any current gate or decision field. The engine's decision layer doesn't reason about preparation adequacy directly (it only consumes preparation to build the DataFrame keys — see `gold_case_execution.py`). Proposed: `NOT_ELIGIBLE` for either gate-level or candidate-level agreement until/unless a preparation-specific gate exists.

**Consequence:** `decision_direction_agreement` (the candidate-level, whole-case metric) should realistically only ever be computed for cases whose *primary* domain is `INDICATION_EVIDENCE` — the other four domains are better served by a proposed, separate `gate_level_agreement` metric (see §6), which already has a natural home in `evaluation_run.py`'s existing two-metric structure without inventing a third metric type.

---

## 4. Proposed mapping options per `AssertionState`, with explicit `CONDITIONAL` discussion

| `AssertionState` | Proposed mapping | Confidence |
|---|---|---|
| `PRESENT` | → `DecisionDirection.POSITIVE` | High — unambiguous, matches the plain-language meaning of both sides. |
| `ABSENT` | → `DecisionDirection.NEGATIVE` | High — same reasoning. |
| `NOT_STATED` | → **no mapping; case NOT_ELIGIBLE** | High — the source never addressed the question; there is nothing to agree or disagree *about*. Forcing a direction here would manufacture an expectation the Ground Truth never actually contains. |
| `INSUFFICIENT` | → **no mapping; case NOT_ELIGIBLE** | High — same reasoning as NOT_STATED; distinct failure mode, same eligibility consequence. |
| `CONDITIONAL` | **Three real options — no single obvious answer:** | Open question, see below |

**`CONDITIONAL` — the actual design fork:**

- **Option A — No mapping; case NOT_ELIGIBLE (the conservative default).** Treats a mixed/qualified finding the same as NOT_STATED/INSUFFICIENT for agreement purposes: there is a real answer, but it isn't a *direction*, so scoring it as one would misrepresent what the source actually says. This is what effectively happened to Case 003 by omission, and is the safest starting default if no decision is made before this document is acted on.
- **Option B — Maps to `DecisionDirection.HOLD`.** There's a real conceptual argument for this: `HOLD` already exists in the vocabulary specifically to represent "not a clean yes, not a clean no" — a `CONDITIONAL` claim (some measures improve, some don't, per Case 003's own governing review) is arguably exactly what `HOLD` was designed to capture. Risk: `HOLD` may already carry other meanings in existing case design (e.g., "insufficient engine evidence to decide" rather than "the reference itself is mixed") — conflating "the literature is mixed" with "the engine couldn't decide" would blur two different sources of uncertainty into one label.
- **Option C — Case-specific, curator-declared sub-mapping, decided before evidence collection.** Rather than one global rule for all CONDITIONAL claims, the curator declares, at Ground-Truth-curation time (before Engine Evidence exists), whether *this specific* mixed finding leans operationally positive, operationally negative, or is genuinely undecidable — with a written rationale, the same discipline already established for `EquivalenceJustification`. More expressive, but a heavier process requirement, and introduces a new curator judgment surface that itself needs review rules.

**No recommendation is made here between A/B/C — this is the primary open architectural decision this document exists to surface**, not to resolve. See §9.

---

## 5. Gate-level expected outputs vs. overall decision-direction expectations

Proposal: extend `ExpectedOutput` (currently a single, whole-case summary struct) to carry **two independent kinds of expectation**, not one:

```
ExpectedOutput
    expected_decision_direction: Optional[DecisionDirection]   # already exists — whole-case
    expected_gate_results: dict                                 # already exists — currently unused by any case built so far
```

`expected_gate_results` already exists on `ExpectedOutput` (per `gold_case.py`'s current definition: `gate_name -> "PASSED"|"FAILED"|"NOT_EVALUABLE"`) but no case built in this program has populated it. This proposal doesn't need a new field — it needs a **documented convention** for using the field that already exists:

- A case whose primary domain is `SAFETY`, `IDENTITY_QUALITY`, or `REGULATORY_STATUS` should populate `expected_gate_results[<matching gate>]` and leave `expected_decision_direction` unset (or explicitly `NOT_ELIGIBLE`) unless the case *also* has independent grounds for a whole-case direction claim.
- A case whose primary domain is `INDICATION_EVIDENCE` should populate `expected_decision_direction`.
- Nothing prevents a case from populating both, if it genuinely has grounds for each — but neither should be inferred from the other.

This directly resolves the domain-eligibility split from §3 without inventing new dataclass fields, only a documented usage convention for a field that's already there but unused.

---

## 6. Eligibility rules for `decision_direction_agreement`

A case is eligible for `decision_direction_agreement` if and only if **all** of the following hold:

1. Its primary Ground Truth domain is `INDICATION_EVIDENCE` (per §3).
2. Its resolved outcome's `assertion_state` has a defined mapping under the *adopted* option from §4 (i.e., not `NOT_STATED`/`INSUFFICIENT`, and — pending the CONDITIONAL decision — not `CONDITIONAL` either, if Option A is adopted).
3. `ExpectedOutput.expected_decision_direction` was set and frozen **before** any `EngineEvidenceInput` existed for the case (see §7).
4. The case has actually reached `READY` and produced a real candidate-level output (a case stuck at `DEFER`/`BLOCK` has no output to compare against anything).

A case failing any of these conditions is recorded with an explicit `AgreementEligibility.NOT_ELIGIBLE` status (a new, small enum — not implemented here) and a named reason, mirroring `ExecutionReadiness`'s own READY/DEFER/BLOCK pattern rather than a silent skip. **Case 003, under this proposal, is `NOT_ELIGIBLE` for reason "CONDITIONAL has no adopted mapping"** — consistent with its already-frozen status.

---

## 7. Execution-order requirements

Proposed new Execution Precondition, extending the set already established in Phase 3C:

> A Reference-Grounded Gold Case intending to support `decision_direction_agreement` SHALL have `ExpectedOutput.expected_decision_direction` (and/or `expected_gate_results`, per §5) set and frozen in the case's own file **before** any `EngineEvidenceInput` is drafted for that case. If Engine Evidence already exists (or the engine has already been run) when this expectation is first set, the case SHALL be marked `NOT_ELIGIBLE` for `decision_direction_agreement` regardless of whether the retrofitted expectation happens to match the observed output.

This is the direct generalization of the discipline the last several turns already enforced on Case 003 by hand — this proposal's contribution is making it a named, checkable rule rather than something that has to be caught by careful manual review each time.

**Mechanical note (not an implementation instruction, just where this would eventually live):** this could plausibly be enforced the same way `execution_readiness.py` enforces its own preconditions — a similarly-shaped guard, checked before `decision_direction_agreement` is computed, not before general engine execution (a case can execute and be scientifically interesting without ever being eligible for this specific metric).

---

## 8. Backward compatibility with all completed phases

- **Case 001 (Melissa, Deferred):** unaffected. Never reached execution; this proposal only governs cases that reach a real candidate-level output.
- **Case 002 (Passiflora, Access-Blocked):** unaffected, same reason.
- **Case 003 (Chamomile, execution-complete/agreement-ineligible):** correctly reclassified under this proposal as `NOT_ELIGIBLE` — not retroactively scored, not reopened, its frozen status is exactly what §6's eligibility rule 2 would produce for a `CONDITIONAL` claim under Option A. No change needed to Case 003 itself.
- **`execution_readiness.py` / `ExecutionReadiness` (READY/DEFER/BLOCK):** entirely orthogonal to this proposal — readiness governs *whether the engine may run at all*; this proposal governs *whether a completed run's output may be scored for agreement*. No overlap, no conflict, no need to touch the frozen readiness module.
- **`gold_case_execution.py`'s evidence-channel invariant:** unaffected — this proposal operates entirely downstream of evidence transport and engine execution.
- **`VALIDATION_PROTOCOL.md` v0.2 / `VALIDATION_CASE_TEMPLATE.md`:** both remain frozen. This proposal is scoped as a future §Execution Preconditions *addition*, not a revision of anything currently in either document. No existing section would need to change — only a new section added, if and when this is accepted.

---

## 9. Migration strategy for future Gold Cases

1. **Immediate (no code change):** any new case whose curator intends it to support `decision_direction_agreement` should, as a documentation practice, state its intended `expected_decision_direction` in the case file's module docstring at Ground-Truth-freeze time — even before `ExpectedOutput` population is formalized in code — so the ordering discipline (§7) is followed in spirit immediately, not blocked on implementation.
2. **Once the CONDITIONAL decision (§4) is made:** implement the mapping table as a small, pure function (e.g., `assertion_state_to_decision_direction()`), analogous in size and style to `execution_readiness.py`'s own `_decide()` — a single, explicit, testable function, not scattered conditionals.
3. **Retrofit existing frozen cases:** Case 003 gets an explicit `AgreementEligibility.NOT_ELIGIBLE` annotation added to its own execution file (not its frozen Ground Truth file) once the enum exists — documentation, not a re-execution.
4. **New cases going forward (Case 004+):** the case-selection pre-screen already adopted for Case 003 (governing-source accessibility check before proposing a candidate) gets one more item: "if this case is intended to support agreement scoring, is its primary domain `INDICATION_EVIDENCE` and does its likely `AssertionState` have an adopted mapping?" — checked at candidate-selection time, before any curation work begins, the same "fail fast, before hours are spent" principle already adopted from the Passiflora experience.

---

## 10. Open design questions requiring architectural decisions (yours, not mine to default)

1. **Which CONDITIONAL option (A/B/C, §4)?** The single largest open question this document raises. Recommend deciding this before implementing anything else in this proposal, since it determines whether Option-C-style per-case rationale infrastructure is needed at all.
2. **Does `HOLD` need to be split into two distinct meanings** ("reference evidence is genuinely mixed" vs. "engine lacks enough evidence to decide") if Option B is chosen? If so, that's a change to the existing `DecisionDirection` enum, not just a new mapping function — a larger change than this proposal currently scopes.
3. **Should gate-level agreement (§3/§5) be a formally named third metric** in `evaluation_run.py`, alongside the existing `decision_direction_agreement` and `safety_serious_false_negative_rate`? Or treated as an informal secondary check? This affects whether `MetricReport` needs a new variant.
4. **Who owns the eligibility check (§6/§7)** — a new function, or an extension of `execution_readiness.py`'s existing `assess_execution_readiness()`? Keeping them separate (recommended above) preserves the "readiness is about permission to execute, agreement-eligibility is about permission to score" boundary, but a combined checker would mean one fewer function to keep in sync — a real minimality-vs-separation-of-concerns tradeoff, not a settled call.
5. **Does `INCOMPLETE_DATA`/other `RiskStratum` values interact with agreement eligibility?** E.g., should a case already flagged with a `RiskStratum` indicating known scientific ambiguity be automatically `NOT_ELIGIBLE`, independent of its `AssertionState`? Not addressed above; worth a decision before this is finalized.

---

*End of design document. No code, protocol document, or Gold Case was modified in producing this analysis.*
