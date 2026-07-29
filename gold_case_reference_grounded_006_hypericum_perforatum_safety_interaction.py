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
    NOTE: answering this Scientific Question by running the engine
    happens in a SEPARATE file, case_006_engine_evidence_run.py — the
    same file-separation convention Case 003 already established
    (gold_case_reference_grounded_003_matricaria_chamomilla.py's own
    docstring: "Leakage Rule 9.1 requires this to be a separate,
    later, independently-decided step; keeping it in its own file also
    means Case Truth record is never touched by an execution-time
    decision"). This file builds and resolves the reference-truth
    (Ground Truth) layer only; no EngineEvidenceInput exists here, and
    the engine is never executed in this file.

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
reference for this domain/subject. With claim.severity now assigned by
severity_assignment_policy.py (see "WHY severity=SeverityLevel.SERIOUS"
below), reference_precedence.py's _resolve_safety() has the parseable
severity it requires and reaches ResolutionStatus.SELECTED for
EMA_HMPC. This is a genuine single-candidate resolution, not a
same-rank comparison: the three same-rank SAFETY sources named above
remain unverified, so this resolution rests on EMA_HMPC alone, with
that gap disclosed rather than hidden.

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

WHY severity=SeverityLevel.SERIOUS (via severity_assignment_policy.py
— a documented repository rule, not curator judgment inside this file)
The prior revision of this file assigned SeverityLevel.SERIOUS as an
ad hoc curator judgment call, which was correctly rejected: at that
time, no explicit repository rule existed mapping this contraindication
class to a severity, so the file was corrected to leave severity=None
rather than freeze an invented judgment. That gap has now been closed
architecturally, not case-specifically: severity_assignment_policy.py
(SEVERITY_ASSIGNMENT_RULE_VERSION="1.0.0") defines
assign_contraindication_severity(assertion_type, drug_classes), which
returns SeverityLevel.SERIOUS for a CONTRAINDICATION or INTERACTION
claim whose contraindicated substances fall into one or more of its
explicit HighRiskInteractionDrugClass values, and returns None (no
rule applies) for anything else — never a guessed severity for an
unrecognized class. This case's claim is built with drug_classes=
{TRANSPLANT_IMMUNOSUPPRESSANT, ANTICOAGULANT, ANTIRETROVIRAL_THERAPY,
CYTOTOXIC_AGENT} — a direct, source-grounded mapping from Section
4.3's own named substances: cyclosporine/everolimus/sirolimus/systemic
tacrolimus (TRANSPLANT_IMMUNOSUPPRESSANT), coumarin-type anticoagulants
(ANTICOAGULANT), fosamprenavir/indinavir/other protease inhibitors/
nucleoside reverse transcriptase inhibitors (ANTIRETROVIRAL_THERAPY),
and irinotecan/imatinib/other cytostatic agents (CYTOTOXIC_AGENT). The
policy module — not this file — is the citable rule; this file only
supplies the drug-class classification, which is checkable against the
verbatim text above, not a free-form paragraph of reasoning.

CONSEQUENCE: reference_precedence._resolve_safety() requires a
parseable safety_severity to resolve at all — with severity now
SERIOUS, the single applicable reference (EMA_HMPC) resolves to
ResolutionStatus.SELECTED, and the resolved SAFETY outcome carries
assertion_state=PRESENT, severity=SERIOUS, and
selected_reference_id=EMA_HMPC's reference_id.

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

ARCHITECTURAL QUESTION — NOW RESOLVED (was open in a prior revision
of this file)
A prior revision of this file documented, and deliberately did not
work around, an open question: gold_case_execution.
execute_gold_case_against_engine() unconditionally required
validation_unit.indication, and EngineEvidenceInput.target_indication
was a required, non-optional field — both indication-shaped
requirements that made no sense for this case's indication-INDEPENDENT
SAFETY claim (Section 4.3's WEU contraindication applies identically
regardless of which of the monograph's indications the preparation is
used for). Per explicit supervisory authorization, this has now been
fixed architecturally, not with a case-specific workaround:
- engine_evidence_input.EngineEvidenceInput.target_indication is now
  Optional[str] = None.
- gold_case_execution.py now defines an explicit WHITELIST,
  INDICATION_REQUIRED_DOMAINS = frozenset({ReferenceDomain.
  INDICATION_EVIDENCE}), and _requires_indication(gold_case), which
  reads the domain(s) this case's own claims declare. Indication is
  required only when a case's domain(s) intersect that whitelist; an
  unknown/empty/mixed domain set still fails safe (indication
  required) — this only ever WIDENS what's optional for a domain
  explicitly reasoned about, never narrows the requirement elsewhere.
- When indication is not required, execute_gold_case_against_engine()
  runs the engine via BotanicalRDCandidateEngine.run()'s OWN existing
  reference_plant= parameter (an already-existing engine capability,
  matching by taxon name across the full candidate universe,
  independent of indication) — botanical_rd_candidate_engine.py itself
  is not modified. No placeholder indication string (e.g. "mild to
  moderate depression" or "indication-independent") is ever
  substituted anywhere in this fix.
See gold_case_execution.py's own module docstring ("INDICATION-
INDEPENDENT DOMAINS") for the full architectural rationale, and
test_indication_dependence_architecture.py for the regression suite
covering this change in general (not Case-006-specific).

CONSEQUENCE FOR THIS FILE
- validation_unit.indication remains at its default (None) — this is
  now a genuine, architecturally-supported "not applicable," not a
  workaround-free stop condition.
- GoldCase.engine_evidence remains empty ([]) and engine_evidence_
  origin remains None IN THIS FILE — the same Leakage-Rule-9.1
  file-separation convention Case 003 established: this file is the
  frozen Ground Truth record; EngineEvidenceInput, execution, gate
  agreement, and locking all happen in the separate
  case_006_engine_evidence_run.py, never here.
- This file's own resolved_outcomes now resolve to SELECTED (see "WHY
  severity=SeverityLevel.SERIOUS" above), so
  gold_case.is_lockable() succeeds on the Ground-Truth layer built
  here — but lock_gold_case() is still never called in THIS file; see
  case_006_engine_evidence_run.py for the actual lock, which only
  happens there after execution and gate-agreement verification
  succeed.
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
from severity_assignment_policy import HighRiskInteractionDrugClass, assign_contraindication_severity
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
        # Assigned via severity_assignment_policy.py — a documented
        # repository rule, not curator judgment inside this file. See
        # module docstring's "WHY severity=SeverityLevel.SERIOUS" for
        # the drug-class-to-source-text mapping.
        severity=assign_contraindication_severity(
            assertion_type=AssertionType.CONTRAINDICATION,
            drug_classes=frozenset({
                HighRiskInteractionDrugClass.TRANSPLANT_IMMUNOSUPPRESSANT,
                HighRiskInteractionDrugClass.ANTICOAGULANT,
                HighRiskInteractionDrugClass.ANTIRETROVIRAL_THERAPY,
                HighRiskInteractionDrugClass.CYTOTOXIC_AGENT,
            }),
        ),
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
    never called here — the same Leakage-Rule-9.1 file-separation
    convention Case 003 established. EngineEvidenceInput collection,
    execution, gate-agreement verification, and locking all happen in
    the separate case_006_engine_evidence_run.py, never in this file.
    validation_unit.indication is left at its default (None) — now a
    genuine, architecturally-supported "not applicable" for this
    indication-independent SAFETY case (see module docstring's
    "ARCHITECTURAL QUESTION — NOW RESOLVED"), not a workaround.
    expected_output.expected_decision_direction is left at its default
    (None) — SAFETY is not in agreement_eligibility._ELIGIBLE_DOMAINS,
    so there is nothing for this case to derive a whole-case direction
    from under current protocol policy (§14.1); gate-level agreement is
    assessed separately in case_006_engine_evidence_run.py.
    """
    unit = ValidationUnit(
        taxon="Hypericum perforatum L.",
        taxon_synonyms=["Hypericum perforatum L."],
        plant_part="herb",
        preparation=_hypericum_weu_extract_preparation(),
        population="Adults and elderly",
        route_of_administration="Oral",
        # LEFT UNSET (None) — architecturally supported for this
        # indication-independent SAFETY case (see module docstring's
        # "ARCHITECTURAL QUESTION — NOW RESOLVED"). Not a guessed or
        # invented indication.
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
        # SAFETY_SERIOUS is now justified — severity_assignment_policy.py
        # assigns SeverityLevel.SERIOUS via an explicit, documented rule
        # (see module docstring), not a curator guess.
        risk_strata=[RiskStratum.SAFETY_SERIOUS, RiskStratum.INTERACTION],
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
