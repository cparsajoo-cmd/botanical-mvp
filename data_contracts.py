"""
Phase 3 — standard data contracts for the platform's core entities.

WHY THIS EXISTS
Right now every part of the engine passes data around as bare dicts /
DataFrame rows with ad-hoc column names, so it's easy for one function
to write "Concentration" and another to read "concentration_value" and
never notice. These dataclasses are the single, named shape each entity
is supposed to have — Plant, Compound, PlantCompoundOccurrence,
TargetMechanism, ScientificEvidence, CommercialProduct,
RegulatoryRecord, SafetyInteraction, CandidateAssessment — matching
field-for-field what was specified in the Phase 1 audit request
(sections 4.5, 4.7, 4.8, 4.9, 4.13, 4.14, and 6).

WHAT THIS IS NOT (yet)
This is the CONTRACT layer only. Nothing in botanical_rd_candidate_engine.py
or the Supabase tables has been changed to use these yet — that's Phase 4
(scientific correction) and later, done incrementally against this
contract so each change stays small and reversible. Supabase table
schemas are also untouched; these dataclasses describe the shape data
SHOULD have, they don't migrate where it currently lives.

WHY DATACLASSES, NOT PYDANTIC
pydantic is available on the deployed app only as a transitive
dependency of `supabase` (not pinned in requirements.txt), so relying
on it here would be fragile — a future `supabase` version could drop
or change its pydantic dependency and silently break this file. Python's
built-in `dataclasses` module needs nothing extra and is guaranteed to
work in any environment (including this one, where every entity below
has a passing test with zero installs). If a stricter validation layer
(pydantic, or hand-rolled) is wanted later, it's a natural upgrade
FROM this file without changing the field names/shapes.

MISSING DATA IS EXPLICIT, NOT SILENT
Every field defaults to None (or an empty list/dict) rather than a
placeholder string like "" or "Unknown" baked in at the dataclass
level — callers decide how to DISPLAY a missing value, but the contract
itself never manufactures a fake-looking answer. `verification_status`
/ `confidence` fields exist specifically so "we don't know" and "we
verified this is false" stay distinguishable (see the Phase 1 audit,
4.4 and 4.6: "not found" must never collapse into "does not exist").
"""

from dataclasses import dataclass, field, fields, asdict
from datetime import date
from enum import Enum
from typing import Optional


# ======================================================================
# Shared controlled vocabularies
# ======================================================================

class GateStatus(str, Enum):
    """Task 1 — Formal Gate Layer. A gate is independent of
    R&D_Opportunity_Score and Decision_Class: it answers "does this
    candidate clear a specific, named precondition" rather than
    contributing points. PASSED/FAILED are affirmative findings;
    NOT_EVALUABLE means the signal needed to judge the gate wasn't
    available, or wasn't specific enough to support an affirmative
    finding, for this row (never silently treated as PASSED — see
    botanical_rd_candidate_engine._evaluate_gates for the exact
    per-gate rules)."""
    PASSED = "passed"
    FAILED = "failed"
    NOT_EVALUABLE = "not_evaluable"


class VerificationStatus(str, Enum):
    """Generic confidence-in-the-record-itself status, usable on any
    entity below (a Plant name, a Compound identity, an Occurrence
    claim, a Product listing, ...). Deliberately separate from
    scientific EVIDENCE quality (see EvidenceHierarchyLevel) — this is
    about whether the RECORD is trustworthy, not whether the underlying
    science is strong."""
    VERIFIED = "Verified"
    UNVERIFIED = "Unverified"
    CONFLICTING_SOURCES = "Conflicting sources"
    UNKNOWN = "Unknown"


class EvidenceHierarchyLevel(str, Enum):
    """Per Phase 1 audit 4.14 — ordered strongest to weakest. Ordering
    matters: EVIDENCE_HIERARCHY_ORDER below is the authoritative rank,
    this Enum only defines the members."""
    SYSTEMATIC_REVIEW_META_ANALYSIS = "Systematic review / meta-analysis"
    CLINICAL_TRIAL = "Clinical trial"
    OBSERVATIONAL_HUMAN = "Observational human evidence"
    VALIDATED_EX_VIVO_IN_VIVO = "Validated ex vivo / in vivo"
    IN_VITRO_MECHANISTIC = "In vitro / mechanistic"
    TRADITIONAL_USE_MONOGRAPH = "Traditional-use / regulatory monograph"
    OCCURRENCE_ANALYTICAL_ONLY = "Occurrence / analytical chemistry only"
    COMPUTATIONAL_HYPOTHESIS = "Computational hypothesis"


# Strongest-first order, for programmatic comparison
# (e.g. "is record A's evidence at least as strong as record B's?").
EVIDENCE_HIERARCHY_ORDER = [
    EvidenceHierarchyLevel.SYSTEMATIC_REVIEW_META_ANALYSIS,
    EvidenceHierarchyLevel.CLINICAL_TRIAL,
    EvidenceHierarchyLevel.OBSERVATIONAL_HUMAN,
    EvidenceHierarchyLevel.VALIDATED_EX_VIVO_IN_VIVO,
    EvidenceHierarchyLevel.IN_VITRO_MECHANISTIC,
    EvidenceHierarchyLevel.TRADITIONAL_USE_MONOGRAPH,
    EvidenceHierarchyLevel.OCCURRENCE_ANALYTICAL_ONLY,
    EvidenceHierarchyLevel.COMPUTATIONAL_HYPOTHESIS,
]


class SimilarityType(str, Enum):
    """Per Phase 1 audit 4.8 — chemical similarity is not one thing."""
    EXACT_SAME_COMPOUND = "Exact same compound"
    SYNONYM_IDENTIFIER_MATCH = "Synonym / identifier match"
    SAME_COMPOUND_FAMILY = "Same compound family"
    CHEMICAL_STRUCTURE_SIMILARITY = "Chemical structure similarity"
    SAME_VALIDATED_BIOLOGICAL_TARGET = "Same validated biological target"
    SAME_MECHANISM_PATHWAY = "Same mechanism / pathway"
    TEXTUAL_SIMILARITY_ONLY = "Textual similarity only"


class MarketVerificationStatus(str, Enum):
    """Per Phase 1 audit 4.6 — replaces the old binary "found/not found"
    with real distinctions between not-searched, searched-and-empty,
    and unverified-but-reported."""
    VERIFIED_MARKETED_PRODUCT = "Verified marketed product"
    COMMERCIAL_EVIDENCE_UNVERIFIED = "Commercial evidence reported, not independently verified"
    REGULATORY_MONOGRAPH_EXISTS = "Regulatory monograph exists"
    TRADITIONAL_USE_STATUS = "Traditional-use status"
    NO_VERIFIED_PRODUCT_FOUND = "No verified product found"
    SEARCH_NOT_PERFORMED = "Search not performed"
    SOURCE_UNAVAILABLE = "Source unavailable"
    UNKNOWN = "Unknown"


class DecisionClass(str, Enum):
    """Per Phase 1 audit 4.7 (proposal A-H), replacing the current 4-tier
    Strong/Promising/Early-stage/Low-priority scale used in
    botanical_rd_candidate_engine.py. NOT wired in yet — introducing
    this is a Phase 4/6 migration, done deliberately (old scoring
    thresholds don't map 1:1 onto these 8 classes) rather than bundled
    into this contract-definition step."""
    VERIFIED_COMMERCIAL_ROUTE = "A. Verified commercial route"
    ESTABLISHED_SCIENTIFIC_CANDIDATE = "B. Established scientific candidate"
    ALTERNATIVE_SOURCE_RD_CANDIDATE = "C. Alternative-source R&D candidate"
    MECHANISM_BASED_RD_CANDIDATE = "D. Mechanism-based R&D candidate"
    WHITE_SPACE_OPPORTUNITY = "E. White-space opportunity"
    EXPLORATORY_HYPOTHESIS = "F. Exploratory hypothesis"
    HOLD_INSUFFICIENT_EVIDENCE = "G. Hold / insufficient evidence"
    NO_GO_SAFETY_CONCERN = "H. No-go / safety concern"


class SynergyEvidence(str, Enum):
    """Per Phase 1 audit 4.12 — co-occurrence is not synergy."""
    CO_OCCURRENCE_CONFIRMED = "Co-occurrence confirmed"
    ADDITIVE_EFFECT_SUGGESTED = "Additive effect suggested"
    SYNERGY_EXPERIMENTALLY_DEMONSTRATED = "Synergy experimentally demonstrated"
    INTERACTION_UNKNOWN = "Interaction unknown"
    POTENTIAL_ANTAGONISM = "Potential antagonism"


class ExtractionSuitability(str, Enum):
    """Per Phase 1 audit 4.11 — keeps "we inferred this" visibly
    separate from "this was actually reported/measured"."""
    METHOD_REPORTED = "Extraction method reported"
    COMPOUND_DETECTED_IN_EXTRACT = "Compound detected in that extract"
    EXTRACTION_YIELD_REPORTED = "Extraction yield reported"
    SUITABLE_FOR_DOSAGE_FORM = "Method suitable for selected dosage form"
    SUITABILITY_INFERRED_ONLY = "Suitability inferred only"


class EvidenceApplicability(str, Enum):
    """Task 10.2 — evidence-ITEM-level preparation applicability.

    Deliberately separate from ExtractionSuitability (4.11, above):
    ExtractionSuitability describes whether a compound's extraction
    method is reported/suitable — a claim about the EXTRACTION. This
    enum describes whether ONE evidence record, as a whole, can
    reasonably inform the proposed product concept (selected
    indication / dosage form / preparation) — a claim about the
    EVIDENCE ITEM'S transferability. Conflating the two was flagged
    explicitly and rejected; this enum must not be assigned to
    ExtractionSuitability fields or vice versa.

    Ordered strongest-to-weakest for `APPLICABILITY_STRENGTH_ORDER`
    below, mirroring the EVIDENCE_HIERARCHY_ORDER pattern. NOT_ASSESSABLE
    and NOT_APPLICABLE are intentionally excluded from ranking as
    "applicable" — see
    botanical_rd_candidate_engine._summarize_applicability().
    """
    DIRECTLY_APPLICABLE = "Directly applicable"
    PARTIALLY_APPLICABLE = "Partially applicable"
    INDIRECTLY_RELEVANT = "Indirectly relevant"
    NOT_ASSESSABLE = "Not assessable"
    NOT_APPLICABLE = "Not applicable"


# Strongest-first order, for "what is the best applicability found among
# this candidate's evidence items" — NOT_ASSESSABLE/NOT_APPLICABLE are
# intentionally excluded from ranking as "applicable" (see
# botanical_rd_candidate_engine._summarize_applicability()).
APPLICABILITY_STRENGTH_ORDER = [
    EvidenceApplicability.DIRECTLY_APPLICABLE,
    EvidenceApplicability.PARTIALLY_APPLICABLE,
    EvidenceApplicability.INDIRECTLY_RELEVANT,
]


# ======================================================================
# Core entities
# ======================================================================

@dataclass
class Plant:
    """A botanical taxon. `scientific_name` is the accepted/canonical
    name this record is filed under; `synonyms` and `raw_name_variants`
    hold every other name (hybrid/infraspecific taxonomy, common
    misspellings, database-specific formatting) known to refer to the
    same plant, so lookups don't silently miss real matches."""
    scientific_name: str
    accepted_taxonomic_name: Optional[str] = None
    synonyms: list = field(default_factory=list)
    common_names: list = field(default_factory=list)
    family: Optional[str] = None
    native_region: Optional[str] = None
    plant_parts_known: list = field(default_factory=list)
    traditional_system: Optional[str] = None
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    source_record_ids: list = field(default_factory=list)


@dataclass
class Compound:
    """A chemical compound, with the identifiers needed for real
    chemical-similarity comparison (Phase 1 audit 4.8) rather than
    name-string matching alone."""
    compound_name: str
    synonyms: list = field(default_factory=list)
    compound_class: Optional[str] = None
    pubchem_cid: Optional[str] = None
    chembl_id: Optional[str] = None
    smiles: Optional[str] = None
    inchikey: Optional[str] = None
    molecular_fingerprint: Optional[str] = None
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    source_record_ids: list = field(default_factory=list)


@dataclass
class PlantCompoundOccurrence:
    """A single claim that a compound occurs in a plant. Every field
    the Phase 1 audit (4.9) required is here — deliberately granular
    (plant PART, detection METHOD, dry/fresh BASIS, extraction SOLVENT)
    so an occurrence in one plant part/extract is never silently
    generalized to the whole plant or a different dosage form."""
    plant_scientific_name: str
    accepted_taxonomic_name: Optional[str]
    plant_synonym_used: Optional[str]
    compound_id: str
    plant_part: Optional[str] = None
    detection_method: Optional[str] = None
    concentration_value: Optional[float] = None
    concentration_unit: Optional[str] = None
    extract_basis: Optional[str] = None  # e.g. "% total extract"
    dry_fresh_basis: Optional[str] = None  # "dry weight" | "fresh weight" | None
    extraction_solvent: Optional[str] = None
    study_or_source: Optional[str] = None
    confidence: Optional[float] = None  # 0-100, or None if unscored
    verification_status: VerificationStatus = VerificationStatus.UNKNOWN
    source_record_ids: list = field(default_factory=list)


@dataclass
class TargetMechanism:
    """A biological target/pathway/mechanism, and how a compound's
    relationship to it was established (see SimilarityType) — a
    'target_verified' match is only as informative as this record says
    it is."""
    target_name: str
    target_type: Optional[str] = None  # e.g. "receptor", "enzyme", "pathway"
    organ_system: Optional[str] = None
    similarity_type: Optional[SimilarityType] = None
    specificity_compound_count: Optional[int] = None  # how many compounds DB-wide share this target
    source_record_ids: list = field(default_factory=list)


@dataclass
class ScientificEvidence:
    """A single evidence record. Per Phase 1 audit 4.14/4.15 — includes
    both the fields needed to judge evidence QUALITY and the fields
    needed to flag NEGATIVE/contradictory findings, so confirmation
    bias (only positive evidence being retained) can't happen silently."""
    source_type: Optional[str] = None
    doi_pmid_url: Optional[str] = None
    study_type: Optional[str] = None
    population: Optional[str] = None  # "human" | "animal" | "in vitro"
    sample_size: Optional[int] = None
    intervention: Optional[str] = None
    comparator: Optional[str] = None
    dose: Optional[str] = None
    duration: Optional[str] = None
    outcome: Optional[str] = None
    statistical_result: Optional[str] = None
    plant_identity_verified: Optional[bool] = None
    extract_characterized: Optional[bool] = None
    risk_of_bias: Optional[str] = None
    relevance_to_dosage_form: Optional[str] = None
    relevance_to_indication: Optional[str] = None
    confidence_score: Optional[float] = None  # 0-100
    evidence_hierarchy_level: Optional[EvidenceHierarchyLevel] = None
    is_negative_or_contradictory: bool = False
    negative_finding_type: Optional[str] = None  # "failed trial" | "null result" | "retraction" | ...
    source_record_id: Optional[str] = None

    # Task 11.1 — Task 10.2's Preparation Applicability fields, added
    # additively so ScientificEvidence can represent everything a real
    # evidence_records row already carries. Deliberately NOT collapsed
    # into relevance_to_dosage_form/relevance_to_indication above:
    # those two predate the EvidenceApplicability enum, are untyped
    # free strings, and were never wired to the conservative,
    # dimension-based classification standard_evidence_builder.py
    # actually computes (see that module's docstring) — reusing them
    # here would silently narrow a 5-value controlled vocabulary with
    # an explicit rationale/evaluated/missing/mismatch breakdown back
    # down to an untyped string, losing information Task 10.2
    # deliberately added.
    applicability_classification: Optional[EvidenceApplicability] = None
    applicability_rationale: Optional[str] = None
    applicability_evaluated_dimensions: list = field(default_factory=list)
    applicability_missing_dimensions: list = field(default_factory=list)
    applicability_detected_mismatches: list = field(default_factory=list)


@dataclass
class CommercialProduct:
    """An actual marketed product — per Phase 1 audit 4.5, deliberately
    NOT the same thing as "a plant name appeared in commercial-sounding
    text". Every field here has to be populated from a real product
    record, not inferred from a plant/compound occurrence."""
    product_name: str
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    country_market: Optional[str] = None
    ingredient_list: list = field(default_factory=list)
    plant_species: Optional[str] = None
    plant_part: Optional[str] = None
    extract_ratio: Optional[str] = None
    standardization_marker: Optional[str] = None
    dosage_form: Optional[str] = None
    claims: list = field(default_factory=list)
    regulatory_category: Optional[str] = None
    retail_or_official_source: Optional[str] = None
    first_verified_date: Optional[date] = None
    last_verified_date: Optional[date] = None
    availability_status: Optional[str] = None
    source_record_ids: list = field(default_factory=list)


@dataclass
class RegulatoryRecord:
    """A regulatory status claim — per Phase 1 audit 4.6/4.17, scoped
    explicitly to WHICH herb form/extract/indication/dosage form/market
    it applies to, since a plant can be commercial for one extract and
    an R&D opportunity for another."""
    status: MarketVerificationStatus
    jurisdiction_or_market: Optional[str] = None
    monograph_source: Optional[str] = None  # e.g. "EMA/HMPC", "WHO", "ESCOP"
    scope_whole_herb_or_extract: Optional[str] = None
    scope_traditional_indication: Optional[str] = None
    scope_dosage_form: Optional[str] = None
    last_verified_date: Optional[date] = None
    source_record_ids: list = field(default_factory=list)


@dataclass
class SafetyInteraction:
    """A single safety/interaction record with full context — per
    Phase 1 audit 4.13. A hazard tag with no context (dose, route,
    species) is close to useless for a real go/no-go decision, and
    "no adverse events reported" must never be storable as if it were
    itself a hazard flag (existing tests already guard the ENGINE side
    of this; this dataclass guards the DATA side)."""
    compound_or_whole_plant: str
    dose: Optional[str] = None
    duration: Optional[str] = None
    plant_part: Optional[str] = None
    extract: Optional[str] = None
    route: Optional[str] = None
    species_or_human: Optional[str] = None
    adverse_event: Optional[str] = None
    severity: Optional[str] = None
    causality: Optional[str] = None
    contraindication: Optional[str] = None
    pregnancy_lactation_risk: Optional[str] = None
    hepatic_renal_risk: Optional[str] = None
    cyp_interaction: Optional[str] = None
    drug_class_interaction: Optional[str] = None
    source_quality: Optional[str] = None
    source_record_id: Optional[str] = None


@dataclass
class CandidateAssessment:
    """The final, explainable per-row output — per Phase 1 audit
    section 6. This is the eventual replacement shape for today's
    R&D-candidate CSV row; Evidence_Confidence and R&D_Opportunity_Score
    are separate fields on purpose (Phase 1 audit 4.16: opportunity
    without confidence must never look like a strong recommendation).
    `source_record_ids` and `evidence_gaps` exist so no row can be
    "just generated text" — every claim traces to something, and every
    known unknown is named rather than silently absent."""
    project_id: str
    indication: str
    product_type: Optional[str]
    dosage_form: Optional[str]
    target_market: Optional[str]

    reference_plant: str
    reference_plant_part: Optional[str]
    reference_compound: Optional[str]
    reference_compound_id: Optional[str]

    alternative_plant: str
    alternative_plant_part: Optional[str]
    alternative_compound: Optional[str]
    alternative_compound_id: Optional[str]

    match_type: Optional[str] = None
    chemical_similarity: Optional[SimilarityType] = None
    target_or_mechanism: Optional[str] = None
    occurrence_evidence: Optional[str] = None

    concentration_value: Optional[float] = None
    concentration_unit: Optional[str] = None
    concentration_basis: Optional[str] = None

    extraction_method: Optional[str] = None
    extraction_fit: Optional[ExtractionSuitability] = None

    co_compounds: list = field(default_factory=list)
    synergy_evidence: Optional[SynergyEvidence] = None

    safety_flags: list = field(default_factory=list)
    interaction_flags: list = field(default_factory=list)

    regulatory_status: Optional[MarketVerificationStatus] = None
    verified_product_count: int = 0
    market_status: Optional[MarketVerificationStatus] = None
    novelty_status: Optional[str] = None

    evidence_confidence: Optional[float] = None  # 0-100, separate from opportunity
    rd_opportunity_score: Optional[float] = None  # 0-100
    decision_class: Optional[DecisionClass] = None

    evidence_gaps: list = field(default_factory=list)
    rationale: Optional[str] = None
    source_record_ids: list = field(default_factory=list)
    last_verified: Optional[date] = None

    # ------------------------------------------------------------------
    # Added post-Phase-3, as the real OUTPUT_COLUMNS grew (Phase 4-6,
    # architecture-audit gap fixes, and the external-review fixes
    # rounds). Appended here rather than interleaved above so every
    # EXISTING positional or keyword instantiation of this class keeps
    # working unchanged — this class's job is to track the real schema,
    # not to enforce a particular field order.
    # ------------------------------------------------------------------
    target_provenance: Optional[str] = None
    evidence_source: Optional[str] = None
    occurrence_corroboration: Optional[str] = None
    candidate_evidence_strength_tier: Optional[str] = None
    evidence_level: Optional[str] = None
    evidence_hierarchy_detail: Optional[str] = None
    has_negative_evidence: Optional[bool] = None
    negative_evidence_types: list = field(default_factory=list)
    regulatory_barriers: list = field(default_factory=list)
    industrial_feasibility: Optional[str] = None
    score_breakdown: Optional[str] = None
    decision_class_ah: Optional[str] = None
    white_space_type: Optional[str] = None
    confidence_note: Optional[str] = None
    go_investigate_hold_no_go: Optional[str] = None
    scientific_rationale: Optional[str] = None
    commercial_regulatory_rationale: Optional[str] = None
    evidence_strengths: list = field(default_factory=list)
    evidence_weaknesses: list = field(default_factory=list)
    next_experiment_suggestion: Optional[str] = None
    comparative_rationale: Optional[str] = None

    # Task 1 — Formal Gate Layer. Additive only: a dict of exactly four
    # keys (safety / identity / minimum_evidence / regulatory), each
    # mapping to {"gate_name": <same key>, "status": GateStatus,
    # "reason": str, "evidence": str} (see
    # botanical_rd_candidate_engine._evaluate_gates). None on any row
    # produced before this field existed — never backfilled or
    # inferred. Does not replace or alter decision_class in any way.
    gate_results: Optional[dict] = None

    # Task 3 — records which ScoringConfig (see
    # botanical_rd_candidate_engine.ScoringConfig) this row's
    # rd_opportunity_score was computed with. Purely descriptive
    # metadata — never read back into scoring. None on any row
    # produced before this field existed.
    scoring_config_version: Optional[str] = None

    # Task 10.2 — Evidence-level Preparation Applicability. Additive
    # only: a dict summarizing the EvidenceApplicability classification
    # of every evidence item matched to this candidate (see
    # botanical_rd_candidate_engine._summarize_applicability() for the
    # exact shape). Never read by _decision_class(), _score_candidate(),
    # _evaluate_gates(), or go_investigate_hold_no_go() — carries no
    # influence on Decision_Class, Decision_Class_AH,
    # R&D_Opportunity_Score, gate outcomes, or ranking. None on any row
    # produced before this field existed — never backfilled or inferred.
    applicability_summary: Optional[dict] = None


# ======================================================================
# Shared helpers
# ======================================================================

def completeness_report(entity) -> dict:
    """For any dataclass instance above: which fields are populated vs.
    None/empty, and a 0-100 completeness score. This is the building
    block for the "Data Completeness Score" the Phase 1 audit (4.4)
    asked for — one row's completeness here, aggregate however the
    caller needs (per-table, per-run, etc.)."""
    values = asdict(entity)
    total = len(values)
    missing = []
    for key, value in values.items():
        if value is None or value == [] or value == {} or value == "":
            missing.append(key)
    populated = total - len(missing)
    return {
        "populated_fields": populated,
        "total_fields": total,
        "missing_fields": missing,
        "completeness_score": round(100 * populated / total, 1) if total else 0.0,
    }


def evidence_hierarchy_rank(level: Optional[EvidenceHierarchyLevel]) -> int:
    """Lower rank = stronger evidence. None (unknown/no evidence) ranks
    weakest, past even COMPUTATIONAL_HYPOTHESIS, since "we don't know
    what kind of evidence this is" is not the same claim as "this is a
    computational hypothesis" — it's weaker, and should sort weaker."""
    if level is None:
        return len(EVIDENCE_HIERARCHY_ORDER)
    return EVIDENCE_HIERARCHY_ORDER.index(level)


def is_evidence_at_least(
    level: Optional[EvidenceHierarchyLevel],
    minimum: EvidenceHierarchyLevel,
) -> bool:
    """True if `level` is at least as strong as `minimum` on the
    hierarchy (lower rank = stronger, so 'at least as strong' means
    rank <= minimum's rank)."""
    return evidence_hierarchy_rank(level) <= evidence_hierarchy_rank(minimum)


def dataclass_field_names(dc_type) -> list:
    """Convenience: field names of any dataclass above, e.g. for
    building a DataFrame column order or a Supabase table's expected
    columns."""
    return [f.name for f in fields(dc_type)]
