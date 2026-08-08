# Evidence Certainty / Limitation Semantics Hardening

## Scope
Validation-driven remediation only. No plant-specific rules, no UI changes, no ranking-weight changes.

## Root cause
The structured final decision layer correctly recognized positive efficacy direction, but often treated publication-level limitations as irrelevant to decision certainty. As a result, positive evidence with explicit heterogeneity, methodological weaknesses, limited durability evidence, adjunctive framing, or need for stronger confirmation could be flattened to GO.

## General remediation
`final_decision_policy.py` now distinguishes evidence direction from limitation semantics at the decision layer.

Recognized limitation classes include:
- caution-level: heterogeneity, risk of bias, methodological weaknesses/limitations, explicit need for stronger/more evidence, long-term uncertainty, variability, limited study base, adjunctive framing;
- firm uncertainty: insufficient to establish clinical benefit, not adequately corroborated, inability to draw firm conclusions.

Additional general safeguards:
- endpoint-split results are represented as mixed rather than hard null;
- active-comparator wording such as "both interventions were effective" is not erased by a non-significant between-group difference;
- a supportive direct RCT without a governing synthesis produces GO WITH CAUTION rather than a full-certainty GO;
- a limitation-qualified synthesis plus supportive direct clinical evidence produces GO WITH CAUTION;
- an equal-rank supportive review and a firm-insufficiency review produce EXPERT REVIEW REQUIRED.

## Regression on former unseen Holdout v4
This set is now a development/regression set and is NOT an independent validation set.

Before this remediation: 2/10 matched the frozen v4 reference labels.
After this remediation: 9/10 matched.

The remaining mismatch is v4_003 (Foeniculum vulgare / dysmenorrhea): the frozen reference label is GO, while the engine now returns GO WITH CAUTION because the later evidence snapshot itself says "potentially effective" and calls for further high-quality trials. This case should be reference-adjudicated rather than forcing the engine back to GO.

## Tests
- focused certainty/decision/validation suite: 33 passed, 0 failed;
- production app import integrity test: passed when run independently;
- broad suite excluding unavailable Supabase/Streamlit-dependent collection files progressed through 81% with no new failure before the execution environment timeout.

## Interpretation
This patch closes the over-optimistic GO failure mode when limitations are actually present in the evidence supplied to the engine. It does not invent limitations that retrieval failed to collect.
