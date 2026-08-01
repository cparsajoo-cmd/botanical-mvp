"""Disease/indication-centric botanical candidate discovery.

Candidate entry is based on plant-specific evidence records.  A general record
about an indication is never copied onto every plant, and chemistry is never an
entry gate.  Compound information is retained only as supporting metadata.
"""
from __future__ import annotations

import re
from typing import Iterable
import pandas as pd

# Post-Phase-5-review correction: OUTPUT_COLUMNS (imported below from
# botanical_rd_candidate_engine.py) predates Phase 5 and does not list
# these three diagnostic columns. Every place this module reindexes a
# DataFrame to OUTPUT_COLUMNS must ALSO include these, or the entire
# Evidence Normalization / Evidence Validation stage's output is silently
# dropped before it ever leaves discover_indication_candidates() — exactly
# the regression a backward-compatibility test caught (the columns were
# being computed correctly, then discarded by the final reindex call).
# OUTPUT_COLUMNS itself is intentionally left unmodified — it is shared
# with the legacy compound-substitution engine, which never runs Phase 5.
_PHASE5_DIAGNOSTIC_COLUMNS = ("Normalization_Summary", "Validation_Status", "Validation_Summary")

INDICATION_CENTRIC_REFERENCE_LABEL = "Indication-centric discovery"
COMPOUND_NOT_GATING_LABEL = "Not used as candidate gate"

DISEASE_FAMILIES = {
    "metabolic": {
        "triggers": ("diabetes", "blood sugar", "glycemic", "glycaemic", "metabolic", "insulin resistance", "hypergly"),
        "direct": ("type 2 diabetes", "diabetes mellitus", "diabetic", "hyperglycemia", "hyperglycaemia", "blood glucose", "fasting glucose", "postprandial glucose", "hba1c", "glycemic control", "glycaemic control", "insulin resistance"),
        "mechanistic": ("ampk", "glut4", "ppar", "alpha glucosidase", "α-glucosidase", "dpp-4", "insulin secretion", "insulin sensitivity", "glucose uptake", "hepatic gluconeogenesis"),
    },
    "sleep": {
        "triggers": ("sleep", "insomnia"),
        "direct": ("insomnia", "sleep disturbance", "sleep quality", "sleep latency", "sleep disorder", "difficulty falling asleep", "poor sleep", "sleep onset"),
        "mechanistic": ("gaba", "gabaa receptor", "melatonin", "benzodiazepine receptor", "sedative", "hypnotic", "sleep onset latency", "adenosine receptor"),
    },
    "cognitive": {
        "triggers": ("alzheimer", "dementia", "cognitive decline", "neurodegeneration", "memory loss", "memory impairment"),
        "direct": ("alzheimer's disease", "alzheimer disease", "dementia", "cognitive decline", "mild cognitive impairment", "memory impairment"),
        "mechanistic": ("acetylcholinesterase", "amyloid beta", "amyloid-beta", "tau protein", "neuroinflammation", "nmda receptor", "cholinergic"),
    },
    "skin_aging": {
        "triggers": ("skin aging", "skin ageing", "photoaging", "photoageing", "wrinkle", "skin elasticity"),
        "direct": ("skin aging", "skin ageing", "photoaging", "photoageing", "wrinkle reduction", "skin elasticity", "fine lines", "collagen loss"),
        "mechanistic": ("collagen synthesis", "mmp-1", "matrix metalloproteinase", "elastin", "uv induced damage", "antioxidant", "fibroblast"),
    },
}


def _norm(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9αβγ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _terms(indication: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    q = _norm(indication)
    for family in DISEASE_FAMILIES.values():
        if any(_norm(t) in q for t in family["triggers"]):
            return family["direct"], family["mechanistic"]
    tokens = tuple(t for t in q.split() if len(t) >= 4 and t not in {"support", "comfort", "health"})
    return tokens, ()


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    n = _norm(text)
    return any(_norm(term) in n for term in terms if _norm(term))


def _pick_from_row(engine, row: pd.Series, names: list[str]) -> str:
    return engine._pick(row, names)


def _record_text(row: pd.Series) -> str:
    preferred = (
        "Title", "title", "Abstract", "abstract", "Outcome", "outcome",
        "Indication", "indication", "Disease", "disease", "Condition", "condition",
        "Evidence_Text", "evidence_text", "Snippet", "snippet", "decision_reason",
        "evidence_flags", "Study_Type", "study_type", "Evidence_Level", "evidence_level",
        "Target", "target", "Mechanism", "mechanism",
    )
    values = []
    for col in preferred:
        if col in row.index and pd.notna(row.get(col)) and str(row.get(col)).strip():
            values.append(str(row.get(col)))
    return " ".join(values)


def _record_source(engine, row: pd.Series) -> str:
    return _pick_from_row(engine, row, [
        "Source_URL", "source_url", "URL", "url", "PMID", "pmid",
        "DOI", "doi", "Evidence_Record_ID", "evidence_record_id", "id",
    ])


def _records_for_plant(engine, plant: str) -> list[tuple[str, str, object]]:
    """Return only records explicitly attached to this plant.

    No indication-key lookup is performed.  This prevents generic diabetes (or
    other indication) records from leaking into every botanical candidate.
    """
    plant_n = _norm(plant)
    records: list[tuple[str, str, object]] = []
    frames = [getattr(engine, "evidence_df", pd.DataFrame()), getattr(engine, "scientific_evidence_df", pd.DataFrame())]
    plant_cols = ("Scientific_Name", "scientific_name", "Plant", "plant", "Botanical", "botanical", "Common_Name", "common_name")
    for frame in frames:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        for idx, row in frame.iterrows():
            row_plant = _pick_from_row(engine, row, list(plant_cols))
            if not row_plant:
                continue
            row_plant_n = _norm(row_plant)
            if not (row_plant_n == plant_n or row_plant_n in plant_n or plant_n in row_plant_n):
                continue
            text = _record_text(row)
            if not text:
                continue
            records.append((text, _record_source(engine, row), idx))
    return records


def discover_indication_candidates(engine, indication: str, dosage_form: str = "", market: str = "", product_type: str = "") -> pd.DataFrame:
    """Return OUTPUT_COLUMNS-compatible rows using plant-specific evidence."""
    from botanical_rd_candidate_engine import OUTPUT_COLUMNS

    candidates = engine._candidate_frame()
    if candidates.empty:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS))

    direct_terms, mechanism_terms = _terms(indication)
    rows = []

    for _, item in candidates.iterrows():
        plant = engine._pick(item, ["Scientific_Name", "scientific_name", "Plant", "plant"])
        if not plant:
            continue

        indications = engine._pick(item, ["Indications_Text", "Indications", "indication"])
        targets = engine._pick(item, ["Known_Targets", "target", "mechanism"])
        compounds = engine._split_compound_terms(engine._pick(item, ["Known_Active_Compounds", "compound_name"]))
        records = _records_for_plant(engine, plant)

        direct_records = [(t, s, i) for t, s, i in records if _contains_any(t, direct_terms)]
        mechanism_records = [(t, s, i) for t, s, i in records if _contains_any(t, mechanism_terms)]

        # Database profile fields may create an exploratory lead, but never a
        # direct-evidence candidate and never a shortlist by themselves.
        profile_direct = _contains_any(indications, direct_terms)
        profile_mechanistic = _contains_any(" | ".join((targets, indications)), mechanism_terms)

        if not direct_records and not mechanism_records and not profile_direct and not profile_mechanistic:
            continue

        evidence_text = " ".join(t for t, _, _ in records)[:12000]
        direct = bool(direct_records)
        mechanistic_empirical = bool(mechanism_records)
        profile_only = not direct and not mechanistic_empirical

        source_records = direct_records if direct else mechanism_records
        sources = list(dict.fromkeys(s for _, s, _ in source_records if str(s).strip()))
        record_ids = [str(i) for _, _, i in source_records]

        level_text = " ".join(t for t, _, _ in source_records)
        level = engine._evidence_level(level_text) if level_text else "Profile-level hypothesis"
        hierarchy = level
        if level_text:
            try:
                from evidence_hierarchy_classifier import classify_evidence_hierarchy
                hierarchy = classify_evidence_hierarchy(level_text)
            except Exception:
                pass

        context_n = _norm(f"{level} {hierarchy} {level_text}")
        human = any(t in context_n for t in ("clinical", "human", "randomized", "randomised", "meta analysis", "systematic review"))
        preclinical = any(t in context_n for t in ("in vivo", "animal", "in vitro", "ex vivo", "preclinical", "cell"))

        # --- Phase 5 (IMPLEMENTATION_PLAN.md): Evidence Normalization and
        # Evidence Validation, as two explicit stages that run BEFORE
        # candidate scoring below. Purely additive/diagnostic — nothing in
        # this block reads into or changes evidence_points/tier/score
        # further down; Phase 3's authoritative scoring weights are
        # untouched, per this phase's own constraint. Any failure here is
        # caught and degrades to "not assessed", never blocks discovery.
        try:
            from evidence_normalization import normalize_evidence_record
            from evidence_validation import validate_evidence_record
            _phase5_row = {
                "Scientific_Name": plant, "Target_Indication": indication,
                "Dosage_Form": dosage_form, "Evidence_Level": level,
                "Evidence_Hierarchy_Detail": hierarchy, "Notes": evidence_text,
                "Source_Record_IDs": "; ".join(sources),
                "Study_Model": "Human" if human else ("Animal" if preclinical else ""),
            }
            _normalized_fields = normalize_evidence_record(_phase5_row)
            _validation_result = validate_evidence_record(
                _phase5_row, plant_name=plant, indication=indication,
                dosage_form=dosage_form, normalized_fields=_normalized_fields,
            )
            normalization_summary = "; ".join(
                f"{name}={f.verification_status}" for name, f in _normalized_fields.items()
                if f.verification_status != "missing"
            ) or "No fields normalized (all source values missing)"
            validation_status = _validation_result["overall_status"]
            validation_summary = "; ".join(
                f"{check}: {'pass' if result.get('passed') else 'fail'}"
                for check, result in _validation_result.items()
                if isinstance(result, dict) and "passed" in result
            )
        except Exception:
            normalization_summary = "Not assessed (Phase 5 stage error)"
            validation_status = "not_assessable"
            validation_summary = "Not assessed (Phase 5 stage error)"

        if direct and human:
            evidence_points = 35
            tier = "Direct human evidence"
            decision = "Indication-based R&D candidate"
            call = "Investigate"
        elif direct and preclinical:
            evidence_points = 27
            tier = "Direct preclinical evidence"
            decision = "Indication-based R&D candidate"
            call = "Investigate"
        elif direct:
            evidence_points = 22
            tier = "Direct but unclassified evidence"
            decision = "Indication-based R&D candidate"
            call = "Investigate — verify evidence type"
        elif mechanistic_empirical:
            evidence_points = 12
            tier = "Candidate-specific mechanistic evidence"
            decision = "Exploratory mechanistic hypothesis"
            call = "Investigate — mechanistic only"
        else:
            evidence_points = 4
            tier = "Profile-derived hypothesis only"
            decision = "Exploratory profile hypothesis"
            call = "Hold — collect candidate-specific evidence"

        trace_points = min(10, 2 * len(sources))
        mechanism_points = 10 if mechanistic_empirical else 3 if profile_mechanistic else 0
        applicability_points = 8 if dosage_form and _contains_any(evidence_text, (dosage_form, "oral", "infusion", "tea", "aqueous")) else 0
        compound_support = 5 if compounds and (direct or mechanistic_empirical) else 0
        score = min(100.0, float(evidence_points + trace_points + mechanism_points + applicability_points + compound_support + 10))
        confidence = min(100.0, float((30 if direct else 15 if mechanistic_empirical else 5) + (25 if human else 15 if preclinical else 5) + min(25, len(sources) * 5)))

        provenance = (
            "Candidate-specific indication evidence" if direct
            else "Candidate-specific mechanistic evidence only" if mechanistic_empirical
            else "Profile-derived hypothesis; no candidate-specific empirical record"
        )
        mechanism_label = targets or "; ".join(mechanism_terms[:5] if (mechanistic_empirical or profile_mechanistic) else [])
        rationale = (
            f"{plant} entered through plant-specific evidence linked to the requested indication; "
            "shared chemistry was not used as an entry gate."
            if not profile_only else
            f"{plant} is retained only as a profile-derived hypothesis; no plant-specific empirical record linked to the requested indication was found."
        )

        row = {col: "" for col in OUTPUT_COLUMNS}
        row.update({
            "Reference_Plant": INDICATION_CENTRIC_REFERENCE_LABEL,
            "Reference_Plant_Part": "",
            "Reference_Compound": COMPOUND_NOT_GATING_LABEL,
            "Alternative_Plant": plant,
            "Alternative_Plant_Part": engine._pick(item, ["Plant_Part", "plant_part"]),
            "Shared_or_Similar_Compound": "; ".join(compounds[:8]),
            "Target_or_Mechanism": mechanism_label,
            "Target_Provenance": provenance,
            "Concentration_Info": "Not established",
            "Extraction_Method": engine._pick(item, ["Typical_Extraction", "Extraction_Method", "extraction"]),
            "Industrial_Feasibility": "Requires product-specific assessment",
            "Co_Compounds": "; ".join(compounds[1:9]),
            "Safety_Flags": "",
            "Interaction_Flags": "",
            "Evidence_Source": "; ".join(sources),
            "Source_Record_IDs": "; ".join(sources or record_ids),
            "Occurrence_Corroboration": f"{len(sources)} traceable plant-specific source(s)",
            "Candidate_Evidence_Strength_Tier": tier,
            "Evidence_Level": level,
            "Evidence_Hierarchy_Detail": hierarchy,
            "Has_Negative_Evidence": False,
            "Negative_Evidence_Types": "",
            "Market_Status": "Search not performed",
            "Regulatory_Barriers": "Not assessed",
            "Novelty_Status": "Indication-derived candidate",
            # Phase 5 (IMPLEMENTATION_PLAN.md) — diagnostic-only columns from
            # the Evidence Normalization / Evidence Validation stages run
            # above, before scoring. Deliberately NOT wired into
            # Has_Negative_Evidence, evidence_points, or any other
            # scoring-affecting field in this phase — see this phase's own
            # "do not change authoritative scoring weights" constraint.
            "Normalization_Summary": normalization_summary,
            "Validation_Status": validation_status,
            "Validation_Summary": validation_summary,
            "R&D_Opportunity_Score": score,
            "Score_Breakdown": {
                "Direct indication evidence": evidence_points,
                "Traceability": trace_points,
                "Mechanistic plausibility": mechanism_points,
                "Preparation applicability": applicability_points,
                "Compound support (non-gating; max 5)": compound_support,
                "Baseline development potential": 10,
            },
            "Evidence_Confidence": confidence,
            "Decision_Class": decision,
            "Decision_Class_AH": "C" if direct else "F",
            "White_Space_Type": "To be assessed",
            "Confidence_Note": "Candidate generated independently of chemical similarity.",
            "Go_Investigate_Hold_NoGo": call,
            "Scientific_Rationale": rationale,
            "Commercial_Regulatory_Rationale": "Commercial and regulatory enrichment required.",
            "Evidence_Strengths": provenance,
            "Evidence_Weaknesses": "Preparation, dose, effect size and regulatory applicability require record-level review.",
            "Next_Experiment_Suggestion": "Verify plant-specific records, preparation, dose, outcomes and effect size before investment.",
            "Evidence_Conflict_Reasoning": "Not yet assessed at record level.",
            "Evidence_Conflict_Structured": {},
            "Recommendation_Confidence_Statement": f"Evidence confidence {confidence:.1f}/100.",
            "Competitive_Positioning": "Not yet enriched.",
            "Regulatory_Rationale": "Regulatory search not yet performed.",
            "Commercial_Rationale": "Market search not yet performed.",
            "Safety_Rationale": "Safety review required; absence of a flag is not proof of safety.",
            "Clinical_Rationale": "Plant-specific human evidence detected." if human and direct else "No confirmed plant-specific human-evidence classification detected.",
            "Comparative_Rationale": "Ranked by indication evidence rather than shared chemistry.",
            "Comparative_Rationale_Structured": {},
            "Rationale": rationale,
            "Gate_Results": {},
            "Scoring_Config_Version": "2.1-indication-centric-no-leakage",
            "Applicability_Summary": {"evidence_record_ids": record_ids, "classification": "Not assessed"},
            "GRADE_Certainty": "Not graded",
            "GRADE_Certainty_Rationale": "Record-level grading required.",
        })
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS))
    out = pd.DataFrame(rows)
    out = out.sort_values(["R&D_Opportunity_Score", "Evidence_Confidence"], ascending=False)
    return out.reindex(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS)).reset_index(drop=True)
