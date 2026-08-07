# Gold Corpus Coverage Audit — updated through Case 021

**Audit date:** 2026-08-07  
**Scope:** Gold Case / Gold Corpus / Benchmark only. No production engine, scoring, safety, regulatory, or market logic was changed.

## Active corpus

- Active reference-grounded cases: **20**
- Abandoned case numbers: **2**
- Latest case: **021 — Serenoa repens, real same-rank systematic-review conflict**
- Engine evidence attached to Ground Truth cases: **none**
- Gold Cases remain development/unlocked unless separately promoted by the existing protocol.

## Domain coverage

| ReferenceDomain | Cases | Count |
|---|---|---:|
| INDICATION_EVIDENCE | 001, 003, 004, 005, 009, 010, 011, 012, 019, 020, 021 | 11 |
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
| Systematic reviews | COVERED | 003, 004, 005, 011, 021 |
| Meta-analysis | COVERED | 003, 011, 021 |
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
| Null human evidence standalone | GAP | Null outcomes exist inside reviews; no independent null-outcome case yet |
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

1. **Standalone null human evidence** using a permitted governing source.
2. **Source-unavailable / retrieval-failure case** with a real pre-declared critical source and frozen snapshot semantics.
3. **FDA-specific coverage** only if the protocol is deliberately expanded; do not force FDA into an incompatible source type.
4. **RCT / observational source coverage** only after a protocol-level decision permits those source types as governing references.
5. More multi-reference cases are useful only when they add a materially different conflict mechanism; quantity alone is not a target.

## Integrity rule

`gold_cases/` remains the source of truth for curated Gold Cases. `gold_corpus/` is a derived benchmark layer. The corpus manifest must be regenerated from the case registry and Gold Case builders rather than becoming an independent manually edited source of case truth.
