"""Canonical, deterministic embedding text for one evidence record.

Single authoritative function: build_evidence_embedding_text(). Both the
backfill script and any future re-embedding path must call this and only
this, so the text an embedding was computed from is always reproducible
from the record alone -- which is what makes content_hash-based
re-embedding-only-on-change possible at all. This includes its
citation/identity-only fallback tier (used only when every primary field
is empty) -- that fallback lives here too, not in a second function
elsewhere, so there is still only one place text is ever assembled from.

This module has NO network dependency and NO disease-specific vocabulary.
It only assembles already-extracted field values into a labeled string.
"""
from __future__ import annotations

import hashlib
from typing import Mapping


# Source types that are proxy/composition/protection records, not efficacy
# evidence, and must not be embedded as if they described a clinical or
# mechanistic finding. Matched case-insensitively against Source_Type.
# See EMBEDDING_ARCHITECTURE_REVIEW.md section 3 for why each is excluded;
# this list reflects the Source_Type tags that actually exist in this
# repository's connectors today (verified by inspection, not assumed) --
# "market records" from the brief has no corresponding connector in this
# repository at the time of writing, so nothing is excluded under that
# label yet; the check is written generically (against a documented,
# extensible set) so a future market-record connector only needs to add
# its Source_Type/Evidence_Type string here, not new exclusion logic.
EXCLUDED_SOURCE_TYPES = {
    "chebi",                # chebi_connector.py -- chemical ontology, not efficacy evidence
    "patent/literature",    # patent_connector.py -- protection landscape, not efficacy evidence
    "dailymed",             # dailymed_connector.py -- multi-ingredient label proxy
}

EXCLUDED_EVIDENCE_TYPES = {
    "chemical composition",  # ChEBI / PubChem
    "patent landscape",      # patent_connector.py
    "safety/label",          # DailyMed -- label text, not an efficacy finding
}


def is_proxy_or_excluded_record(source_type: object, evidence_type: object) -> bool:
    """True if this record must not be embedded as efficacy evidence.

    Safety-only records ARE NOT excluded by this function -- they remain
    available for plant-wide safety aggregation elsewhere (see
    indication_candidate_discovery._aggregate_plant_safety, unchanged by
    this module). This function excludes only proxy/composition/protection
    sources: chemistry-ontology, patent-landscape, and label-proxy records
    that were never efficacy evidence in the first place.
    """
    st = str(source_type or "").strip().lower()
    et = str(evidence_type or "").strip().lower()
    return st in EXCLUDED_SOURCE_TYPES or et in EXCLUDED_EVIDENCE_TYPES


def _labeled(label: str, value: object) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "unknown"}:
        return ""
    return f"{label}: {text}"


def build_evidence_embedding_text(record: Mapping[str, object]) -> str:
    """Build the canonical, deterministic text embedded for one evidence
    record.

    ``record`` is expected to carry the same field names already used
    throughout indication_candidate_discovery.py's per-record evidence
    index (see _build_plant_evidence_index): plant_name, tier1_text
    (target_indication/extracted_indication/detected), tier2_text
    (primary_outcome/result_direction/mechanism/target), tier3_text
    (title/abstract/notes/source_raw_text/study_type/evidence_type), plus
    study_type, evidence_level, preparation. Structured safety/interaction
    fields (adverse_events, interactions_structured, safety_findings) are
    deliberately NOT accepted by this function's field list below -- they
    must not independently create efficacy relevance (see module
    docstring). Passing them in ``record`` has no effect: this function
    only reads the specific keys listed here.

    A record identified by is_proxy_or_excluded_record() as a proxy source
    (patent landscape, ChEBI, DailyMed label proxy) returns an empty
    string -- callers must skip embedding such records entirely rather than
    embed a placeholder, so they never contribute a false efficacy match.

    If every field above is empty (e.g. a record whose plant_id resolves
    but whose related ``plants`` row wasn't found/joined, and which
    carries no indication/outcome/study text of any kind), this function
    falls back to a general, non-disease-specific reference/citation text
    built ONLY from already-persisted identity fields: ``fallback_plant_id``,
    ``fallback_source_title``, ``fallback_source_type``, ``fallback_pmid``,
    ``fallback_doi``, ``fallback_nct_id``, ``fallback_source_url``. Every
    part of that fallback is a direct, unmodified copy of a persisted
    field -- nothing is inferred, summarized, or invented, and no
    disease-specific vocabulary is introduced. A caller that doesn't
    supply any ``fallback_*`` key gets exactly the previous behavior (an
    empty string when the primary fields are all empty).
    """
    if is_proxy_or_excluded_record(
        record.get("source_type"), record.get("evidence_type")
    ):
        return ""

    parts = [
        _labeled("Plant", record.get("plant_name")),
        _labeled("Indication", record.get("tier1_text")),
        _labeled("Outcome/Mechanism", record.get("tier2_text")),
        _labeled("Study type", record.get("study_type")),
        _labeled("Evidence level", record.get("evidence_level")),
        _labeled("Preparation", record.get("preparation")),
        _labeled("Source text", record.get("tier3_text")),
    ]
    text = "\n".join(p for p in parts if p)
    if text:
        return text

    # A bare plant_id is not, on its own, meaningful embedding content --
    # it must only ever supplement at least one genuine identity/citation
    # field below, never stand alone as "the" content for a record.
    identity_parts = [
        _labeled("Source", record.get("fallback_source_title")),
        _labeled("Source type", record.get("fallback_source_type")),
        _labeled("PMID", record.get("fallback_pmid")),
        _labeled("DOI", record.get("fallback_doi")),
        _labeled("NCT ID", record.get("fallback_nct_id")),
        _labeled("Source URL", record.get("fallback_source_url")),
    ]
    if not any(identity_parts):
        return ""

    fallback_parts = [_labeled("Plant ID", record.get("fallback_plant_id"))] + identity_parts
    return "\n".join(p for p in fallback_parts if p)


def compute_content_hash(embedding_text: str) -> str:
    """Deterministic hash of the canonical embedding text.

    Used to skip re-embedding a record whose text (and therefore whose
    correct embedding) has not changed since it was last embedded under
    the same model/version -- see backfill_evidence_embeddings.py.
    """
    return hashlib.sha256(embedding_text.encode("utf-8")).hexdigest()
