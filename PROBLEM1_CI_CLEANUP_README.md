# Problem 1 CI cleanup

GitHub CI was failing because the obsolete file `test_pubmed_local_intervention_relation_v1.py` remained in the repository after the legacy PubMed token-relation heuristic had been intentionally removed.

Replace the repository-root copy of `test_pubmed_local_intervention_relation_v1.py` with the file in this package. Do **not** restore `verify_pubmed_intervention_attribution`; the canonical `Candidate_Intervention_Assertion` architecture supersedes it.

Local validation of the replacement file: `3 passed`.

The `PytestUnknownMarkWarning` messages for `phase4_legacy_behavior` are warnings only and are unrelated to this CI failure.
