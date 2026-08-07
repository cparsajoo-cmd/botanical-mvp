# Case 020 Implementation Report

## Purpose
Close the ESCOP governing-source gap without changing production logic or source-precedence rules.

## Case
- Case ID: `refgrounded_020_echinacea_purpurea_escop_monograph`
- Taxon: *Echinacea purpurea* (L.) Moench
- Plant part: flowering aerial parts
- Domain: `INDICATION_EVIDENCE`
- Assertion: `SUPPORTS_INDICATION`
- Assertion state: `PRESENT`
- Subject: recurrent infections of the upper respiratory tract (common colds)
- Governing source type: `ESCOP_MONOGRAPH`

## Source verification
Official ESCOP public monograph summary:
`https://www.escop.com/downloads/echinaceae-purpureae-herba-purple-coneflower-herb/`

The public source explicitly identifies the herbal drug as the flowering aerial parts of *Echinacea purpurea* and lists recurrent upper-respiratory infections/common colds among its therapeutic indications.

The full monograph is paid-access. No preparation, dose, route, duration, or population information was inferred from inaccessible content.

## Validation
- Case 020 focused tests: 8/8 passed.
- Case 020 + Gold Corpus + Phase 7: 38 passed.
- Canonical Gold Case regression + Gold Corpus + Phase 7: 139 passed.
- Engine evidence: empty.
- Locked: false.
- Production logic modified: no.

## Coverage impact
- ESCOP governing source: GAP -> COVERED.
- Active canonical cases: 19 (Case 002 remains abandoned).
- No duplicate meta-analysis or EMA-positive-indication case was added.
