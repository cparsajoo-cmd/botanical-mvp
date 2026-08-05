# PHASE 3 — Source Authority / Evidence Quality Audit

## Revision verification — botanical-mvp-main (89)

The uploaded project changed slightly since the audit below was written
against the prior revision. Both revisions were available on disk, so
this is a real `diff`, not a re-verification from scratch.

**Files that actually changed:** exactly two —
`database.py` and `test_database_evidence_schema_extension.py`. Nothing
else in the repository differs (confirmed via a full recursive diff of
both extracted trees).

**What changed in `database.py`:** `_missing_postgrest_column()` was
extended to also recognize PostgreSQL's `42703` ("undefined column")
error shape, in addition to the pre-existing PostgREST `PGRST204`
("schema cache") shape — both structured `APIError` attributes and
their string representations are now parsed, and a qualified column
name (e.g. `evidence_records.dose`) is correctly reduced to just the
column. `_insert_evidence_with_optional_schema_fallback()`'s docstring
was reworded to describe "optional evidence-schema extensions" generally
instead of naming only the five original Task-10.2 applicability fields
(a documentation-accuracy fix, no behavior change). The corresponding
test file gained a `"dose", "preparation"` entry in one existing
assertion's expected set (fixing a pre-existing gap in what that
assertion checked) and three new tests for the 42703 shape.

**Call graph:** unchanged. No new imports, no new call sites, no
function signature changes anywhere relevant to Source Authority /
Evidence Quality.

**Persistence:** unchanged in every way that matters to Phase 3. The
`evidence_payload` dict built in `save_evidence_record()` — the exact
place §1.2 step 4 below shows `Source_Authority_Weight`/`source_authority`
being silently dropped — was not touched. `_OPTIONAL_EVIDENCE_COLUMNS`
gained no new entries. `load_evidence_records()`'s row-mapping dict was
not touched. The only persistence-adjacent change is that a wider range
of "missing column" database errors are now detected and handled by the
SAME existing fallback-and-retry mechanism — a robustness fix to error
detection, not a change to what is written or read.

**Scoring:** unchanged. `candidate_shortlisting.py`, `evidence_interpretation.py`,
`evidence_quality_engine.py`, `botanical_rd_candidate_engine.py`,
`source_registry.py`, `multi_source_collector.py`, `evidence_standardizer.py`,
and `standard_evidence_schema.py` are byte-for-byte identical to the
revision the original audit below was run against.

**Are the prior architectural decisions still valid?** Yes, all of them.
Findings 1-11 from the person's revision-verification checklist were
re-confirmed directly against this revision's actual `database.py` (not
assumed from the old report):

 1. `Source_Authority_Weight` generated in collection — **still true**, `multi_source_collector.py` unchanged.
 2. Preserved through standardization — **still true**, `evidence_standardizer.py` unchanged.
 3. Maps to `EvidenceRecord.source_authority` — **still true**, `standard_evidence_schema.py` unchanged.
 4. Not written to the database payload — **still true**, verified against the new `database.py`: the `evidence_payload` dict (now at a shifted line number because of the longer `_missing_postgrest_column`, but textually identical) still has no `source_authority`/`Source_Authority_Weight` key.
 5. Not read back in `load_evidence_records()` — **still true**, that function's row-mapping dict is unchanged.
 6. Not used in `candidate_shortlisting.py` scoring — **still true**, that file is unchanged; zero references to `authority`.
 7. `candidate_shortlisting._evidence_quality` is the live 30-point path — **still true**, unchanged.
 8. `evidence_interpretation.py` is the other live quality/direction path — **still true**, unchanged.
 9. `evidence_quality_engine.py` is outcome-coupled — **still true**, unchanged, still only reachable through the unimported `decision_engine.py`.
10. `decision_engine.py` remains dead/unimported — **still true**, re-grepped against this revision (`import decision_engine` / `from decision_engine`: zero hits anywhere, including tests).
11. Next migration number should be `0007` — **still true**; `migrations/` on disk in this revision still contains only `0002`, `0004`, `0005` (+ `_down` pairs) — identical to the prior revision.

**New finding directly from this revision:** the `42703`-vs-`PGRST204`
robustness fix is a real, independent improvement worth preserving —
Phase 3's own new `source_authority`/`source_authority_score`/
`source_authority_reason` optional columns (added later in this document)
will benefit from it automatically, since they go through the same
`_insert_evidence_with_optional_schema_fallback()` retry path. No
Phase 3 design decision needed to change because of it.

**One correction to the original audit below, caught while re-reading
`candidate_shortlisting.py` during this pass:** §4's decision-path table
states `Scientific_Triage_Score` "was not found by this name in any
file searched." That was incomplete — `Scientific_Triage_Score` **does**
exist (`round(triage_score, 1)`, assigned in the same `rows.append({...})`
block that also sets `Scientific_Triage_Status`), as a numeric score
distinct from the categorical `Scientific_Triage_Status` gate value the
rest of §4 correctly traced. This does not change any Phase 3 design
decision (Source Authority still integrates through `_evidence_quality`,
not through `Scientific_Triage_Score`), but is recorded here since the
brief requires not treating an old report's claim as ground truth without
re-checking it.

**Conclusion:** the new project revision does not materially change the
Phase 3 audit findings below.

---



Status: **Audit + revision verification complete. Phase 3 design and
implementation (evidence_authority.py, persistence, scoring integration,
tests) proceeded after this document and are described in
PHASE3_SOURCE_AUTHORITY_IMPLEMENTATION.md.**

Every claim below was verified by direct inspection of the actual repository
(`botanical-mvp-main`, as uploaded) — file paths, line-level behavior, and
call graphs, not field-name assumptions. Where a claim could not be verified
by reading code, it is stated as "not verified" rather than asserted.

---

## 1. Source Authority — current reality

### 1.1 Where it is defined
`source_registry.py` is the **only** place `authority_weight` exists as a
config value. It is a static per-connector float (0.7–1.0) on 15 entries
(PubMed, Europe PMC, Semantic Scholar, OpenAlex, CrossRef, ClinicalTrials.gov,
"EMA/WHO/ESCOP Regulatory" — a single combined bucket, not three separate
entities —, FDA Labels, LiverTox, DailyMed, OpenFDA FAERS, PubChem, ChEMBL,
ChEBI, Patent Landscape). `get_source_config(name)` is a linear lookup by
connector name.

**Finding — coarse granularity.** `authority_weight` is keyed by *connector*,
not by *document type*. "EMA/WHO/ESCOP Regulatory" is one entry with one
weight (1.0) — the registry cannot currently distinguish an EMA HMPC
monograph from a WHO monograph from an ESCOP monograph, nor a Cochrane review
from a random PubMed-indexed systematic review, nor a commercial
website/blog from peer-reviewed literature (there is no commercial-website or
blog connector/category in the registry at all today).

### 1.2 Generation → propagation trace
Followed exactly as instructed, step by step:

1. **Generated**: `multi_source_collector.py:141` —
   `record["Source_Authority_Weight"] = source_config.get("authority_weight", "")`
   at collection time, per evidence dict, from `source_registry.get_source_config`.
2. **Standardization**: `evidence_standardizer.py:69` lists
   `"Source_Authority_Weight"` among fields it passes through (not dropped
   there).
3. **Canonical model**: `standard_evidence_schema.py` —
   `_LEGACY_FIELD_MAP["Source_Authority_Weight"] = "source_authority"`, and
   `EvidenceRecord.source_authority: Optional[str] = None` exists as a
   dataclass field (line ~231). So the canonical adapter *does* carry it in
   memory, as an untyped string/passthrough, not a numeric factor.
4. **Database write** (`database.py::save_evidence_record`): **it is
   dropped here.** `record = canonicalize_evidence_record(record)` round-trips
   through `EvidenceRecord`, but the `evidence_payload` dict built afterward
   (the actual Supabase insert payload, ~140 lines, every other legacy field
   explicitly re-read with `record.get(...)`) **never reads
   `Source_Authority_Weight` or `source_authority` at all.** There is no
   `"source_authority"` key, and it is not in `_OPTIONAL_EVIDENCE_COLUMNS`
   either. It is silently discarded before the insert — not a schema-missing
   fallback case, a genuine omission from the payload construction.
5. **Database read** (`database.py::load_evidence_records`): confirms (4) —
   the returned row dict has no `Source_Authority_Weight` / `source_authority`
   key at all. Every other Phase-2 field (`pmid`, `dose`, `preparation`, etc.)
   has a corresponding `item.get(...)` line; authority has none.
6. **Candidate rows / scoring**: `candidate_shortlisting.py` (the module that
   actually computes `Evidence_Quality_Score` and feeds `Overall_Score`) was
   grepped for `authority` — **zero matches.** Confirmed independently: since
   step 4 never persists it, step 6 could not use it even if it wanted to.
7. **Explainability**: no `source_authority` field appears in any
   score-breakdown / rationale output searched.

**Conclusion**: Source Authority today is **collected and discarded**. It
exists for the lifetime of one in-process dict during a collection run, is
never durable, and has **zero effect on any score, ranking, or decision**.
This is worse than "authority isn't used" — it means the field name
`source_authority` already exists on the canonical `EvidenceRecord` dataclass
and in the legacy-field map, creating an illusion (to a future reader) that
the concept is wired end-to-end when it is not.

### 1.3 Are PubMed/EMA/WHO/commercial-site sources actually weighted differently today?
No, at the level that matters (scoring). At the config level yes
(`source_registry.py` weights differ), but since none of it survives past
in-memory collection, every persisted/scored piece of evidence is, in
practice, unweighted by authority. There is also no "commercial website" or
"blog" connector in the registry, so the audit's required category
(`Commercial Website`, `Blog`, `Unknown Source`) has no real-world source of
truth to detect from in this codebase today — it would need to come from
free-text/URL heuristics on `Source_URL`/`Source_Organization`, which
`evidence_hierarchy_classifier.py`, `evidence_classifier.py`, and
`ema_monograph_registry.py`/`ema_regulatory_connector.py` partially cover for
regulatory detection (see §3).

### 1.4 `decision_engine.py` — dead code, not the active path
`decision_engine.py` imports `evidence_quality_engine.apply_evidence_quality`
and calls it once (line 216). **`decision_engine.py` itself has zero
importers anywhere in the repository** (grepped `import decision_engine` /
`from decision_engine` across all `.py` files, including tests — no hits).
It is not reachable from `app.py`, any `step_*.py` pipeline stage, or any
test. This is a pre-existing dead module, not part of the frozen Phase 1
engine (`botanical_rd_candidate_engine.py`) or the active shortlisting path
(`candidate_shortlisting.py`). Flagged as an out-of-scope observation, not
something Phase 3 is asked to fix — but it matters for the next finding.

---

## 2. Evidence Quality — how many implementations, and which one is real

Three genuinely separate implementations exist, answering the audit's
required question directly:

### 2.1 `evidence_quality_engine.assess_evidence_quality` / `apply_evidence_quality`
- Lives only in `evidence_quality_engine.py`.
- **Confirmed outcome-coupled** (the audit's suspected bug, verified by
  reading the function): `quality_score += 10` for
  `"significant improvement"/"improved"/"effective"/"efficacy"/"positive"`
  text; `quality_score -= 10` for `"no significant"/"not effective"/"negative"`;
  `+6`/`-5` for safety-tolerability wording. Outcome direction and safety
  wording are folded directly into `Evidence_Quality_Score`/`_Class`, exactly
  the coupling the brief prohibits ("یک RCT منفی باید از نظر quality همچنان
  RCT باکیفیت باشد" is violated here: a negative RCT loses 10 points purely
  for being negative, on top of/independent of its actual study-design
  points).
- **Only caller is `decision_engine.py`** (§1.4), which nothing imports. So
  this specific bug, while real and worth documenting, is **not currently
  reachable from any production scoring path or any test that exercises the
  real engine.** `pytest -q`-visible failure surface from fixing/removing it
  should be limited to whatever direct unit tests target
  `evidence_quality_engine.py` itself (none found by filename search —
  no `test_evidence_quality_engine.py` exists in the repo).

### 2.2 `evidence_interpretation.classify_evidence_quality` (+ `QUALITY_FACTOR`)
- Lives in `evidence_interpretation.py` (Phase 1 module, 576 lines,
  extensively documented in its own header as the fix for exactly this
  direction/design conflation, but scoped only to the "Clinical / human
  evidence" tier's *contribution* calculation).
- **Correctly design-based, not outcome-based**: `classify_evidence_quality(text, study_design)`
  only inspects `_LOW_QUALITY_PHRASES` / `_HIGH_QUALITY_PHRASES` (methodological
  wording — blinding, sample size adequacy, risk-of-bias language — not
  outcome polarity) and falls back to `QUALITY_UNKNOWN` for
  `STUDY_DESIGN_UNSPECIFIED`. Returns one of `high`/`moderate`/`low`/`unknown`.
- `QUALITY_FACTOR` (`{high: 1.0, moderate: 1.0, low: 0.6, unknown: 1.0}`) is
  explicitly documented as **scale-only, never sign-changing** — matches the
  brief's required architecture almost exactly already.
- **Confirmed live**: imported by `botanical_rd_candidate_engine.py` (the
  frozen Phase 1/2 core engine), `structured_rationale.py`,
  `evidence_confidence.py`, `pharma_report_generator.py`. This is the
  evidence-direction-and-quality logic that is actually running in
  production today.
- **Not persisted as its own field.** Its output (`high`/`moderate`/`low`/`unknown`)
  is consumed in-process by `interpret_evidence()` to compute `contribution`,
  but that `Evidence_Quality` label itself does not appear to be written to
  `EvidenceRecord`/the database under a dedicated column distinct from the
  canonical `evidence_quality` field described next.

### 2.3 The canonical `EvidenceRecord.evidence_quality` field
- `standard_evidence_schema.py`: `_LEGACY_FIELD_MAP["Evidence_Level"] = "evidence_quality"`.
- **This is a naming collision the brief specifically warns about.**
  `Evidence_Level` in this codebase is the engine's *coarse study-TYPE tier*
  (`_evidence_level()` in `botanical_rd_candidate_engine.py` — values like
  "Clinical / human evidence", "Regulatory / monograph evidence",
  "Preclinical / mechanistic evidence", "General literature signal", "No
  direct evidence" — confirmed from `evidence_interpretation.py`'s own
  docstring, which explicitly disclaims touching `_evidence_level()`). It is
  **not** a quality/certainty grade (not GRADE-like, not
  high/moderate/low). Mapping it to a canonical field literally named
  `evidence_quality` means the canonical model's `evidence_quality` and
  `evidence_interpretation.py`'s own `Evidence_Quality` (high/moderate/low/unknown,
  §2.2) are **two different concepts sharing confusingly similar names**,
  with the canonical field actually holding the *tier*, not the *quality
  grade*. Phase 3 must not silently treat these as the same field.

### 2.4 The real, active scoring implementation: `candidate_shortlisting._evidence_quality`
- This is the function that actually produces the `Evidence_Quality_Score`
  which reaches `Overall_Score`/`R&D_Opportunity_Score` (traced via
  `_derive_evidence_confidence(indication_points, evq_points)` and the
  `"Evidence_Quality_Score": evq_points` assignment at line ~1754, which
  feeds the summary row that later gets capped at `min(Overall_Score, 74.0)`
  and written to `R&D_Opportunity_Score`).
- **Architecture already separates hierarchy/depth/diversity/consistency
  (`raw_total`) from an `outcome_multiplier`** applied afterward
  (0.55 for all-null/harmful, 0.80 for mixed, 1.0 for clean positive or
  clean negative-only... — outcome_multiplier is **not** direction-sign-aware
  in the way the brief wants; a purely negative, high-quality, single-study
  RCT gets the same 1.0 multiplier path as a purely positive one, since the
  multiplier logic only distinguishes "has positive + no positive" combinations,
  not negative-only). Confirmed no `authority` term anywhere in this function
  or its ~230-line body.
- **Cap confirmed**: `total = round(min(30.0, raw_total * outcome_multiplier), 1)`
  — Evidence Quality's ceiling inside the 100-point `Overall_Score` is
  **30.0**, not the `evidence_quality_engine.py` module's 0–100 scale. This
  is the cap Phase 3 must integrate Source Authority inside of, per the
  brief's "سقف فعلی Evidence Quality را حفظ کن" instruction.
- **Answering the audit's explicit question**: "آیا نتیجه منفی به اشتباه
  «کیفیت پایین» تلقی می‌شود؟" — Partially. `row_hierarchy_points()` itself
  (study-design classification) is outcome-blind — good. But `_outcome_profile()`
  and `outcome_multiplier` DO reduce the *aggregate* quality score for a
  candidate whose evidence set is null/harmful-dominated. This is a
  deliberate, documented design choice in this function (comment: "Null/negative
  records are retained and visibly lower the score instead of being silently
  discarded") — but it conflates "quality of evidence" with "how favorable the
  evidence is" in the aggregate number, which is exactly the concept mixing
  the Phase 3 brief prohibits. This function pre-dates the brief and was not
  written against Phase 3's separation requirement.
- **Only implementation actually reachable from `pytest -q` on the real
  engine.** `test_candidate_shortlisting.py` exists and presumably exercises
  this.

### 2.5 Fields grepped per the audit's explicit list — actual status
| Symbol | Found in | Status |
|---|---|---|
| `evidence_interpretation.classify_evidence_quality` | `evidence_interpretation.py` | **Live**, design-based, correct architecture (§2.2) |
| `evidence_interpretation.QUALITY_FACTOR` | `evidence_interpretation.py` | **Live**, scale-only (§2.2) |
| `evidence_quality_engine.assess_evidence_quality` | `evidence_quality_engine.py` | **Dead** (only caller is unreferenced `decision_engine.py`), outcome-coupled bug confirmed (§2.1) |
| `candidate_shortlisting._evidence_quality` | `candidate_shortlisting.py` | **Live, this is the real production scoring path** (§2.4) |
| `evidence_confidence` | `evidence_confidence.py` | Live; consumes `evidence_interpretation` output — not itself an independent quality implementation, a downstream consumer |
| `Evidence_Level` | many | Coarse study-TYPE tier, not a quality grade — see §2.3 collision |
| `Study_Design` | `evidence_interpretation.py` | Live, correctly independent of direction/quality |
| `GRADE_Certainty` | `candidate_shortlisting.py`, `grade_certainty_classifier.py` | Live text signal consumed as one of several hierarchy-detection inputs; not itself audited line-by-line here — out of Phase 3's required scope beyond confirming it's read, not written |
| `Data_Quality_Score` | `database.py` (`data_quality_score` NUMERIC column, Phase 2), `record.get("Data_Quality_Score")` mapped to canonical `confidence` | Schema-ready, **not populated by any connector** per Phase 2's own comment — confirmed still true, not Phase 3's concern |
| `Evidence_Quality_Score` | `evidence_quality_engine.py` (0–100, dead path) AND `candidate_shortlisting.py` (0–30, live path) | **Name collision**: two different scales/semantics share this exact string. Phase 3 must not add a third meaning under the same name. |
| `Evidence_Quality_Class` | `evidence_quality_engine.py` only | Dead path only |

---

## 3. Source-type detection precedent already in the repo

Not previously listed as in-scope symbols, but directly relevant to §5's
detection requirement — found while tracing regulatory status:
`ema_monograph_registry.py`, `ema_monograph_connector.py`,
`ema_regulatory_connector.py`, and `regulatory_barrier_classifier.py` already
implement deterministic, word-boundary-safe matching for EMA/WHO/ESCOP-style
regulatory text (precedent Phase 3 should reuse the *style* of — bounded
phrase matching via `re.search(r"\b...\b", text)` — rather than re-inventing
a matcher, consistent with `evidence_interpretation.py`'s own `_find()`/`_has()`
helpers). These were not modified or fully read line-by-line in this audit
pass; a full read is deferred to the design/implementation phase since it
does not change any finding above.

---

## 4. Direct answers to the audit's required questions

**Source Authority**
- Currently generated in `source_registry.py` (static config) +
  `multi_source_collector.py` (assignment onto the record dict).
- `authority_weight` exists only in `source_registry.py` — confirmed, no
  duplicate definition elsewhere.
- `Source_Authority_Weight` **is** preserved through `evidence_standardizer.py`.
- It **does** map into `EvidenceRecord.source_authority` via
  `_LEGACY_FIELD_MAP`, but as an **untyped `Optional[str]`** (the registry
  value is actually a float 0.7–1.0; the canonical field type doesn't reflect
  that — no float/score field exists on `EvidenceRecord` for authority at
  all today).
- Not stored in `sources` or `evidence_records` tables — confirmed absent
  from both the insert payload and the select/read mapping.
- Not re-read by `load_evidence_records()` — confirmed.
- `candidate_shortlisting.py` does **not** use it in scoring — confirmed,
  zero references.
- It is metadata only, and currently **inert** metadata (collected, then
  discarded before persistence) — not a real scoring input today.
- PubMed vs. EMA vs. commercial vs. unknown do **not** get different
  effective weight today, because nothing downstream of collection reads
  `authority_weight` at all.

**Evidence Quality**
- Three implementations found (not counting the canonical-field collision),
  answered in full in §2.5.
- Confirmed outcome/negative-outcome coupling exists, but only in the dead
  `evidence_quality_engine.py` path.
- The live `candidate_shortlisting._evidence_quality` path is outcome-blind
  at the per-study classification level but outcome-sensitive at the
  aggregate level via `outcome_multiplier` — a softer, but real, version of
  the same conflation, and the one Phase 3 actually needs to address since
  it's the reachable path.
- `evidence_interpretation.py`'s Phase 1 quality output does reach the real
  engine (`botanical_rd_candidate_engine.py`) but only for the
  Clinical-evidence-tier `contribution` calculation, not as a field
  persisted or fed into `candidate_shortlisting.py`'s independent
  `_evidence_quality`. These are two separate live code paths computing two
  differently-scoped "quality" signals for two different consumers
  (`botanical_rd_candidate_engine.py` vs. `candidate_shortlisting.py`) —
  Phase 3's design must state explicitly which one Source Authority attaches
  to, and how (or whether) the two are reconciled, since the brief assumes
  one Evidence Quality/Direction/Authority pipeline and this repository
  currently has two, only loosely connected by the same source `EvidenceRecord`
  data (not by shared quality-computation code).

**Decision path — functions that actually determine each output**
| Output | Determining function(s) |
|---|---|
| Evidence Quality component (0–30, live) | `candidate_shortlisting._evidence_quality` |
| `Overall_Score` / `R&D_Opportunity_Score` | assembled in `candidate_shortlisting.py`'s main summary-build loop (~line 1300–1780 range); capped at 74.0 via `min(float(row["Overall_Score"]), 74.0)` |
| `Evidence_Confidence` | `candidate_shortlisting._derive_evidence_confidence(indication_points, evq_points)` |
| Shortlist / Exploratory / Excluded | not fully re-traced in this pass (out of the audit's minimum required path list beyond confirming `_evidence_quality`'s `total`/`tier` feed into the summary row that gate logic elsewhere reads) — flagged for confirmation at design time, not asserted here |
| Scientific_Triage_Score | not found by this name in any file searched — **not verified to exist under this exact name in the current repo**; needs a targeted search before the design doc references it, rather than assuming it exists |

---

## 5. Migration numbering — real gap found

`migrations/` on disk contains only `0002`, `0004`, `0005` (+ their `_down`
pairs). Code comments and `PHASE2_EVIDENCE_IMPLEMENTATION_REPORT.md`
reference `migrations/0006_add_dose_preparation.sql` and
`docs/reports/IMPLEMENTATION_PLAN.md` references
`migrations/0003_add_decision_records.sql` — **neither file is present in
this uploaded repository**, even though `database.py`'s runtime behavior
(`dose`/`preparation` in `_OPTIONAL_EVIDENCE_COLUMNS`, optional-column
fallback) is consistent with 0006 having been applied by hand against the
real Supabase instance without the `.sql` file being committed back to this
repo copy. This matches the project's stated "no migration runner, applied
by hand" precedent, but means the next Phase 3 migration should **not**
assume 0001/0003/0006 are free numbers to reuse — the safe next number,
given what's actually visible on disk, is **0007** (also happens to match
the brief's own suggested filename).

---

## 6. Risks / gaps to carry into the design phase

1. **Two independent "quality" pipelines** (`botanical_rd_candidate_engine.py`
   via `evidence_interpretation.py`, vs. `candidate_shortlisting.py` via its
   own `_evidence_quality`) must both be considered — attaching Source
   Authority to only one will not satisfy "می‌بایست وارد امتیازدهی شود" for
   candidates scored through the other path. Needs an explicit design
   decision, not an assumption.
2. `EvidenceRecord.source_authority` already exists as a **string** field
   with real callers writing into it (via `from_legacy_dict`) — Phase 3 must
   decide whether to keep it as a label field and add a new numeric
   `source_authority_score`/`source_authority_reason` alongside it (additive,
   matches the brief's canonical-field list), rather than repurposing the
   existing field's type, since `_CANONICAL_TO_LEGACY` round-trips it and any
   type change could silently break `to_legacy_dict()`/existing tests.
3. `evidence_quality_engine.py`'s outcome-coupling bug is real but currently
   unreachable dead code (§2.1/§1.4) — worth fixing for correctness/consistency
   since the brief explicitly calls it out by name, but it is **not** the
   source of any live scoring distortion today; the live distortion (if any)
   is the softer aggregate `outcome_multiplier` effect in
   `candidate_shortlisting.py` (§2.4).
4. No commercial-website/blog connector exists in `source_registry.py` today
   — the `evidence_authority.py` taxonomy's "Commercial Website"/"Blog"/
   "Unknown Source" categories will only ever be reachable via
   metadata/URL-pattern fallback classification, not via a dedicated
   connector entry, which is fine but should be designed for explicitly.
5. `Scientific_Triage_Score` was not found — needs confirming before any
   design doc references it as an existing decision output.

---

**This audit was the required pre-implementation checkpoint.** Design and
implementation proceeded after it (and after the revision-verification
pass above confirmed nothing here needed to change) — see
PHASE3_SOURCE_AUTHORITY_IMPLEMENTATION.md for what was actually built,
which files changed, and the real test results.
