# Structured Body-of-Evidence Decision Architecture

## Why this redesign
Repeated fresh holdouts showed that patching isolated wording patterns was not a scalable scientific decision strategy. The core problem was architectural: evidence direction, certainty, legacy score classes, and validation adapters could disagree or operate independently.

## New authoritative decision architecture
Question/Retrieval -> Evidence Records -> Body-of-Evidence Assessment -> Safety/Regulatory Eligibility -> Final_Decision_Status

The new Body-of-Evidence Assessment separates:
- governing evidence tier
- effect direction
- number of independent governing sources
- material certainty limitations
- explicit internal conflict
- freshness / newer contradiction
- body-level certainty

No plant name, PMID, benchmark case ID, or indication-specific rule appears in the body model.

## Conservative decision invariants
- GO is no longer a default/fall-through state.
- One clean systematic review is supportive but normally Moderate body certainty -> GO WITH CAUTION.
- Multiple clean independent top-tier syntheses can reach High certainty -> GO.
- One positive direct RCT without a governing synthesis -> cautious support, not High certainty.
- Null/negative governing synthesis -> INSUFFICIENT EVIDENCE.
- Explicit conflict/debate or meaningful opposing top-tier evidence -> EXPERT REVIEW REQUIRED.
- Newer direct contradiction can challenge an older supportive synthesis.
- Serious Safety / Regulatory hard stops remain authoritative and override efficacy.
- Regulatory restrictions retain GO WITH CAUTION precedence.
- Unresolved therapeutic evidence abstains; it never silently becomes GO.

## Single source of truth
Validation adapters now read `Final_Decision_Status` first. Legacy `Decision_Class` remains backward-compatible presentation/scoring metadata, but it is no longer the scientific source of truth.

## Version
Decision engine logic version bumped from 1.2.0 to 1.3.0.

## Regression
Focused architecture/decision/safety tests: 159 passed.
Chunked broad local regression: 2364 passed, 3 xfailed.
Additional local tests requiring full Supabase/Streamlit runtime or long-running holdout infrastructure were not counted as passed in this environment.

Historical holdout outputs were not rewritten as unseen performance. The next valid accuracy estimate must come from a new frozen holdout after this architecture is merged.
