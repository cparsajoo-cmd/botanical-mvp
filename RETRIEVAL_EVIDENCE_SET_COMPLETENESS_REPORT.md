# Retrieval Evidence-Set Completeness Remediation

## Scope
This phase addresses the proven retrieval-completeness failure exposed by the fresh unseen holdout. It does not change final-decision rules, safety rules, regulatory rules, evidence-direction semantics, or benchmark labels.

## Root cause
The production PubMed collector used one relevance-ranked query and accepted only the first `max_results` hits. A single study family or evidence type could therefore occupy the full retrieval budget. This is especially risky when a highly ranked positive meta-analysis coexists with a separate systematic review reporting uncertainty or conflicting results.

A second query-construction defect existed when `dosage_form` was empty: the generated Boolean group could start with `OR`.

## Remediation
`evidence_collector.py` now builds a bounded, polarity-neutral three-query portfolio:

1. Broad clinical/review query.
2. Systematic-review/meta-analysis query.
3. Randomized/clinical-study query.

Results are merged round-robin so the first query cannot monopolize all slots, then deduplicated at publication level using PMID, falling back to URL/title. The final returned set remains bounded by the caller's existing `max_results` value.

No positive/negative/beneficial/uncertain result terms are used in the search strategy, so retrieval is not instructed to find the benchmark answer.

## Tests
- Direct retrieval-completeness + existing PubMed/multi-source tests: 15 passed.
- Broader retrieval/E2E/evidence-direction regression selection: 62 passed.
- Python compilation: passed.

## Interpretation
This patch improves the probability that independent high-level evidence designs coexist in the evidence set. It does not guarantee that every conflicting publication exists in PubMed, is indexed under the same terminology, or will be returned within a bounded result budget. A future live retrieval validation should measure evidence-set recall on a new frozen corpus rather than assuming completeness from query diversity alone.
