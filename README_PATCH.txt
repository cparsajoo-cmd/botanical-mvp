Stage 5/6 general scientific fix v6 (cumulative over v5)

Production files to overwrite:
- candidate_shortlisting.py
- evidence_adjudication_engine.py
- step_rd_candidates.py

Scientific/presentation changes:
- carries v5 canonical human/outcome context alignment
- separates EXPERT REVIEW REQUIRED from Weak / not recommended
- unresolved candidates render in an amber Requires expert review / unresolved section
- insufficient evidence / Hold / hard No-Go / excluded remain in red Weak / not recommended
- prevents unresolved exploratory candidates from being duplicated across sections
- no scoring/ranking/gate values are changed by this presentation separation
- general: no sleep-, infusion-, or plant-specific rules

Validation in local dependency-stubbed environment:
- targeted regression bundle: 22 passed
- full suite progressed through 44% with no failures before sandbox timeout
