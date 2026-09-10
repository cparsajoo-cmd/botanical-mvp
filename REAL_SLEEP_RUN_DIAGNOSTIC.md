# REAL_SLEEP_RUN_DIAGNOSTIC.md

## Honest scope

This sandbox still has no live Supabase connection and no OpenAI API key
(same constraint as the prior pass), so the actual production
Sleep/Relaxation run cannot be reproduced here. This is a three-candidate
comparison — Valeriana officinalis, Matricaria chamomilla, Punica granatum,
exactly the three you asked about — built directly from the cahier's own
described evidence patterns for each plant, run through the real,
unmodified `build_plant_candidate_shortlist()`. Every number below is an
actual function output, not estimated.

**Recommendation unchanged from last pass:** re-run the real Sleep query
against live Supabase data with these fixes applied for the authoritative
full table.

## Fixture construction (what each candidate represents)

- **Valeriana officinalis**: 1 record with a genuinely resolved positive
  human-RCT direction naming the indication in its own rationale text
  ("human clinical trial reported significant improvement in sleep quality
  for Sleep & Relaxation support"), safety reassuring, regulatory monograph
  present, plus 4 lower-tier observational records with unresolved
  direction.
- **Matricaria chamomilla**: 3 human RCT records that explicitly report
  **no significant difference from placebo** for the indication (a genuine
  null result, not silence).
- **Punica granatum**: mirrors the cahier's exact real-production pattern —
  1 record tagged "human clinical trial" / "clinical evidence" but with
  `Result_Direction = "unknown"` and no indication mention in its own
  outcome text (only matched via the upstream `Indication_Match_Type`
  field), plus 7 in-vitro/mechanistic antioxidant-assay records with no
  resolved direction at all. No safety or regulatory data.

## Results

| Field | Valeriana officinalis | Matricaria chamomilla | Punica granatum |
|---|---:|---:|---:|
| Overall_Score | **57.3** | 41.0 | 27.2 |
| Indication_Relevance_Score | 32.6 | 31.8 | 24.0 |
| Scientific_Evidence_Score | 7.47 | 0.00 | 0.00 |
| Evidence_Quality_Score | 18.3 | 21.1 | 15.3 |
| Evidence_Consistency_Class | MOSTLY_POSITIVE | CONSISTENT_NULL | INSUFFICIENT_DIRECTION_DATA |
| Outcome_Specific_Human_Evidence_Count | 1 | 3 | **0** |
| Plant_Applicability_Factor | 0.6 | 0.6 | 0.6 |
| Target_Definition_Completeness | complete | complete | complete |
| Compound_Quality_Score | 1.2 | 1.2 | 1.2 |
| Mechanism_Support_Score | 2.0 | 2.0 | 2.0 |
| Safety_Regulatory_Score | 14.0 | 6.0 | 0.0 |
| Novelty_Market_Score | 0.0 | 0.0 | 0.0 |
| Decision_Class_AH | C — Alternative-source R&D candidate | F — Exploratory hypothesis | F — Exploratory hypothesis |
| Go_Investigate_Hold_NoGo | Investigate — verify preparation applicability | Investigate — verify before proceeding | Investigate — verify before proceeding |
| Indication_Evidence_Mode | Direct human/clinical | Direct human/clinical | **UNVERIFIED_DIRECT_HUMAN_SIGNAL** |

**Final ranking: Valeriana officinalis (57.3) > Matricaria chamomilla
(41.0) > Punica granatum (27.2).**

## Directly answering your question

**Punica no longer outranks Valerian.** The prior inversion (reported at
Overall_Score 66.5 for Punica-like data vs. a comparable/lower Valerian
score under the pre-fix code) was caused by defects now fixed:

- **Defect 2** is the decisive one for this specific comparison: Punica's
  `Indication_Relevance_Score` drops from a would-be 32.6/35 ("Direct
  human/clinical") to 24.0, because `Indication_Evidence_Mode` correctly
  reads `UNVERIFIED_DIRECT_HUMAN_SIGNAL` — the one record tagged "clinical"
  has `Result_Direction = "unknown"` and never states the indication in its
  own outcome text. `Outcome_Specific_Human_Evidence_Count = 0` is now
  reflected in the relevance score itself, not just a separate,
  unconsulted count.
- **Defect 1** (prior pass): with 7 of 8 records having no resolved
  direction, `Evidence_Consistency_Class` correctly reads
  `INSUFFICIENT_DIRECTION_DATA` rather than a partial-credit `MIXED` —
  `Scientific_Evidence_Score` correctly floors at 0.0 instead of the old
  ~2-point partial credit for undirected evidence.
- **Defects 4/5/6/7** (prior pass): Mechanism/Compound/Safety/Market are no
  longer saturated to near-max on row volume or absent-data credit.

Valeriana's evidence is genuinely stronger by every one of these corrected
measures (a resolved positive result naming the indication, reassuring
safety, a regulatory monograph) and now correctly ranks first.

**Chamomile is the case worth flagging separately:** it has *more* human
evidence than Valeriana (3 RCTs vs. 1) and correctly keeps
`Indication_Evidence_Mode = "Direct human/clinical"` (its records DO state
a resolved outcome for the indication) — but that outcome is a genuine
**null result** (`CONSISTENT_NULL`), so `Scientific_Evidence_Score` floors
at 0.0 and `Decision_Class_AH` correctly drops to `"F — Exploratory
hypothesis"` despite having the most verified human evidence of the three.
This is the system correctly distinguishing "well-evidenced" from
"positively-evidenced" — more RCTs do not help a candidate whose RCTs
report no benefit.

## Caveat

This is 3 synthetic-but-realistic candidates, not the real 50+ candidate
Sleep run. The relative ranking mechanism demonstrated here (verified
evidence quality and direction controlling the outcome, not evidence
volume or upstream AI optimism) is the same mechanism that will apply to
the real run, but exact scores and the full candidate set can only come
from re-running against live data.
