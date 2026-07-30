# Layer 1 Proposal — EMA/HMPC Per-Substance Monograph Connector

Prepared by: implementation engineer (Claude) · For: Hamid (architecture reviewer)
Status: PROPOSAL ONLY — no production code touched. This extends the prior "Regulatory Connectors" proposal's Layer 1. Everything below is a design for you to approve/amend before I write a single line of implementation.

---

## 1. What this connector would add, precisely

Today, `ema_regulatory_connector.py` answers one question: *"is this taxon present in EMA's inventory of substances proposed for assessment?"* — a coarse, single-bit signal, deliberately limited because the **inventory PDF** is a multi-column table that can't be reliably parsed.

This proposal is a **separate, second connector** targeting a structurally different document: the **per-substance "European Union herbal monograph"** PDF (one per taxon/plant-part, once adopted). I fetched and read several real examples (*Matricaria recutita* flos, *Tanacetum parthenium* herba, *Achillea millefolium* flos) to confirm their structure before proposing anything. Unlike the inventory table, these follow a **standardized, SmPC-style numbered section format**:

```
4.1  Therapeutic indications
4.2  Posology and method of administration
4.3  Contraindications
4.4  Special warnings and precautions for use
4.5  Interaction with other medicinal products and other forms of interaction
4.6  Fertility, pregnancy and lactation
4.8  Undesirable effects
4.9  Overdose
```

This is genuinely more machine-extractable than the inventory table — the same reasoning that made `ema_regulatory_connector.py` viable applies here, just to a different document shape. It is **not** comparable to WHO/ESCOP (no document exists there at all) or to fabricating structured data.

---

## 2. The two real problems to solve — and my proposed answer for each

### Problem A: finding the right PDF URL for a given taxon

There is no reliable bulk index (the existing connector's own docstring already established that EMA's monograph browse page is JS-rendered, not fetchable). I see three options:

| Option | What it is | Honest assessment |
|---|---|---|
| **A1 — small curated URL registry** (recommended for the pilot) | A hand-verified mapping of `scientific_name → monograph PDF URL(s)`, built by a human (you or me, with your review) checking each real URL, starting only with the plants already in this platform's Gold Cases and seed data. | Bounded, honest, verifiable — **this stores only a pointer to a real document, not a fabricated status value**, so it does not repeat the `REGULATORY_DB` mistake. Same shape as `US_UK_PLANT_REGULATORY_STATUS`'s curation discipline, but even lower-risk since there's no interpretive judgment involved, just a URL. Effort: low per plant, scales linearly — realistic for ~10-15 plants, not realistic by hand for all ~150+ HMPC substances. |
| A2 — programmatic discovery via EMA search/sitemap | Try to script discovery of monograph URLs at scale. | I did not find a reliable, bulk, machine-readable index during this review — would likely mean scraping a JS-rendered page (the exact fragility your EMA connector's docstring already rejected for the inventory data). Not recommended now; could revisit later if EMA exposes a real index. |
| A3 — combination | Curated registry (A1) for the pilot set, with a documented process for adding entries one at a time as new plants are needed. | This is really A1 with a growth path, not a separate option — I'd frame it this way rather than as "A3." |

**My recommendation: A1**, scoped to the plants your platform already has curated evidence for — these are also the plants where a wrong or missing regulatory answer would be most visible/costly, so they're the right pilot set:

*Melissa officinalis, Valeriana officinalis, Passiflora incarnata, Matricaria chamomilla/recutita, Lavandula angustifolia, Humulus lupulus, Tilia cordata* (from `seed_data.SLEEP_TEA_EVIDENCE`), plus *Cimicifuga racemosa, Hypericum perforatum, Ginkgo biloba* (from your existing Gold Cases).

### Problem B: multiple monographs per taxon, and the well-established-use / traditional-use split

Real monographs are **not one-per-plant** — e.g. *Matricaria recutita* has separate monographs for *flos* (flower) and *aetheroleum* (essential oil), each with its own indications/posology. And within a single monograph, most sections are split into two columns: "Well-established use" and "Traditional use" — each can have different indications/posology/contraindications.

**Proposal:** key every record by `(Scientific_Name, Plant_Part, Preparation)` — the same granularity your `ValidationUnit`/Gold Case structure already uses for `PREPARATION_SPEC` (Case 007's `taxon` + `plant_part` + `PreparationSpec`). Within a record, keep well-established-use and traditional-use text **separate, never merged** — merging them would silently misrepresent which regulatory pathway a given indication/dose belongs to, which matters a great deal for an R&D/regulatory-affairs user. If the two-column split isn't reliably recoverable from a given PDF's text extraction (same risk class as the inventory PDF's column problem), the connector should report the **combined section text with an explicit "well-established/traditional split not reliably extracted for this document" flag** — never guess which column a sentence belongs to.

Also: only fetch **final, adopted** monographs, never drafts — track `Monograph_Status` and `Monograph_Reference_Number`/date explicitly so staleness is visible.

---

## 3. Proposed output shape (fields, not code)

One record per `(Scientific_Name, Plant_Part, Preparation)`:

- `Scientific_Name`, `Plant_Part`, `Preparation`
- `Monograph_Reference_Number` (e.g. `EMA/HMPC/55843/2011`), `Monograph_Status` ("Final"/etc.), `Monograph_Adoption_Date`
- `Monograph_URL` (the real source PDF — always shown to the user)
- `Therapeutic_Indications_WEU` / `Therapeutic_Indications_TU` (well-established-use / traditional-use, kept separate; combined+flagged if split not extractable)
- `Posology_WEU` / `Posology_TU`
- `Contraindications`, `Special_Warnings`, `Interactions`, `Pregnancy_Lactation`, `Undesirable_Effects`, `Overdose` — each following the same WEU/TU separation where the source itself separates them, combined+flagged otherwise
- `Extraction_Confidence` — per-section, not just per-document: some sections may extract cleanly while others (e.g. long multi-paragraph interaction text) may not. A single document-level confidence score would hide exactly the kind of partial failure your EMA inventory connector's docstring already warned against overclaiming.
- `Source_Type = "Regulatory Monograph"` — **deliberately a new, distinct `Source_Type`, not `"Regulatory"`** (the existing bulk-inventory connector's type). Keeping them distinct is what makes the next decision (Section 4) possible to apply cleanly.

---

## 4. The scoring/leakage question this connector inherits — needs your decision before I build anything

This is the most important open item, and it follows directly from the score-leakage finding in the prior proposal (§1.2b): `EMA_Status`/`Regulatory_Status`/`Notes` from the existing connector already leak into `_evidence_level()`'s free-text scoring pool via `EVIDENCE_TEXT_INDEX_ALLOWLIST`, worth up to 20 points.

This new connector would produce **far richer, more clinical-sounding text** (contraindications, posology, undesirable effects) than the existing connector's short "listed in inventory" notes. If these new fields were added to `EVIDENCE_TEXT_INDEX_ALLOWLIST` the same way, the leak identified earlier would get substantially worse — e.g., `Undesirable_Effects` text could trigger `evidence_extractor`'s safety-flag detection, and `Posology`/`Contraindications` text could trigger `Regulatory_Status`/clinical-term matches in ways that are much harder to predict than the current one-line connector notes.

**My recommendation:** these new fields should be written to their own table/path, **explicitly excluded** from `EVIDENCE_TEXT_INDEX_ALLOWLIST` and from any free-text index that feeds `_evidence_level()`, `classify_evidence_hierarchy()`, or `classify_negative_evidence()` — full stop, regardless of which way you decide the earlier Option A/B question. This connector's job is to answer a Regulatory Affairs question, not to silently become a second, richer source of scoring leakage. If you later *want* monograph-derived contraindications to influence the Hard Safety Gate deliberately, that should be its own explicit, reviewed decision (structured field → structured gate input, the same "never natural-text-into-gate" principle you set as a hard line early in this review) — not an accidental byproduct of adding columns to an allowlist.

---

## 5. Sequencing / effort estimate

1. **Pilot, 10 plants (the list in §2, Option A1):** build the URL registry (manual, reviewed by you), build the section-parser (regex on numbered headers + WEU/TU column detection), wire output to a new, scoring-isolated table. This is the unit I'd propose actually implementing first, once approved.
2. **Expand registry** to more plants only as your Gold Case / candidate database actually needs them — no reason to front-load coverage for plants nobody is evaluating yet.
3. **UI/display integration** (showing this in `Plant_Profile.py` / reports) — separate, smaller follow-on step after the data exists and you've reviewed a few real outputs for accuracy.

I have **not** started building any of this. Confirming before I write code:

## Decisions needed from you
1. Approve the pilot plant list (§2) and the URL-registry approach (A1) — or tell me which plants/approach you'd rather start with.
2. Approve keeping the well-established-use / traditional-use split as separate fields, never merged (§2, Problem B).
3. **Approve the scoring-isolation rule in §4** — this is the one I'd consider closest to a hard requirement rather than a preference, given what we already found in the existing connector.
4. Confirm whether you want me to draft the actual URL registry (i.e., go find and verify the real monograph PDF URLs for the 10 pilot plants) as the next concrete step, or whether you want to review this design further first.
