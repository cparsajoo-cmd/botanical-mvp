"""ADMET / Developability decision-support layer.

WHAT THIS MODULE IS
A SEPARATE, additive, downstream decision-support annotation on top of the
already-validated Stage-6 report-ready frame (merge_authoritative_scores()'s
output). It is deliberately NOT part of the scoring/ranking architecture:
nothing in this module reads or writes R&D_Opportunity_Score, Overall_Score,
Decision_Class_AH, Go_Investigate_Hold_NoGo, or any other authoritative
field, and it never changes candidate inclusion/exclusion or ranking order.

WHY IT IS SEPARATE (architecture note, 2026-09-11)
The platform's existing "safety" layer (safety_assertion_engine.py) answers
a different question: what does the RETRIEVED LITERATURE say about a
candidate's safety (contraindications, interactions, adverse events)? This
module answers a complementary, compound-structural question: what do this
candidate's linked COMPOUNDS' own physicochemical/pharmacokinetic
properties suggest about developability (absorption, distribution,
metabolism, excretion) and what does the project's own curated compound
data say about compound-level toxicity? The two are combined only at the
plant-level toxicity dimension (see aggregate_plant_admet()), and even
then the evidence-based safety signal is always treated as authoritative
over the internally curated one -- literature evidence outranks a curated
category label. safety_assertion_engine.py itself is never modified or
duplicated by this module.

DATA SOURCES USED (V1) -- see each source's own provenance tag below
  1. DATABASE_DERIVED_INTERNAL_CURATED: the project's own `compound_profiles`
     Supabase table (compound_profile_database.py / compound_profile_seed.py
     -- ~310 curated records), which already carries per-compound
     `bioavailability` and `toxicity` categorical ratings (Low/Medium/High).
     These are internally curated (source field typically "Internal curated
     seed"), NOT independently verified against an external toxicology
     database -- always labelled as such, never presented as experimental.
  2. PROPERTY_DERIVED_COMPUTATIONAL: PubChem computed physicochemical
     descriptors (MolecularWeight, XLogP, TPSA, HBondDonorCount,
     HBondAcceptorCount, RotatableBondCount), fetched via the new
     pubchem_connector.resolve_compound_properties() (batched by CID,
     added additively -- existing PubChem functions are untouched).
     Interpreted only through the well-established Lipinski Rule-of-Five /
     Veber oral-bioavailability heuristics -- a molecular-descriptor-based
     absorption INTERPRETATION, explicitly never called a direct ADMET
     measurement or prediction of metabolism/excretion/toxicity.
  3. EVIDENCE_BASED_SAFETY: the existing, already-computed plant-level
     Safety_Assertion_Status / Safety_Concern_Level / Safety_Status_Rationale
     / Safety_Evidence_IDs fields (safety_assertion_engine.py, reused
     verbatim, never recomputed here).
  4. INSUFFICIENT_DATA: the explicit, honest default for every dimension
     this platform has no genuine data source for yet (Distribution,
     Metabolism, Excretion in V1 -- no BBB/PPB/CYP/renal-excretion data
     source exists in this codebase). Missing data is never treated as
     favorable.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
  - It does not average compound-level signals into a single numeric
    "ADMET score". Status labels are categorical and rule-based.
  - It does not claim a single compound's ADMET profile is the ADMET
    profile of the whole plant/extract -- every plant-level output is
    explicitly an AGGREGATED, compound-driven interpretation (see the
    `disclaimer` field on every aggregate_plant_admet() result).
  - It does not fabricate Metabolism/Excretion/Distribution values. V1
    intentionally leaves these INSUFFICIENT_DATA absent a genuine data
    source (documented, not silently skipped).
  - It never raises out of attach_admet_developability() for a single
    candidate's failure; see that function's per-row isolation.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

import pandas as pd

from compound_plant_resolver import normalize_compound_name

ADMET_MODULE_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

# Overall plant/candidate-level decision-support label (section 7 of spec).
# Deliberately only four values, used ONLY for the plant-level
# overall_developability_status -- never for individual dimensions, which
# use their own, more descriptive vocabularies below so nuance is not lost.
OVERALL_FAVORABLE = "FAVORABLE"
OVERALL_REVIEW = "REVIEW"
OVERALL_HIGH_CONCERN = "HIGH_CONCERN"
OVERALL_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
OVERALL_UNAVAILABLE = "ADMET_ASSESSMENT_UNAVAILABLE"  # per-row failure fallback only

# Compound/plant-level Absorption status (property-derived interpretation).
ABSORPTION_FAVORABLE = "FAVORABLE_PROPERTY_PROFILE"
ABSORPTION_REVIEW = "REVIEW_PROPERTY_PROFILE"
ABSORPTION_POOR = "POOR_PROPERTY_PROFILE"
ABSORPTION_DATABASE_FAVORABLE = "FAVORABLE_CURATED_BIOAVAILABILITY"
ABSORPTION_DATABASE_REVIEW = "REVIEW_CURATED_BIOAVAILABILITY"
ABSORPTION_INSUFFICIENT = "INSUFFICIENT_DATA"

# Plant-level Toxicity status (evidence-based safety engine is authoritative;
# curated compound-level toxicity ratings are a secondary, capped signal).
TOXICITY_SERIOUS = "SERIOUS_CONCERN"
TOXICITY_MODERATE = "MODERATE_CONCERN"
TOXICITY_CONFLICTING = "CONFLICTING_EVIDENCE"
TOXICITY_CURATED_FLAG = "CURATED_CONCERN_UNVERIFIED"
TOXICITY_LIMITED_REASSURANCE = "NO_CONCERN_SIGNAL_LIMITED_EVIDENCE"
TOXICITY_INSUFFICIENT = "INSUFFICIENT_DATA"

# Provenance tags -- every signal produced by this module carries one.
PROVENANCE_DATABASE_CURATED = "DATABASE_DERIVED_INTERNAL_CURATED"
PROVENANCE_PROPERTY_COMPUTATIONAL = "PROPERTY_DERIVED_COMPUTATIONAL"
PROVENANCE_EVIDENCE_SAFETY = "EVIDENCE_BASED_SAFETY_LITERATURE"
PROVENANCE_INSUFFICIENT = "INSUFFICIENT_DATA"

# Lipinski Rule-of-Five + Veber oral-bioavailability descriptor thresholds.
# Standard, widely published med-chem heuristics -- not calibrated by this
# project, not a substitute for a real ADMET prediction model.
_LIPINSKI_VEBER_RULES = (
    ("MolecularWeight", lambda v: v <= 500, "Molecular weight > 500 Da"),
    ("XLogP", lambda v: v <= 5, "Calculated LogP > 5"),
    ("HBondDonorCount", lambda v: v <= 5, "H-bond donors > 5"),
    ("HBondAcceptorCount", lambda v: v <= 10, "H-bond acceptors > 10"),
    ("RotatableBondCount", lambda v: v <= 10, "Rotatable bonds > 10 (Veber)"),
    ("TPSA", lambda v: v <= 140, "Topological polar surface area > 140 \u00c5\u00b2 (Veber)"),
)

# Bound on how many linked compounds are assessed per plant candidate --
# purely a performance/noise guard (a plant with 40 catalogued compounds
# should not fan out into 40 property lookups); does not affect ranking.
MAX_COMPOUNDS_PER_PLANT = 15


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, float) and pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _norm_lower(value: Any) -> str:
    return _clean(value).lower()


# ---------------------------------------------------------------------------
# Step 1: compound-level assessment
# ---------------------------------------------------------------------------

def _lipinski_veber_assessment(properties: Mapping[str, Any] | None) -> dict[str, Any]:
    """Property-derived (computational) absorption-related interpretation.

    Returns INSUFFICIENT_DATA whenever fewer than half of the six
    descriptors are actually present -- a profile built on 1-2 of 6
    descriptors is not a defensible basis for a status, even a cautious
    one.
    """
    props = properties or {}
    present = {name: props.get(name) for name, _, _ in _LIPINSKI_VEBER_RULES if props.get(name) is not None}
    if len(present) < 3:
        return {
            "status": ABSORPTION_INSUFFICIENT,
            "evidence_level": PROVENANCE_INSUFFICIENT,
            "violations": [],
            "descriptors_used": present,
        }

    violations = []
    for name, rule_ok, label in _LIPINSKI_VEBER_RULES:
        value = props.get(name)
        if value is None:
            continue
        try:
            if not rule_ok(float(value)):
                violations.append(label)
        except (TypeError, ValueError):
            continue

    if len(violations) == 0:
        status = ABSORPTION_FAVORABLE
    elif len(violations) == 1:
        status = ABSORPTION_REVIEW
    else:
        status = ABSORPTION_POOR

    return {
        "status": status,
        "evidence_level": PROVENANCE_PROPERTY_COMPUTATIONAL,
        "violations": violations,
        "descriptors_used": present,
    }


def _curated_bioavailability_assessment(compound_profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Database-derived (internal curated) absorption-related signal from
    the compound_profiles table's own `bioavailability` field, when present.
    """
    if not compound_profile:
        return {"status": ABSORPTION_INSUFFICIENT, "evidence_level": PROVENANCE_INSUFFICIENT, "rating": None}
    rating = _clean(compound_profile.get("bioavailability"))
    if not rating:
        return {"status": ABSORPTION_INSUFFICIENT, "evidence_level": PROVENANCE_INSUFFICIENT, "rating": None}
    rating_lower = rating.lower()
    if rating_lower == "high":
        status = ABSORPTION_DATABASE_FAVORABLE
    elif rating_lower == "medium":
        status = ABSORPTION_DATABASE_REVIEW
    elif rating_lower == "low":
        status = ABSORPTION_DATABASE_REVIEW
    else:
        status = ABSORPTION_INSUFFICIENT
    return {"status": status, "evidence_level": PROVENANCE_DATABASE_CURATED, "rating": rating}


def _curated_toxicity_signal(compound_profile: Mapping[str, Any] | None) -> dict[str, Any]:
    """Database-derived (internal curated) compound-level toxicity rating
    from compound_profiles.toxicity, when present. This is a SECONDARY
    signal at the plant level (see aggregate_plant_admet) -- explicitly
    capped below the evidence-based safety engine's authority and never
    presented as independently verified or experimental.
    """
    if not compound_profile:
        return {"status": TOXICITY_INSUFFICIENT, "evidence_level": PROVENANCE_INSUFFICIENT, "rating": None}
    rating = _clean(compound_profile.get("toxicity"))
    if not rating:
        return {"status": TOXICITY_INSUFFICIENT, "evidence_level": PROVENANCE_INSUFFICIENT, "rating": None}
    flagged = rating.lower() in ("medium", "high")
    return {
        "status": TOXICITY_CURATED_FLAG if flagged else TOXICITY_INSUFFICIENT,
        "evidence_level": PROVENANCE_DATABASE_CURATED,
        "rating": rating,
    }


def assess_compound_admet(
    compound_name: Any,
    *,
    pubchem_properties: Mapping[str, Any] | None = None,
    compound_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assess ONE compound across the available ADMET-relevant dimensions.

    ``pubchem_properties``: {"MolecularWeight": ..., "XLogP": ..., "TPSA":
    ..., "HBondDonorCount": ..., "HBondAcceptorCount": ...,
    "RotatableBondCount": ...} -- as returned by
    pubchem_connector.resolve_compound_properties(). May be None/empty.

    ``compound_profile``: one row (dict-like) from the project's
    compound_profiles table, matched by compound name. May be None.

    Distribution/Metabolism/Excretion are returned as INSUFFICIENT_DATA in
    V1 -- this platform has no genuine BBB/plasma-protein-binding/CYP/renal-
    excretion data source. The keys are still present (with an explicit
    reason) so callers/UI never have to special-case a missing dimension.

    Never raises: malformed inputs degrade to INSUFFICIENT_DATA fields
    rather than an exception, so one bad compound record cannot break a
    whole plant's assessment.
    """
    name = _clean(compound_name)

    try:
        property_result = _lipinski_veber_assessment(pubchem_properties)
    except Exception:
        property_result = {"status": ABSORPTION_INSUFFICIENT, "evidence_level": PROVENANCE_INSUFFICIENT, "violations": [], "descriptors_used": {}}

    try:
        curated_absorption = _curated_bioavailability_assessment(compound_profile)
    except Exception:
        curated_absorption = {"status": ABSORPTION_INSUFFICIENT, "evidence_level": PROVENANCE_INSUFFICIENT, "rating": None}

    # Prefer the database-derived (curated) bioavailability rating over the
    # computational descriptor heuristic when a real curated rating exists
    # -- it is a more directly relevant signal than a generic physchem rule
    # -- but always retain BOTH in `details` so nothing is hidden.
    if curated_absorption["status"] != ABSORPTION_INSUFFICIENT:
        absorption_status = curated_absorption["status"]
        absorption_evidence_level = curated_absorption["evidence_level"]
    else:
        absorption_status = property_result["status"]
        absorption_evidence_level = property_result["evidence_level"]

    absorption_details = []
    if curated_absorption["status"] != ABSORPTION_INSUFFICIENT:
        absorption_details.append(
            f"Curated bioavailability rating: {curated_absorption['rating']} "
            f"(internal curated compound profile, not independently verified)."
        )
    if property_result["status"] != ABSORPTION_INSUFFICIENT:
        if property_result["violations"]:
            absorption_details.append(
                "Molecular-descriptor absorption liability flags (Lipinski/Veber, "
                "property-derived interpretation, not a direct measurement): "
                + "; ".join(property_result["violations"]) + "."
            )
        else:
            absorption_details.append(
                "No Lipinski/Veber descriptor violations found (property-derived "
                "interpretation, not a direct measurement)."
            )
    if not absorption_details:
        absorption_details.append("Insufficient data: no curated bioavailability rating and no usable molecular descriptors.")

    try:
        curated_tox = _curated_toxicity_signal(compound_profile)
    except Exception:
        curated_tox = {"status": TOXICITY_INSUFFICIENT, "evidence_level": PROVENANCE_INSUFFICIENT, "rating": None}

    toxicity_details = []
    if curated_tox["status"] == TOXICITY_CURATED_FLAG:
        toxicity_details.append(
            f"Compound-level curated toxicity rating: {curated_tox['rating']} "
            f"(internal curated compound profile, not independently verified; "
            f"this does NOT by itself establish whole-extract toxicity)."
        )
    else:
        toxicity_details.append("No curated compound-level toxicity rating available for this compound.")

    return {
        "compound": name,
        "absorption": {
            "status": absorption_status,
            "evidence_level": absorption_evidence_level,
            "details": absorption_details,
        },
        "distribution": {
            "status": ABSORPTION_INSUFFICIENT,
            "evidence_level": PROVENANCE_INSUFFICIENT,
            "details": ["Insufficient data: no blood-brain-barrier / plasma-protein-binding data source is integrated in this platform (V1)."],
        },
        "metabolism": {
            "status": ABSORPTION_INSUFFICIENT,
            "evidence_level": PROVENANCE_INSUFFICIENT,
            "details": ["Insufficient data: no CYP interaction data source is integrated in this platform (V1)."],
        },
        "excretion": {
            "status": ABSORPTION_INSUFFICIENT,
            "evidence_level": PROVENANCE_INSUFFICIENT,
            "details": ["Insufficient data: no excretion/clearance data source is integrated in this platform (V1)."],
        },
        "compound_toxicity_signal": {
            "status": curated_tox["status"],
            "evidence_level": curated_tox["evidence_level"],
            "details": toxicity_details,
        },
    }


# ---------------------------------------------------------------------------
# Step 2: plant-level aggregation
# ---------------------------------------------------------------------------

def _aggregate_absorption(compound_assessments: list[dict[str, Any]]) -> dict[str, Any]:
    resolved = [c for c in compound_assessments if c["absorption"]["status"] != ABSORPTION_INSUFFICIENT]
    if not resolved:
        return {
            "status": ABSORPTION_INSUFFICIENT,
            "compounds_flagged": [],
            "details": ["No linked compound had usable bioavailability data or molecular descriptors."],
        }

    poor = [c["compound"] for c in resolved if c["absorption"]["status"] in (ABSORPTION_POOR,)]
    review = [
        c["compound"] for c in resolved
        if c["absorption"]["status"] in (ABSORPTION_REVIEW, ABSORPTION_DATABASE_REVIEW)
    ]
    favorable = [
        c["compound"] for c in resolved
        if c["absorption"]["status"] in (ABSORPTION_FAVORABLE, ABSORPTION_DATABASE_FAVORABLE)
    ]

    if poor:
        return {
            "status": ABSORPTION_POOR,
            "compounds_flagged": poor,
            "details": [f"{len(poor)}/{len(resolved)} assessed compound(s) show a developability-liability property profile: " + ", ".join(poor) + "."],
        }
    if review:
        return {
            "status": ABSORPTION_REVIEW,
            "compounds_flagged": review,
            "details": [f"{len(review)}/{len(resolved)} assessed compound(s) show a borderline or medium/low curated bioavailability profile: " + ", ".join(review) + "."],
        }
    return {
        "status": ABSORPTION_FAVORABLE,
        "compounds_flagged": [],
        "details": [f"{len(favorable)}/{len(resolved)} assessed compound(s) show a favorable absorption-related profile."],
    }


def _aggregate_toxicity(
    safety_fields: Mapping[str, Any] | None,
    compound_assessments: list[dict[str, Any]],
) -> dict[str, Any]:
    """Plant-level toxicity: the existing, evidence-based safety engine
    output is authoritative; curated compound-level toxicity ratings are a
    secondary, EXPLICITLY CAPPED signal (can raise INSUFFICIENT_DATA to
    REVIEW-equivalent territory, but can never by themselves produce
    SERIOUS_CONCERN -- an unverified curated label is not strong enough
    evidence for the platform's highest-severity toxicity label).
    """
    safety = safety_fields or {}
    status_field = _clean(safety.get("Safety_Assertion_Status"))
    concern_level = _clean(safety.get("Safety_Concern_Level")).upper()
    rationale = _clean(safety.get("Safety_Status_Rationale"))
    evidence_ids = safety.get("Safety_Evidence_IDs") or ()

    details = []
    curated_flags = [
        c["compound"] for c in compound_assessments
        if c["compound_toxicity_signal"]["status"] == TOXICITY_CURATED_FLAG
    ]

    if status_field == "CONFLICTING_SAFETY_EVIDENCE":
        status = TOXICITY_CONFLICTING
        details.append("Conflicting risk-present and risk-absent safety evidence was retrieved for this plant (existing safety engine); unresolved, not evidence of safety.")
    elif status_field in ("SAFETY_CONCERN_RETRIEVED", "INTERACTION_SIGNAL_RETRIEVED"):
        if concern_level == "SERIOUS":
            status = TOXICITY_SERIOUS
        else:
            status = TOXICITY_MODERATE
        if rationale:
            details.append(rationale)
        else:
            details.append("A safety/interaction concern was retrieved from the evidence (existing safety engine).")
    elif status_field == "STUDY_SPECIFIC_REASSURANCE_ONLY":
        status = TOXICITY_LIMITED_REASSURANCE
        details.append("Only study-specific reassurance evidence was retrieved (existing safety engine); this does not establish general safety.")
    elif curated_flags:
        # No literature-derived safety signal at all, but at least one
        # linked compound carries an unverified curated Medium/High
        # toxicity rating -- surfaced as a REVIEW-level (not serious) flag.
        status = TOXICITY_CURATED_FLAG
        details.append(
            f"No literature-derived safety concern was retrieved, but {len(curated_flags)} linked "
            f"compound(s) carry an unverified, internally curated Medium/High toxicity rating: "
            + ", ".join(curated_flags) + ". Recommend targeted verification before relying on this."
        )
    else:
        status = TOXICITY_INSUFFICIENT
        details.append("No literature-derived safety evidence and no curated compound-level toxicity rating available for this plant's linked compounds.")

    return {
        "status": status,
        "compounds_flagged": curated_flags,
        "details": details,
        "source_safety_assertion_status": status_field or None,
        "source_safety_concern_level": concern_level or None,
        "source_safety_evidence_ids": list(evidence_ids) if isinstance(evidence_ids, (list, tuple)) else evidence_ids,
    }


def _overall_status(absorption: dict[str, Any], toxicity: dict[str, Any], compound_coverage: float) -> tuple[str, list[str]]:
    """Deterministic, documented precedence -- see module docstring.
    Returns (status, reasons).
    """
    reasons = []
    if toxicity["status"] == TOXICITY_SERIOUS:
        reasons.append("Serious, literature-evidenced toxicity/safety concern (existing safety engine).")
        return OVERALL_HIGH_CONCERN, reasons

    if toxicity["status"] in (TOXICITY_MODERATE, TOXICITY_CONFLICTING):
        reasons.append("Moderate or conflicting literature-evidenced safety signal (existing safety engine).")
        return OVERALL_REVIEW, reasons

    if absorption["status"] == ABSORPTION_POOR:
        reasons.append("One or more linked compounds show a poor developability property profile.")
        return OVERALL_REVIEW, reasons

    if toxicity["status"] == TOXICITY_CURATED_FLAG:
        reasons.append("Unverified curated compound-level toxicity flag present (no literature safety signal).")
        return OVERALL_REVIEW, reasons

    if absorption["status"] == ABSORPTION_FAVORABLE and toxicity["status"] == TOXICITY_LIMITED_REASSURANCE:
        reasons.append("Favorable absorption-related profile combined with genuine (study-specific) safety reassurance evidence.")
        return OVERALL_FAVORABLE, reasons

    if absorption["status"] in (ABSORPTION_REVIEW,) or (absorption["status"] == ABSORPTION_FAVORABLE and toxicity["status"] == TOXICITY_INSUFFICIENT):
        reasons.append("Partial developability signal available; not enough evidence for a confident label either way.")
        return OVERALL_REVIEW, reasons

    reasons.append("Insufficient linked-compound and safety data for a meaningful developability assessment.")
    return OVERALL_INSUFFICIENT_DATA, reasons


def aggregate_plant_admet(
    plant_name: Any,
    compound_assessments: list[dict[str, Any]],
    *,
    safety_fields: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate compound-level assess_compound_admet() results into one
    plant-level developability summary. NEVER averages into a numeric
    score; every output is a categorical, traceable status plus the
    specific compounds/evidence that drove it.
    """
    compound_assessments = list(compound_assessments or [])
    compounds_assessed = [c["compound"] for c in compound_assessments]
    compounds_with_usable_data = sum(
        1 for c in compound_assessments
        if c["absorption"]["status"] != ABSORPTION_INSUFFICIENT
        or c["compound_toxicity_signal"]["status"] != TOXICITY_INSUFFICIENT
    )
    compound_coverage = (
        compounds_with_usable_data / len(compound_assessments) if compound_assessments else 0.0
    )

    absorption = _aggregate_absorption(compound_assessments)
    toxicity = _aggregate_toxicity(safety_fields, compound_assessments)

    distribution = {"status": ABSORPTION_INSUFFICIENT, "details": ["Insufficient data: no distribution (BBB/plasma-protein-binding) data source integrated (V1)."]}
    metabolism = {"status": ABSORPTION_INSUFFICIENT, "details": ["Insufficient data: no CYP metabolism data source integrated (V1)."]}
    excretion = {"status": ABSORPTION_INSUFFICIENT, "details": ["Insufficient data: no excretion data source integrated (V1)."]}

    overall_status, overall_reasons = _overall_status(absorption, toxicity, compound_coverage)

    dimensions_resolved = sum(
        1 for dim in (absorption, distribution, metabolism, excretion, toxicity)
        if dim["status"] not in (ABSORPTION_INSUFFICIENT, TOXICITY_INSUFFICIENT)
    )
    dims_total = 5
    completeness_score = round(dimensions_resolved / dims_total, 3)
    if dimensions_resolved == 0:
        completeness_label = "LOW"
    elif dimensions_resolved <= 2:
        completeness_label = "MODERATE"
    else:
        completeness_label = "HIGH"

    key_flags: list[str] = []
    if absorption["compounds_flagged"]:
        key_flags.append("Absorption liability: " + ", ".join(absorption["compounds_flagged"]))
    if toxicity["compounds_flagged"]:
        key_flags.append("Unverified curated toxicity flag: " + ", ".join(toxicity["compounds_flagged"]))
    if toxicity["status"] in (TOXICITY_SERIOUS, TOXICITY_MODERATE, TOXICITY_CONFLICTING):
        key_flags.append("Literature safety signal: " + toxicity["details"][0])

    return {
        "plant": _clean(plant_name),
        "compounds_assessed": compounds_assessed,
        "compounds_assessed_count": len(compound_assessments),
        "compounds_with_usable_data_count": compounds_with_usable_data,
        "compound_data_coverage": round(compound_coverage, 3),
        "absorption": absorption,
        "distribution": distribution,
        "metabolism": metabolism,
        "excretion": excretion,
        "toxicity": toxicity,
        "overall_developability_status": overall_status,
        "overall_status_reasons": overall_reasons,
        "data_completeness_score": completeness_score,
        "data_completeness_label": completeness_label,
        "key_flags": key_flags,
        "compound_level_detail": compound_assessments,
        "module_version": ADMET_MODULE_VERSION,
        "disclaimer": (
            "This is an aggregated, compound-driven decision-support interpretation, "
            "not a measured pharmacokinetic profile of the whole botanical extract. "
            "A single compound's concern does not automatically mean the whole "
            "plant/extract is unsafe; conversely, missing compound toxicity data "
            "must never be read as evidence of safety."
        ),
    }


def _unavailable_result(plant_name: Any, reason: str) -> dict[str, Any]:
    return {
        "plant": _clean(plant_name),
        "compounds_assessed": [],
        "compounds_assessed_count": 0,
        "compounds_with_usable_data_count": 0,
        "compound_data_coverage": 0.0,
        "absorption": {"status": ABSORPTION_INSUFFICIENT, "compounds_flagged": [], "details": [reason]},
        "distribution": {"status": ABSORPTION_INSUFFICIENT, "details": [reason]},
        "metabolism": {"status": ABSORPTION_INSUFFICIENT, "details": [reason]},
        "excretion": {"status": ABSORPTION_INSUFFICIENT, "details": [reason]},
        "toxicity": {"status": TOXICITY_INSUFFICIENT, "compounds_flagged": [], "details": [reason]},
        "overall_developability_status": OVERALL_UNAVAILABLE,
        "overall_status_reasons": [reason],
        "data_completeness_score": 0.0,
        "data_completeness_label": "LOW",
        "key_flags": [],
        "compound_level_detail": [],
        "module_version": ADMET_MODULE_VERSION,
        "disclaimer": (
            "ADMET assessment unavailable for this candidate. This candidate's "
            "ranking, scoring and other results are unaffected."
        ),
    }


# ---------------------------------------------------------------------------
# Step 3: report_df attach function (Stage-6 integration point)
# ---------------------------------------------------------------------------

def _linked_compound_names(row: pd.Series, plant_compounds_df: pd.DataFrame | None) -> list[str]:
    """Prefer the already-computed, indication/evidence-aware
    Discovery_Linked_Compounds field on the report row (candidate_
    shortlisting.py / rd_discovery_classification.py) -- the same field
    compound_source_traceability.py already reads. Falls back to a direct
    plant_compounds_df filter by scientific name (broader, not indication-
    scoped) only when that field is empty/absent, so a candidate still gets
    an assessment even before/without the discovery-lane fields.
    """
    from compound_source_traceability import _compound_names  # reuse, no duplication

    names = _compound_names(row.get("Discovery_Linked_Compounds"))
    if not names and isinstance(plant_compounds_df, pd.DataFrame) and not plant_compounds_df.empty:
        plant = _norm_lower(row.get("Alternative_Plant"))
        if plant and "scientific_name" in plant_compounds_df.columns and "compound_name" in plant_compounds_df.columns:
            mask = plant_compounds_df["scientific_name"].astype(str).str.strip().str.lower() == plant
            names = [
                str(c).strip() for c in plant_compounds_df.loc[mask, "compound_name"].tolist()
                if str(c).strip()
            ]
    # de-duplicate, preserve order, bound the fan-out
    seen: dict[str, None] = {}
    for n in names:
        seen.setdefault(n, None)
    return list(seen.keys())[:MAX_COMPOUNDS_PER_PLANT]


def _compound_profile_lookup(compound_profiles_df: pd.DataFrame | None) -> dict[str, dict[str, Any]]:
    if not isinstance(compound_profiles_df, pd.DataFrame) or compound_profiles_df.empty:
        return {}
    if "compound_name" not in compound_profiles_df.columns:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in compound_profiles_df.iterrows():
        key = normalize_compound_name(row.get("compound_name"))
        if key and key not in lookup:
            lookup[key] = row.to_dict()
    return lookup


def collect_linked_compound_names(
    report_df: pd.DataFrame,
    plant_compounds_df: pd.DataFrame | None = None,
) -> list[str]:
    """Return the de-duplicated UNION of linked compound names across every
    row of ``report_df`` -- intended to be resolved against PubChem exactly
    ONCE per run (see pubchem_connector.resolve_compound_properties()) and
    the resulting property map then passed into attach_admet_developability()
    as ``compound_property_map``. Never call PubChem per-row/per-plant.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return []
    if "Alternative_Plant" not in report_df.columns:
        return []
    seen: dict[str, None] = {}
    for _, row in report_df.iterrows():
        for name in _linked_compound_names(row, plant_compounds_df):
            seen.setdefault(name, None)
    return list(seen.keys())


def attach_admet_developability(
    report_df: pd.DataFrame,
    *,
    plant_compounds_df: pd.DataFrame | None = None,
    compound_profiles_df: pd.DataFrame | None = None,
    compound_property_map: Mapping[str, Mapping[str, Any]] | None = None,
) -> pd.DataFrame:
    """Append ADMET/Developability columns to a Stage-6 report-ready frame.

    MUST run downstream of merge_authoritative_scores() -- this function
    never reads or writes any authoritative scoring/ranking/gate field, and
    its output columns are intentionally NOT part of authoritative_fields
    (see admet_developability.py's module docstring / the architecture
    clarification this was built against). Safe to call multiple times or
    skip entirely: it only ever adds new columns, never mutates existing
    ones, and preserves row count and order exactly.

    ``compound_property_map``: optional {normalized_compound_name:
    {property_name: value}} -- typically the result of a single prior
    pubchem_connector.resolve_compound_properties() call over the UNION of
    every linked compound across all candidates (resolved once by the
    caller, e.g. render_rd_candidates_step(), and reused here -- this
    function performs NO network calls itself). If omitted, Absorption
    falls back to the curated compound_profiles.bioavailability rating
    only (still meaningful, just without the property-derived layer).

    Per-row failure isolation: any exception while assessing one candidate
    is caught and that candidate gets an explicit "ADMET assessment
    unavailable" result -- it is never dropped, reordered, or left to
    propagate an error into the rest of the pipeline.
    """
    if not isinstance(report_df, pd.DataFrame) or report_df.empty:
        return report_df
    if "Alternative_Plant" not in report_df.columns:
        return report_df

    out = report_df.copy()
    profile_lookup = _compound_profile_lookup(compound_profiles_df)
    property_map = compound_property_map or {}

    payloads = []
    for _, row in out.iterrows():
        plant = row.get("Alternative_Plant")
        try:
            compound_names = _linked_compound_names(row, plant_compounds_df)

            compound_assessments = []
            for name in compound_names:
                key = normalize_compound_name(name)
                compound_assessments.append(
                    assess_compound_admet(
                        name,
                        pubchem_properties=property_map.get(key),
                        compound_profile=profile_lookup.get(key),
                    )
                )

            safety_fields = {
                "Safety_Assertion_Status": row.get("Safety_Assertion_Status"),
                "Safety_Concern_Level": row.get("Safety_Concern_Level"),
                "Safety_Status_Rationale": row.get("Safety_Status_Rationale"),
                "Safety_Evidence_IDs": row.get("Safety_Evidence_IDs"),
            }

            result = aggregate_plant_admet(plant, compound_assessments, safety_fields=safety_fields)
        except Exception as exc:  # noqa: BLE001 -- deliberate, documented catch-all isolation boundary
            result = _unavailable_result(plant, f"ADMET assessment unavailable ({type(exc).__name__}).")

        payloads.append({
            "ADMET_Overall_Status": result["overall_developability_status"],
            "ADMET_Data_Completeness_Label": result["data_completeness_label"],
            "ADMET_Data_Completeness_Score": result["data_completeness_score"],
            "ADMET_Compounds_Assessed_Count": result["compounds_assessed_count"],
            "ADMET_Compounds_With_Usable_Data_Count": result["compounds_with_usable_data_count"],
            "ADMET_Key_Flags": json.dumps(result["key_flags"], ensure_ascii=False),
            "ADMET_Summary": json.dumps({
                "absorption": {"status": result["absorption"]["status"], "details": result["absorption"]["details"]},
                "distribution": {"status": result["distribution"]["status"], "details": result["distribution"]["details"]},
                "metabolism": {"status": result["metabolism"]["status"], "details": result["metabolism"]["details"]},
                "excretion": {"status": result["excretion"]["status"], "details": result["excretion"]["details"]},
                "toxicity": {"status": result["toxicity"]["status"], "details": result["toxicity"]["details"]},
                "overall_status_reasons": result["overall_status_reasons"],
            }, ensure_ascii=False),
            "ADMET_Detail": json.dumps(result, ensure_ascii=False),
            "ADMET_Disclaimer": result["disclaimer"],
        })

    payload_df = pd.DataFrame(payloads, index=out.index)
    for column in payload_df.columns:
        out[column] = payload_df[column]
    return out


def parse_admet_summary(value: Any) -> dict:
    text = _clean(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_admet_detail(value: Any) -> dict:
    return parse_admet_summary(value)


def parse_admet_key_flags(value: Any) -> list:
    text = _clean(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []
