Final CI hotfix v10
Root cause: v9 correctly computed outcome_context_unverified_but_supported, but a later unconditional human/outcome guard ignored that exception and returned EXPERT REVIEW REQUIRED anyway. The later guard now respects the same conservative exception. No scoring, evidence lineage, safety, ranking, or AI logic changed.
Overwrite only step_rd_candidates.py.
