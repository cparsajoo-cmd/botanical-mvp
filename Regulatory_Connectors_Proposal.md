# Regulatory Connectors & REGULATORY_STATUS Gold Case — Proposal for Sign-Off

Prepared by: implementation engineer (Claude) · For: Hamid (architecture reviewer)
Status: PROPOSAL ONLY — no production code touched. Everything below is either (a) a verified fact from reading the current repo, or (b) explicitly labeled as a recommendation/option requiring your decision.

---

## 1. Audit — confirming/correcting your context summary

I read the actual code (not just file names) for every claim below.

### 1.1 Confirmed exactly as stated
- `ema_regulatory_connector.py` is the only live, real connector. It fetches EMA's HMPC "Inventory of herbal substances for assessment" PDF, and — deliberately — reports only *presence in the inventory*, not the ESCOP/WHO/German/French columns, because column alignment isn't reliably recoverable from PDF text extraction. This is honest engineering.
- `regulatory_connector.py`'s old `REGULATORY_DB` (4 hardcoded plants) is disabled via `_LEGACY_STUB_ENABLED = False`, kept only as historical reference, with an explicit comment against silently reviving it. Every call now goes to the real EMA connector.
- The **hard regulatory gate** (`_hard_regulatory_gate` in `botanical_rd_candidate_engine.py`) is driven purely by `regulatory_barrier_classifier.py`'s text-pattern matching (e.g., "novel food", "prescription only", "banned") on evidence text — it never reads `EMA_Status`/`WHO_Status`/`ESCOP_Status` or the connector output at all. Only `"Prohibited / banned"` triggers a hard `FAILED`; everything else is `PASSED` or `NOT_EVALUABLE`.
- `regulatory_frameworks.py`'s `MARKET_REGULATORY_FRAMEWORKS` is static, market-level descriptive text, confirmed unused in scoring.
- `fda_connector.py` (openFDA drug labels) and `openfda_connector.py` (openFDA FAERS adverse events) both query drug-safety/labeling data, not herbal regulatory status.
- The `ReferenceDomain.REGULATORY_STATUS` gold-case domain has zero cases — confirmed by grepping every `gold_case_reference_grounded_*.py` file.

### 1.2 Corrections / additions to your summary

**(a) There is a second, distinct static regulatory source you didn't mention.** `regulatory_frameworks.py` also defines `US_UK_PLANT_REGULATORY_STATUS` — a small, manually curated, explicitly-hedged dict (~8 plants) giving US market-history and UK THR-registration category (e.g. *"Likely grandfathered (long pre-1994 US market history)"*). It's wired into `structured_rationale.py` as a second jurisdiction in the "Regulatory Intelligence" display object, always passed through verbatim, never guessed for plants outside the curated set. Unlike the old `REGULATORY_DB` stub, this one is honestly hedged and explicitly documented as non-authoritative — but it's still a hand-typed, non-live source sitting next to a real connector, which is worth knowing about when you evaluate "what's actually live vs. curated" going forward.

**(b) Important finding — the "display-only, never influences score" claim is only partially true.** I verified this empirically, not just by reading docstrings.

- The `build_regulatory_intelligence()` *structured display object* genuinely never feeds back into scoring — its docstring says so and the code confirms it.
- **But** `EMA_Status`, `WHO_Status`, `ESCOP_Status`, `Regulatory_Status`, and `Notes` — the very fields the EMA connector writes — are in `EVIDENCE_TEXT_INDEX_ALLOWLIST`, which means they get concatenated into the same free-text pool (`_build_evidence_text_index()`) that `_evidence_level()` reads to classify a candidate's `Evidence_Level`. I ran the actual classifier against real (non-fabricated) EMA connector output text:

  ```
  Input: "Found in EMA's official HMPC inventory as: Valerianae radix. This
  confirms the substance has been formally proposed/prioritized for EU
  herbal monograph assessment..."
  Output: "Regulatory / monograph evidence"
  ```

  `"Regulatory / monograph evidence"` is worth **20 points** in `_score_candidate()` — second only to clinical evidence (24), above preclinical (12). Since the evidence-text index is keyed by *plant* (and by every compound mentioned), this is not a narrow edge case: once a plant is found in EMA's inventory and that connector row is saved via the normal bulk-evidence-collection path (`multi_source_collector.py`'s `CONNECTOR_MAP["EMA/WHO/ESCOP Regulatory"]`), its text becomes part of the raw evidence pool for *every* compound/indication candidate for that plant, and can single-handedly lift a candidate from "No direct evidence" (0 pts) or "General literature" (7 pts) to "Regulatory / monograph evidence" (20 pts) — with real R&D_Opportunity_Score consequences.
- Same mechanism, second source: `SLEEP_TEA_EVIDENCE` (the curated seed data for the original sleep-tea plants) embeds literal `"EMA: ... WHO: ... ESCOP: ..."` status strings directly into the text pool used for scoring — so for those plants, curated regulatory status also contributes to score through this path, independent of the disabled `REGULATORY_DB` stub.
- **This is a real gap between stated design intent and actual behavior**, not a hypothetical. It doesn't require any fix from me right now — flagging it is the audit's job — but it's directly relevant to Section 3 below, since one architectural option there ("should regulatory status ever influence score") turns out to already be partially, accidentally true today through this side channel, rather than a clean yes/no you're choosing between.

**(c) Minor: Gold Case numbering gap.** There is no `gold_case_reference_grounded_002_*.py` anywhere in the repo — cases go 001, 003, 004, 005, 006, 007. I'm not assuming anything about why (deleted, renumbered, never created) — just flagging it since you referred to "Cases 001–007" as a continuous set and it isn't quite.

---

## 2. Per-authority feasibility audit

For each authority: (a) does a real, programmatic public source exist, (b) what would a connector need to do / effort, (c) honest "no" where that's the answer.

| Authority | Real programmatic source? | Assessment |
|---|---|---|
| **WHO** (monographs on medicinal plants) | **No.** | WHO's herbal monograph volumes exist only as published PDF/print volumes (WHO Monographs on Selected Medicinal Plants, Vols. 1–4). No API, no bulk machine-readable export, no structured database. Same category as the "not available" authorities you already have. Do not attempt to scrape the PDF volumes — even less structurally regular than EMA's inventory PDF. |
| **ESCOP** | **No.** | ESCOP monographs are a paid, subscription/print publication (the ESCOP Monographs book, 3rd ed. + supplements). No public API, no open bulk data, and licensing would likely prohibit programmatic scraping/redistribution even if a page existed. Documented "not available" is the only honest answer. |
| **FDA — botanical-specific status** | **No dedicated API; partial signal only.** | There is no FDA endpoint that answers "is this botanical a recognized dietary ingredient / does it have GRAS status / is it in an NDI notification." openFDA covers drug labels and adverse events (already connected, wrong question). FDA's actual NDI (New Dietary Ingredient) notification list and GRAS notice inventory exist as searchable web databases (FDA's own site), not documented public APIs — same PDF/HTML-scrape risk profile as EMA/MHRA. Effort to build even a fragile version: medium-high, and I'd recommend against it per your own stated principle (no scraping fragile sources). |
| **TGA (Australia)** | **Partial — worth a closer look, not a clean "yes."** | The Australian Register of Therapeutic Goods (ARTG) is primarily a web search interface, but TGA does publish downloadable bulk datasets (cancellations, suspensions, listings) as structured CSV/XML extracts under "Datasets" on tga.gov.au. This is a genuine structured bulk source, not a documented REST API — closer in spirit to what you already accepted for EMA (a real bulk document, not an API) than to a live lookup. Effort: medium — would need someone to verify current extract schema/coverage (does it cover "listed" complementary medicines specifically, with active ingredient granularity) before committing engineering time. I did not verify this deeply enough to promise it works; flagging as "possibly real, needs a spike" rather than "yes" or "no."|
| **Health Canada** | **Yes — this is the strongest option of the group.** | The Licensed Natural Health Products Database (LNHPD) has a genuine, documented, JSON/XML REST API at `https://health-products.canada.ca/api/natural-licences/`, updated daily, with per-ingredient granularity (I confirmed a live example: a query for `medicinalingredient` returns real per-product rows including `"ingredient_name": "Valeriana officinalis"` with potency/dose/source-material fields). This is materially different from every other "not available" authority — it's a real bulk, structured, machine-readable, officially documented API. |
| **MHRA (UK)** | **No API — a downloadable list, same shape as EMA.** | MHRA publishes "Herbal medicines granted a traditional herbal registration (THR)" as a document/PDF list on gov.uk, updated periodically, not a queryable API. This is the same category of source as the EMA HMPC inventory PDF (a real, official, bulk-downloadable document) — a THR connector is architecturally the same kind of build as `ema_regulatory_connector.py`: fetch the document, parse conservatively, report only what's reliably extractable (presence/absence of a THR registration by product name — matching to a *scientific name* would be lossier than EMA's case, since THR entries are branded product names, not pharmacopoeial Latin names). Effort: medium, with a lower ceiling on match quality than EMA's connector. |
| **Swissmedic (Switzerland)** | **No.** | Swissmedic's phytopharmaceutical/complementary-medicine authorisation data is web-search only (Swissmedic's own product database), no public API or bulk export identified. Same "not available" category. |
| **BfArM (Germany)** | **No — and largely historical anyway.** | The Kommission E monographs (1978–1994) are a closed historical corpus, not a live database; BfArM's current herbal work happens through the EU HMPC framework (already covered by your live EMA connector). No separate BfArM-specific API exists for herbal status. |
| **EFSA (Novel Food)** | **Partial — a real catalogue, unclear machine-readability.** | The EU Novel Food Status Catalogue (hosted by the European Commission, informed by EFSA/Member State input) is a real, authoritative, searchable web catalogue with per-substance novel-food determinations. Whether it exposes a documented bulk API vs. only a web search UI needs direct verification before committing to a build — I did not confirm a public API endpoint, only that the catalogue itself is real and authoritative. This is the *specific* source that would resolve the platform's existing "Novel Food" gap, so it's worth a dedicated spike even if the initial answer is "web-UI only, treat like MHRA/EMA."|

**Bottom line:** out of nine authorities, **one (Health Canada)** has a confirmed, genuine, documented bulk API worth building against immediately. **Two more (MHRA, and possibly TGA/EFSA)** have real structured bulk documents/datasets that could support an EMA-style conservative connector (fetch + report only what's reliably extractable), at medium effort and with the same "don't overclaim precision" discipline your EMA connector already models. **The rest (WHO, ESCOP, FDA botanical status, Swissmedic, BfArM) have no real programmatic source** — continuing to report them as "not available" is the correct, honest answer, and I'd recommend explicitly against scraping any of them.

---

## 3. Architectural decision — should regulatory status ever influence score? (your sign-off required)

I'm not deciding this. Two real options, with tradeoffs — and one complication from Section 1.2(b) that changes the shape of the decision.

**Option A — keep it strictly display-only (current stated intent).**
- Pro: keeps R&D_Opportunity_Score's meaning stable and auditable — a score change always traces to chemistry/evidence/product-fit/market signal, not to a connector that only covers one of nine authorities.
- Pro: avoids rewarding candidates simply for being *findable* in an inventory (EMA HMPC inventory presence means "proposed for assessment," not "approved" or "safe" or "commercially validated") — conflating "listed" with "good" would be a real scoring bug, not a feature.
- Con: as shown in 1.2(b), this is **not actually what happens today** — regulatory text already leaks into `Evidence_Level` scoring through the free-text index, worth up to 20 points, for any plant the EMA connector finds. "Keep it display-only" as a decision would require *also* fixing that leak (e.g., excluding `Source_Type == "Regulatory"` rows from `EVIDENCE_TEXT_INDEX_ALLOWLIST` concatenation, or from `_evidence_level()`'s regulatory-terms matching) — otherwise you'd be reaffirming a policy the code doesn't currently honor.

**Option B — make regulatory status a deliberate, small, explicit scoring input (replacing the accidental one).**
- Pro: if EMA HMPC inventory presence is a genuine (if narrow) positive market-viability signal, an explicit, bounded, well-documented weight is more honest and more auditable than the current accidental text-matching path — you'd know exactly which candidates got the bonus and why, instead of it depending on whether the word "monograph" happened to appear in concatenated Notes text.
- Con: still only covers ~1 of 9 authorities' worth of real signal (EMA), and even that signal is coarse (inventory presence ≠ monograph adopted ≠ traditional-use vs. well-established-use). A candidate for a plant with a *stronger* real regulatory story (e.g., actual UK THR registration) but no EMA inventory hit would score lower than a merely-proposed-for-assessment plant — a scoring bias that has nothing to do with R&D opportunity.
- Con: bigger design surface — would need real criteria (does "listed in inventory" deserve less than "adopted monograph"? does a `regulatory_barrier` finding subtract, on top of the existing hard gate?), which is a nontrivial redesign, not a small tweak.

**My honest read (not a recommendation dressed as one, per your ask):** the two options aren't symmetric right now — Option A is the one you already believe is in effect, but Section 1.2(b) shows it isn't cleanly true. So the immediate decision isn't really "A vs. B" — it's **"do you want A enforced (close the leak) or B designed (make it explicit)?"** Either is defensible; leaving it as-is (undocumented partial leak) is the one option I'd flag as not defensible, independent of which of A/B you prefer.

---

## 4. Proposed first REGULATORY_STATUS Gold Case (design only — no code)

Following `VALIDATION_PROTOCOL.md` v0.3 §14.1: `REGULATORY_STATUS` maps to its corresponding **engine gate individually** (`_hard_regulatory_gate` / `regulatory_barrier_classifier`), not to whole-case `Decision_Class_AH` agreement — so this case's expected outcome should be phrased as a gate-level assertion, not a decision-class assertion.

I found and verified two real candidates. I recommend Option 1 — it's stronger on every §6 Permitted-Sources criterion — but I'm presenting both rather than deciding for you.

### Option 1 (recommended): *Aristolochia* species — HMPC Public Statement, restriction

**Real, authoritative, source-locatable document:** *"Public Statement on the Risks Associated with the Use of Herbal Products Containing Aristolochia Species"*, Committee on Herbal Medicinal Products, **Doc. Ref. EMA/HMPC/138381/2005**, adopted by HMPC November 2005 (endorsing the HMPWP Position Paper of October 2000). I fetched and read this document directly. Section 2 states, verbatim: *"Use of Aristolochia species in herbal medicines is no longer permitted in many countries due to the toxicity of the aristolochic acid constituents, which have been shown to be nephrotoxic, carcinogenic and mutagenic."*

**Why this is the stronger candidate:**
- **`source_type = EMA_HMPC`** — no open precedence-table question. This is the *same* source_type your live connector already reads and the only one present in all five domain hierarchies (§6 of the protocol names it as the mechanically-preferred choice).
- It is a genuine **restriction/prohibition** claim (not a market-access technicality like Novel Food), a real historical case where herbal use was withdrawn across multiple EU markets for a documented toxicological reason — exactly the shape of finding `_hard_regulatory_gate`'s `"Prohibited / banned"` category exists to catch.
- Real `source_locator`: Section 2, EMA/HMPC/138381/2005, dated 23 November 2005 — precise enough for `VALIDATION_PROTOCOL.md` §8's traceability requirement.

**Proposed shape:**
- `ReferenceDomain.REGULATORY_STATUS`, `AssertionType.RESTRICTION`, `AssertionState.PRESENT`
- `evidence_text.transformation_type = VERBATIM` (the Section 2 excerpt above)
- Reference `source_type = EMA_HMPC`, `reference_id` = the document reference number, `source_locator` = "Section 2"

**A finding I want to flag rather than quietly smooth over:** the real document's phrasing is *"no longer permitted"* — `regulatory_barrier_classifier.py`'s `"Prohibited / banned"` phrase list is `["banned", "prohibited", "illegal in", "not permitted for sale", "outlawed"]`. **"No longer permitted" does not literal-match any of those phrases.** So if this case's `EngineEvidenceInput.notes` used the document's actual verbatim wording, the classifier would currently **miss** it — `regulatory_barrier_types` would come back empty, and `_hard_regulatory_gate` would return `PASSED`, not `FAILED`. That's not a flaw in my case design; it's a real, honest gap the case would correctly expose in the classifier's phrase coverage. I think this is actually a *better* first case than a softball — it tells you something true about the classifier rather than confirming what you already assumed — but it means the case's "expected outcome" should document **both** what a human curator reading the source would conclude (a real restriction exists) **and** what the current classifier actually returns (gate passes, because "no longer permitted" isn't in its phrase list) — and that gap itself may be worth a small, separate, explicitly-approved fix to `_BARRIER_TYPES`'s phrase list, not folded silently into this validation case.

### Option 2: Cannabis sativa L. (cannabinoid extracts) — EU Novel Food status

**Real source:** the EU Novel Food Status Catalogue's cannabinoid entry (European Commission, EFSA-informed), documenting that cannabinoid extracts require pre-market authorisation under Regulation (EU) 2015/2283.

**Why it's the weaker choice:**
- `reference_precedence.py`'s REGULATORY_STATUS hierarchy (`NATIONAL_REGULATORY`, `EMA_HMPC`, `OTHER_NATIONAL_REGULATORY`) has no `source_type` specifically for an EU Novel Food Catalogue determination — it would likely resolve to `OTHER_NATIONAL_REGULATORY`, but that's a naming/precedence call I shouldn't make unilaterally (§6/§7: an unmatched `source_type` resolves to `INSUFFICIENT_METADATA` and the case can't lock).
- Separately, `"Novel food / pre-market approval required"` is a real category in the barrier classifier, but (per §1.1) it does **not** trigger `GateStatus.FAILED` today — only `"Prohibited / banned"` does. So this case would validate detection/reporting only, not the hard exclusion — a materially different (weaker) claim than Option 1.

Still worth keeping on record as the case that would exercise the Novel Food path specifically, if you'd rather validate that path first — just flagging that it comes with an open precedence-table question Option 1 doesn't have.

---

## 5. Five proposed features — feasibility and ranked value (honest assessment, not agreement)

| Feature | Feasible with real data? | Data availability | Implementation effort | Actual decision value to an R&D user |
|---|---|---|---|---|
| **1. Automatic cross-country regulatory status comparison** | Partially. | Low — only EMA (live) + Health Canada (live) + maybe MHRA/TGA would be real; the other 5 authorities stay "not available," so a "comparison" table would be mostly gaps. | Medium — mostly UI/aggregation work once individual connectors exist. | **Medium.** Useful once ≥3 real sources exist, but built now it would visually overstate coverage (a table with 6 of 9 columns saying "not available" looks like a broken feature, not a comparison). Sequence this *after* at least Health Canada + one more connector ship. |
| **2. Dose-limit / safety-warning / contraindication alerts** | Yes, but this is a different data problem than "regulatory status" — it needs pharmacovigilance/monograph safety text (EMA HMPC monographs' own "Contraindications"/"Posology" sections, LiverTox, FAERS — several of which you already have connectors for), not the inventory-presence data this proposal is about. | Medium-high — EMA monograph *safety sections* are separate PDFs per substance, not the bulk inventory PDF; would need per-substance fetching, much higher effort than the inventory connector. | High. | **High** — genuinely the most decision-relevant of the five for an R&D user (this is safety-critical, not just informational), but it's a bigger, separate build, not a natural extension of the regulatory-status connectors discussed above. Don't conflate it with this proposal's scope. |
| **3. Health-claim usability check per market** | Partially. | Low-medium — EU has a real, structured source (the EU Health Claims Register, a genuine EFSA-vetted public database of authorised claims) which is a strong candidate; other markets (US structure/function claims, UK) are messier legal categories without a clean database. | Medium for EU only; high for multi-market. | **Medium-high** for EU specifically (this is one of the few "regulatory" features with a genuinely authoritative, queryable source) — I'd rank the EU Health Claims Register as a stronger next-connector candidate than several of the ones discussed above, worth a separate proposal if you're interested. |
| **4. Regulatory/monograph change monitoring** | Yes, mechanically simple — diff the EMA inventory PDF (or Health Canada API) between runs. | High for the two live sources; N/A for the rest. | Low — you already fetch the inventory each run; persisting a snapshot and diffing is a small addition. | **Low-medium** — nice-to-have, low decision value on its own (an R&D user cares about *current* status far more than *change history* at MVP stage), but very cheap to build once the base connector exists. Good "free" addition, not a priority in itself. |
| **5. Regulatory-Affairs-ready report generation** | Yes, as an output-formatting task, not a new data source. | N/A — this consumes existing data, doesn't need new connectors. | Low-medium — mostly reuses `pharma_report_generator.py`'s existing patterns and the `REGULATORY_INTELLIGENCE_LIMITATIONS` disclosures already written. | **Low**, honestly, at current data coverage — a "Regulatory-Affairs-ready" report built on 1-of-9 live authorities plus "not available" for the rest would need very careful framing to avoid implying more coverage than exists, and a real Regulatory Affairs professional would likely still need to do the actual multi-jurisdiction work by hand. Higher value once features 1/3 above mature; premature now. |

**Honest overall ranking by "build this next":** Health-claim register (3, EU) and closing the score-leakage gap (§1.2b) are the two things I'd actually prioritize over any of these five as currently scoped. Of the five, only #4 (change monitoring) is cheap enough to bundle into the next connector work; the rest deserve their own sequencing decisions rather than being treated as one bundle of "5 good ideas."

---

## Summary of decisions I need from you before building anything
1. Section 1.2(b): close the score-leakage (Option A enforcement) vs. design it as an explicit scored input (Option B) vs. leave as-is (not recommended).
2. Section 4: which REGULATORY_STATUS gold-case candidate to build — *Aristolochia*/EMA_HMPC restriction (recommended, verified, no open precedence question) or Cannabis/Novel-Food (needs a `source_type` precedence decision, and only validates detection, not the hard gate).
3. Section 4: if you pick *Aristolochia*, whether to also approve a small, separate fix adding "no longer permitted" (and similar phrasing) to `regulatory_barrier_classifier.py`'s `"Prohibited / banned"` phrase list — since the document's real wording currently wouldn't trigger the hard gate as-is.
4. Section 2: whether Health Canada's LNHPD API is worth building as the next connector (my recommendation, but flagging it as a recommendation, not a decision).
