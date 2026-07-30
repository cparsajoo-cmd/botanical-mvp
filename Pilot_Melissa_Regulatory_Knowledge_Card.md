# Pilot Demo — Regulatory Knowledge Card, Melissa officinalis L., folium

Prepared by: implementation engineer (Claude) · For: Hamid (architecture reviewer)
Status: DEMONSTRATION OF DESIGN OUTPUT ONLY — this is what the proposed Layer 1 connector's parsed record would look like, hand-verified against the real source below. No parsing code has been written; I extracted this manually to validate the schema and the section-based approach before either of us commits engineering time to it.

**Real source document:** *Community herbal monograph on Melissa officinalis L., folium*, Committee on Herbal Medicinal Products (HMPC), **Doc. Ref. EMA/HMPC/196745/2012**, adopted 14 May 2013, "Final."
**URL:** `https://www.ema.europa.eu/en/documents/herbal-monograph/final-community-herbal-monograph-melissa-officinalis-l-folium_en.pdf`
**Reproduction basis:** the source document itself states *"Reproduction is authorised provided the source is acknowledged"* — the text below is quoted directly for this reason; a real Regulatory Affairs record needs the exact regulatory wording, not a paraphrase (paraphrasing a contraindication or dose would be actively wrong for this use case).

---

## Extracted record

```
Scientific_Name:              Melissa officinalis L.
Plant_Part:                   folium (leaf)
Common_Name (EN):             Melissa leaf
Monograph_Reference_Number:   EMA/HMPC/196745/2012
Monograph_Status:             Final
Monograph_Adoption_Date:      2013-05-14
Monograph_URL:                [source URL above]
```

### 4.1 — Therapeutic Indications

- **Well-established use:** *(not applicable — see note below)*
- **Traditional use:**
  - "Traditional herbal medicinal product for relief of mild symptoms of mental stress and to aid sleep."
  - "Traditional herbal medicinal product for symptomatic treatment of mild gastrointestinal complaints including bloating and flatulence."
  - *(Explicit qualifier in source: "based upon long-standing use" only — not clinical evidence.)*

### 4.2 — Posology and Method of Administration

- **Traditional use** (adolescents >12, adults, elderly — under-12s not recommended):
  - Herbal tea: 1.5–4.5 g comminuted herb / 150 ml boiling water, 1–3×/day
  - Powdered herb: 0.19–0.55 g, 2–3×/day
  - Liquid extract: 2–4 ml, 1–3×/day
  - Tincture: 2–6 ml, 1–3×/day
  - **Duration of use:** if symptoms persist beyond 2 weeks, consult a doctor
  - **Route:** oral

### 4.3 — Contraindications

- "Hypersensitivity to the active substance."

### 4.4 — Special Warnings and Precautions

- Use in children under 12 not established (insufficient data)
- If symptoms worsen, consult a doctor
- Ethanol-containing preparations require standard ethanol excipient labelling

### 4.5 — Interactions

- "No data available."

### 4.6 — Fertility, Pregnancy and Lactation

- "Safety during pregnancy and lactation has not been established. In the absence of sufficient data, the use during pregnancy and lactation is not recommended."
- "No fertility data available."

### 4.7 — Effects on Driving/Machine Use

- "May impair ability to drive and use machines. Affected patients should not drive or operate machinery."

### 4.8 — Undesirable Effects

- "None known." (If reactions occur, consult a doctor.)

### 4.9 — Overdose

- "No case of overdose has been reported."

---

## What this pilot confirms about the parsing approach

1. **Numbered section headers extract cleanly.** Every section (4.1 through 4.9) appears with an exact, consistent numeric heading in the real document text — a simple, reliable anchor for automated section-splitting. This is a real, positive confirmation of the Layer 1 proposal's core assumption.

2. **A real-world case the schema needs to handle gracefully: the well-established-use column can be entirely empty.** For Melissa officinalis, *every single clinical section* has no "Well-established use" content at all — this monograph is pure traditional-use. My original schema design implicitly assumed both columns would usually have content with occasional gaps; this pilot shows "WEU entirely absent" is a common, not edge, case (many HMPC monographs are traditional-use-only). **Correction to the Layer 1 proposal:** `Therapeutic_Indications_WEU` and its siblings should default to an explicit `"Not applicable — no well-established-use data in this monograph"` state, distinguished from `"present but not reliably extracted"` — these are two different failure/absence modes and conflating them would misrepresent regulatory status (an empty WEU column is a real regulatory fact, not a parsing failure).

3. **Section 4.7 ("Effects on ability to drive and use machines") exists in the real document and wasn't in my original proposed field list.** Minor addition needed to the schema — flagging rather than silently patching it in.

4. **This card is exactly the kind of content that must never re-enter the scoring free-text pool** (per the Layer 1 proposal §4 hard rule) — notice how much of this reads like clinical/safety language ("may impair ability to drive," "hypersensitivity," "not recommended during pregnancy"). If this got concatenated into `_evidence_level()`'s text index the way the current connector's short notes already do, it would very likely misclassify as strong clinical/safety evidence for a signal that's actually "traditional use only, no clinical data." This pilot makes the leakage risk concrete rather than theoretical.

---

## What I'm NOT proposing to do yet

I have not written any parsing code, and this record was built by me reading the PDF directly — not by a script. The next step, if you approve this shape, is to decide whether to (a) write an actual PDF section-parser against this and a few more real documents before trusting it at scale, or (b) keep building 2–3 more pilot records by hand first to see how much the section structure varies across monographs (combination monographs, WEU-heavy monographs like *Ginkgo biloba*, etc.) before writing any parsing code at all.

---

## Ready for your call

If this record's shape and the two corrections above (§ "What this pilot confirms," points 2–3) look right to you, I'll move to **Option 1**: verifying the real monograph URLs and adoption status for the remaining 9 plants (*Valeriana officinalis, Passiflora incarnata, Matricaria chamomilla, Lavandula angustifolia, Humulus lupulus, Tilia cordata, Cimicifuga racemosa, Hypericum perforatum, Ginkgo biloba*), flagging complications like Valeriana's combination monograph as they come up — the same way I did here, not silently.
