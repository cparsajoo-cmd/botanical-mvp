"""Disease/indication-centric botanical candidate discovery.

This module deliberately separates two scientific questions:
1) Which botanicals have evidence for an indication? (this module)
2) Which botanicals share an active compound? (legacy substitution mode)

Compound overlap is supportive metadata only and never controls candidate entry.
"""
from __future__ import annotations

import re
from typing import Iterable
import pandas as pd


DISEASE_FAMILIES = {
    "metabolic": {
        "triggers": ("diabetes", "blood sugar", "glycemic", "glycaemic", "metabolic", "insulin resistance", "hypergly"),
        "direct": ("type 2 diabetes", "diabetes mellitus", "diabetic", "hyperglycemia", "hyperglycaemia", "blood glucose", "fasting glucose", "postprandial glucose", "hba1c", "glycemic control", "glycaemic control", "insulin resistance"),
        "mechanistic": ("ampk", "glut4", "ppar", "alpha glucosidase", "α-glucosidase", "dpp-4", "insulin secretion", "insulin sensitivity", "glucose uptake", "hepatic gluconeogenesis"),
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


def _source_ids(source_index: dict, plant: str, indication: str) -> list[str]:
    out = []
    for key in (_norm(plant), _norm(indication)):
        out.extend(source_index.get(key, []))
    return list(dict.fromkeys(x for x in out if str(x).strip()))


def discover_indication_candidates(engine, indication: str, dosage_form: str = "", market: str = "", product_type: str = "") -> pd.DataFrame:
    """Return OUTPUT_COLUMNS-compatible rows without compound-gated discovery."""
    from botanical_rd_candidate_engine import OUTPUT_COLUMNS

    candidates = engine._candidate_frame()
    if candidates.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    evidence_index, source_index, applicability_index = engine._build_evidence_text_index()
    direct_terms, mechanism_terms = _terms(indication)
    rows = []

    for _, item in candidates.iterrows():
        plant = engine._pick(item, ["Scientific_Name", "scientific_name", "Plant", "plant"])
        if not plant:
            continue
        indications = engine._pick(item, ["Indications_Text", "Indications", "indication"])
        targets = engine._pick(item, ["Known_Targets", "target", "mechanism"])
        compounds = engine._split_compound_terms(engine._pick(item, ["Known_Active_Compounds", "compound_name"]))
        plant_text = evidence_index.get(_norm(plant), "")
        query_text = evidence_index.get(_norm(indication), "")
        evidence_text = " ".join(x for x in (plant_text, query_text) if x).strip()[:6000]
        combined = " | ".join((indications, targets, evidence_text))

        direct = _contains_any(combined, direct_terms)
        mechanistic = _contains_any(" | ".join((targets, evidence_text)), mechanism_terms)
        if not direct and not mechanistic:
            continue

        sources = _source_ids(source_index, plant, indication)
        level = engine._evidence_level(evidence_text)
        hierarchy = engine._evidence_level(evidence_text)
        try:
            from evidence_hierarchy_classifier import classify_evidence_hierarchy
            hierarchy = classify_evidence_hierarchy(evidence_text)
        except Exception:
            pass

        level_n = _norm(level)
        human = any(t in level_n or t in _norm(evidence_text) for t in ("clinical", "human", "randomized", "randomised", "meta analysis", "systematic review"))
        preclinical = any(t in level_n or t in _norm(evidence_text) for t in ("in vivo", "animal", "in vitro", "ex vivo", "preclinical"))

        evidence_points = 35 if direct and human else 27 if direct and preclinical else 22 if direct else 12
        trace_points = min(10, 2 * len(sources))
        mechanism_points = 10 if mechanistic else 0
        applicability_points = 8 if dosage_form and _contains_any(combined, (dosage_form, "oral", "infusion", "tea", "aqueous")) else 3
        compound_support = 5 if compounds and mechanistic else 0
        score = min(100.0, float(evidence_points + trace_points + mechanism_points + applicability_points + compound_support + 10))
        confidence = min(100.0, float((30 if direct else 10) + (25 if human else 15 if preclinical else 5) + min(25, len(sources) * 5)))

        evidence_source = "; ".join(sources)
        provenance = "Candidate-specific indication evidence" if direct else "Candidate-specific mechanistic evidence only"
        mechanism_label = targets or "; ".join(mechanism_terms[:5] if mechanistic else [])
        rationale = (
            f"{plant} entered the candidate universe because candidate-specific text/evidence is linked to the requested indication; "
            "compound overlap was not used as an entry gate."
        )

        row = {col: "" for col in OUTPUT_COLUMNS}
        row.update({
            "Reference_Plant": "Indication-centric discovery",
            "Reference_Plant_Part": "",
            "Reference_Compound": "Not used as candidate gate",
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
            "Evidence_Source": evidence_source,
            "Source_Record_IDs": "; ".join(sources),
            "Occurrence_Corroboration": f"{len(sources)} traceable source(s)",
            "Candidate_Evidence_Strength_Tier": "Direct human evidence" if direct and human else "Direct preclinical evidence" if direct else "Mechanistic evidence",
            "Evidence_Level": level,
            "Evidence_Hierarchy_Detail": hierarchy,
            "Has_Negative_Evidence": False,
            "Negative_Evidence_Types": "",
            "Market_Status": "Search not performed",
            "Regulatory_Barriers": "Not assessed",
            "Novelty_Status": "Indication-derived candidate",
            "R&D_Opportunity_Score": score,
            "Score_Breakdown": {
                "Direct indication evidence": evidence_points,
                "Traceability": trace_points,
                "Mechanistic plausibility": mechanism_points,
                "Preparation applicability": applicability_points,
                "Compound support (non-gating)": compound_support,
                "Baseline development potential": 10,
            },
            "Evidence_Confidence": confidence,
            "Decision_Class": "Indication-based R&D candidate" if direct else "Exploratory mechanistic hypothesis",
            "Decision_Class_AH": "C" if direct else "F",
            "White_Space_Type": "To be assessed",
            "Confidence_Note": "Candidate generated independently of chemical similarity.",
            "Go_Investigate_Hold_NoGo": "Investigate" if direct else "Investigate — mechanistic only",
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
            "Clinical_Rationale": "Human evidence detected." if human else "No confirmed human-evidence classification detected.",
            "Comparative_Rationale": "Ranked by indication evidence rather than shared chemistry.",
            "Comparative_Rationale_Structured": {},
            "Rationale": rationale,
            "Gate_Results": {},
            "Scoring_Config_Version": "2.0-indication-centric",
            "Applicability_Summary": {"evidence_record_ids": [], "classification": "Not assessed"},
            "GRADE_Certainty": "Not graded",
            "GRADE_Certainty_Rationale": "Record-level grading required.",
        })
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    out = pd.DataFrame(rows)
    out = out.sort_values(["R&D_Opportunity_Score", "Evidence_Confidence"], ascending=False)
    return out.reindex(columns=OUTPUT_COLUMNS).reset_index(drop=True)
