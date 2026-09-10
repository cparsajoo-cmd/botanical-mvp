# INVESTOR_DEMO_RISK_CHECKLIST.md

## What is now safe to demonstrate

- **Score components are honest, not inflated.** No component awards
  positive credit for missing information (safety, regulatory, market,
  mechanism, compound). A candidate with more database rows for the same
  compound/mechanism no longer outranks one with fewer but genuinely
  distinct rows.
- **"Direct human/clinical" relevance now means verified.** A candidate
  cannot reach near-maximal indication relevance from upstream AI/semantic
  matching alone if `Outcome_Specific_Human_Evidence_Count == 0` — it is
  labeled `UNVERIFIED_DIRECT_HUMAN_SIGNAL` and visibly capped, not silently
  presented as clinical evidence.
- **"Established scientific candidate" is a defensible claim.** It now
  requires the same evidence conditions as an actual "Go" call plus
  verified (not AI-inferred) direct human evidence — not score alone. If
  asked "why is this Established," the answer traces to real evidence, not
  a compound count.
- **The Valeriana/Chamomile/Punica ranking is now defensible from
  evidence**, and you can explain it live: Valeriana wins on a resolved
  positive result naming the indication; Chamomile has more RCTs but they
  report no benefit, correctly capping it below Valeriana; Punica's
  apparent "clinical" tag has no resolved outcome and is correctly flagged
  unverified. See REAL_SLEEP_RUN_DIAGNOSTIC.md for the exact numbers.
- **An incomplete product/project definition (no plant part/dose/route
  specified) no longer silently produces an unqualified "Go."** It shows
  "Investigate — complete target product definition" instead, without
  penalizing the underlying science score — a defensible, honest state to
  show live if a demo query doesn't specify every field.
- **Empty candidate sets and missing critical columns are handled
  gracefully** (verified by reading the actual guard code): an empty or
  malformed input dataframe returns empty results, not a crash.
- **Step 2 evidence collection already isolates per-connector failures**
  (verified: `research_engine.py::_collect_one_plant()` and
  `multi_source_collector.py`'s per-connector dispatch both wrap individual
  source calls in `except Exception`). One source (Crossref, ClinicalTrials,
  PubChem, ChEBI, etc.) failing or timing out does not stop the others or
  crash collection for that plant.
- **LLM calls have a bounded timeout and bounded retry** (`llm_client.py`
  — verified, not just asserted): a slow or unavailable OpenAI endpoint
  will not hang the run indefinitely.

## What should NOT be claimed

- **Not clinically validated.** `SCORING_MODEL_VERSION`/
  `PROVISIONAL_NOTICE`/`RANKING_CALIBRATION_STATUS` are unchanged — this is
  still an R&D prioritization score, not an efficacy or clinical-success
  probability. Do not say "clinically proven" or "validated" for any
  candidate, including "Established" ones.
- **Not a full pharmaceutical-grade evidence-adjudication rebuild.** This
  pass fixed specific, named scoring/authority defects; it did not rebuild
  or independently re-validate the underlying evidence-adjudication
  architecture end to end.
- **Do not claim Defect 10 (fail-gracefully) is fully solved.** It was
  audited, not comprehensively hardened — see the residual risk below.
- **Do not claim the 3-candidate Sleep comparison is the full real run.**
  It is a faithful, real-pipeline reconstruction of the reported patterns,
  not a reproduction of the actual live-data query. Say so if asked.

## External dependencies that could fail during a live demo

- **Supabase** (evidence database). If credentials are missing or the
  service is unreachable, `supabase_client.py` raises an explicit,
  readable error rather than hanging — but this was not traced further
  upstream to confirm every caller catches it gracefully with a friendly
  UI message rather than a raw traceback. **Recommendation: do a live
  connectivity check shortly before the demo starts**, since this specific
  path was not fully verified end-to-end this pass.
- **OpenAI** (AI adjudication, mechanistic reasoning, hypothesis
  generation). Bounded timeout/retry confirmed; if it fails/falls back,
  `Evidence_Adjudication_Status` will show `AI_ADJUDICATION_FALLBACK` /
  `AI_ADJUDICATION_UNAVAILABLE` and the deterministic scientific score
  still stands — an honest degraded state, not a crash, but the AI-derived
  fields (Indication_Evidence_Direction, mechanistic hypotheses) will be
  visibly absent or marked as fallback.
- **Secondary connectors** (Crossref, ClinicalTrials.gov, PubChem, ChEBI,
  patent/commercial search): confirmed isolated per-source (see above) —
  losing any one of these during the demo should not visibly disrupt the
  run, only that source's contribution.

## Graceful fallback behavior confirmed this pass

- Empty/malformed candidate input → empty result, not a crash.
- Per-connector failure in Step 2 → isolated, other sources continue.
- LLM failure/timeout → bounded, falls back to deterministic scoring.
- Missing safety/regulatory/market/mechanism data → scored as neutral
  (zero), never as a positive or a silent exclusion.
- Incomplete target/product definition → Investigate, never Excluded.

## Remaining red flags — read before the demo

1. **No per-candidate exception isolation in the Step 5 scoring loop**
   (`candidate_shortlisting.py`'s ~700-line per-plant loop inside
   `build_plant_candidate_shortlist()`). Unlike Step 2 collection, this
   loop has no `try/except` around a single plant's scoring — a malformed
   evidence record or an unexpected value in one plant's data *could*
   raise an exception that aborts the entire shortlist for every
   candidate, not just the one plant. **I looked at fixing this and
   deliberately did not**: the loop is large and interconnected enough
   that a safe fix would need real time to write and verify, and doing it
   under time pressure risked violating "no newly introduced failures are
   acceptable" more than it reduced risk. This is a real, unverified-safe
   gap, not a confirmed bug — the extensive defensive `.get()`/`_norm()`
   patterns used throughout every helper function in this file make an
   actual crash less likely in practice than the raw absence of a
   try/except would suggest, but it is not a guarantee.
   **Mitigation for tomorrow: run the exact planned demo query once,
   beforehand, end to end**, so any live-data edge case that would trigger
   this is caught before the audience sees it.
2. **The Supabase-unavailable path is not fully traced end to end** (see
   above) — confirmed the low-level client raises cleanly, not confirmed
   every caller shows a friendly message instead of a raw error.
3. **Defect 10's other named scenarios** (one malformed evidence record,
   missing optional dataframe columns beyond what was spot-checked, a
   connector returning `None` vs. an empty dataframe) were not individually
   walked through this pass — time was spent verifying the two highest-
   value, most demo-relevant paths (empty candidate set, per-connector
   isolation) rather than the full named list.
4. **`Target_Definition_Completeness`/`Final_Canonical_Evidence_Direction`
   are new fields** — they are wired into scoring/decision logic and
   tested, but have not been added to any Streamlit UI table or CSV export
   column list beyond `authoritative_fields` (the internal merge
   contract). If the demo UI has a fixed column list, these new fields may
   not be visible there yet even though they're correctly computed.
