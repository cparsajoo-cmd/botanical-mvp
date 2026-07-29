# Case 006 — Source Suitability Screening

Status: DRAFT screening only. No Gold Case, test, or Engine Evidence created.
Protocol version referenced: `VALIDATION_PROTOCOL.md` v0.3.
Repository materials inspected (read-only): `VALIDATION_PROTOCOL.md`, `VALIDATION_CASE_TEMPLATE.md`, `gold_case_reference_grounded_001_melissa_officinalis.py`, `_003_matricaria_chamomilla.py`, `_004_ginkgo_biloba.py`, `_005_cimicifuga_racemosa.py`, `assertion_vocabulary.py`, `applicability_check.py`, `reference_precedence.py`. No prior source-suitability screening record exists in the repository (Case 006 is the first).

---

## 1. Existing coverage (Cases 001–005 — note: no Case 002 file exists)

All four existing cases share the same domain and assertion type:

| Case | Taxon | Domain | Assertion type | Subject | Assertion state | Source type |
|---|---|---|---|---|---|---|
| 001 | Melissa officinalis | Indication/Evidence | Supports indication | sleep | PRESENT | EMA_HMPC |
| 003 | Matricaria chamomilla | Indication/Evidence | Supports indication | sleep | CONDITIONAL | SYSTEMATIC_REVIEW |
| 004 | Ginkgo biloba | Indication/Evidence | Supports indication | cognitive impairment | ABSENT | SYSTEMATIC_REVIEW |
| 005 | Cimicifuga racemosa | Indication/Evidence | Supports indication | menopausal symptoms | INSUFFICIENT | SYSTEMATIC_REVIEW |

Gaps: `ReferenceDomain.SAFETY`, `IDENTITY_QUALITY`, `REGULATORY_STATUS`, `PREPARATION_SPEC` are entirely untested. `AssertionType` values other than `SUPPORTS_INDICATION` are untested. `AssertionState.NOT_STATED` is untested. No case has produced a `SELECTED` `SAFETY`/`SERIOUS`/`PRESENT` outcome, so `safety_serious_false_negative_rate` (Protocol §10) has presumably never left `NOT_COMPUTABLE` across the existing suite.

## 2. Candidate-source ranking table (proposed domain: SAFETY)

| Rank (SAFETY fallback order) | Source type | Document | Accessibility | Status this pass |
|---|---|---|---|---|
| 1 | EMA_HMPC | EU herbal monograph, *Hypericum perforatum L., herba*, Final Rev. 1, EMA/HMPC/7695/2021, adopted 23 Nov 2022 | Full text PDF, public, no paywall | **VERIFIED — fetched in full** |
| 2 | WHO_MONOGRAPH | WHO monograph on *Hypericum perforatum* (WHO Monographs on Selected Medicinal Plants) | Not fetched | **UNVERIFIED — presumed to exist, not confirmed this pass** |
| 3 | ESCOP_MONOGRAPH | ESCOP monograph, *Hyperici herba* | Not fetched | **UNVERIFIED — presumed to exist, not confirmed this pass** |
| 4 | COMMISSION_E | Commission E monograph, St. John's Wort | Not fetched | **UNVERIFIED — presumed to exist, not confirmed this pass** |
| — | Not a permitted `source_type` | EMEA "Public Statement" on antiretroviral interactions (2000) | Public, fetched (snippet only) | **NON-PERMITTED** — a public-statement/news item, not a monograph; excluded per Protocol §7. Supporting context only, not usable as `ReferenceDescriptor.source_type`. |

Only one focused search pass + one document fetch was run, per Search Discipline. Ranks 2–4 are named because they are the documented SAFETY fallback-rank sources (`reference_precedence.py`), not because their content was checked.

## 3. Screening fields

1. **Taxon / synonyms:** *Hypericum perforatum* L. Common name: St. John's wort. (Additional Latin synonyms exist in general botanical literature; none were re-verified this pass — **UNVERIFIED**, low consequence since the monograph itself uses the accepted name.)
2. **Plant part:** Herba (aerial flowering parts) — directly stated in the monograph's own title ("Hypericum perforatum L., herba").
3. **Proposed domain:** `ReferenceDomain.SAFETY`.
4. **Proposed assertion type:** `AssertionType.CONTRAINDICATION`.
5. **Proposed subject:** concomitant use with CYP3A4/CYP2B6/CYP2C9/CYP2C19- or P-glycoprotein-affected medicinal products (e.g., coumarin anticoagulants, calcineurin inhibitors/mTOR inhibitors used in transplantation, protease inhibitors and NRTIs, irinotecan, imatinib).
6. **Population / preparation / route / jurisdiction:**
   - *Governing-source-supported:* jurisdiction = EU; route = Oral; well-established-use (WEU) posology population = "Adults and elderly"; preparation family = WEU dry/liquid extracts (a–c in the monograph).
   - *ValidationUnit target metadata (proposed only, not yet decided):* mirror the above — Adults and elderly / Oral / EU — pending the preparation choice in item 14 below.
   - *Unresolved/unavailable:* exact hyperforin mg/day content per specific WEU preparation is not stated in the monograph itself (it references a separate Assessment Report, EMA/HMPC/244315/2016, ch. 5.5.4, not fetched this pass) — **UNVERIFIED**.
7. **Candidate governing source:** EU herbal monograph on *Hypericum perforatum* L., herba — Final, Revision 1, EMA/HMPC/7695/2021 (23 Nov 2022). `source_type = "EMA_HMPC"`.
8. **Accessibility:** Full text, freely accessible PDF at ema.europa.eu; fetched in full this pass. No paywall.
9. **Exact relevant source conclusion (Section 4.3, Contraindications, well-established-use column):** the monograph states that, in addition to hypersensitivity, concomitant use with coumarin-type anticoagulants, cyclosporine, everolimus, sirolimus, tacrolimus (systemic), fosamprenavir, indinavir and other protease inhibitors, nucleoside reverse transcriptase inhibitors, irinotecan, imatinib, and other CYP3A4/CYP2B6/CYP2C9/CYP2C19-metabolized or P-glycoprotein-transported cytostatic agents is a contraindication (paraphrased here; verbatim excerpt to be pulled directly from the PDF at claim-extraction time, not from this screening doc).
10. **Proposed `AssertionState`:** `PRESENT` — the source states the contraindication unconditionally for the WEU pathway, not conditionally.
11. **Same-rank competing sources:** 3 named (WHO_MONOGRAPH, ESCOP_MONOGRAPH, COMMISSION_E) per the SAFETY fallback-rank list; **0 verified/fetched** this pass.
12. **Disagreement among sources:** Not checked for the 3 unverified same-rank sources. Within the EMA_HMPC document's own adoption record, two HMPC members (Italy, Greece) filed formal dissenting opinions arguing the low-hyperforin **Traditional Use** pathway's interaction risk may be understated — this is an intra-document dissent about the *traditional-use, low-hyperforin* band specifically, not about the *well-established-use* pathway proposed as this case's governing claim.
13. **Source-precedence reasoning:** For SAFETY, `_resolve_safety()` picks by severity first, ties broken by fallback rank (EMA_HMPC first). EMA_HMPC is presumptively usable alone if no same-rank source contradicts it at equal or higher severity — but that has not been confirmed, since WHO/ESCOP/Commission E were not fetched.
14. **Comparability limitations:**
    - **Preparation is the single biggest risk.** The monograph names 11 herbal preparations (a–k) across WEU and Traditional Use pathways. The WEU pathway's contraindication is stated unconditionally; the Traditional Use pathway's is gated by hyperforin dose (≤1 mg/day: hypersensitivity only; >1 mg/day: same full contraindication list). Picking the wrong preparation/pathway changes the correct `AssertionState`.
    - Population/dose: no per-preparation hyperforin mg/day figure is given in the monograph text itself (see item 6).
    - Indication: this SAFETY claim is indication-independent (it applies regardless of which of the monograph's 4 indications the preparation is used for), but `EngineEvidenceInput.target_indication` is a required field with no natural SAFETY-domain value — see Supervisory Decision 5.
15. **Metadata-leakage risk:** Low. Search was limited to bibliographic/document lookup; the engine's internal vocabulary (e.g. any `HARD_SAFETY_TERMS`-equivalent) was not consulted or referenced in selecting this candidate or claim (Leakage Rule 9.4).
16. **Ground Truth / Engine Evidence leakage risk:** Elevated risk of a specific, avoidable kind: the contraindication section names specific drug substances verbatim (cyclosporine, coumarins, protease inhibitors, etc.). A curator drafting `EngineEvidenceInput.notes`/`compound_activity_targets` after reading this claim could unintentionally copy those same drug names in to "help" the engine reach the contraindication. Leakage Rule 9.1's ordering (claim first, then an independently-reasoned evidence draft) is necessary but not sufficient here — the independence note should explicitly address this specific risk.
17. **Coverage gap this case would fill:** (a) first case in `ReferenceDomain.SAFETY`; (b) first case using `AssertionType.CONTRAINDICATION`; (c) first case capable of producing a `SELECTED`/`SERIOUS`/`PRESENT` SAFETY outcome, i.e. potentially the first case in the program where `safety_serious_false_negative_rate` actually computes rather than reporting `NOT_COMPUTABLE`; (d) first case exercising per-gate mapping (Protocol §14.1) instead of whole-case `decision_direction_agreement` — an expected `NOT_ELIGIBLE` for that metric is correct behavior here, not a defect, and must still be recorded per §14.7.
18. **Final suitability verdict: RECOMMENDED WITH CONDITIONS.**

## Unresolved conflicts and limitations
- Same-rank sources (WHO/ESCOP/Commission E) not verified — see item 11–13.
- Preparation/pathway not yet chosen — see item 14.
- No existing case has used a non-`NONE` `SeverityLevel`, so there is no established convention in this repository for how "SERIOUS" gets assigned from monograph text to a locked `ReferenceClaim.severity`.
- `EngineEvidenceInput.target_indication` has no natural value for an indication-independent SAFETY claim.
- Hyperforin mg/day per specific WEU preparation is unconfirmed (would require the separate, unfetched Assessment Report).

## SUPERVISORY DECISION REQUIRED
1. Approve `SAFETY` domain / `CONTRAINDICATION` assertion type as Case 006's target (a protocol-level first, not just a case-level choice).
2. Approve the specific WEU preparation to lock (e.g., preparation "a": dry extract, DER 3–7:1, methanol 80% V/V) as the one whose unconditional contraindication governs this case, given the preparation-dependent split described in item 14.
3. Define/approve the convention for assigning `SeverityLevel.SERIOUS` (vs. MODERATE) from monograph contraindication language — no prior case sets this precedent.
4. Decide whether to spend a second, separate search pass verifying WHO_MONOGRAPH/ESCOP_MONOGRAPH/COMMISSION_E as same-rank SAFETY sources, or proceed on EMA_HMPC alone with that gap disclosed in the case.
5. Decide how to populate `EngineEvidenceInput.target_indication` for an indication-independent SAFETY claim (e.g., default to WEU Indication 1, "mild to moderate depression," vs. some other resolution).
