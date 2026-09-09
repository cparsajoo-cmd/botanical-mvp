ROOT CAUSE
----------
The implementation-fingerprint stale-result guard was placed inside
_recommendation_block(), which is a presentation function also called directly by
UI unit tests with synthetic report_ready_df fixtures that intentionally do not
contain Pipeline_Implementation_Fingerprint. The guard therefore returned before
any dataframe was rendered, causing the 14 CI failures (all observed as 0 rendered
frames / empty shown-plant sets).

FIX
---
Keep production stale-result protection, but move enforcement to the real Stage-6
session-state call site (the Generate Final Recommendation path). The renderer
remains reusable/pure for tests and legacy/internal callers.

HOW TO APPLY
------------
From the repository root:

    python apply_stage6_ci_fingerprint_guard_fix.py

Then run:

    pytest test_recommendation_block_phase3.py test_stage6_expert_review_bucket_v6.py -q
    pytest -q

The script creates step_rd_candidates.py.before_stage6_ci_fix as a backup.

IMPORTANT
---------
Do NOT replace step_rd_candidates.py with an older copy. This patcher edits the
CURRENT repository file in-place, preserving the later v10/v11 scientific
hotfixes already present on main.
