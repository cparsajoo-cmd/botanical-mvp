V9 final execution-order fix.
Production file changed: step_rd_candidates.py only.
Root cause: AI insight fields were attached after final decision reconciliation, so rules depending on AI_Evidence_Consistency could never execute. Also outcome-context-unverified direct evidence was capped before the supported uncertainty exception could be applied.
