"""Disease/indication-centric botanical candidate discovery.

Candidate entry is based on plant-specific evidence records.  A general record
about an indication is never copied onto every plant, and chemistry is never an
entry gate.  Compound information is retained only as supporting metadata.
"""
from __future__ import annotations

import re
import json
import ast
import time
from typing import Iterable
import pandas as pd

from safety_interaction_attribution import (
    extract_attributed_safety_interactions,
    extract_structured_safety_interactions,
)
from indication_semantics import indication_terms as _resolve_indication_terms
from standard_evidence_builder import (
    evaluate_applicability,
    evidence_transferability_fields,
    preparation_from_product_form,
    preparation_category_from_text,
)
from general_indication_relevance import (
    ENGINE_VERSION as RELEVANCE_ENGINE_VERSION,
    HYBRID_CONFIG_VERSION,
    MATCH_EXACT_INDICATION,
    MATCH_EXPLICIT_FIELD_OVERLAP,
    MATCH_OUTCOME_OR_MECHANISM_SUPPORT,
    MATCH_CORPUS_DERIVED_SEMANTIC,
    MATCH_HYBRID_SEMANTIC,
    MATCH_EMBEDDING_SEMANTIC,
    MATCH_WEAK_LEXICAL,
    MATCH_CURATED_ASSIST_FALLBACK,
    build_indication_profile,
    corpus_texts_from_records,
    score_record_relevance_hybrid,
)

# Embedding/vector-search infrastructure is optional at import time. Step 5
# must never crash because the `openai` package is missing, misconfigured,
# or unreachable -- this defensive import is what makes that possible at
# the module-load level; per-run failures (bad API key, network error, RPC
# unavailable) are handled separately, at call time, inside embed_query()
# and match_evidence_embeddings() themselves (both already catch and
# return None/[] rather than raising).
try:
    from embedding_service import EMBEDDING_MODEL, EMBEDDING_VERSION, embed_query
    from vector_search import match_evidence_embeddings
    _EMBEDDING_INFRA_IMPORTED = True
except Exception as _embedding_import_exc:  # pragma: no cover - environment-dependent
    EMBEDDING_MODEL = "text-embedding-3-small"
    EMBEDDING_VERSION = "v1"
    _EMBEDDING_INFRA_IMPORTED = False

    def embed_query(*args, **kwargs):
        return None

    def match_evidence_embeddings(*args, **kwargs):
        return []

# TEMPORARY DIAGNOSTIC INSTRUMENTATION (performance audit — indication-
# centric Candidate Discovery runtime hang). Prints only; no behavior
# change. See discover_indication_candidates() and
# _build_plant_evidence_index() for where this is used.
def _perf(msg: str) -> None:
    print(f"[PERF] {msg}", flush=True)


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
    "Safety_Reassurance", "Safety_Data_Status",
    "Evidence_Species", "Evidence_Plant_Part", "Evidence_Preparation",
    "Evidence_Preparation_Category", "Evidence_Route", "Evidence_Dose",
    "Evidence_Dose_Unit", "Applicability_Classification",
    "Applicability_Data_Completeness", "Dimension_Status",
)

# Record-level output of the authoritative general_indication_relevance.py
# engine. Same reindex-guard requirement as _PHASE5_DIAGNOSTIC_COLUMNS above:
# OUTPUT_COLUMNS predates this engine and does not list these, so they must
# be included in every final reindex() call in this module or they are
# silently dropped before discover_indication_candidates() returns.
_RELEVANCE_ENGINE_COLUMNS = (
    "Indication_Match_Score", "Indication_Match_Type", "Indication_Match_Terms",
    "Indication_Match_Reason", "Indication_Match_Confidence",
    "Indication_Relevance_Engine_Version",
    "Explicit_Indication_Score", "Embedding_Similarity",
    "Outcome_Mechanism_Score", "Lexical_Fallback_Score",
    "Embedding_Model", "Embedding_Version",
)

INDICATION_CENTRIC_REFERENCE_LABEL = "Indication-centric discovery"
COMPOUND_NOT_GATING_LABEL = "Not used as candidate gate"
SCORING_CONFIG_VERSION = "2.2-indication-record-level-evidence"

# NOTE: superseded by indication_semantics.py, which its own docstring
# already describes as "the single source of truth used by both raw
# candidate discovery and plant-level shortlisting" -- it just was not
# actually wired into _terms() below until this fix. candidate_shortlisting.py
# (the later scoring stage) already used indication_semantics exclusively;
# this module still used only this narrower, 4-family dict for the earlier
# record-filtering stage, so any indication outside these four families (e.g.
# "Cough", "Migraine", "Eczema") fell back to a bare single/few-word literal
# substring match with no synonym or mechanistic support at all -- unlike the
# 27-family, alias-aware indication_semantics module, which already covers
# these indications with real clinical/mechanistic term sets.
# Kept only for reference; _terms() no longer reads from it.
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
    """Resolve an indication to (direct_terms, mechanistic_terms) from
    indication_semantics.py.

    This is NO LONGER the primary indication-matching mechanism (see
    general_indication_relevance.py, which is now authoritative and requires
    no per-indication dictionary entry). It is kept only to supply
    ``assist_terms`` to score_record_relevance()'s strictly-capped,
    disclosed backward-compatibility fallback path -- consulted only when
    the general corpus-adaptive engine finds no match at all. Its absence
    for any indication does not prevent discovery.
    """
    return _resolve_indication_terms(indication)




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
        if col in row and pd.notna(row.get(col)) and str(row.get(col)).strip():
            values.append(str(row.get(col)))

    # A record can exist solely to carry structured safety/interaction JSONB
    # (e.g. a case-report-derived adverse-event or drug-interaction entry with
    # no Title/Abstract/Outcome/Notes/Target_Indication text of its own). None
    # of the columns above cover that case, so such a record previously
    # produced an empty `text` here and was silently dropped by the
    # `if not text: continue` guard in _build_plant_evidence_index -- meaning
    # its Adverse_Events / Interactions_Structured never reached the plant's
    # evidence index at all, regardless of which indication it was stored
    # under. Render these structured columns (via _structured_text, which
    # safely handles JSONB dicts/lists without pandas truthiness ambiguity)
    # so the record is treated as non-empty and kept.
    structured_cols = (
        "Adverse_Events", "adverse_events",
        "Interactions_Structured", "interactions_structured",
        "Safety_Findings", "safety_findings",
        "Interactions", "interactions",
    )
    for col in structured_cols:
        if col in row:
            rendered = _structured_text(row.get(col))
            if rendered:
                values.append(rendered)

    # Join with ". " rather than a bare space. Downstream extraction
    # (safety_interaction_attribution._split) splits on sentence-ending
    # punctuation to classify one fragment at a time. Without a separator,
    # unrelated column values (e.g. Study_Type="Unknown", Evidence_Level=
    # "Unknown", Target_Indication="...", Notes="...") were glued into a
    # single run-on "sentence", so a genuine adverse-event/interaction
    # sentence in Notes could absorb neighboring placeholder values into the
    # accepted output, and vice versa. Each value keeps its own content
    # unchanged; only the join separator changes.
    return ". ".join(v.strip().rstrip(".") for v in values if v.strip())


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




def _extract_explicit_safety_and_interactions(
    text: object,
    plant_name: str = "",
) -> tuple[str, str]:
    """Compatibility wrapper returning adverse and interaction text only."""
    result = extract_attributed_safety_interactions(
        text, plant_name=plant_name, structurally_linked=True,
    )
    return "; ".join(result["adverse_events"]), "; ".join(result["interactions"])


def _extract_safety_details(text: object, plant_name: str) -> tuple[str, str, str, str]:
    """Detailed conservative output used by the indication workflow."""
    result = extract_attributed_safety_interactions(
        text, plant_name=plant_name, structurally_linked=True,
    )
    return (
        "; ".join(result["adverse_events"]),
        "; ".join(result["interactions"]),
        "; ".join(result["safety_reassurance"]),
        result["safety_data_status"],
    )




def _merge_unique_text(values: list[str]) -> str:
    """Join non-empty semicolon-delimited values without duplication."""
    seen = set()
    out = []
    for value in values:
        for part in str(value or "").split(";"):
            clean = part.strip()
            key = _norm(clean)
            if clean and key and key not in seen:
                seen.add(key)
                out.append(clean)
    return "; ".join(out)


def _aggregate_plant_safety(records: list[dict], plant_name: str) -> dict:
    """Aggregate plant-specific safety across all indications.

    Efficacy relevance is indication-specific, but adverse events and
    plant-drug interactions are properties of the botanical/preparation and
    must not disappear merely because the safety source was indexed under a
    different indication. Structured fields are preferred; conservative raw
    text attribution is used only as fallback for each record.
    """
    adverse_values: list[str] = []
    interaction_values: list[str] = []
    reassurance_values: list[str] = []
    statuses: list[str] = []

    for record in records:
        structured_safety = str(record.get("safety_findings") or "").strip()
        structured_interactions = str(record.get("interactions") or "").strip()

        if structured_safety or structured_interactions:
            structured = extract_structured_safety_interactions(
                structured_safety,
                structured_interactions,
                plant_name=plant_name,
            )
            adverse_values.extend(structured.get("adverse_events", []))
            interaction_values.extend(structured.get("interactions", []))
            reassurance_values.extend(structured.get("safety_reassurance", []))
            status = structured.get("safety_data_status")
            if status and status != "not_assessed":
                statuses.append(status)

        raw = extract_attributed_safety_interactions(
            " ".join(str(record.get(k) or "") for k in ("text", "notes")),
            plant_name=plant_name,
            structurally_linked=True,
        )
        adverse_values.extend(raw.get("adverse_events", []))
        interaction_values.extend(raw.get("interactions", []))
        reassurance_values.extend(raw.get("safety_reassurance", []))
        status = raw.get("safety_data_status")
        if status and status != "not_assessed":
            statuses.append(status)

    adverse = _merge_unique_text(adverse_values)
    interactions = _merge_unique_text(interaction_values)
    reassurance = _merge_unique_text(reassurance_values)

    status_parts = []
    if adverse:
        status_parts.append("adverse_signal_present")
    if interactions:
        status_parts.append("interaction_signal_present")
    if reassurance:
        status_parts.append("reassurance_reported")
    if not status_parts:
        if any("source_excluded" in str(s) for s in statuses):
            status_parts.append("source_excluded")
        else:
            status_parts.append("not_assessed")

    return {
        "adverse_events": adverse,
        "interactions": interactions,
        "safety_reassurance": reassurance,
        "safety_data_status": "; ".join(status_parts),
    }


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
    _t_start = time.perf_counter()
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
    _rows_examined = 0
    _rows_retained = 0

    for frame in frames:
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        # Performance fix (Step 5 runtime audit): frame.iterrows() rebuilds a
        # full pandas Series -- with its own dtype-unification and index
        # machinery -- for every one of the (real production: ~22,500+)
        # evidence rows, purely so this function can call row.get(col) a
        # few dozen times per row. That Series construction, not the field
        # lookups themselves, was measured as the dominant cost of this
        # loop. frame.to_dict("records") converts the whole frame to plain
        # dicts in one vectorized pass; iterating those dicts (paired back
        # up with the frame's original index via zip, so idx/_record_id's
        # fallback-index behavior is byte-identical to before) preserves
        # every field value and type exactly -- pd.notna()/str() behave the
        # same on a dict's scalar values as on a Series', and the `col in
        # row` checks above were updated to work for both -- while removing
        # only the per-row Series-construction overhead itself.
        for idx, row in zip(frame.index, frame.to_dict("records")):
            _rows_examined += 1
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
            _rows_retained += 1
            index.setdefault(plant_key, []).append({
                "text": text,
                "source": source,
                "record_id": record_id,
                "plant_name": row_plant,
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
                # Keep study preparation, dosage form, route, plant part and
                # dose as separate facts.  The old pooled "preparation" field
                # mixed all five concepts, allowing a selected/legacy dosage
                # form to masquerade as the preparation actually studied.
                "plant_part": _structured_text(_pick_from_row(engine, row, ["Plant_Part", "plant_part"])),
                "preparation": _structured_text(_pick_from_row(engine, row, [
                    "Preparation", "preparation", "Extraction_Method", "extraction_method",
                ])),
                "preparation_category": _structured_text(_pick_from_row(engine, row, [
                    "Preparation_Category", "preparation_category", "LLM_Preparation_Category",
                ])),
                "dosage_form": _structured_text(_pick_from_row(engine, row, [
                    "Dosage_Form_Detected", "Detected_Dosage_Forms", "Dosage_Form", "dosage_form",
                ])),
                "route": _structured_text(_pick_from_row(engine, row, [
                    "Administration_Route", "administration_route", "Route", "route",
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
                # Field-aware tiers for general_indication_relevance.py. Tier 1
                # (explicit indication fields) is authoritative for indication
                # matching; Tier 2 (outcome/mechanism) and Tier 3 (source text)
                # degrade in that order. Kept separate from the flat "text"
                # blob above (which is used for safety/interaction extraction
                # and stays untouched) so a match found only in raw source
                # text never outranks an explicit indication field match.
                "tier1_text": _pick_from_row(engine, row, [
                    "Target_Indication", "target_indication",
                    "Detected_Indications", "detected_indications",
                    "Indication", "indication", "Disease", "disease", "Condition", "condition",
                ]),
                # Direct vs indirect evidence fix: the record's OWN reported
                # outcome (what the study actually found/measured) is kept
                # separate from its mechanism/target ANNOTATION (what
                # biological pathway is implicated). A query term appearing
                # only in the mechanism/target annotation ("GABAergic
                # system", "sedative") is indirect/mechanistic support, not
                # a directly reported result, and general_indication_
                # relevance.py's outcome_text parameter (below) now scores
                # the two differently instead of pooling them into one
                # "tier2" blob that let either trigger the same "direct
                # evidence" strength. This is generalizable to every
                # indication -- it never inspects which words appear, only
                # which FIELD they came from.
                "outcome_text": " ".join(t for t in (
                    _structured_text(_pick_from_row(engine, row, ["Primary_Outcome", "primary_outcome", "Outcome", "outcome"])),
                    _structured_text(_pick_from_row(engine, row, ["Result_Direction", "result_direction"])),
                ) if t),
                "tier2_text": " ".join(t for t in (
                    _pick_from_row(engine, row, ["Mechanism", "mechanism"]),
                    _pick_from_row(engine, row, ["Target", "target"]),
                ) if t),
                "tier3_text": " ".join(t for t in (
                    _pick_from_row(engine, row, ["Title", "title"]),
                    _pick_from_row(engine, row, ["Abstract", "abstract"]),
                    _structured_text(_pick_from_row(engine, row, ["Notes", "notes"])),
                    _pick_from_row(engine, row, ["Source_Raw_Text", "source_raw_text", "Raw_Text", "raw_text"]),
                    _pick_from_row(engine, row, ["Study_Type", "study_type"]),
                    _pick_from_row(engine, row, ["Evidence_Type", "evidence_type", "Evidence_Level", "evidence_level"]),
                ) if t),
            })
    _perf(
        f"_build_plant_evidence_index done rows_examined={_rows_examined} "
        f"rows_retained={_rows_retained} plants_indexed={len(index)} "
        f"elapsed={time.perf_counter() - _t_start:.3f}"
    )
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
    classified_hierarchy = None
    if text:
        try:
            from evidence_hierarchy_classifier import classify_evidence_hierarchy
            classified_hierarchy = classify_evidence_hierarchy(text)
        except Exception:
            classified_hierarchy = None
    hierarchy = explicit_hierarchy or classified_hierarchy or level

    if registry_without_results:
        level = "Registry record without reported results"
        hierarchy = "Registry / protocol only"
        classified_hierarchy = None

    context = _norm(f"{level} {hierarchy} {text}")

    # Study-type/evidence-hierarchy fix (generalizable to every indication,
    # no hardcoded plant/indication vocabulary): `human`/`preclinical` used
    # to be decided by a bare substring check over the WHOLE pooled record
    # text ("human" in context). That produces real false positives -- e.g.
    # "human keratinocytes" or "human liver microsomes" (both in-vitro
    # studies) contain the literal word "human" without being clinical
    # evidence at all, so such a record was previously scored as "Direct
    # human evidence" (the same tier as a genuine RCT). classify_evidence_
    # hierarchy() (evidence_hierarchy_classifier.py) is already built,
    # phrase-aware (requires "human trial"/"human study"/"clinical study",
    # not a bare "human" substring) and checks tiers strongest-first, but
    # was previously computed only for the display column
    # (Evidence_Hierarchy_Detail) and never consulted by scoring. It is now
    # the authoritative source for the human/preclinical split whenever it
    # recognizes a tier; the previous substring check is kept ONLY as a
    # fallback for text the classifier doesn't recognize at all, so
    # existing behavior for unclassifiable free text is unchanged.
    _HUMAN_HIERARCHY_TIERS = {
        "Systematic review / meta-analysis", "Clinical trial",
        "Observational human evidence",
    }
    _PRECLINICAL_HIERARCHY_TIERS = {
        "Validated ex vivo / in vivo", "In vitro / mechanistic",
    }
    if classified_hierarchy in _HUMAN_HIERARCHY_TIERS:
        human = not registry_without_results
        preclinical = False
    elif classified_hierarchy in _PRECLINICAL_HIERARCHY_TIERS:
        human = False
        preclinical = True
    elif classified_hierarchy is not None:
        # Traditional-use/monograph or occurrence/analytical-chemistry-only
        # -- the classifier recognized a tier, and it is neither human
        # clinical nor preclinical.
        human = False
        preclinical = False
    else:
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
        "hierarchy_tier": classified_hierarchy,
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

def discover_indication_candidates(
    engine, indication: str, dosage_form: str = "", market: str = "",
    product_type: str = "", progress_callback=None, target_context=None,
) -> pd.DataFrame:
    """Return OUTPUT_COLUMNS-compatible rows using plant-specific evidence.

    ``progress_callback`` is an optional presentation hook used by the Streamlit
    Step 5 UI. It receives ``(stage, current, total, message)`` and never feeds
    back into scoring, filtering, ranking, or scientific interpretation.
    """

    def _progress(stage: str, current: int = 0, total: int = 0, message: str = ""):
        if progress_callback is None:
            return
        try:
            progress_callback(stage, current, total, message)
        except Exception:
            # UI telemetry must never be able to change or abort scientific
            # execution. A broken/closed Streamlit progress element is ignored.
            pass
    from botanical_rd_candidate_engine import OUTPUT_COLUMNS

    _t0 = time.perf_counter()
    _perf(f"discover_indication_candidates start indication={indication!r} dosage_form={dosage_form!r} market={market!r}")
    resolved_target_context = dict(target_context or {})
    if not resolved_target_context:
        # Backward-compatible direct callers still get the scientifically safe
        # subset of target context that can be established from the legacy
        # arguments. A true preparation-like form (e.g. infusion) is usable;
        # dosage-form-only values such as capsule/tablet are not invented as
        # botanical preparations.
        if indication:
            resolved_target_context["Target_Indication"] = indication
        legacy_preparation = preparation_from_product_form(dosage_form)
        if legacy_preparation:
            resolved_target_context["Target_Preparation"] = legacy_preparation
            category = preparation_category_from_text(legacy_preparation)
            if category:
                resolved_target_context["Target_Preparation_Category"] = category

    candidates = engine._candidate_frame()
    _perf(f"engine._candidate_frame() done candidate_plants={len(candidates)} elapsed={time.perf_counter() - _t0:.3f}")
    _progress(
        "candidate_universe", 0, len(candidates),
        f"Candidate universe prepared: {len(candidates)} plants.",
    )
    if candidates.empty:
        _perf(f"discover_indication_candidates done (empty candidates) elapsed={time.perf_counter() - _t0:.3f}")
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS) + list(_RELEVANCE_ENGINE_COLUMNS))

    # Build ONE corpus-adaptive relevance profile for this query from the
    # full evidence corpus (every plant's records), and reuse it for every
    # record below. This is the single authoritative relevance engine --
    # general_indication_relevance.py -- and it requires no per-indication
    # dictionary entry: an unseen indication (e.g. a novel R&D question) is
    # scored the same way as a familiar one. indication_semantics.py, if it
    # resolves this indication, supplies only a strictly-capped, disclosed
    # assist_terms fallback consulted inside score_record_relevance() when
    # the corpus-adaptive engine finds no match at all; it never overrides
    # a corpus-adaptive match and is never required.
    evidence_index = _build_plant_evidence_index(engine)
    _progress(
        "evidence_index", 0, len(candidates),
        f"Evidence index built for {len(evidence_index)} plants.",
    )
    _t_profile = time.perf_counter()
    relevance_profile = build_indication_profile(
        indication, corpus_texts_from_records(evidence_index),
    )
    _perf(f"build_indication_profile() done elapsed={time.perf_counter() - _t_profile:.3f} (cumulative={time.perf_counter() - _t0:.3f})")
    _progress(
        "profile", 0, len(candidates),
        "Indication relevance profile prepared.",
    )
    assist_family = _resolve_indication_terms(indication)
    assist_terms: tuple[str, ...] = tuple(dict.fromkeys(
        (*assist_family[0], *assist_family[1])
    )) if assist_family else ()

    # --- Embedding: query embedded ONCE per run, vector search called ONCE
    # per run (never once per plant, never once per record). Both steps are
    # wrapped so any failure (missing API key, network error, RPC
    # unavailable, migration not yet applied) degrades to fallback_mode
    # rather than raising -- Step 5 must keep working with the deterministic
    # engine alone when embeddings are unavailable.
    _t_embed = time.perf_counter()
    query_embedding = embed_query(indication)
    _perf(
        f"embed_query() done have_embedding={bool(query_embedding)} "
        f"elapsed={time.perf_counter() - _t_embed:.3f} (cumulative={time.perf_counter() - _t0:.3f})"
    )
    _progress(
        "embedding", 0, len(candidates),
        "Semantic query embedding ready." if query_embedding
        else "Semantic embedding unavailable; continuing with deterministic relevance.",
    )
    embedding_fallback_reason = "" if query_embedding else (
        "embedding provider unavailable" if not _EMBEDDING_INFRA_IMPORTED
        else "query embedding failed or OPENAI_API_KEY not configured"
    )
    embedding_by_record_id: dict[str, float] = {}
    if query_embedding:
        _t_vector_search = time.perf_counter()
        rpc_matches = match_evidence_embeddings(
            query_embedding, match_count=500,
            embedding_model=EMBEDDING_MODEL, embedding_version=EMBEDDING_VERSION,
        )
        _perf(
            f"match_evidence_embeddings() done matches={len(rpc_matches)} "
            f"elapsed={time.perf_counter() - _t_vector_search:.3f} (cumulative={time.perf_counter() - _t0:.3f})"
        )
        for match in rpc_matches:
            rid = match.get("evidence_record_id")
            similarity = match.get("cosine_similarity")
            if rid is not None and similarity is not None:
                embedding_by_record_id[str(rid)] = float(similarity)
        if not rpc_matches:
            embedding_fallback_reason = embedding_fallback_reason or "no embedding matches returned (RPC unavailable or table empty)"

    def _score(record: dict | None, tier1: str, tier2: str, tier3: str):
        embedding_similarity = (
            embedding_by_record_id.get(str(record.get("record_id"))) if record else None
        )
        outcome_text = record.get("outcome_text", "") if record else ""
        return score_record_relevance_hybrid(
            relevance_profile, tier1, tier2, tier3, assist_terms,
            embedding_similarity=embedding_similarity,
            outcome_text=outcome_text,
        )

    _MATCH_STRONG = (MATCH_EXACT_INDICATION, MATCH_EXPLICIT_FIELD_OVERLAP)
    _MATCH_SUPPORTIVE = (
        MATCH_OUTCOME_OR_MECHANISM_SUPPORT, MATCH_CORPUS_DERIVED_SEMANTIC,
        MATCH_HYBRID_SEMANTIC, MATCH_EMBEDDING_SEMANTIC,
        MATCH_WEAK_LEXICAL, MATCH_CURATED_ASSIST_FALLBACK,
    )

    rows = []

    _loop_start = time.perf_counter()
    _total_candidate_plants = len(candidates)
    _plants_processed = 0
    _evidence_records_examined = 0
    _records_scored_for_relevance = 0
    _relevant_records_retained = 0
    _safety_extraction_calls = 0
    _normalization_calls = 0
    _validation_calls = 0
    _PROGRESS_EVERY = 200

    # Narrowly-scoped inner-loop diagnostic pass (per-section cumulative
    # call counts and elapsed seconds). Diagnostic-only: no thresholds,
    # counts, or behavior are read from these values anywhere.
    _SECTION_ORDER = (
        "records_for_plant", "safety_aggregate", "relevance",
        "dedup_sort", "characteristics", "safety_extraction",
        "normalization", "validation", "row_build",
    )
    _section_calls = {name: 0 for name in _SECTION_ORDER}
    _section_seconds = {name: 0.0 for name in _SECTION_ORDER}

    def _section_add(name, elapsed):
        _section_calls[name] += 1
        _section_seconds[name] += elapsed

    def _print_loop_profile(label):
        detail_lines = [
            f"  plants_processed={_plants_processed}/{_total_candidate_plants}, "
            f"evidence_records_examined={_evidence_records_examined}, "
            f"relevant_records_retained={_relevant_records_retained}, "
            f"output_rows={len(rows)}, "
            f"elapsed={time.perf_counter() - _loop_start:.3f}"
        ]
        for name in _SECTION_ORDER:
            calls = _section_calls[name]
            total = _section_seconds[name]
            avg_ms = (total / calls * 1000.0) if calls else 0.0
            detail_lines.append(
                f"  {name}: calls={calls} total={total:.3f} avg_ms={avg_ms:.2f}"
            )
        print(f"[PERF] loop profile {label}\n" + "\n".join(detail_lines), flush=True)

    _progress(
        "scoring", 0, _total_candidate_plants,
        f"Scoring 0 / {_total_candidate_plants} plants…",
    )

    # Same performance fix as _build_plant_evidence_index() above, applied to
    # the outer per-candidate-plant loop: candidates.iterrows() pays Series-
    # construction cost once per candidate plant (real production: ~2,000+)
    # purely to support engine._pick(item, [...]), which only ever calls
    # item.get(name, "") -- identical on a dict. Converting once, up front,
    # to a list of plain dicts removes that per-plant overhead with no
    # change to which plant, field, or value is read.
    for item in candidates.to_dict("records"):
        _plants_processed += 1
        plant = engine._pick(item, ["Scientific_Name", "scientific_name", "Plant", "plant"])
        if not plant:
            continue

        indications = engine._pick(item, ["Indications_Text", "Indications", "indication"])
        targets = engine._pick(item, ["Known_Targets", "target", "mechanism"])
        compounds = engine._split_compound_terms(engine._pick(item, ["Known_Active_Compounds", "compound_name"]))
        _t = time.perf_counter()
        records = _records_for_plant(engine, plant, evidence_index)
        _section_add("records_for_plant", time.perf_counter() - _t)
        _evidence_records_examined += len(records)

        for record in records:
            if "relevance" not in record:
                _t = time.perf_counter()
                record["relevance"] = _score(
                    record, record.get("tier1_text", ""), record.get("tier2_text", ""), record.get("tier3_text", ""),
                )
                _section_add("relevance", time.perf_counter() - _t)
                _records_scored_for_relevance += 1

        direct_records = [r for r in records if r["relevance"].match_type in _MATCH_STRONG]
        mechanism_records = [r for r in records if r["relevance"].match_type in _MATCH_SUPPORTIVE]

        # Database profile fields may create an exploratory lead, but never a
        # direct-evidence candidate and never a shortlist by themselves.
        # No embedding is attempted here: profile fields (Indications_Text/
        # Known_Targets) have no evidence_record_id to join an embedding
        # match to, so this always scores via the deterministic engine only.
        _t = time.perf_counter()
        profile_relevance = _score(None, indications, targets, "")
        _section_add("relevance", time.perf_counter() - _t)
        _records_scored_for_relevance += 1
        profile_direct = profile_relevance.match_type in _MATCH_STRONG
        profile_mechanistic = profile_relevance.match_type in _MATCH_SUPPORTIVE

        if not direct_records and not mechanism_records and not profile_direct and not profile_mechanistic:
            if _plants_processed % _PROGRESS_EVERY == 0:
                _progress(
                    "scoring", _plants_processed, _total_candidate_plants,
                    f"Scoring {_plants_processed} / {_total_candidate_plants} plants…",
                )
                _perf(
                    f"indication loop {_plants_processed}/{_total_candidate_plants} plants, "
                    f"evidence_records_examined={_evidence_records_examined}, "
                    f"relevant_records_retained={_relevant_records_retained}, "
                    f"output_rows={len(rows)}, "
                    f"elapsed={time.perf_counter() - _loop_start:.3f}"
                )
                _print_loop_profile(f"{_plants_processed}/{_total_candidate_plants}")
            continue

        # Phase 2E (performance correction — item 1 only): moved from
        # before the relevance gate above to here, immediately after it.
        # Safety/interaction evidence is still plant-wide, not
        # indication-bound, and is still computed exactly once per
        # RETAINED plant (never once per evidence record, never
        # recomputed inside the evidence_units loop below) — only the
        # ORDER changed. Per the Phase 2D performance audit,
        # _aggregate_plant_safety() was the single most expensive
        # section (41.13s / 27.8% of total loop time in the real
        # 2,119-plant log) and was running for every candidate plant
        # BEFORE the relevance gate, even though its result is only
        # ever read below, for plants that pass the gate — i.e. it ran
        # in full for the ~91% of plants (1,937 of 2,119 in that log)
        # that get skipped by the `continue` above and never reach
        # this line. No relevance rule, threshold, match type, or
        # candidate inclusion/exclusion changed — this is strictly a
        # reordering of two already-existing, unmodified blocks.
        _t = time.perf_counter()
        plant_safety = _aggregate_plant_safety(records, plant)
        _section_add("safety_aggregate", time.perf_counter() - _t)

        # Preserve record-level granularity.  The previous implementation
        # collapsed every source for a plant into one synthetic row, assigned
        # that row the strongest hierarchy label seen anywhere in the combined
        # text, and therefore made many plants tie.  Each relevant source now
        # becomes its own raw association row; candidate_shortlisting.py can
        # then measure study depth, hierarchy mix, consistency and independent
        # source count honestly.
        relevant_records: list[dict] = []
        seen_relevant: set[tuple[str, str, str]] = set()
        _t = time.perf_counter()
        for record in direct_records + mechanism_records:
            key = (_norm(record.get("record_id")), _norm(record.get("source")), _norm(record.get("text")))
            if key not in seen_relevant:
                seen_relevant.add(key)
                relevant_records.append(record)
        _section_add("dedup_sort", time.perf_counter() - _t)
        _relevant_records_retained += len(relevant_records)

        evidence_units: list[dict | None] = relevant_records or [None]
        for record in evidence_units:
            record_text = str(record.get("text") or "")[:12000] if record else ""
            record_relevance = record["relevance"] if record else profile_relevance
            record_direct = bool(record and record_relevance.match_type in _MATCH_STRONG)
            record_mechanistic = bool(record and record_relevance.match_type in _MATCH_SUPPORTIVE)
            profile_only = record is None

            _t = time.perf_counter()
            characteristics = (
                _record_evidence_characteristics(engine, record)
                if record is not None else {
                    "level": "Profile-level hypothesis",
                    "hierarchy": "Profile-level hypothesis",
                    "hierarchy_tier": None,
                    "human": False,
                    "preclinical": False,
                    "registry_without_results": False,
                    "negative": False,
                }
            )
            _section_add("characteristics", time.perf_counter() - _t)
            level = characteristics["level"]
            hierarchy = characteristics["hierarchy"]
            hierarchy_tier = characteristics.get("hierarchy_tier")
            human = characteristics["human"]
            preclinical = characteristics["preclinical"]
            registry_without_results = characteristics["registry_without_results"]
            negative = characteristics["negative"]

            source = str(record.get("source") or "").strip() if record else ""
            record_id = str(record.get("record_id") or "").strip() if record else ""
            sources = [source] if source else []
            record_ids = [record_id] if record_id else []
            result_direction = characteristics.get("resolved_result_direction", "") if record else ""
            record_preparation = str(record.get("preparation") or "").strip() if record else ""

            # Authoritative preparation transferability is now computed from
            # separate record facts vs. the explicit target product context.
            # The legacy _preparation_applicability() signal remains available
            # for old callers/tests but no longer drives this production row.
            _transfer_fields = evidence_transferability_fields(
                species=plant,
                plant_part=(record.get("plant_part") if record else ""),
                preparation=record_preparation,
                preparation_category=(record.get("preparation_category") if record else ""),
                route=(record.get("route") if record else ""),
                dose=(record.get("dose") if record else ""),
                indication_match_type=(record_relevance.match_type if record else ""),
            )
            if record and record.get("preparation_category"):
                _transfer_fields["Evidence_Preparation_Category"] = str(
                    record.get("preparation_category") or ""
                ).strip()
            _transfer_result = evaluate_applicability(
                _transfer_fields, resolved_target_context
            ) if resolved_target_context else {
                "Applicability_Classification": "UNKNOWN",
                "Applicability_Data_Completeness": "incomplete",
                "Dimension_Status": {},
            }
            _transfer_class = _transfer_result.get("Applicability_Classification", "UNKNOWN")
            if _transfer_class == "MISMATCH":
                preparation_status = "Mismatch"
                preparation_mismatches = ["Confirmed evidence-vs-target transferability mismatch"]
            elif _transfer_class in {"MATCH", "PARTIAL"}:
                preparation_status = "Compatible"
                preparation_mismatches = []
            else:
                preparation_status = "Unknown"
                preparation_mismatches = ["Transferability incomplete or unknown"]

            safety_findings = str(record.get("safety_findings") or "").strip() if record else ""
            interactions = str(record.get("interactions") or "").strip() if record else ""
            safety_reassurance = ""
            safety_data_status = "not_assessed"
            if record:
                # First sanitize structured fields as plant-scoped evidence. The
                # plant prefix supplies the structural attribution, while the
                # conservative extractor still rejects comparator noise,
                # protective/negated toxicity, other botanicals and retractions.
                structured_safety = structured_interactions = structured_reassurance = ""
                structured_status = "not_assessed"
                _t = time.perf_counter()
                if safety_findings or interactions:
                    structured_result = extract_structured_safety_interactions(
                        safety_findings, interactions, plant_name=plant,
                    )
                    _safety_extraction_calls += 1
                    structured_safety = "; ".join(structured_result["adverse_events"])
                    structured_interactions = "; ".join(structured_result["interactions"])
                    structured_reassurance = "; ".join(structured_result["safety_reassurance"])
                    structured_status = structured_result["safety_data_status"]

                # Then inspect raw source text only as a fallback. It must carry
                # its own plant/intervention anchor and explicit relation.
                source_safety, source_interactions, source_reassurance, source_status = (
                    _extract_safety_details(
                        " ".join(str(record.get(k) or "") for k in ("text", "notes")),
                        plant_name=plant,
                    )
                )
                _safety_extraction_calls += 1
                _section_add("safety_extraction", time.perf_counter() - _t)
                safety_findings = structured_safety or source_safety
                interactions = structured_interactions or source_interactions
                safety_reassurance = structured_reassurance or source_reassurance
                safety_data_status = (
                    structured_status if structured_status != "not_assessed" else source_status
                )

            # Add cross-indication plant-specific safety. A safety case report
            # indexed under eye health or cognition must still inform a
            # metabolic R&D decision for the same botanical.
            safety_findings = _merge_unique_text([
                safety_findings, plant_safety["adverse_events"]
            ])
            interactions = _merge_unique_text([
                interactions, plant_safety["interactions"]
            ])
            safety_reassurance = _merge_unique_text([
                safety_reassurance, plant_safety["safety_reassurance"]
            ])
            status_parts = []
            if safety_findings:
                status_parts.append("adverse_signal_present")
            if interactions:
                status_parts.append("interaction_signal_present")
            if safety_reassurance:
                status_parts.append("reassurance_reported")
            safety_data_status = "; ".join(status_parts) or plant_safety["safety_data_status"]

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
                _t = time.perf_counter()
                _normalized_fields = normalize_evidence_record(_phase5_row)
                _normalization_calls += 1
                _section_add("normalization", time.perf_counter() - _t)
                _t = time.perf_counter()
                _validation_result = validate_evidence_record(
                    _phase5_row,
                    plant_name=plant,
                    indication=indication,
                    dosage_form=dosage_form,
                    normalized_fields=_normalized_fields,
                )
                _validation_calls += 1
                _section_add("validation", time.perf_counter() - _t)
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
                # Evidence-hierarchy fix (generalizable to every indication):
                # previously every human-associated record earned the same
                # flat 35 points regardless of study type, so a single case
                # report scored identically to a Cochrane systematic review.
                # classify_evidence_hierarchy() (evidence_hierarchy_
                # classifier.py) already distinguishes these; its tier is
                # now used to grade this bucket instead of collapsing it.
                # Ten weak observational mentions still cannot out-rank one
                # strong review, because this graduation applies PER
                # RECORD -- it does not change how many records a plant can
                # accumulate.
                evidence_points = {
                    "Systematic review / meta-analysis": 35,
                    "Clinical trial": 32,
                    "Observational human evidence": 28,
                }.get(hierarchy_tier, 30)
                tier = "Direct human evidence"
                decision = "Indication-based R&D candidate"
                call = "Investigate"
            elif record_direct and preclinical:
                # Same fix, preclinical bucket: a validated in-vivo/animal
                # model is stronger evidence than an in-vitro/mechanistic
                # (receptor-binding, cell-line) finding, which the previous
                # flat 27 did not reflect.
                evidence_points = {
                    "Validated ex vivo / in vivo": 27,
                    "In vitro / mechanistic": 20,
                }.get(hierarchy_tier, 24)
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
                record_relevance.matched_terms[:5] if (record_mechanistic or profile_mechanistic) else []
            )
            rationale = (
                f"{plant} has a plant-specific evidence record linked to the requested indication; "
                "shared chemistry was not used as an entry gate."
                if record is not None else
                f"{plant} is retained only as a profile-derived hypothesis; no plant-specific empirical record linked to the requested indication was found."
            )

            _t = time.perf_counter()
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
                "Safety_Reassurance": safety_reassurance,
                "Safety_Data_Status": safety_data_status,
                "Indication_Match_Score": record_relevance.final_relevance_score,
                "Indication_Match_Type": record_relevance.match_type,
                "Indication_Match_Terms": "; ".join(record_relevance.matched_terms),
                "Indication_Match_Reason": record_relevance.reason,
                "Indication_Match_Confidence": record_relevance.confidence,
                "Indication_Relevance_Engine_Version": f"{RELEVANCE_ENGINE_VERSION}+{HYBRID_CONFIG_VERSION}",
                "Explicit_Indication_Score": record_relevance.explicit_indication_score,
                "Embedding_Similarity": record_relevance.embedding_similarity,
                "Outcome_Mechanism_Score": record_relevance.outcome_mechanism_score,
                "Lexical_Fallback_Score": record_relevance.lexical_fallback_score,
                "Embedding_Model": EMBEDDING_MODEL if not record_relevance.fallback_mode else f"{EMBEDDING_MODEL} (fallback: {embedding_fallback_reason or 'unavailable for this record'})",
                "Embedding_Version": EMBEDDING_VERSION,
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
                "Evidence_Species": _transfer_fields.get("Evidence_Species", ""),
                "Evidence_Plant_Part": _transfer_fields.get("Evidence_Plant_Part", ""),
                "Evidence_Preparation": _transfer_fields.get("Evidence_Preparation", ""),
                "Evidence_Preparation_Category": _transfer_fields.get("Evidence_Preparation_Category", ""),
                "Evidence_Route": _transfer_fields.get("Evidence_Route", ""),
                "Evidence_Dose": _transfer_fields.get("Evidence_Dose", ""),
                "Evidence_Dose_Unit": _transfer_fields.get("Evidence_Dose_Unit", ""),
                "Applicability_Classification": _transfer_result.get("Applicability_Classification", "UNKNOWN"),
                "Applicability_Data_Completeness": _transfer_result.get("Applicability_Data_Completeness", "incomplete"),
                "Dimension_Status": _transfer_result.get("Dimension_Status", {}),
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
                # Phase 4 — Eligibility Gate compatibility fields.
                # This module has its OWN hard-safety-exclusion logic
                # (safety_findings above) that is untouched by Phase 4 —
                # it was out of scope for that phase's audit and is not
                # rebuilt here. These fields exist ONLY so that
                # consumers now reading the structured Eligibility_Status/
                # Eligible_For_Normal_Ranking columns (candidate_shortlisting.py,
                # step_rd_candidates.py, pharma_report_generator.py) don't
                # silently treat every row from this discovery mode as
                # ineligible just because the column was previously blank
                # here — `call` (Go_Investigate_Hold_NoGo, computed above)
                # is this module's own existing, tested signal for
                # Hold/No-Go, reused as-is rather than re-derived.
                "Eligibility_Status": (
                    "eligible_with_restrictions" if (safety_findings or interactions) else "eligible"
                ),
                "Hard_No_Go": False,
                "Eligible_For_Normal_Ranking": not str(call).strip().startswith(("Hold", "No-Go")),
                "Score_Validity": "valid",
                "Gate_Type": "none",
                "Gate_Reason": (
                    "Indication-centric discovery path; Phase 4 Eligibility "
                    "Gate is not wired into this module's own hard-safety-"
                    "exclusion logic (documented as out of scope for Phase "
                    "4 — see the Phase 4 report's file list)."
                ),
                "Gate_Evidence_IDs": record_id or "",
                "Safety_Severity": "minor" if (safety_findings or interactions) else "none",
                "Safety_Scope": "unknown",
                "Safety_Context_Relevance": "unknown",
                "Regulatory_Status": "insufficient_data",
                "Regulatory_Scope": "unknown",
                "Regulatory_Context_Relevance": "unknown",
                "Data_Completeness": "complete" if (record_direct or record_mechanistic) else "incomplete",
                "Requires_Expert_Review": False,
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
            _section_add("row_build", time.perf_counter() - _t)

        if _plants_processed % _PROGRESS_EVERY == 0:
            _progress(
                "scoring", _plants_processed, _total_candidate_plants,
                f"Scoring {_plants_processed} / {_total_candidate_plants} plants…",
            )
            _perf(
                f"indication loop {_plants_processed}/{_total_candidate_plants} plants, "
                f"evidence_records_examined={_evidence_records_examined}, "
                f"relevant_records_retained={_relevant_records_retained}, "
                f"output_rows={len(rows)}, "
                f"elapsed={time.perf_counter() - _loop_start:.3f}"
            )
            _print_loop_profile(f"{_plants_processed}/{_total_candidate_plants}")

    _progress(
        "scoring", _total_candidate_plants, _total_candidate_plants,
        f"Scoring complete: {_total_candidate_plants} / {_total_candidate_plants} plants.",
    )
    _perf(
        f"indication loop done plants_processed={_plants_processed}/{_total_candidate_plants}, "
        f"evidence_records_examined={_evidence_records_examined}, "
        f"records_scored_for_relevance={_records_scored_for_relevance}, "
        f"relevant_records_retained={_relevant_records_retained}, "
        f"safety_extraction_calls={_safety_extraction_calls}, "
        f"normalization_calls={_normalization_calls}, "
        f"validation_calls={_validation_calls}, "
        f"output_rows={len(rows)}, "
        f"elapsed={time.perf_counter() - _loop_start:.3f} "
        f"(cumulative={time.perf_counter() - _t0:.3f})"
    )
    _print_loop_profile("final")

    if not rows:
        _progress("discovery_done", 0, 0, "Candidate discovery finished — no candidates found.")
        return pd.DataFrame(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS) + list(_RELEVANCE_ENGINE_COLUMNS))
    out = pd.DataFrame(rows)
    out = out.sort_values(["R&D_Opportunity_Score", "Evidence_Confidence"], ascending=False)
    _progress(
        "discovery_done", len(out), len(out),
        f"Record-level discovery complete: {len(out)} candidate evidence rows.",
    )
    return out.reindex(columns=list(OUTPUT_COLUMNS) + list(_PHASE5_DIAGNOSTIC_COLUMNS) + list(_RELEVANCE_ENGINE_COLUMNS)).reset_index(drop=True)
