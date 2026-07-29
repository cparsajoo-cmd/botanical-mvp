# Validation Case Template — Reference-Grounded Validation Program

Status: **DRAFT — pending Hamid's final confirmation of this revision**
Version: v0.2 (companion to `VALIDATION_PROTOCOL.md` v0.2)

Every future case (case 1 through case N) is filled in from exactly this template. The rules behind each section live in `VALIDATION_PROTOCOL.md`; this document is only the fill-in structure.

Each row is mapped to the real field in the codebase, so this template is not decorative prose — it maps directly onto `GoldCase`. Where no real field exists yet, that is stated explicitly.

---

| # | Field | Maps to | Notes |
|---|---|---|---|
| 1 | **Case ID** | `GoldCase.case_id` | Stable, unique identifier |
| 2 | **Protocol Version** | ⚠️ **No native field** | Record which version of `VALIDATION_PROTOCOL.md` (e.g. "v0.2") this case was built under — until formalized in code, document alongside Case ID. Necessary so that if the protocol changes later, every existing case's governing version stays traceable. |
| 3 | **Scientific Question** | ⚠️ **No native field** | Written per the Section 4 template of the Protocol; kept in case-level documentation (alongside the code, not inside the dataclass) |
| 4 | **Target Population** | `ValidationUnit.population` | |
| 5 | **Preparation** | `ValidationUnit.preparation` (`PreparationSpec`: dosage_form, solvent, der_min, der_max, source_status) | |
| 6 | **Route** | `ValidationUnit.route_of_administration` | |
| 7 | **Jurisdiction** | `ValidationUnit.jurisdiction` | |
| 8 | **Reference Source** | `GoldCaseReference.reference` (`ReferenceDescriptor`: reference_id, source_type, version, ...) | `source_type` must come from the Protocol's Section 6 table |
| 9 | **Reference Claims** | `GoldCaseReference.claims` (`list[ReferenceClaim]`) | `evidence_text.transformation_type` restricted to VERBATIM / NORMALIZED_TERMINOLOGY / TRANSLATED |
| 10 | **Ground Truth** | `GoldCase.resolved_outcomes` (`list[ResolvedExpectedOutcome]`) | Always computed via `resolve_expected_outcomes()` — never hand-typed |
| 11 | **Engine Evidence** | `GoldCase.engine_evidence` (`list[EngineEvidenceInput]`) + `GoldCase.engine_evidence_origin` | Per the Protocol's Leakage Rules, decided **after** row 9; `engine_evidence_origin` should be `CURATOR_SUPPLIED` or `INDEPENDENT_PRODUCTION_SOURCE` — never `MANUAL_TEST_FIXTURE` (that value is for synthetic fixtures only) |
| 12 | **Expected Outcome** | `GoldCase.expected_output` (`ExpectedOutput`) | A simplified display summary — distinct from the real Ground Truth in row 10, per `gold_case.py`'s own explicit separation |
| 13 | **Locking Status** | `GoldCase.locked`, `GoldCase.dataset_snapshot_hash`, `GoldCase.dataset_split` (`DatasetSplit`) | |
| 14 | **Reviewer** | ⚠️ **No native field** | Suggest recording via `FieldProvenance.curator` (`ReviewerRole`) inside `case_provenance`, or a new field in a later phase (a code change — out of scope now) |
| 15 | **Second Reviewer** | ⚠️ **No native field** | Only implied indirectly by `curation_status == INTERNALLY_REVIEWED`; the second reviewer's identity is not recorded anywhere — same gap as row 14 |
| 16 | **Notes** | `ValidationUnit.notes` or free-form case-level notes | |
| 17 | **Leakage Assessment** | Output of `dataset_split.assess_leakage()` (`LeakageAssessment`) + `GoldCase.leakage_control` (`LeakageControl`) | Must be `VALID_FOR_HOLDOUT` before use in an `EvaluationRun` |
| 18 | **Execution Date** | `EvaluationRun.execution_timestamp` (only exists after running) | |
| 19 | **Evaluation Result** | `EvaluationRun.results` (`list[MetricReport]`) | Only two metrics implemented: `decision_direction_agreement`, `safety_serious_false_negative_rate` |
| 20 | **Lessons Learned** | ⚠️ **No native field** | Suggest an accumulating log outside the dataclasses (e.g. `VALIDATION_CASE_LOG.md`), not part of `GoldCase` itself |

---

## Known Gaps (for a future decision, not this phase)

Four rows above (Protocol Version, Reviewer, Second Reviewer, Lessons Learned) have no home in the current `GoldCase` data model. For Phase 3B's first case, these can stay outside the dataclasses, in documentation alongside the case — no code change required. If the program grows to dozens or hundreds of cases, formalizing these (either as new `GoldCase` fields or a companion dataclass such as `CaseReviewRecord`) is a separate architecture decision for a later phase, not part of Phase 3A/3B.

---

**Status of this document:** draft, pending Hamid's confirmation of this specific revision. Once both documents (`VALIDATION_PROTOCOL.md` and this file) are confirmed, Phase 3B — building the first real case exactly against this template — begins.
