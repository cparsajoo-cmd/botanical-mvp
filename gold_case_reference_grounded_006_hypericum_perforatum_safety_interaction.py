"""
Reference-Grounded Validation — Phase 6, Case 006.

WHAT THIS IS
The fifth real (kind=GoldCaseKind.REFERENCE_GROUNDED) case built under
VALIDATION_PROTOCOL.md v0.3, and the FIRST case in this program in
ReferenceDomain.SAFETY using AssertionType.CONTRAINDICATION — Cases
001/003/004/005 are all ReferenceDomain.INDICATION_EVIDENCE /
AssertionType.SUPPORTS_INDICATION. Built following the approved
"case_006_source_suitability_screening.md" (two passes: initial
screening + same-rank-source verification), both supervisor-approved
before this file was written.

CASE SCOPE (Protocol §4)
Taxon:      Hypericum perforatum L. — St. John's wort, herb (herba)
Domain:     ReferenceDomain.SAFETY
Assertion:  AssertionType.CONTRAINDICATION,
            subject="concomitant medicinal products metabolised by
            CYP3A4, CYP2B6, CYP2C9, or CYP2C19, or transported by
            P-glycoprotein"
Governing source: European Union herbal monograph on Hypericum
            perforatum L., herba — Final, Revision 1, EMA/HMPC/7695/2021
            (adopted by HMPC 23 November 2022). source_type="EMA_HMPC".
Preparation LOCKED: Well-Established Use (WEU) herbal preparation a) —
            dry extract, DER 3-7:1, extraction solvent methanol 80%
            V/V — the preparation the monograph itself pairs with WEU
            Indication 1) ("treatment of mild to moderate depressive
            episodes"). This is the ONLY preparation used anywhere in
            this file; the Traditional Use (TU) pathway (which, for
            LOW-hyperforin preparations, states a narrower,
            hyperforin-dose-gated contraindication — see "WHY WEU, NOT
            TU" below) is never referenced.
Scientific Question (Case Template row 3 — no native GoldCase field):
    "Does the reference-grounded resolved outcome for Hypericum
    perforatum L. in domain Safety (Contraindication) for concomitant
    medicinal products metabolised by CYP3A4, CYP2B6, CYP2C9, or
    CYP2C19, or transported by P-glycoprotein, under
    population 'Adults and elderly' / route Oral / preparation Extract
    (DER 3-7:1, methanol 80% V/V) / jurisdiction EU, agree with the
    decision the engine produces when given equivalent, independently
    curator-supplied evidence?"
    NOTE: this Scientific Question cannot yet be answered by running
    the engine — see "OPEN ARCHITECTURAL QUESTION" below. This file
    builds and resolves the reference-truth (Ground Truth) layer only;
    no EngineEvidenceInput exists yet, and the engine is never
    executed here.

SOURCE-PRECEDENCE (Protocol §6/§9.3 — already screened and approved;
summarized here, not repeated in full)
Case 006's own approved screening file identified three same-rank
SAFETY sources (WHO_MONOGRAPH, ESCOP_MONOGRAPH, COMMISSION_E) and
verified all three EXIST and are topically relevant, but NONE was
accessible as full text in either search pass (WHO: print-only;
ESCOP: paywalled + robots-disallowed; Commission E: paywalled English
translation, and its 1984 original likely predates the CYP450
interaction pharmacology this claim rests on). No material
contradiction was found — but this reflects inaccessibility, not
confirmed agreement, and is recorded here as a genuine, disclosed
evidentiary gap, not treated as resolved. This GoldCase therefore has
exactly ONE GoldCaseReference (EMA_HMPC), and it is the only applicable
reference for this domain/subject — but reference_precedence.py's
_resolve_safety() does not select on applicability/count alone: it
requires every applicable reference to carry a parseable
safety_severity before it will resolve at all. Because this case's
claim.severity is None (see "WHY severity IS LEFT UNRESOLVED" below),
EMA_HMPC — despite being the sole applicable reference, with no
competitor to out-rank or tie against — is never actually selected.
_resolve_safety() returns ResolutionStatus.INSUFFICIENT_METADATA
instead, and the resolved SAFETY outcome carries no selected
reference, no assertion_state, and no severity. The single-reference
situation therefore never reaches a selection step at all; it is
blocked one precondition earlier, on missing severity metadata.

WHY WEU, NOT TU (resolves screening item 14's preparation ambiguity)
The monograph's Traditional Use pathway states the interaction
contraindication only for preparations with daily hyperforin intake
>1 mg; for ≤1 mg/day only hypersensitivity is contraindicated. The
Well-Established Use pathway's Section 4.3 states the full
interaction-based contraindication list UNCONDITIONALLY, with no
hyperforin threshold. Locking WEU preparation a) (per the mandatory
supervisory decision) removes this ambiguity entirely for this case:
there is no dose-band question to resolve for preparation a), because
the WEU column simply does not gate the contraindication by dose.

WHY severity IS LEFT UNRESOLVED (severity=None — neither SERIOUS nor
MODERATE, and NOT SeverityLevel.NONE either)
The prior revision of this file assigned SeverityLevel.SERIOUS as a
curator judgment call and flagged it for supervisor confirmation.
Per explicit supervisory instruction, that judgment is now checked
against the repository rather than kept as a plausible-sounding
default: VALIDATION_PROTOCOL.md, assertion_vocabulary.py, and
reference_precedence.py were searched for any rule mapping an
EMA/HMPC contraindication of this kind (or any specific source_type /
assertion_type / drug-class combination) to a SeverityLevel value.
NONE EXISTS. VALIDATION_PROTOCOL.md §6 states only that "severity
decides first" for SAFETY-domain precedence — it defines how an
ALREADY-ASSIGNED severity is used to resolve between references, not
how a severity is assigned to a claim in the first place. No case
before this one has ever populated a non-None SeverityLevel, so there
is no in-repository precedent either. Assigning SERIOUS here would
freeze an invented judgment as Ground Truth; assigning
SeverityLevel.NONE would be a different but equally invented error in
the opposite direction — NONE means "the source states there is no
safety concern," which directly contradicts what Section 4.3 actually
says. Leaving `severity=None` is the only option that adds no
unsupported claim.

CONSEQUENCE: reference_precedence._resolve_safety() requires a
parseable safety_severity (one of "NONE"/"MINOR"/"MODERATE"/"SERIOUS")
to resolve AT ALL — derive_reference_verdict_from_claim() maps
claim.severity=None to verdict.safety_severity=None, which
_resolve_safety() cannot look up in _SEVERITY_ORDER, so it returns
ResolutionStatus.INSUFFICIENT_METADATA for this domain, not SELECTED.
This case's SAFETY resolved outcome therefore carries
resolution_status=INSUFFICIENT_METADATA, assertion_state=None, and
severity=None — an honest non-answer, not a bug to route around, and
consistent with how Case 005 recorded a real non-answer
(AssertionState.INSUFFICIENT) rather than forcing one. A future,
separate protocol decision that defines an explicit severity-
assignment rule could change this; none is invented here.

VERBATIM EXTRACTION — GOVERNING SOURCE
Reference claim's evidence_text is the exact Well-Established-Use-
column text of Section 4.3 "Contraindications", copied verbatim from
the monograph PDF fetched directly during screening (line-wraps
rejoined; no words added, removed, or reordered):
    "Hypersensitivity to the active substance. Concomitant use with
    coumarin-type anticoagulants, cyclosporine, everolimus, sirolimus,
    tacrolimus for systemic use, fosamprenavir, indinavir and other
    protease inhibitors, nucleoside reverse transcriptase inhibitors,
    irinotecan, imatinib and other cytostatic agents metabolised by
    CYP3A4, CYP2B6, CYP2C9, CYP2C19 or transported by P-glycoprotein
    (see section 4.5 'Interactions with other medicinal products and
    other forms of interaction')."

WHY subject="concomitant medicinal products metabolised by CYP3A4,
CYP2B6, CYP2C9, or CYP2C19, or transported by P-glycoprotein" (not
individual drug names, and not narrowed to CYP3A4/P-gp alone)
The monograph's own contraindication is a class-based statement naming
FOUR distinct CYP isoenzymes (CYP3A4, CYP2B6, CYP2C9, CYP2C19) in
addition to the P-glycoprotein transporter — not a list of unrelated,
independently-contraindicated single drugs, and not solely a
CYP3A4/P-gp claim. An earlier revision of this file used
"concomitant CYP3A4/P-glycoprotein substrate medicinal products" as
the subject, which silently dropped CYP2B6, CYP2C9, and CYP2C19 —
materially narrower than what Section 4.3 actually states. That was
corrected here per explicit supervisory review; the subject now names
every pathway the source names, at the same class level the source
itself uses, inventing neither a narrower nor a broader framing.

WHY domain=SAFETY IS NOT ELIGIBLE FOR WHOLE-CASE decision_direction_
agreement (Protocol §14.1)
agreement_eligibility._ELIGIBLE_DOMAINS presently contains only
ReferenceDomain.INDICATION_EVIDENCE. This case's resolved outcome is
in ReferenceDomain.SAFETY, so assess_agreement_eligibility() is
expected to return NOT_ELIGIBLE, reason=NO_ELIGIBLE_DOMAIN_OUTCOME —
correct, protocol-conforming behavior (§10, §14.7), not a defect, and
not something this file works around. SAFETY maps to its own engine
gate individually (§14.1), never to the whole-case decision — a
separate question this file does not attempt to answer, since no
EngineEvidenceInput exists yet (see below) and the engine is never
run here.

OPEN ARCHITECTURAL QUESTION — DOCUMENTED, NOT INVENTED AROUND
(per the explicit supervisory instruction accompanying this build)
gold_case_execution.execute_gold_case_against_engine() unconditionally
requires validation_unit.indication (raises GoldCaseNotExecutableError
otherwise), and engine_evidence_input.EngineEvidenceInput.target_
indication is a required, non-optional field. Both are indication-
shaped fields the engine's execution API demands regardless of domain
— but this case's Ground Truth claim (a drug-interaction
contraindication) is, by the governing source's own structure,
indication-INDEPENDENT: Section 4.3's WEU contraindication applies
identically no matter which of the monograph's indications the
preparation is used for. There is no single non-arbitrary value already
supported by the governing source for "the" indication of a pure-
SAFETY case, and inventing one (e.g. defaulting to WEU Indication 1,
"mild to moderate depressive episodes," solely so the engine can run)
would be exactly the kind of unsupported-metadata invention Protocol
§8 and this build's own instructions forbid. This is judged to be a
genuine, project-level, not case-level, design question: should
SAFETY-only GoldCases populate this field with the preparation's own
paired WEU indication, some other convention, or should the execution
API itself be changed to make target_indication optional for non-
INDICATION_EVIDENCE domains? None of those options is decided here.

CONSEQUENCE OF THE OPEN QUESTION (scope actually delivered in this
file)
- validation_unit.indication is left at its default (None) —
  deliberately, not an oversight.
- GoldCase.engine_evidence is left empty ([]) and engine_evidence_
  origin is left None — the SAME pattern Case 005 already established
  for "EngineEvidenceInput collection is a separate, later,
  independently-decided step" (Leakage Rule 9.1), here additionally
  blocked on the open question above, not merely deferred by choice.
- This file therefore builds and resolves ONLY the reference-truth
  (Ground Truth) layer: ValidationUnit metadata that the governing
  source itself directly supports (preparation, population, route,
  jurisdiction, plant_part), the ReferenceDescriptor, the
  ReferenceClaim, and GoldCase.resolved_outcomes.
- gold_case_execution.execute_gold_case_against_engine() CANNOT
  currently run this case (it would raise GoldCaseNotExecutableError
  on the missing indication) — this is intentional, not a bug to fix
  here, and is exercised directly by this file's own test suite.
- Case 006 is NOT locked (lock_gold_case() is never called) — is_lockable()
  itself does not require validation_unit.indication, so the
  Ground-Truth layer built here IS lock-eligible on its own terms, but
  locking is left to a later, separate curatorial step exactly as in
  Cases 003/004/005.

STOP CONDITION
Per the accompanying instructions: this open question requires a
supervisory/architectural decision before EngineEvidenceInput can be
curated for this case (Leakage Rule 9.1 also requires the Ground Truth
claim above to be finalized first regardless). No workaround has been
invented. Construction stops here for this specific decision; the
Ground-Truth deliverables below are complete on their own terms.

A second, narrower stop applies to severity specifically: no explicit
repository rule maps this contraindication class to a SeverityLevel
(see "WHY severity IS LEFT UNRESOLVED" above), so severity is left
None rather than invented, and this case's SAFETY resolved outcome is
resolution_status=INSUFFICIENT_METADATA as a direct, mechanical
consequence — not a separately-invented status.
"""

from __future__ import annotations

from datetime import date

from applicability_check import ReferenceDomain, check_applicability
from assertion_vocabulary import (
    AssertionState, AssertionType, CurationStatus,
    ExtractionConfidenceLevel, GoldCaseKind, TransformationType,
)
from field_provenance import FieldProvenance, VerificationStatus
from gold_case import GoldCase, GoldCaseReference, RiskStratum
from reference_claim import ExtractionConfidence, NormalizedEvidenceText, ReferenceClaim
from reference_descriptor import ReferenceDescriptor
from resolved_expected_outcome import resolve_expected_outcomes
from validation_unit import PreparationSpec, ValidationUnit

# --- Real reference-source metadata (EMA/HMPC/7695/2021) -------------------
_EMA_REFERENCE_ID = "EMA_HMPC_7695_2021_hypericum_perforatum_herba"
_EMA_DOCUMENT_TITLE = "European Union herbal monograph on Hypericum perforatum L., herba"
_EMA_DOCUMENT_VERSION = "Final, Revision 1, adopted by HMPC 23 November 2022 (EMA/HMPC/7695/2021)"
_EMA_DOCUMENT_DATE = date(2022, 11, 23)
_EMA_CONTRAINDICATION_LOCATOR = (
    "Section 4.3 'Contraindications', Well-established use column — "
    "EMA/HMPC/7695/2021, p.8/14"
)
_EMA_PREPARATION_LOCATOR = (
    "Section 2 'Qualitative and quantitative composition', ii) Herbal "
    "preparations a), and Section 4.2 'Posology and method of "
    "administration', Indication 1), Well-established use column — "
    "EMA/HMPC/7695/2021, p.3-6/14"
)
# Verbatim, complete Well-Established-Use-column text of Section 4.3.
# Line-wraps from the source PDF rejoined into continuous prose; no
# words added, removed, or reordered. Includes the hypersensitivity
# sentence because that is how the source itself states the section —
# splitting it out would not change the claim below, which targets the
# interaction sentence specifically via `subject`.
_EMA_CONTRAINDICATION_VERBATIM = (
    "Hypersensitivity to the active substance. Concomitant use with "
    "coumarin-type anticoagulants, cyclosporine, everolimus, sirolimus, "
    "tacrolimus for systemic use, fosamprenavir, indinavir and other "
    "protease inhibitors, nucleoside reverse transcriptase inhibitors, "
    "irinotecan, imatinib and other cytostatic agents metabolised by "
    "CYP3A4, CYP2B6, CYP2C9, CYP2C19 or transported by P-glycoprotein "
    "(see section 4.5 'Interactions with other medicinal products and "
    "other forms of interaction')."
)
# Fixed, explicit date this source extraction was actually performed —
# deliberately NOT date.today(). See Case 001's identical convention.
_EXTRACTION_DATE = date(2026, 7, 29)


def _hypericum_weu_extract_preparation() -> PreparationSpec:
    """The ONE PreparationSpec both the ReferenceDescriptor and the
    ValidationUnit use — WEU herbal preparation a): dry extract,
    DER 3-7:1, extraction solvent methanol 80% V/V, paired by the
    monograph itself with WEU Indication 1). source_status is left
    None: the monograph text obtained during screening does not use
    the "native"/"concentrated" EMA/HMPC vocabulary for this specific
    preparation, and no value is invented here to fill it in."""
    return PreparationSpec(
        dosage_form="Extract",
        solvent="methanol 80% V/V",
        der_min=3.0,
        der_max=7.0,
        source_status=None,
    )


def _build_reference_descriptor() -> ReferenceDescriptor:
    return ReferenceDescriptor(
        reference_id=_EMA_REFERENCE_ID,
        source_type="EMA_HMPC",
        version=_EMA_DOCUMENT_VERSION,
        document_date=_EMA_DOCUMENT_DATE,
        jurisdiction="EU",
        taxon="Hypericum perforatum L.",
        plant_part="herb",
        preparation=_hypericum_weu_extract_preparation(),
        # EMA-grounded population, verbatim from Section 4.2 Posology,
        # Well-established-use column — shared by preparations a)/b)/c).
        population="Adults and elderly",
        claim_type="well-established-use",
        # DELIBERATELY EMPTY — see module docstring's "OPEN
        # ARCHITECTURAL QUESTION". Section 4.3's WEU contraindication
        # is not itself scoped to one indication (it applies across
        # the whole WEU pathway), so declaring an indication_scope
        # here would assert a narrower scope than the source states.
        # An empty list is read by _check_document_scope() as "not
        # checked from the reference side," never as "covers nothing"
        # — the honest state here.
        indication_scope=[],
        route_scope=["Oral"],
        retracted_or_superseded=False,
    )


def _build_reference_claim(reference: ReferenceDescriptor) -> ReferenceClaim:
    evidence_text = NormalizedEvidenceText(
        original_text=_EMA_CONTRAINDICATION_VERBATIM,
        normalized_text=_EMA_CONTRAINDICATION_VERBATIM,
        transformation_type=TransformationType.VERBATIM,
        transformation_version="verbatim-extraction-v1",
        source_locator=_EMA_CONTRAINDICATION_LOCATOR,
    )
    extraction_confidence = ExtractionConfidence(
        level=ExtractionConfidenceLevel.HIGH,
        basis=(
            "Verbatim excerpt copied directly from the official EMA-"
            "published final monograph PDF (EMA/HMPC/7695/2021, adopted "
            "23 November 2022), Section 4.3, Well-established use "
            "column, fetched and read in full during source-suitability "
            "screening. Extraction confidence is HIGH for the verbatim "
            "text itself; this is independent of the separately "
            "disclosed, lower-confidence status of the three unverified "
            "same-rank sources (WHO/ESCOP/Commission E — see module "
            "docstring), which this field does not cover."
        ),
        extractor_type="hybrid",
        extractor_version="claude-assisted-extraction-v1",
    )
    return ReferenceClaim(
        domain=ReferenceDomain.SAFETY,
        assertion_type=AssertionType.CONTRAINDICATION,
        subject=(
            "concomitant medicinal products metabolised by CYP3A4, "
            "CYP2B6, CYP2C9, or CYP2C19, or transported by P-glycoprotein"
        ),
        assertion_state=AssertionState.PRESENT,
        # DELIBERATELY None, not SeverityLevel.SERIOUS — see module
        # docstring's "WHY severity IS LEFT UNRESOLVED". No repository
        # rule maps this contraindication class to a SeverityLevel;
        # inventing one here (in either direction) is exactly what was
        # corrected out of this file.
        severity=None,
        source_reference_id=reference.reference_id,
        source_locator=_EMA_CONTRAINDICATION_LOCATOR,
        evidence_text=evidence_text,
        extraction_confidence=extraction_confidence,
    )


def _build_case_provenance() -> list:
    return [
        FieldProvenance(
            document_id=_EMA_REFERENCE_ID,
            document_version=_EMA_DOCUMENT_VERSION,
            locator=_EMA_CONTRAINDICATION_LOCATOR,
            supported_field=(
                "resolved_outcomes[domain=Safety, "
                "subject='concomitant medicinal products metabolised by "
                "cyp3a4, cyp2b6, cyp2c9, or cyp2c19, or transported by "
                "p-glycoprotein']"
            ),
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
        FieldProvenance(
            document_id=_EMA_REFERENCE_ID,
            document_version=_EMA_DOCUMENT_VERSION,
            locator=_EMA_PREPARATION_LOCATOR,
            supported_field=(
                "validation_unit.preparation (Extract, DER 3-7:1, "
                "methanol 80% V/V) / .population ('Adults and elderly') "
                "/ .route_of_administration ('Oral') / .jurisdiction "
                "('EU') — all taken from the same governing monograph, "
                "not a separate source"
            ),
            extraction_date=_EXTRACTION_DATE,
            curator=None,
            verification_status=VerificationStatus.UNVERIFIED,
        ),
    ]


def build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction() -> GoldCase:
    """Builds the case through resolved_outcomes only. Returns an
    UNLOCKED GoldCase (locked=False); lock_gold_case() is intentionally
    never called here (same convention as Cases 003/004/005).
    EngineEvidenceInput collection is NOT started in this file — see
    module docstring's "OPEN ARCHITECTURAL QUESTION" and "STOP
    CONDITION" sections. validation_unit.indication is deliberately
    left at its default (None). expected_output.expected_decision_
    direction is left at its default (None) — SAFETY is not in
    agreement_eligibility._ELIGIBLE_DOMAINS, so there is nothing for
    this case to derive a whole-case direction from under current
    protocol policy (§14.1).
    """
    unit = ValidationUnit(
        taxon="Hypericum perforatum L.",
        taxon_synonyms=["Hypericum perforatum L."],
        plant_part="herb",
        preparation=_hypericum_weu_extract_preparation(),
        population="Adults and elderly",
        route_of_administration="Oral",
        # DELIBERATELY LEFT UNSET (None) — see module docstring's "OPEN
        # ARCHITECTURAL QUESTION". Not an oversight; do not silently
        # fill this in with a guessed or invented indication.
        indication=None,
        jurisdiction="EU",
    )

    reference = _build_reference_descriptor()
    claim = _build_reference_claim(reference)

    gref = GoldCaseReference(reference=reference, claims=[claim])
    gref.applicability_by_domain[ReferenceDomain.SAFETY] = check_applicability(
        reference, unit, ReferenceDomain.SAFETY,
    )

    case = GoldCase(
        case_id="refgrounded_006_hypericum_perforatum_safety_interaction",
        validation_unit=unit,
        # SAFETY_SERIOUS deliberately NOT included — that stratum would
        # assert a severity judgment this case's claim no longer makes
        # (see module docstring's "WHY severity IS LEFT UNRESOLVED").
        # INTERACTION applies regardless of severity — this is a
        # documented drug-interaction contraindication either way.
        risk_strata=[RiskStratum.INTERACTION],
        references=[gref],
        case_provenance=_build_case_provenance(),
        kind=GoldCaseKind.REFERENCE_GROUNDED,
        curation_status=CurationStatus.REFERENCE_CURATED,
        # engine_evidence intentionally left empty; engine_evidence_origin
        # intentionally left None. expected_output intentionally left at
        # its default (expected_decision_direction=None) — see docstring.
    )
    case.resolved_outcomes = resolve_expected_outcomes(case)
    return case


if __name__ == "__main__":
    built_case = build_gold_case_refgrounded_006_hypericum_perforatum_safety_interaction()
    print(f"case_id: {built_case.case_id}")
    print(f"locked: {built_case.locked}")
    print(f"validation_unit.indication: {built_case.validation_unit.indication!r} (deliberately unset — see module docstring)")
    for outcome in built_case.resolved_outcomes:
        print(
            f"domain={outcome.domain.value!r} subject={outcome.subject!r} "
            f"assertion_type={outcome.assertion_type.value!r} "
            f"resolution_status={outcome.resolution_status.value!r} "
            f"selected_reference_id={outcome.selected_reference_id!r} "
            f"assertion_state={outcome.assertion_state} "
            f"severity={outcome.severity}"
        )
