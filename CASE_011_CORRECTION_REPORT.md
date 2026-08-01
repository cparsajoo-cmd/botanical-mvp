# Case 011 Correction Report

## Decision
The former SAFETY case was removed from the active benchmark because it used `SUPPORTS_INDICATION` inside `ReferenceDomain.SAFETY` and had no safety severity required by the frozen precedence logic.

## Corrected scope
- Taxon: *Matricaria chamomilla* L.
- Domain: `INDICATION_EVIDENCE`
- Subject: generalized anxiety disorder
- Governing source: Hieu et al. 2019 systematic review and meta-analysis
- DOI: 10.1002/ptr.6349
- PMID: 31006899
- Assertion: `SUPPORTS_INDICATION / PRESENT`

## Result
- Old invalid Case 011 file and test removed.
- Corrected Case 011 file and focused test added.
- 5/5 focused tests passed.
