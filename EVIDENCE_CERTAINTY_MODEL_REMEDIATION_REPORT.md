# Evidence Certainty Model Remediation

## Root cause
The v5 blind run exposed three general defects rather than plant-specific errors:

1. Positive governing evidence could carry an explicit caution limitation, but the resolver discarded that limitation once the direction was positive.
2. Common null language such as `little to no difference` was not reliably converted to a null efficacy direction.
3. `UNRESOLVED` scientific evidence could fall through to the default `GO` path.

A fourth separation issue was clarified: Safety eligibility and final scientific rankability are distinct. A mild interaction can remain safety-eligible while a candidate with no therapeutic efficacy evidence remains scientifically insufficient for normal ranking.

## Remediation
- Positive top-tier evidence with material limitations -> `GO WITH CAUTION`.
- Firm uncertainty accompanying positive top-tier evidence -> expert review rather than unconditional GO.
- Common null/no-difference language -> insufficient evidence.
- Unresolved therapeutic evidence -> insufficient evidence, not default GO.
- Regulatory restrictions retain `GO WITH CAUTION` precedence over an unresolved efficacy signal.
- WHO/ESCOP-style explicit therapeutic-indication language remains usable supportive evidence.
- Equal-tier positive + unresolved evidence is treated cautiously rather than as full support.

No plant name, PMID, case id, or benchmark label is used by the production policy.

## Regression result on the now-exposed v5 set
The historical blind result remains 3/10 (30%) and must never be rewritten as unseen performance.

After remediation, v5 regression is 8/10:
- all 5 `GO WITH CAUTION` cases -> correct
- Serenoa null-efficacy -> correct `INSUFFICIENT EVIDENCE`
- Aristolochia and Comfrey -> correct `NO GO SAFETY`
- remaining mismatches:
  - Psyllium: reference says `GO`, engine abstains because snapshot contains only an old direct trial and no governing synthesis; reference is likely too strong.
  - Kava: reference says `EXPERT REVIEW REQUIRED`, engine gives `NO GO SAFETY` because serious hepatotoxicity evidence triggers the hard safety policy; this is conservative and requires reference adjudication, not a weaker safety rule.

## Tests
Focused decision/safety/holdout regression: 37 passed, 0 failed.
Full local suite cannot collect 14 files because this environment lacks `supabase` and `streamlit`; this is an environment dependency limitation, not a failure produced by this patch.
