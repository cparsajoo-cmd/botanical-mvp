# Architecture — Botanical Product Intelligence Platform

Last updated: Phase 7 (repository cleanup), verified against the actual
codebase by automated import-reachability analysis, not written from
memory. If this file and the code ever disagree, the code is right —
re-run the verification method described at the bottom before trusting
either.

## The one real pipeline

Streamlit auto-loads `app.py` as the main entrypoint, plus every file
under `pages/` as separate, independently-loaded pages. These are the
ONLY two ways code in this repository actually runs in production.

```
app.py
 ├─ step_inputs.py            (Step 0: indication/dosage form/market)
 │   └─ regulatory_frameworks.py
 ├─ step_question.py          (Step 1: question understanding)
 │   └─ ai_discovery_engine.py
 │       └─ seed_data.py
 │           └─ schema.py (local SQLite — see "Known oddities" below)
 ├─ step_evidence.py          (Step 2: live evidence collection)
 │   └─ research_engine.py
 │       ├─ multi_source_collector.py  (+ per-source connectors, see below)
 │       ├─ global_candidate_ranking_engine.py  (fallback candidate list only)
 │       └─ botanical_rd_candidate_engine.py    (see Step 5, same engine)
 ├─ step_rd_candidates.py     (Steps 3-6: market landscape, existing
 │                              knowledge, R&D discovery, final recommendation —
 │                              one file implements all four UI steps
 │                              deliberately, not a missing-file gap: they
 │                              share the same cached engine instance and
 │                              session state, and splitting them into
 │                              separate files would mean either duplicating
 │                              that shared state or adding cross-file
 │                              plumbing for no functional benefit)
 │   └─ botanical_rd_candidate_engine.py
 │       ├─ concentration_normalizer.py       (Phase 4)
 │       ├─ evidence_hierarchy_classifier.py  (Phase 4)
 │       ├─ negative_evidence_classifier.py   (Phase 4)
 │       ├─ evidence_confidence.py            (Phase 6)
 │       ├─ decision_class_ah.py              (Phase 6)
 │       ├─ global_plant_candidate_database.py
 │       ├─ compound_occurrence_map.py
 │       └─ (per-source connectors — pubmed, europepmc, clinicaltrials,
 │           chembl, chebi, pubchem, dailymed, fda, openfda, crossref,
 │           openalex, semantic_scholar, livertox, patent, ema_regulatory,
 │           regulatory)
 ├─ step_import_data.py       (optional: manual data import)
 │   └─ supabase_client.py
 └─ evidence_database.py      (Supabase evidence_records preview)
     └─ database.py
         └─ supabase_client.py

pages/Bulk evidence.py         (SEPARATE from the Step 0-6 flow — manually
                                 triggered, not part of app.py's own run)
pages/Diagnostic.py             (debug-only; removed before investor demos)
pages/Plant_Profile.py
pages/Source_Ingestion.py
```

**BotanicalRDCandidateEngine is the one central R&D decision engine.**
It's instantiated in two places (Step 2's research_engine.py, for
candidate-plant selection only, and Step 5's step_rd_candidates.py, for
the actual scoring/decision output the user sees) but there is only
ONE implementation of the scoring/decision logic itself — the
duplicate parallel scoring system that used to run in Step 2
(decision_engine.py + friends) was removed in Phase 2, not fixed,
because nothing downstream ever read its output.

## Data flow, in one sentence per stage

1. **Step 0** — user picks indication (still a fixed selectbox, not
   free-text — a known open item, audit 4.1) / dosage form / target
   market. As of this session, indication/dosage_form/market can ALSO
   be pre-filled from a free-text question (`free_text_question_parser.py`,
   keyword/phrase matching against the same selectbox vocabularies —
   not a trained NLU model, see that file's own docstring for the
   honesty caveats) — the selectboxes themselves are unchanged and
   remain the actual source of truth; free text only pre-fills them.
   `question_understanding_engine.py` (previously imported nowhere,
   flagged across 3 external reviews) is now called from step_inputs.py
   to build a "Standardized Project Definition" (route, product type,
   regulatory focus, evidence requirements) surfaced in Step 0's UI and
   in the final report.
2. **Step 1** — question UNDERSTANDING (matching a free-text question to
   a known indication/dosage form/market) now has a real implementation
   (see Step 0 above) — but question ANALYSIS in this step still pulls
   targets/keywords from hardcoded seed data (`seed_data.py`'s
   `TARGET_DISEASES`/`COMPOUND_TARGETS`), not live-extracted from
   evidence. That distinction — recognizing WHAT the question is about
   vs. reasoning about WHICH targets/mechanisms are actually relevant —
   is still only solved for the first half.
3. **Step 2** — live evidence collection, per candidate plant, saved to
   Supabase's `evidence_records` table. Runs a SMALL number of results
   per source (`max_results: 5` in `source_registry.py`) — full bulk
   coverage only happens on the separate `pages/Bulk evidence.py` page,
   manually triggered, not part of this flow.
4. **Steps 3-6** — `BotanicalRDCandidateEngine.run()`: loads
   `plant_compounds`/`compound_profiles`/`scientific_evidence` from
   Supabase, cross-references against the reference plant/compound,
   scores every candidate, classifies it, and returns the final table.

## Known oddities (verified, not fixed — flagging so nobody "rediscovers" them)

- **A local SQLite database (`schema.py`, `botanical_platform.db`)
  is still in the active import chain**, via `seed_data.py`. It
  coexists with Supabase (the actual production data store) rather
  than replacing it. Nothing currently breaks because of this, but
  it's a second, unused-in-practice persistence layer worth removing
  in a future pass.
- **Retail product search is a stub** (`_search_retail_products()`
  literally returns `"Not implemented"`); **patent search** only
  activates with `EPO_OPS_KEY`/`EPO_OPS_SECRET` set. This is why
  `_market_status()` (Phase 5) defaults to `"Search not performed"`
  rather than claiming a real search ran.
- **`pages/Bulk evidence.py` is not part of the Step 0-6 flow.** It's
  a separate Streamlit page a user has to navigate to manually — full
  evidence coverage is opt-in, not automatic.

## Legacy files (identified, NOT yet moved to `archive/` — see status below)

**Current status, corrected (external review caught this drift): the
archive/ directory does not exist yet in this repository.** An earlier
version of this file claimed "67 legacy files were moved to archive/"
— that was aspirational/future-tense written as if already done, and
it wasn't. The 66 files below are still sitting in the repo root as of
this writing.

**⚠️ CRITICAL BUG FOUND AND FIXED (this revision) — read before ever
running the archive workflow.** `.github/legacy-files.txt` listed
`question_understanding_engine.py` as safe to archive, but a later
session (after the original 67-file list was generated) wired it into
production — `step_inputs.py` actively imports
`standardize_project_definition` from it. The static list was never
re-validated after that change. Had the archive workflow been run in
that state, it would have moved a live production dependency into
`archive/` and broken the app. `question_understanding_engine.py` has
been removed from the list (66 files remain, all individually
re-confirmed safe — see below), and the underlying process gap is now
closed structurally, not just patched once:
- `repo_dependency_audit.py` — a real, reusable tool (not an ad-hoc
  snippet) that recomputes the production/test/legacy classification
  fresh, every time it's run.
- `test_production_dependency_integrity.py` — runs that same check as
  a normal pytest test, so `pytest -q` (which every PR/CI run already
  executes) catches this class of drift automatically, not only when
  someone remembers to re-run a manual script.
- `archive-legacy.yml` now calls `repo_dependency_audit.py validate`
  as its FIRST step, before touching any file, and fails the whole job
  if anything listed is actually reachable from production.

66 files were confirmed — by `repo_dependency_audit.py`, run fresh
against the current codebase (not by trusting the original Phase 1/7
snapshot) — to be unreachable from `app.py` and every file under
`pages/`. Each was a superseded/duplicate engine, an old Step from
before the Step 0-6 consolidation, or a connector that was never wired
in. The full list is in `.github/legacy-files.txt`.

**To actually move them:** go to the repo's Actions tab, select
"Archive legacy files (Phase 7)", and click "Run workflow" (see
`.github/workflows/archive-legacy.yml` — it already exists and is
ready to run, it just hasn't been triggered yet). It now validates the
list itself before moving anything (see above), and runs both the
production smoke test and the full suite after moving, before
committing. After it runs, still verify by hand:
- `archive/` exists and contains the 66 files
- `archive/ARCHIVED_FILES.md` was generated
- `pytest -q` still passes
- Update this section of ARCHITECTURE.md to say "moved" only once
  that's actually confirmed true — do not restate it as done from
  intent alone again (this is the exact mistake that caused the
  "moved to archive/" claim to go stale the first time).

Files that `repo_dependency_audit.py` also flags as "not reachable
from production" but that should NOT be included in the archive list,
because unreachable-from-app.py isn't the same as legacy — both are
intentionally standalone dev tools, run manually, never imported by
the app itself:
- `scoring_sensitivity_report.py` (Phase 6) — a standalone analysis
  tool, meant to be imported and run manually against a `run()`
  result, not called by the app itself.
- `repo_dependency_audit.py` (this session) — the repository-integrity
  tool described above; deliberately not imported by the running app,
  only by its own test file and by `archive-legacy.yml`.

(`data_contracts.py`, previously listed here as a third standalone
exception, is no longer one — a later session wired it into production
via `candidate_output_adapter.py`, which `step_rd_candidates.py`
imports. `repo_dependency_audit.py` now correctly reports it as
production-active; this note is left here specifically so the same
"once true, assumed still true" mistake doesn't get made about it
either.)

## How to re-verify any of the above

Run the real tool, not an inline snippet — copying a snippet out of
this file is exactly how the original snapshot went stale (it was
never re-run after being pasted here once):

```
python3 repo_dependency_audit.py summary
python3 repo_dependency_audit.py validate . .github/legacy-files.txt
```

Or as a normal test: `pytest -q test_production_dependency_integrity.py`.
This is the same method used to produce this file's legacy list —
re-run it after any future change to `app.py`'s or any Step file's
import chain to catch drift, rather than trusting this document.

## Sprint 3 — robustness/contribution-shift analysis (scoring_sensitivity_report.py)

Post-processing only — reads `R&D_Opportunity_Score`/`Score_Breakdown`
from a completed `run()` result, never calls `_score_candidate()`,
never mutates a score or rank. Two genuinely separate analyses live in
this one file: `fragility_report()` (Phase 6 — distance to a
Decision_Class boundary) and `build_robustness_analysis()` (Sprint 3 —
whether the #1-vs-#2 rank within a reference group survives removing
one scoring section). Full documentation, including why
"contribution-shift threshold" is explicitly NOT a raw weight
threshold, why leave-one-dimension-out is section-level only (no
sub-component data is preserved after scoring), and why rank stability
is model sensitivity rather than scientific confidence, is in that
file's own module docstring — read it before extending this analysis
further, rather than re-deriving these constraints from scratch.

## Sprint 4 — Evidence Conflict & Consistency Intelligence (structured_rationale.py)

**Why no new engine was created.** `evidence_conflict_reasoning()`
already computed most of what this Sprint needed (POSITIVE/MIXED/
NEGATIVE bucketing, source-count-aware reasoning). Sprint 4 extends
that same function's neighborhood in `structured_rationale.py` —
`classify_evidence_consistency()`, `classify_dominant_evidence_pattern()`,
`build_possible_explanations()`, `detect_research_gaps()`,
`build_evidence_conflict_structured()` — rather than creating
`conflict_engine.py`/`consistency_engine.py`, which were explicitly
rejected as options.

**Why `Evidence_Confidence` remains unchanged.** Nothing in this
Sprint reads or writes `Evidence_Confidence`, `Candidate_Evidence_Strength_Tier`,
`R&D_Opportunity_Score`, `Decision_Class_AH`, or any robustness/
comparative field — verified by a dedicated test
(`test_sprint4_addition_does_not_change_scores_or_ranking`) that
confirms `run()`'s score/rank output is identical with this column
present. This is a pure interpretation layer over evidence that
already fed into scoring; it doesn't recompute or second-guess that
scoring.

**Why explanations are conservative.** `possible_explanations` only
ever returns one of 7 categories (`SUPPORTED_EXPLANATION_CATEGORIES`
in `structured_rationale.py`) — Population, Dose, Extraction/
preparation, Study design, Endpoint, Study quality, and Evidence level
differences — each backed by either a real keyword-hint match or a
structural check (2+ hierarchy tiers detected in the combined text).
Species, target, mechanism, and publication-specific explanations are
explicitly rejected (`REJECTED_EXPLANATION_CATEGORIES`) because no
comparable structured field exists to honestly support them — adding
them would be a fabricated causal claim, not a detected pattern.

**Why study-level disagreement is intentionally unsupported.**
`_build_evidence_text_index()` concatenates every study's text for a
plant into ONE flat string before any classifier runs — there is no
per-study or per-source attribution anywhere in this pipeline. Every
Sprint 4 output — and every one of its `limitations` entries — states
this explicitly: conflicts represent positive/negative *patterns
detected in the aggregated text*, never "N of M sources agree." Making
that limitation legible is deliberate, not an oversight; solving it
for real would require the same claim-level-provenance rearchitecture
flagged and deferred across three prior review rounds.

**Difference between four terms that sound similar but measure different things:**

| Term | What it measures | Where |
|---|---|---|
| Evidence Confidence | Strength of the evidence FOR THIS CANDIDATE (source count × hierarchy tier) | `evidence_confidence.py`, unchanged since Phase 6 |
| Evidence Consistency (Sprint 4) | Whether the aggregated evidence agrees or conflicts with itself | `structured_rationale.classify_evidence_consistency()` |
| Robustness (Sprint 3) | Whether the #1-vs-#2 RANKING would survive removing one scoring section | `scoring_sensitivity_report.build_robustness_analysis()` |
| Recommendation Score | The actual R&D_Opportunity_Score/Decision_Class_AH | `_score_candidate()`, never touched by any of the above |

These four are computed independently and never substitute for one
another — a candidate can have high Evidence Confidence and low
Evidence Consistency (strong but conflicting evidence) at the same
time, and neither one moves the Recommendation Score.

## Sprint 5 — Regulatory Intelligence (Phase A fix + Phase B, structured_rationale.py)

**Phase A, Issue 1 — why the bug correction was necessary.**
`_market_status()` compared `EMA_Status == "Yes"` — but
`ema_regulatory_connector.py`'s real connector never returns the
literal string `"Yes"`; its actual output is descriptive
(`"Listed in HMPC inventory as 'X' — see source PDF for monograph
status"`). Only the legacy fabricated stub (Phase A Issue 2) ever
produced `"Yes"`. This meant a genuine EMA inventory match on any
plant OTHER than the 4 legacy-stub plants could never produce
`"Regulatory monograph exists"` — silently, with no error. Fixed via
one new static method, `BotanicalRDCandidateEngine._ema_listed()`,
which recognizes the real connector's actual prefix (and the legacy
literal, for backward compatibility with any already-stored data —
new data should never produce it again). See
`test_ema_listed_recognizes_the_real_connectors_actual_output_format`
and `test_market_status_regulatory_monograph_reachable_via_real_connector_format`.

**Phase A, Issue 2 — why the fabricated stub is no longer part of
production interpretation.** `regulatory_connector.py`'s
`REGULATORY_DB` held hand-typed, never-independently-verified
`"EMA_Status"/"WHO_Status"/"ESCOP_Status": "Yes"/"No"` values for 4
plants, reachable via `multi_source_collector.py`'s Step 2 bulk
collection, indistinguishable in shape from genuine connector output.
Per the explicit instruction not to simply delete files, it is
disabled via `_LEGACY_STUB_ENABLED = False` (in `regulatory_connector.py`)
rather than removed — `REGULATORY_DB` remains as historical reference,
but `search_regulatory_sources()` now always calls the real EMA
connector, for every plant. Re-enabling it requires a deliberate,
commented flag change, not a silent revert.

**Phase B — Regulatory Intelligence.** Reuses
`enrich_candidates_with_market_landscape()`'s already-correct,
already-cached `Market_Landscape_EMA_HMPC_Status` output (opt-in,
called once per unique plant) — this module never calls a connector
directly, and inherits Phase A's fix for free since that enrichment
path was never affected by either Phase A bug. Only `EMA/HMPC` is ever
reported as a populated authority; WHO, ESCOP, FDA botanical status,
Health Canada, and Novel Food explicitly report "not available" —
`test_unavailable_authorities_never_report_a_fabricated_status` locks
this in.

**Difference between four terms that sound similar:**

| Term | What it measures |
|---|---|
| Regulatory Status (`ema_status`) | Whether this specific plant is present in EMA's HMPC inventory — a fact about the plant |
| Regulatory Data Quality | Where that fact came from (live connector / static curated reference / unavailable) — a fact about the SOURCE |
| Regulatory Maturity | How resolved the lookup is (verified either way vs. never searched) — NOT a proxy for "is this plant well-regulated" |
| Evidence Confidence | Strength of scientific evidence for this candidate — an entirely separate axis, computed in `evidence_confidence.py`, untouched by any of the above |

None of these substitute for `R&D_Opportunity_Score`/`Decision_Class_AH`
— Regulatory Intelligence never influences scoring or ranking.

## Sprint 6A.1 — Session-scoped Connector Observability (connector_session_observability.py)

1. **Session-scoped.** Every status in this feature describes ONE Step
   2 collection attempt — the one currently held in Streamlit session
   state — never anything about connector behavior generally or over
   time.
2. **Generated from the existing collection result.** `build_connector_session_observability()`
   takes the exact dict `multi_source_collector.collect_multi_source_evidence()`
   already returns (`sources_checked`/`errors`/`saved_records`) — it
   triggers no connector, makes no network call, and recomputes nothing
   that call already decided.
3. **Nothing is persisted.** No database write, no file write — the
   object exists only in memory for the current page render, exactly
   like the data it's built from already did before this module
   existed.
4. **No connector is polled.** This module runs only after a
   user-initiated Step 2 collection has already finished.
5. **No network call is added** — verified directly: `connector_session_observability.py`
   imports nothing from any `*_connector.py` file, and contains no
   `requests`/`Entrez`/network call of any kind.
6. **"Completed" does not mean data was found.** A source can complete
   its search and legitimately find nothing — see point 7.
7. **"Completed — no records" is a distinct, separate status from
   "Failed"** — a source that ran cleanly and found zero matching
   records is not the same claim as a source that errored.
8. **Cache observability refers only to explicit repository-level
   caching** — the only one that exists is `ema_regulatory_connector.py`'s
   `lru_cache`. Every other connector's wording explicitly states this
   says nothing about whether the upstream API/library/infrastructure
   caches on its own.
9. **Configuration status does not validate credentials.** "Not
   configured" only means a required credential is absent; the
   presence of a credential is never reported as "Valid" or
   "Authenticated," since this repository cannot verify that.
10. **Persistent telemetry belongs to a future Sprint 6A.2** — explicitly
    out of scope here; this Sprint stops at session-scoped, in-memory
    observability.
11. **Known technical debt, documented but not fixed this Sprint:**
    `pubmed_connector.py` hardcodes `Entrez.email` to a personal email
    address in source code, rather than reading it from an environment
    variable the way `semantic_scholar_connector.py`'s optional API key
    already does. This is a real configuration-hygiene inconsistency —
    recorded here, not silently left undocumented, but out of this
    Sprint's scope to change. (Verified: this email value never
    appears anywhere in `connector_session_observability.py`'s output —
    see `test_pubmed_email_value_never_appears_anywhere_in_output`.)

**Why "Connector_Session_Observability," not "Connector_Metadata" or
"Connector_Health":** both of those names would imply persistent
tracking, version history, or a health assessment this repository
cannot honestly support (see the Sprint 6 and Sprint 6A audits) — the
name itself needs to communicate the real, narrow scope.
