"""Disease/indication-centric botanical candidate discovery.

Candidate entry is based on plant-specific evidence records.  A general record
about an indication is never copied onto every plant, and chemistry is never an
entry gate.  Compound information is retained only as supporting metadata.
"""
from __future__ import annotations

import re
import json
import ast
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
_PHASE5_DIAGNOSTIC_COLUMNS = (
    "Normalization_Summary", "Validation_Status", "Validation_Summary",
    "Result_Direction", "Preparation_Applicability",
)

INDICATION_CENTRIC_REFERENCE_LABEL = "Indication-centric discovery"
COMPOUND_NOT_GATING_LABEL = "Not used as candidate gate"
SCORING_CONFIG_VERSION = "2.2-indication-record-level-evidence"

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
        "Target_Indication", "target_indication", "Detected_Indications", "detected_indications",
        "Primary_Outcome", "primary_outcome", "Result_Direction", "result_direction",
        "Notes", "notes", "Source_Raw_Text", "source_raw_text", "Raw_Text", "raw_text",
        "Target", "target", "Mechanism", "mechanism",
    )
    values = []
    for col in preferred:
        if col in row.index and pd.notna(row.get(col)) and str(row.get(col)).strip():
            values.append(str(row.get(col)))
    return " ".join(values)


def _structured_text(value: object) -> str:
    """Render persisted JSON/list safety and interaction fields deterministically.

    This is presentation/transport only: it never invents content.  Supabase
    JSONB values otherwise become Python repr strings whose ordering and nested
    shape are difficult for downstream keyword checks and audit exports.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        parts = []
        for key in sorted(value):
            rendered = _structured_text(value[key])
            if rendered:
                parts.append(f"{key}: {rendered}")
        return "; ".join(parts)
    if isinstance(value, (list, tuple, set)):
        return "; ".join(x for x in (_structured_text(v) for v in value) if x)
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "null", "{}", "[]"}:
        return ""
    # BotanicalRDCandidateEngine._pick() stringifies every cell. Recover JSONB
    # containers so their values remain readable after that compatibility layer.
    if text[:1] in {"{", "["}:
        parsed = None
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                parsed = None
        if parsed is not None and parsed is not value:
            return _structured_text(parsed)
    return text




def _extract_explicit_safety_and_interactions(text: object) -> tuple[str, str]:
    """Extract only explicit safety/interaction statements carried by a source.

    This is a conservative transport fallback for legacy evidence rows whose
    structured ``adverse_events`` / ``interactions_structured`` columns are
    empty although the saved source ``raw_text`` or record notes contain an
    explicit statement. It never supplies plant knowledge from a hard-coded
    database and never treats absence of a phrase as evidence of safety.
    """
    raw = str(text or "").strip()
    if not raw:
        return "", ""

    # Keep source wording for auditability, but only the sentence/fragment that
    # contains an explicit safety or interaction phrase.
    fragments = [f.strip() for f in re.split(r"(?<=[.!?;])\s+|\n+", raw) if f.strip()]
    safety_terms = (
        "adverse event", "adverse reaction", "side effect", "well tolerated",
        "no serious adverse", "no severe adverse", "contraindicat", "warning",
        "caution", "toxicity", "toxic", "hepatotoxic", "liver injury",
        "bleeding", "hemorrhag", "hypoglyc", "allergic", "anaphyl",
        "gastrointestinal", "nausea", "vomiting", "diarrhea", "rash",
    )
    interaction_terms = (
        "drug interaction", "interacts with", "interaction with",
        "concomitant use", "coadministr", "co-administr", "avoid with",
        "anticoagul", "antiplatelet", "warfarin", "hypoglycemic agent",
        "antidiabetic medication", "cytochrome p450", "cyp3a4", "cyp2c9",
        "p-glycoprotein", "p glycoprotein",
    )

    safety = []
    interactions = []
    for fragment in fragments:
        norm = _norm(fragment)
        if any(_norm(term) in norm for term in safety_terms):
            safety.append(fragment)
        if any(_norm(term) in norm for term in interaction_terms):
            interactions.append(fragment)

    # Stable de-duplication and a bounded export size.
    def _dedupe(values):
        seen = set(); out = []
        for value in values:
            key = _norm(value)
            if key and key not in seen:
                seen.add(key); out.append(value)
        return "; ".join(out[:4])

    return _dedupe(safety), _dedupe(interactions)


def _explicit_result_direction(record: dict) -> str:
    """Return a source-supported result direction, never a guessed efficacy call.

    The persisted Result_Direction field is authoritative.  When it is absent,
    only explicit outcome phrases in source-carried outcome/notes/effect fields
    are mapped to a conservative canonical label.  Generic indication or
    mechanism language is deliberately excluded.
    """
    direct = _structured_text(record.get("result_direction"))
    if direct:
        return direct
    outcome_text = _norm(" ".join(_structured_text(record.get(k)) for k in (
        "primary_outcome", "effect_size", "notes"
    )))
    if not outcome_text:
        return ""
    harmful = ("worsened", "increased risk", "harmful", "adverse effect", "deteriorat")
    null = ("no significant difference", "not significant", "no effect", "no benefit", "failed to improve")
    positive = ("significant reduction", "significantly reduced", "significant improvement", "significantly improved", "decreased", "improved")
    if any(term in outcome_text for term in harmful):
        return "harmful/adverse"
    if any(term in outcome_text for term in null):
        return "no significant benefit"
    if any(term in outcome_text for term in positive):
        return "positive benefit"
    return ""


def _record_source(engine, row: pd.Series) -> str:
    """Return a human-readable source locator, never a database row id."""
    return _pick_from_row(engine, row, [
        "Source_URL", "source_url", "URL", "url",
        "Source_Title", "source_title", "Title", "title",
        "PMID", "pmid", "DOI", "doi", "NCT_ID", "nct_id",
    ])


def _record_id(engine, row: pd.Series, fallback_index: object = None) -> str:
    """Return the stable evidence identifier used for traceability.

    Prefer the evidence_records primary key, then stable literature/registry
    identifiers.  A dataframe index is used only as a last-resort compatibility
    fallback for transient session evidence that has not yet been persisted.
    """
    value = _pick_from_row(engine, row, [
        "Evidence_Record_ID", "evidence_record_id", "id",
        "PMID", "pmid", "DOI", "doi", "NCT_ID", "nct_id",
    ])
    if value:
        return str(value)
    return str(fallback_index) if fallback_index is not None else ""


def _build_plant_evidence_index(engine) -> dict[str, list[dict]]:
    """Build a plant-keyed evidence index once per discovery run.

    The previous implementation scanned every evidence dataframe once for every
    candidate plant. With thousands of catalogue plants and evidence rows this
    became O(plants × evidence) and could leave Streamlit spinning indefinitely.
    This function performs one linear pass over each active evidence store and
    produces O(1) exact-name lookups for the scoring loop.
    """
    index: dict[str, list[dict]] = {}
    frames = (
        getattr(engine, "evidence_df", pd.DataFrame()),
        getattr(engine, "evidence_records_df", pd.DataFrame()),
        getattr(engine, "scientific_evidence_df", pd.DataFrame()),
    )
    plant_cols = (
        "Scientific_Name", "scientific_name", "Plant", "plant",
        "Botanical", "botanical", "Common_Name", "common_name",
    )
    seen_by_plant: dict[str, set[tuple[str, str, str]]] = {}

    for frame in frames:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        for idx, row in frame.iterrows():
            row_plant = _pick_from_row(engine, row, list(plant_cols))
            plant_key = _norm(row_plant)
            if not plant_key:
                continue
            text = _record_text(row)
            if not text:
                continue
            source = _record_source(engine, row)
            record_id = _record_id(engine, row, idx)
            dedupe_key = (_norm(text), _norm(source), _norm(record_id))
            plant_seen = seen_by_plant.setdefault(plant_key, set())
            if dedupe_key in plant_seen:
                continue
            plant_seen.add(dedupe_key)
            index.setdefault(plant_key, []).append({
                "text": text,
                "source": source,
                "record_id": record_id,
                # Preserve only source-provided metadata needed for record-level
                # evidence classification.  Keeping this per record (instead of
                # concatenating every paper into one plant-level blob) is what
                # allows the downstream shortlist to distinguish one RCT from a
                # review plus several preclinical studies.
                "study_type": _pick_from_row(engine, row, ["Study_Type", "study_type"]),
                "study_model": _pick_from_row(engine, row, ["Study_Model", "study_model"]),
                "evidence_level": _pick_from_row(engine, row, ["Evidence_Level", "evidence_level"]),
                "evidence_hierarchy": _pick_from_row(engine, row, ["Evidence_Hierarchy_Detail", "evidence_hierarchy_detail"]),
                "primary_outcome": _structured_text(_pick_from_row(engine, row, ["Primary_Outcome", "primary_outcome", "Outcome", "outcome"])),
                "result_direction": _structured_text(_pick_from_row(engine, row, ["Result_Direction", "result_direction"])),
                "effect_size": _structured_text(_pick_from_row(engine, row, ["Effect_Size", "effect_size"])),
                "p_value": _structured_text(_pick_from_row(engine, row, ["P_Value", "p_value"])),
                "notes": _structured_text(_pick_from_row(engine, row, ["Notes", "notes"])),
                "preparation": _structured_text(_pick_from_row(engine, row, [
                    "Preparation", "preparation", "Extraction_Method", "extraction_method",
                    "Dosage_Form", "dosage_form", "Administration_Route", "administration_route",
                ])),
                "dose": _structured_text(_pick_from_row(engine, row, ["Dosage", "dosage", "Dose", "dose"])),
                "safety_findings": _structured_text(_pick_from_row(engine, row, [
                    "Safety_Findings", "safety_findings", "Adverse_Events", "adverse_events",
                    "Safety_Signal", "safety_signal", "Safety_Flags", "safety_flags",
                ])),
                "interactions": _structured_text(_pick_from_row(engine, row, [
                    "Interactions_Structured", "interactions_structured", "Interactions", "interactions",
                    "Drug_Interaction_Level", "drug_interaction_level",
                    "Interaction_Flags", "interaction_flags",
                ])),
                "nct_id": _pick_from_row(engine, row, ["NCT_ID", "nct_id"]),
            })
    return index


def _records_for_plant(
    engine,
    plant: str,
    evidence_index: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Return records explicitly attached to ``plant`` without rescanning tables."""
    plant_n = _norm(plant)
    if not plant_n:
        return []
    if evidence_index is None:
        evidence_index = _build_plant_evidence_index(engine)

    exact = evidence_index.get(plant_n)
    if exact is not None:
        return exact

    # Compatibility for records stored under a common/abbreviated name. This
    # fallback compares only the small set of indexed plant keys, never every
    # evidence row, so it does not reintroduce the old quadratic behaviour.
    matched: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for key, records in evidence_index.items():
        if key in plant_n or plant_n in key:
            for record in records:
                dedupe_key = (
                    _norm(record.get("text")),
                    _norm(record.get("source")),
                    _norm(record.get("record_id")),
                )
                if dedupe_key not in seen:
                    seen.add(dedupe_key)
                    matched.append(record)
    return matched


def _record_evidence_characteristics(engine, record: dict) -> dict:
    """Classify one evidence record without borrowing labels from other records.

    The earlier implementation concatenated every source for a plant and then
    assigned the strongest label found anywhere in that blob to the single
    plant row.  Consequently one review could make every underlying source look
    like review-level evidence and many plants received identical scores.  This
    helper keeps study type, model and outcome attached to their own record.
    """
    text = " ".join(str(record.get(k) or "") for k in (
        "text", "study_type", "study_model", "evidence_level",
        "evidence_hierarchy", "primary_outcome", "result_direction", "preparation",
        "dose", "safety_findings", "interactions",
    ))
    normalized = _norm(text)
    source_norm = _norm(record.get("source"))
    registry_record = bool(record.get("nct_id")) or "clinicaltrials gov" in source_norm
    resolved_result_direction = _explicit_result_direction(record)
    result_direction = _norm(resolved_result_direction)
    has_reported_result = bool(result_direction) or any(term in normalized for term in (
        "statistically significant", "significant reduction", "significant improvement",
        "reduced hba1c", "reduced fasting glucose", "improved", "decreased", "increased",
        "no significant difference", "no effect", "worsened",
    ))
    registry_without_results = registry_record and not has_reported_result

    explicit_level = str(record.get("evidence_level") or "").strip()
    explicit_hierarchy = str(record.get("evidence_hierarchy") or "").strip()
    level = explicit_level or (engine._evidence_level(text) if text else "Unknown")
    hierarchy = explicit_hierarchy or level
    if text and not explicit_hierarchy:
        try:
            from evidence_hierarchy_classifier import classify_evidence_hierarchy
            hierarchy = classify_evidence_hierarchy(text)
        except Exception:
            pass

    if registry_without_results:
        level = "Registry record without reported results"
        hierarchy = "Registry / protocol only"

    context = _norm(f"{level} {hierarchy} {text}")
    human = (not registry_without_results) and any(t in context for t in (
        "clinical", "human", "randomized", "randomised", "meta analysis",
        "systematic review", "controlled trial",
    ))
    preclinical = any(t in context for t in (
        "in vivo", "animal", "in vitro", "ex vivo", "preclinical", "cell",
    ))
    negative = any(t in result_direction for t in (
        "negative", "no effect", "no significant", "null", "worsened", "harm",
    ))
    return {
        "level": level,
        "hierarchy": hierarchy,
        "human": human,
        "preclinical": preclinical,
        "registry_without_results": registry_without_results,
        "negative": negative,
        "resolved_result_direction": resolved_result_direction,
    }



def _preparation_applicability(record: dict | None, selected_dosage_form: str) -> tuple[str, list[str]]:
    """Classify preparation applicability from record-provided data only.

    Unknown is never promoted to compatible.  Exact/near route or dosage-form
    matches are compatible; explicit extract/capsule vs infusion/tea mismatches
    are retained as mismatches.
    """
    selected = _norm(selected_dosage_form)
    if not selected:
        return "Not evaluated", []
    if not record:
        return "Unknown", ["No record-level preparation information"]
    prep = _norm(record.get("preparation"))
    if not prep:
        return "Unknown", ["Preparation/route not reported in source record"]

    synonym_groups = (
        {"infusion", "tea", "herbal tea", "aqueous infusion"},
        {"capsule", "tablet", "oral solid", "powder"},
        {"extract", "dry extract", "standardized extract", "standardised extract"},
        {"topical", "cream", "gel", "ointment"},
        {"oral", "by mouth"},
    )
    selected_group = next((g for g in synonym_groups if any(t in selected for t in g)), {selected})
    if any(term in prep for term in selected_group):
        return "Compatible", []

    explicit_groups = [g for g in synonym_groups if any(term in prep for term in g)]
    if explicit_groups:
        return "Mismatch", [f"Selected dosage form '{selected_dosage_form}' differs from reported preparation '{record.get('preparation')}'"]
    return "Unknown", ["Reported preparation could not be mapped to selected dosage form"]

def discover_indication_candidates(engine, indication: str, dosage_form: str = "", market: str = "", product_type: str = "") -> pd.DataFrame:
    """Return OUTPUT_COLUMNS-compatible rows using plant-specific evidence."""
    from botanical_rd_candidate_engine import OUTPUT_COLUMNS

    candidates = engine._candidate_frame()
    if candidates.empty:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS))

    direct_terms, mechanism_terms = _terms(indication)
    evidence_index = _build_plant_evidence_index(engine)
    rows = []

    for _, item in candidates.iterrows():
        plant = engine._pick(item, ["Scientific_Name", "scientific_name", "Plant", "plant"])
        if not plant:
            continue

        indications = engine._pick(item, ["Indications_Text", "Indications", "indication"])
        targets = engine._pick(item, ["Known_Targets", "target", "mechanism"])
        compounds = engine._split_compound_terms(engine._pick(item, ["Known_Active_Compounds", "compound_name"]))
        records = _records_for_plant(engine, plant, evidence_index)

        direct_records = [r for r in records if _contains_any(r["text"], direct_terms)]
        mechanism_records = [r for r in records if _contains_any(r["text"], mechanism_terms)]

        # Database profile fields may create an exploratory lead, but never a
        # direct-evidence candidate and never a shortlist by themselves.
        profile_direct = _contains_any(indications, direct_terms)
        profile_mechanistic = _contains_any(" | ".join((targets, indications)), mechanism_terms)

        if not direct_records and not mechanism_records and not profile_direct and not profile_mechanistic:
            continue

        # Preserve record-level granularity.  The previous implementation
        # collapsed every source for a plant into one synthetic row, assigned
        # that row the strongest hierarchy label seen anywhere in the combined
        # text, and therefore made many plants tie.  Each relevant source now
        # becomes its own raw association row; candidate_shortlisting.py can
        # then measure study depth, hierarchy mix, consistency and independent
        # source count honestly.
        relevant_records: list[dict] = []
        seen_relevant: set[tuple[str, str, str]] = set()
        for record in direct_records + mechanism_records:
            key = (_norm(record.get("record_id")), _norm(record.get("source")), _norm(record.get("text")))
            if key not in seen_relevant:
                seen_relevant.add(key)
                relevant_records.append(record)

        evidence_units: list[dict | None] = relevant_records or [None]
        for record in evidence_units:
            record_text = str(record.get("text") or "")[:12000] if record else ""
            record_direct = bool(record and _contains_any(record_text, direct_terms))
            record_mechanistic = bool(record and _contains_any(record_text, mechanism_terms))
            profile_only = record is None

            characteristics = (
                _record_evidence_characteristics(engine, record)
                if record is not None else {
                    "level": "Profile-level hypothesis",
                    "hierarchy": "Profile-level hypothesis",
                    "human": False,
                    "preclinical": False,
                    "registry_without_results": False,
                    "negative": False,
                }
            )
            level = characteristics["level"]
            hierarchy = characteristics["hierarchy"]
            human = characteristics["human"]
            preclinical = characteristics["preclinical"]
            registry_without_results = characteristics["registry_without_results"]
            negative = characteristics["negative"]

            source = str(record.get("source") or "").strip() if record else ""
            record_id = str(record.get("record_id") or "").strip() if record else ""
            sources = [source] if source else []
            record_ids = [record_id] if record_id else []
            result_direction = characteristics.get("resolved_result_direction", "") if record else ""
            preparation_status, preparation_mismatches = _preparation_applicability(record, dosage_form)
            record_preparation = str(record.get("preparation") or "").strip() if record else ""
            safety_findings = str(record.get("safety_findings") or "").strip() if record else ""
            interactions = str(record.get("interactions") or "").strip() if record else ""
            if record and (not safety_findings or not interactions):
                inferred_safety, inferred_interactions = _extract_explicit_safety_and_interactions(
                    " ".join(str(record.get(k) or "") for k in ("text", "notes"))
                )
                # Source-text fallback only fills a missing structured field; it
                # never overwrites connector/database-provided structured data.
                safety_findings = safety_findings or inferred_safety
                interactions = interactions or inferred_interactions

            # Phase 5 normalization/validation is now run on the individual
            # scientific observation rather than on a plant-wide concatenation.
            try:
                from evidence_normalization import normalize_evidence_record
                from evidence_validation import validate_evidence_record
                _phase5_row = {
                    "Scientific_Name": plant,
                    "Target_Indication": indication,
                    "Dosage_Form": dosage_form,
                    "Evidence_Level": level,
                    "Evidence_Hierarchy_Detail": hierarchy,
                    "Notes": record_text,
                    "Source_Record_IDs": record_id,
                    "Study_Model": "Human" if human else ("Animal" if preclinical else ""),
                }
                _normalized_fields = normalize_evidence_record(_phase5_row)
                _validation_result = validate_evidence_record(
                    _phase5_row,
                    plant_name=plant,
                    indication=indication,
                    dosage_form=dosage_form,
                    normalized_fields=_normalized_fields,
                )
                normalization_summary = "; ".join(
                    f"{name}={field.verification_status}"
                    for name, field in _normalized_fields.items()
                    if field.verification_status != "missing"
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

            if registry_without_results:
                evidence_points = 6
                tier = "Registry record without reported results"
                decision = "Exploratory registered study"
                call = "Hold — await reported results"
            elif record_direct and human:
                evidence_points = 35
                tier = "Direct human evidence"
                decision = "Indication-based R&D candidate"
                call = "Investigate"
            elif record_direct and preclinical:
                evidence_points = 27
                tier = "Direct preclinical evidence"
                decision = "Indication-based R&D candidate"
                call = "Investigate"
            elif record_direct:
                evidence_points = 22
                tier = "Direct but unclassified evidence"
                decision = "Indication-based R&D candidate"
                call = "Investigate — verify evidence type"
            elif record_mechanistic:
                evidence_points = 12
                tier = "Candidate-specific mechanistic evidence"
                decision = "Exploratory mechanistic hypothesis"
                call = "Investigate — mechanistic only"
            else:
                evidence_points = 4
                tier = "Profile-derived hypothesis only"
                decision = "Exploratory profile hypothesis"
                call = "Hold — collect candidate-specific evidence"

            trace_points = 2 if source or record_id else 0
            mechanism_points = 10 if record_mechanistic else 3 if profile_mechanistic else 0
            applicability_points = 8 if preparation_status == "Compatible" else 0
            compound_support = 5 if compounds and (record_direct or record_mechanistic) else 0
            score = min(100.0, float(
                evidence_points + trace_points + mechanism_points
                + applicability_points + compound_support + 10
            ))
            confidence = min(100.0, float(
                (30 if record_direct else 15 if record_mechanistic else 5)
                + (25 if human else 15 if preclinical else 5)
                + (5 if source or record_id else 0)
            ))

            provenance = (
                "Registered study; efficacy results not reported"
                if registry_without_results else
                "Candidate-specific indication evidence"
                if record_direct else
                "Candidate-specific mechanistic evidence only"
                if record_mechanistic else
                "Profile-derived hypothesis; no candidate-specific empirical record"
            )
            mechanism_label = targets or "; ".join(
                mechanism_terms[:5] if (record_mechanistic or profile_mechanistic) else []
            )
            rationale = (
                f"{plant} has a plant-specific evidence record linked to the requested indication; "
                "shared chemistry was not used as an entry gate."
                if record is not None else
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
                "Extraction_Method": record_preparation or engine._pick(item, ["Typical_Extraction", "Extraction_Method", "extraction"]),
                "Industrial_Feasibility": "Requires product-specific assessment",
                "Co_Compounds": "; ".join(compounds[1:9]),
                "Safety_Flags": safety_findings,
                "Interaction_Flags": interactions,
                "Evidence_Source": source,
                "Source_Record_IDs": record_id,
                "Occurrence_Corroboration": "1 traceable plant-specific source" if source or record_id else "0 traceable plant-specific sources",
                "Candidate_Evidence_Strength_Tier": tier,
                "Evidence_Level": level,
                "Evidence_Hierarchy_Detail": hierarchy,
                "Has_Negative_Evidence": negative,
                "Negative_Evidence_Types": "Negative/null reported result" if negative else "",
                "Result_Direction": result_direction,
                "Preparation_Applicability": preparation_status,
                "Market_Status": "Search not performed",
                "Regulatory_Barriers": "Not assessed",
                "Novelty_Status": "Indication-derived candidate",
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
                "Decision_Class_AH": "C" if record_direct and not registry_without_results else "F",
                "White_Space_Type": "To be assessed",
                "Confidence_Note": "Candidate generated independently of chemical similarity.",
                "Go_Investigate_Hold_NoGo": call,
                "Scientific_Rationale": rationale,
                "Commercial_Regulatory_Rationale": "Commercial and regulatory enrichment required.",
                "Evidence_Strengths": provenance,
                "Evidence_Weaknesses": "Preparation, dose, effect size and regulatory applicability require record-level review.",
                "Next_Experiment_Suggestion": "Verify plant-specific records, preparation, dose, outcomes and effect size before investment.",
                "Evidence_Conflict_Reasoning": "Record-level result direction retained; aggregate consistency is assessed during shortlisting.",
                "Evidence_Conflict_Structured": {},
                "Recommendation_Confidence_Statement": f"Evidence confidence {confidence:.1f}/100.",
                "Competitive_Positioning": "Not yet enriched.",
                "Regulatory_Rationale": "Regulatory search not yet performed.",
                "Commercial_Rationale": "Market search not yet performed.",
                "Safety_Rationale": "Safety review required; absence of a flag is not proof of safety.",
                "Clinical_Rationale": (
                    "Plant-specific human evidence detected."
                    if human and record_direct and not registry_without_results else
                    "No confirmed plant-specific human efficacy result detected."
                ),
                "Comparative_Rationale": "Ranked by indication evidence rather than shared chemistry.",
                "Comparative_Rationale_Structured": {},
                "Rationale": rationale,
                "Gate_Results": {},
                "Scoring_Config_Version": SCORING_CONFIG_VERSION,
                "Applicability_Summary": {
                    "evidence_record_ids": record_ids,
                    "classification": preparation_status,
                    "critical_mismatches": preparation_mismatches,
                    "evidence_items": [{
                        "evidence_record_id": record_id or None,
                        "applicability_classification": preparation_status,
                        "detected_mismatches": preparation_mismatches,
                        "missing_dimensions": ["preparation"] if preparation_status == "Unknown" else [],
                    }],
                },
                "GRADE_Certainty": "Not graded",
                "GRADE_Certainty_Rationale": "Record-level grading required.",
            })
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS))
    out = pd.DataFrame(rows)
    out = out.sort_values(["R&D_Opportunity_Score", "Evidence_Confidence"], ascending=False)
    return out.reindex(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS)).reset_index(drop=True)
