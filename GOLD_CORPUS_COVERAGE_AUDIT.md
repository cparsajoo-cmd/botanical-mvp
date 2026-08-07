# Gold Corpus Coverage Audit — updated through Case 023

**Audit date:** 2026-08-07  
**Scope:** Gold Case / Gold Corpus / Benchmark only. No production engine, scoring, safety, regulatory, or market logic was changed.

## Active corpus

- Active reference-grounded cases: **22**
- Abandoned case numbers: **2**
- Latest case: **023 — Momordica charantia, standalone null human evidence**
- Engine evidence attached to Ground Truth cases: **none**
- Gold Cases remain development/unlocked unless separately promoted by the existing protocol.

## Domain coverage

| ReferenceDomain | Cases | Count |
|---|---|---:|
| INDICATION_EVIDENCE | 001, 003, 004, 005, 009, 010, 011, 012, 019, 020, 021, 022, 023 | 13 |
| SAFETY | 006, 014 | 2 |
| PREPARATION_SPEC | 007, 008, 015 | 3 |
| IDENTITY_QUALITY | 013, 017 | 2 |
| REGULATORY_STATUS | 016, 018 | 2 |

## Source / evidence coverage

| Coverage target | Status | Cases / note |
|---|---|---|
| EMA/HMPC | COVERED | 001, 006, 007, 008, 009, 010, 012, 014, 015 |
| WHO | COVERED | 019 |
| ESCOP | COVERED | 020 |
| FDA-specific | GAP | Current protocol has no FDA-specific hierarchy entry; not fabricated here |
| National regulators | COVERED | 016, 018 |
| Systematic reviews | COVERED | 003, 004, 005, 011, 021, 022, 023 |
| Meta-analysis | COVERED | 003, 011, 021, 023 |
| RCT as independent governing Gold source | GAP | Current indication hierarchy does not permit RCT as governing source |
| Observational study as independent governing Gold source | GAP | No permitted governing-source path in current protocol |
| Botanical identity | COVERED | 013, 017 |
| Safety | COVERED | 006, 014 |
| Contraindications | COVERED | 006 |
| Drug interactions | COVERED | 006, 014 |
| Dose-specific evidence | COVERED | 018 |
| Preparation-specific evidence | COVERED | 007, 008, 015 |
| Regulatory restriction | COVERED | 018 |
| Regulatory prohibition | COVERED | 016 |
| Positive human evidence | COVERED | includes 009, 010, 011, 012, 019, 020 and positive side of 021 |
| Negative human evidence | COVERED | 004 and negative side of 021 |
| Null human evidence standalone | **COVERED** | **023 — endpoint-bounded null meta-analytic result, PMID 38274207** |
| Conflicting evidence | **COVERED — REAL MULTI-REFERENCE** | **021 resolves to REFERENCE_CONFLICT** |
| Missing/insufficient evidence | COVERED | 005 |
| Source unavailable | GAP | Framework supports retrieval failure, but no real curated source-unavailable holdout case |

## Case 021 — why it was added

Case 021 closes a structural scientific gap rather than adding another easy single-source case.

Two real and independently verified systematic reviews address Serenoa repens for urinary symptoms associated with benign prostatic enlargement:

1. **Wilt et al., JAMA 1998**, PMID 9820264, DOI 10.1001/jama.280.18.1604 — reported evidence suggesting improvement in urologic symptoms/flow measures.
2. **Franco et al., Cochrane 2023**, CD001423, DOI 10.1002/14651858.CD001423.pub4 — concludes Serenoa repens alone provides little to no benefit for LUTS due to benign prostatic enlargement.

Both references are represented using the already-approved `SYSTEMATIC_REVIEW` source type. Both independently pass applicability against the same broad ValidationUnit. Because they are equal in precedence rank and carry opposing assertion states, the unchanged production precedence logic returns **REFERENCE_CONFLICT**. No recency-specific rule or plant-specific exception was added.

## Remaining highest-value gaps

1. **Source-unavailable / retrieval-failure scientific case** only if a real, reproducible, pre-declared source-unavailability condition can be curated without fabrication; current engineering perturbation coverage already exists.
2. **FDA-specific governing-case coverage** only if the protocol is deliberately expanded; do not force FDA into an incompatible source type.
3. **RCT / observational governing-source coverage** only after a protocol-level decision permits those source types.
4. **External expert review, locking, and wider E2E freezing** are now higher-value than adding more scientific cases.
5. More cases are useful only when they close a materially different scientific or governance gap; quantity alone is not a target.

## Integrity rule

`gold_cases/` remains the source of truth for curated Gold Cases. `gold_corpus/` is a derived benchmark layer. The corpus manifest must be regenerated from the case registry and Gold Case builders rather than becoming an independent manually edited source of case truth.

## Case 022 addition — cross-rank precedence (2026-08-07)

Case 022 adds a real cross-rank INDICATION_EVIDENCE benchmark for *Valeriana officinalis* L. and insomnia:

- Stevinson & Ernst 2000, SYSTEMATIC_REVIEW, PMID 10767649, DOI 10.1016/S1389-9457(99)00015-5 — conclusion: evidence for valerian as a treatment for insomnia is inconclusive.
- EMA/HMPC/150848/2015, EMA_HMPC — recognizes Valeriana officinalis L., radix for relief of sleep disorders.

Both references are independently applicable to the benchmark's narrow insomnia overlap. Under the existing source hierarchy, SYSTEMATIC_REVIEW outranks EMA_HMPC, so the systematic-review `INSUFFICIENT` verdict is selected. This is not a same-rank conflict and no production precedence rule was changed.

Both references are marked CRITICAL for End-to-End retrieval because the benchmark cannot test cross-rank precedence if only the winning source is retrieved.


## Frozen-snapshot End-to-End pilot — Cases 006, 016, 018, 019, 020, 021, 022

Seven representative active cases now have frozen baseline retrieval snapshots built from verified public/official source records. The pilot reuses `end_to_end_validation.py`; no second validation engine was created. Candidate-discovery outputs are frozen in the snapshot solely to make the benchmark deterministic.

### Scenario coverage

- Baseline critical-source retrieval: **9/9 critical references retrieved**.
- Missing-critical-source perturbation: fail-closed `CRITICAL_SOURCE_MISSED` confirmed for all seven pilot cases.
- Source-unavailable perturbation: `SOURCE_UNAVAILABLE` plus critical-source miss confirmed for all seven pilot cases.
- Duplicate capture: article-identity deduplication confirmed using a duplicated real Serenoa review record.
- Known irrelevant source: the real ESCOP *Echinacea purpurea* root monograph is retrieved and counted as irrelevant for the Case 020 flowering-aerial-parts benchmark.

### Actual production-engine pilot findings

The frozen baseline was executed through the unmodified production engine. Findings are benchmark observations, not tuning targets:

- Critical-source recall: **1.00 (9/9)**.
- Evidence-retrieval recall: **1.00 (9/9)**.
- Evidence-direction accuracy against the current GoldSource expectation vocabulary: **0.111 (1/9)**. Most source-derived monograph/regulatory/review summaries were classified as `unclear`.
- Serious-safety false-negative rate in the pilot: **1.00 (1/1)**. Case 006 retrieved the EMA serious contraindication source, but the safety gate did not fail. This reproduces the previously documented Hypericum safety-gate miss.
- Regulatory prohibition/restriction detection in the pilot: both Case 016 and Case 018 triggered the regulatory gate as expected.
- No production logic, scoring, safety rule, regulatory rule, or market logic was changed in response to these findings.

### Interpretation caution

The evidence-direction metric currently compares a generic efficacy-direction classifier (`positive/negative/null/mixed/unclear`) with GoldSource expectations that also encode presence of regulatory/safety assertions as `positive`. Therefore some direction mismatches are a **validation-vocabulary mismatch**, not necessarily a scientific error in the source or Gold Case. This should be addressed at benchmark interpretation/protocol level before using that metric as a headline engine-accuracy claim; the engine was not modified in this phase.

## Case 023 addition — standalone null human evidence (2026-08-07)

Case 023 closes the last high-value standalone direction gap using a real systematic review/meta-analysis: *Momordica charantia* and fasting blood glucose, PMID 38274207, DOI 10.3389/fnut.2023.1200801. The case is restricted to the fasting-blood-glucose endpoint, for which the source reports no statistically significant effect versus placebo (MD -0.03; 95% CI -0.38 to 0.31).

The repository has no dedicated `NULL` assertion state. The unchanged Ground Truth vocabulary therefore represents the bounded efficacy claim as `SUPPORTS_INDICATION + ABSENT`, while the Gold Corpus manifest records `scientific_result_kind = NULL_STATISTICAL_RESULT`. This is benchmark metadata only and does not change production interpretation logic.

PMID 38274207 and its DOI were absent from the uploaded repository before inclusion. The source was not duplicated into a second corpus-extension record, so the independent corpus-record count remains **181**. Active reference-grounded Gold Cases increase from **21 to 22**.

## Freeze status after Case 023

Scientific direction coverage is now substantially saturated, including positive, negative, conflicting, insufficient, and standalone null human evidence. The corpus is still **not globally freeze-ready** because external expert review, formal locking, and broader frozen E2E baseline coverage remain incomplete. The next phase should prioritize governance completion rather than count growth.

