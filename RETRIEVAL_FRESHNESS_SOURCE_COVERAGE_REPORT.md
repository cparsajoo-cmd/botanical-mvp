# Retrieval Freshness / Source Coverage Remediation

## Finding
The remaining Hawthorn v3 mismatch was traced to retrieval coverage rather than final-decision logic. The frozen snapshot contains an older positive Cochrane review and an adverse-event review, but not later direct clinical evidence with less favorable efficacy findings.

Two generic retrieval weaknesses were confirmed:

1. Exact query wording was too restrictive. Validation indications can contain context phrases such as `adjunctive support` that are not consistently present in PubMed indexing, and species-level naming can miss literature indexed at genus level (for example, `Crataegus spp.`).
2. Every PubMed lane used `sort=relevance`, allowing older highly cited reviews to dominate while newer direct evidence could remain outside the bounded top-N set.

## Remediation
- Added `_indication_core()` to remove only generic decision-context modifiers while preserving the underlying clinical condition.
- Added genus-level query relaxation in addition to exact species matching.
- Added a polarity-neutral relaxed evidence-design query.
- Added `build_pubmed_query_plan()` with a dedicated recency lane using PubMed `sort=pub date`.
- Extended the PubMed connector so sort mode is explicit and testable.
- Kept round-robin merge and article-level deduplication, so total evidence remains bounded.
- Did not add any positive/negative/conflict search terms and did not add Hawthorn-specific logic.

## Validation
- Focused retrieval / E2E regression: 72 passed, 0 failed.
- Frozen v3 regression remains 4/5 by design because the historical Hawthorn snapshot was not rewritten after observing the mismatch.

## Interpretation
This patch improves future live evidence-set completeness. It does not retroactively alter frozen validation evidence and therefore preserves the audit trail of the original retrieval failure.
