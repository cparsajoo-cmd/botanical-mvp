# Verified Monograph Registry — 10 Pilot Plants

Prepared by: implementation engineer (Claude) · For: Hamid (architecture reviewer)
Status: Research complete for all 10 plants. Every entry below was verified by search + direct document fetch, not guessed. This is the input the Layer 1 connector code would use — but it surfaces a structural issue (below) that needs a decision before I start writing the parser.

---

## 1. Confirmed registry — standalone, single-substance monographs

| # | Scientific Name | Plant Part | Monograph Ref. | Status | Adopted | URL |
|---|---|---|---|---|---|---|
| 1 | *Melissa officinalis* L. | folium | `EMA/HMPC/196745/2012` | Final | 2013-05-14 | `.../final-community-herbal-monograph-melissa-officinalis-l-folium_en.pdf` |
| 2 | *Valeriana officinalis* L. | radix | `EMA/HMPC/150848/2015, Corr.1` | Final | 2016-02-02 | `.../final-european-union-herbal-monograph-valeriana-officinalis-l-radix_en.pdf` |
| 3 | *Passiflora incarnata* L. | herba | `EMA/HMPC/669740/2013` ✅ *(corrected — see note)* | Final | 2014-03-25 | `.../final-community-herbal-monograph-passiflora-incarnata-l-herba_en.pdf` |
| 4 | *Matricaria recutita* L. *(syn. Matricaria chamomilla — see note)* | flos | `EMA/HMPC/55843/2011` | Final | 2015-07-07 | `.../final-european-union-herbal-monograph-matricaria-recutita-l-flos_en.pdf` |
| 5a | *Lavandula angustifolia* Mill. | flos | `EMA/HMPC/734125/2010` | Final | 2012-03-27 | `.../final-community-herbal-monograph-lavandula-angustifolia-p-mill-flos_en.pdf` |
| 5b | *Lavandula angustifolia* Mill. | aetheroleum | `EMA/HMPC/143181/2010` | Final | 2012-03-27 | `.../final-community-herbal-monograph-lavandula-angustifolia-miller-aetheroleum_en.pdf` |
| 6 | *Humulus lupulus* L. | flos | `EMA/HMPC/682384/2013` | Final (revised) | 2014-05-06 | `.../final-community-herbal-monograph-humulus-lupulus-l-flos_en.pdf` |
| 7 | *Tilia cordata* Mill., *T. platyphyllos* Scop., *T. × vulgaris* Heyne, or mixtures | flos | `EMA/HMPC/337066/2011` | Final | 2012-05-22 | `.../final-community-herbal-monograph-tilia-cordata-miller-tilia-platyphyllos-scop-tilia-x-vulgaris-heyne_en.pdf` |
| 8 | *Cimicifuga racemosa* (L.) Nutt. | rhizoma | `EMA/HMPC/48745/2017` ⚠️ *(corrected — see note)* | Final, Rev. 1 | 2018-03-27 | `.../final-european-union-herbal-monograph-cimicifuga-racemosa-l-nutt-rhizome-revision-1_en.pdf` |
| 9 | *Hypericum perforatum* L. | herba | `EMA/HMPC/7695/2021, Rev.1` | Final (unified WEU+TU) | 2022-11-23 | `.../final-european-union-herbal-monograph-hypericum-perforatum-l-herba-revision-1_en.pdf` |
| 10 | *Ginkgo biloba* L. | folium | `EMA/HMPC/321097/2012` | Final | 2015-01-28 | `.../final-european-union-herbal-monograph-ginkgo-biloba-l-folium_en.pdf` |

**All 10 (11 counting Lavandula's two parts) are now fully verified** — every URL and reference number above was confirmed by directly fetching the document itself, not inferred from a citation or search snippet.

**Note on #3 (Passiflora) — a correction that validates the "flag, don't guess" discipline:** my first pass inferred the monograph reference as `669738` from an adjacent document's numbering pattern, and flagged it as unconfirmed rather than presenting it as solid. I then fetched the monograph PDF directly: the real reference is `EMA/HMPC/669740/2013` — my inference was wrong (669738 turned out to be the *assessment report's* number, a different document). This is exactly the failure mode the flag was meant to catch, and it did.

**Note on #8 (Cimicifuga) — a real correction, not just a caveat:** the number I originally listed, `EMA/HMPC/600717/2007` (adopted Nov 2010), is a **superseded** version. There is a newer revised final monograph, `EMA/HMPC/48745/2017`, adopted 27 March 2018, which explicitly replaces the 2010 one. This is directly relevant to your existing Gold Case 005 (Cimicifuga racemosa) — worth checking separately whether that case cites the current or the superseded monograph.

**Note on #4 (Matricaria):** your `seed_data.py` uses **"Matricaria chamomilla"**; EMA's own nomenclature is **"Matricaria recutita"** (synonyms for the same species). The connector's plant-name matching will need to handle this explicitly, or candidates keyed to "Matricaria chamomilla" won't match this registry entry.

---

## 2. Structural complication found — needs a scope decision before coding

While researching, I found that **several of these 10 plants also have separate combination monographs** covering 2+ of the pilot plants together — these are real, adopted (or in-progress) EMA/HMPC documents, not something I'm proposing to invent:

| Combination monograph | Plants involved (from our pilot list) | Status |
|---|---|---|
| *Valeriana officinalis*, radix **and** *Humulus lupulus*, flos | #2 + #6 | Final, `EMA/HMPC/327107/2017` (revision 1) |
| *Valerianae radix* **and** *Passiflorae herba* | #2 + #3 | Still in development — "ongoing call for scientific data," not yet a monograph |
| **"Species sedativae"** — herbal tea combinations of 2–4 substances from: *Valeriana, Melissa, Humulus, Lavandula, Passiflora* | #1 + #2 + #3 + #5 + #6 (up to 5 plants in one document) | Final, `EMA/HMPC/438183/2017` |
| *Hypericum perforatum*, herba **and** *Cimicifuga racemosa*, rhizoma | #8 + #9 | Still in development — draft assessment report stage as of 2025, not yet a final monograph |

**Why this matters for the Layer 1 design:** my original proposal implicitly assumed "one connector record per single-substance monograph." That's still correct as the primary unit, but it's now clear that a meaningful fraction of real-world regulatory content for exactly this pilot set lives in *combination* monographs — and those combinations aren't arbitrary, they're the actual traditional "sedative tea" combinations your sleep-tea evidence data already models. Two ways to handle this, and I don't think I should pick unilaterally:

**Option A — standalone monographs only for v1 pilot.** Build the connector against the 10 (really 11, counting Lavandula's two parts) standalone entries in §1 only. Explicitly document combination monographs as **out of scope** for this pass — a known, named gap, not a silent one. Simpler, ships faster, still covers the core R&D question ("does this single plant have a monograph, and what does it say").

**Option B — include combination monographs as a second, distinct record type.** Model them separately (they answer a different question — "is this combination specifically recognized," not "is this plant recognized") linked to the relevant standalone plant records. More complete, meaningfully more valuable given your sleep-tea evidence already involves plant *combinations*, but real added design and parsing work (combination monographs have different composition tables — e.g. "Species sedativae"'s percentage-range table across 5 plants).

**Decision confirmed by Hamid: Option B** — combination monographs will be modeled as a second, distinct record type, linked to the relevant standalone plant records.

## Combination monographs to include (verified references)

| Combination monograph | Plants | Ref. | Status |
|---|---|---|---|
| *Valeriana officinalis*, radix + *Humulus lupulus*, flos | #2 + #6 | `EMA/HMPC/327107/2017` (Rev. 1) | Final |
| "Species sedativae" (2–4-substance sedative tea combinations) | #1, #2, #3, #5, #6 | `EMA/HMPC/438183/2017` | Final |
| *Valerianae radix* + *Passiflorae herba* | #2 + #3 | — | Not yet adopted (ongoing call for data) — exclude for now, note as pending |
| *Hypericum perforatum*, herba + *Cimicifuga racemosa*, rhizoma | #8 + #9 | `EMA/HMPC/884573/2022` (draft) | Draft, not final — exclude for now, note as pending |

Two of the four combination monographs are still in development, not adopted — those should be tracked as "pending" (a real, honest status) rather than skipped silently, but obviously can't be parsed as final content yet.

## All research is now complete. Ready to write code.

Both single-substance (§1) and combination (above) registries are fully verified. Next step is the actual parser + connector implementation against this data.
