# Evidence Transport / Botanical Identity Remediation

## Scope
Root-cause remediation only. No Gold labels changed. No holdout membership changed. No plant-specific decision rule added.

## Proven root cause
Evidence indexing used literal normalized botanical strings, while candidate identity could contain nomenclatural author citations. Thus `Ginkgo biloba` and `Ginkgo biloba L.` indexed separately even though they are the same taxon.

## Remediation
- Added `botanical_taxonomy.taxon_match_key()`.
- Resolve known taxonomic synonyms first.
- Strip nomenclatural author citations for identity matching only.
- Preserve infraspecific rank + epithet.
- Use the same taxon key for evidence_df, scientific_evidence_df, curated evidence, raw-evidence collection, and applicability collection.
- Display/provenance names are untouched.

## Regression observations on the previously exposed 15-case set
These cases are now regression fixtures, NOT unseen validation.

- Case 007 Valeriana preparation: evidence now attaches; decision moves from INSUFFICIENT EVIDENCE to GO. Remaining mismatch is Domain Routing, not transport.
- Case 008 Ginkgo preparation: evidence now attaches; decision moves from INSUFFICIENT EVIDENCE to GO. Remaining mismatch is Domain Routing.
- Case 013 Echinacea identity/quality: identity evidence transport is normalized, but identity/quality is not a first-class final-decision domain; remains INSUFFICIENT EVIDENCE.
- Case 014 Ginkgo safety interaction: EMA dabigatran evidence now reaches Safety and its evidence ID is traceable. Remaining mismatch is severity/context/final routing.
- Case 015 Hypericum preparation: evidence now attaches; decision moves from INSUFFICIENT EVIDENCE to GO. Remaining mismatch is Domain Routing.
- Case 017 Matricaria identity/quality: transport no longer depends on author-suffixed literal matching; remaining mismatch is Domain Routing.

## Tests
35 focused tests passed, including new identity-transport tests plus holdout runner, scientific-decision validation, serious-interaction gating, and evidence-field transport tests.

## Next data-supported remediation
1. Non-therapeutic Domain Routing for Preparation specification and Identity/Quality.
2. Safety-context/severity routing for cautionary interactions such as Case 014.
3. Evidence Interpretation for the already-proven Cases 003, 005, and 011.
