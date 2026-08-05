from __future__ import annotations

STANDARD_EVIDENCE_FIELDS = {
    "Plant": "",
    "Study_Type": "",
    "Study_Model": "",
    "Dosage_Form_Detected": "",
    "Target_Indication_Detected": "",
    "Population": "",
    "Sample_Size": "",
    "Comparator": "",
    "Primary_Outcome": "",
    "Result_Direction": "",
    "Safety_Signal": "",
    "Evidence_Level": "",
    "Direct_For_Selected_Product": "",
    "Directness_Reason": "",
    "Evidence_Score": 0,
}


# ======================================================================
# PHASE 2 — Canonical EvidenceRecord
#
# See PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md for the full "before" survey.
# This module ("standard evidence schema") was chosen as the home for the
# canonical model per the Phase 2 brief's preference for reusing an
# existing Evidence module over creating a parallel one:
# STANDARD_EVIDENCE_FIELDS above is a narrow, effectively orphaned legacy
# template (not imported anywhere else in the repository — see audit §1),
# so this file had no active, competing responsibility that a new class
# would collide with, while still being the module whose name and purpose
# ("evidence schema") most directly matches "canonical Evidence model".
#
# EvidenceRecord does NOT replace any existing dict-shaped pathway.
# Every function below is an ADAPTER at the boundary of the existing
# dict/DataFrame pipeline (source_ingestion_engine.py,
# evidence_standardizer.py, standard_evidence_builder.py, database.py) —
# none of those modules are required to change their return types.
#
# ARTICLE IDENTITY vs. EVIDENCE IDENTITY vs. SCORE IDENTITY
#   - article_identity  = "which published/registered source is this".
#     Computed only from DOI / PMID / Trial Registration / normalized
#     title+year+first_author / heuristic fallback (see
#     deduplication_engine.compute_article_identity()). Two EvidenceRecords
#     for the same article (e.g. fetched once via PubMed, once via Europe
#     PMC) share the same article_identity.
#   - evidence_identity = "which specific scientific claim/context, from
#     which article, is this". Adds plant species + indication + dosage
#     form + preparation to article_identity (see
#     deduplication_engine.compute_evidence_identity()). One article can
#     legitimately produce several EvidenceRecords with the same
#     article_identity but different evidence_identity (e.g. the same
#     review article covering two different plants, or two different
#     indications) — these must NOT be collapsed by article-level dedup.
#   - score_identity = "has this exact evidence_identity already
#     contributed to this exact score component". Computed on demand by
#     score_breakdown_schema.score_contribution_key(evidence_identity,
#     component_name) — never stored on EvidenceRecord itself, since it is
#     a property of a (evidence, score component) PAIR, not of the
#     evidence alone.
# ======================================================================

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# Legacy dict key -> EvidenceRecord field name. Used by both
# EvidenceRecord.from_legacy_dict() and EvidenceRecord.to_legacy_dict().
# This is the ONE place old/new field-name conflicts are resolved for the
# canonical model; see the audit (§3b) for which names were considered
# and NOT blindly merged (Study_Type/Result_Direction/Evidence_Level stay
# on three separate EvidenceRecord fields, exactly as Phase 1 requires).
_LEGACY_FIELD_MAP = {
    "Evidence_Record_ID": "evidence_record_id",
    "DOI": "doi",
    "PMID": "pmid",
    "NCT_ID": "trial_registration",
    "Source_Title": "article_title",
    "First_Author": "first_author",
    "Source_Year": "publication_year",
    "Source_Type": "source_type",
    # PHASE 3 — Source Authority / Evidence Quality integration. Prior to
    # Phase 3, "Source_Authority_Weight" (the numeric 0.7-1.0 float set by
    # multi_source_collector.py from source_registry.py's connector-level
    # config) mapped directly onto `source_authority`, a field the Phase 3
    # brief requires be kept as a text LABEL (e.g. "EMA HMPC Monograph"),
    # not a numeric weight — see PHASE3_SOURCE_AUTHORITY_AUDIT.md §1 for
    # the full trace of this pre-existing type mismatch (the field was
    # typed Optional[str] but actually held a raw float at runtime, and
    # was never persisted or read anywhere downstream regardless).
    #
    # Phase 3 resolution: "Source_Authority_Weight" now maps to the new
    # NUMERIC canonical field `source_authority_score` instead — its
    # correct semantic home — kept as a backward-compatible alias for any
    # existing dict that still sets this legacy key. `source_authority`
    # (the label) and `source_authority_reason` get their own, new legacy
    # keys ("Source_Authority" / "Source_Authority_Reason") emitted going
    # forward by evidence_authority.py-driven classification. Iteration
    # order matters here: "Source_Authority_Score" is listed AFTER
    # "Source_Authority_Weight" so that if a record ever legitimately
    # carries both (new code writing the new key alongside the old one
    # for transition safety), the newer, more specific key wins on
    # from_legacy_dict() while to_legacy_dict() always emits the new key
    # name (see _CANONICAL_TO_LEGACY's last-write-wins construction).
    "Source_Authority_Weight": "source_authority_score",
    "Source_Authority": "source_authority",
    "Source_Authority_Score": "source_authority_score",
    "Source_Authority_Reason": "source_authority_reason",
    "Study_Type": "study_design",
    "Result_Direction": "evidence_direction",
    "Evidence_Level": "evidence_quality",
    "Common_Name": "plant_common_name",
    "Scientific_Name": "plant_species",
    "Plant_Part": "plant_part",
    # PHASE 2 (review round, issue 7) — "Preparation" is a NEW,
    # deliberately separate legacy key, not a reuse of Extraction_Method.
    # The two are not semantically equivalent: Extraction_Method (see
    # standard_evidence_builder.py's own module docstring) is a
    # compound-extraction/solvent concept tracked (when present at all)
    # on plant_compounds, a completely different table from
    # evidence_records; "preparation" here means how the herbal material
    # itself was prepared for the STUDIED evidence item (e.g. infusion
    # vs. tincture vs. capsule), which is closer to Dosage_Form than to
    # Extraction_Method but is still its own concept the schema has never
    # had a column for. "Preparation" is therefore a new, optional,
    # additive dict key — no existing caller reads it today, so nothing
    # breaks; no database migration is implied (it only exists inside
    # this dict, never persisted as its own evidence_records column
    # unless a future phase explicitly adds one).
    "Preparation": "preparation",
    "Dosage_Form": "dosage_form",
    "Dose": "dose",
    "Target_Indication": "indication",
    "Population": "population",
    "Primary_Outcome": "outcome",
    "Notes": "supporting_sentence",
    "Data_Quality_Score": "confidence",
    "Source_URL": "article_identifier",
}

# Reverse map for to_legacy_dict(); fields with no legacy counterpart
# (first_author, preparation, dose) are simply not emitted.
_CANONICAL_TO_LEGACY = {v: k for k, v in _LEGACY_FIELD_MAP.items()}


def _clean(value):
    """None/''/[]/{} all normalize to None. Never fabricates a value."""
    if value in (None, "", [], {}):
        return None
    return value


def _get_first_present(record, *keys):
    for key in keys:
        if key in record and record.get(key) not in (None, "", [], {}):
            return record.get(key)
    return None


def _extract_first_author(authors_raw):
    """Deterministic, no scientific guessing: a list/tuple takes its
    first element; a string is split on the first of ";", " and ",
    " & ", "," (checked in that fixed priority order, never reordered)
    and the first token is returned, stripped. Returns None for
    anything empty/unusable — never a fabricated name.
    """
    if authors_raw is None:
        return None
    if isinstance(authors_raw, (list, tuple)):
        for item in authors_raw:
            text = str(item).strip()
            if text:
                return text
        return None
    text = str(authors_raw).strip()
    if not text:
        return None
    for separator in (";", " and ", " & ", ","):
        if separator in text:
            first = text.split(separator)[0].strip()
            return first or None
    return text


# ----------------------------------------------------------------------
# PHASE 2 (review round, issue 8) — recursive, bounded JSON-safe
# converter. Used by EvidenceRecord.to_dict() and available to any other
# caller that needs to serialize a value that may contain dataclasses,
# datetimes, Decimals, Enums, sets/tuples, or (if installed) numpy
# scalars. Unknown/unrecognized object types fall back to str(value) —
# a deliberate, documented, and tested policy (not a silent failure and
# not a raised exception), since Evidence-pipeline callers already
# tolerate free-text-shaped fields everywhere else in this codebase.
# ----------------------------------------------------------------------
def _json_safe(value):
    import dataclasses as _dc
    from datetime import date, datetime
    from decimal import Decimal
    from enum import Enum

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return _json_safe(value.value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    if _dc.is_dataclass(value) and not isinstance(value, type):
        return {
            f.name: _json_safe(getattr(value, f.name))
            for f in _dc.fields(value)
        }
    try:
        import numpy as _np
        if isinstance(value, _np.generic):
            return value.item()
    except ImportError:
        pass
    # Documented, tested fallback for any other object type.
    return str(value)


@dataclass
class EvidenceRecord:
    """Canonical, cross-cutting Evidence record for Phase 2.

    Not immutable (project has no other frozen Evidence-shaped dataclass
    in the active pipeline — EngineEvidenceInput is frozen, but that is a
    deliberately separate, structurally isolated GoldCase-validation
    input type per engine_evidence_input.py's own docstring, not part of
    this canonical model or its identity/dedup guarantees).

    Every optional field defaults to None (or an empty, per-instance
    list for evidence_record_ids_seen — see field(default_factory=list)
    below; never a shared mutable default). Missing information is
    always None, never a fabricated placeholder.
    """

    # --- identity / traceability ---
    evidence_record_id: Optional[str] = None
    article_identifier: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None
    trial_registration: Optional[str] = None

    # --- article metadata ---
    article_title: Optional[str] = None
    first_author: Optional[str] = None
    publication_year: Optional[str] = None
    source_type: Optional[str] = None
    # PHASE 3 — Source Authority. `source_authority` remains the text
    # LABEL (e.g. "EMA HMPC Monograph", "Unknown Source" — see
    # evidence_authority.AUTHORITY_LABELS), unchanged in type per the
    # Phase 3 brief. `source_authority_score` and `source_authority_reason`
    # are new, additive fields carrying the numeric factor
    # (evidence_authority.AUTHORITY_FACTORS) and the deterministic
    # human-readable rationale evidence_authority.classify_source_authority()
    # returns. Kept as three separate fields rather than folding score/
    # reason into `.extra` because both are first-class, always-expected
    # outputs of the same classification call, not incidental passthrough
    # data.
    source_authority: Optional[str] = None
    source_authority_score: Optional[float] = None
    source_authority_reason: Optional[str] = None

    # --- scientific classification (Phase 1 axes kept separate) ---
    study_design: Optional[str] = None
    evidence_direction: Optional[str] = None
    evidence_quality: Optional[str] = None

    # --- plant / preparation context ---
    plant_common_name: Optional[str] = None
    plant_species: Optional[str] = None
    plant_part: Optional[str] = None
    preparation: Optional[str] = None
    dosage_form: Optional[str] = None
    dose: Optional[str] = None

    # --- clinical content ---
    indication: Optional[str] = None
    population: Optional[str] = None
    outcome: Optional[str] = None
    supporting_sentence: Optional[str] = None
    confidence: Optional[str] = None

    # Anything present on the source legacy dict that has no canonical
    # field above is preserved here, verbatim, so round-tripping through
    # EvidenceRecord never silently drops connector-provided data. Never
    # a shared mutable default (field(default_factory=dict), per record).
    extra: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def from_canonical(cls, **kwargs) -> "EvidenceRecord":
        """Build directly from canonical field names/values."""
        return cls(**kwargs)

    @classmethod
    def from_legacy_dict(cls, record: Dict[str, Any]) -> "EvidenceRecord":
        """Build from any of the dicts already flowing through the
        existing pipeline (post-normalize_source_record, post-
        standardize_extracted_record, or a load_evidence_records() row).

        Never guesses: a legacy key that is missing or empty stays None
        on the canonical record. Unrecognized keys are preserved in
        `.extra` rather than discarded.
        """
        if record is None:
            record = {}

        values: Dict[str, Any] = {}
        consumed = set()

        for legacy_key, canonical_field in _LEGACY_FIELD_MAP.items():
            if legacy_key in record:
                consumed.add(legacy_key)
                values[canonical_field] = _clean(record.get(legacy_key))

        # Lower-case DB-row aliases (some read paths use lowercase keys,
        # e.g. embedding_service.py / raw Supabase rows) — checked only
        # when the PascalCase key above was absent, never overwriting an
        # already-consumed value.
        _lowercase_aliases = {
            "doi": "doi", "pmid": "pmid", "nct_id": "trial_registration",
            "evidence_record_id": "evidence_record_id",
            "first_author": "first_author",
        }
        for lower_key, canonical_field in _lowercase_aliases.items():
            if canonical_field not in values or values[canonical_field] is None:
                if lower_key in record and lower_key not in consumed:
                    consumed.add(lower_key)
                    values[canonical_field] = _clean(record.get(lower_key))

        # PHASE 2 (review round, issue 6) — no connector in this
        # repository currently extracts author metadata from its API
        # response at all (confirmed by grep across every *_connector.py
        # file — none set First_Author/first_author/Authors/authors/
        # Author/author today), so this path is never exercised by real
        # production data yet. It exists so that the moment ANY connector
        # (or a future one) starts providing author data under any of
        # these real-world spellings, first_author is picked up with no
        # further pipeline change required. Deterministic, not a guess:
        # a list takes its first element; a string is split on the first
        # of ";", " and ", " & ", "," (in that priority order) and the
        # first token is used, never re-ordered or scored by any
        # heuristic. Raw multi-author data is preserved in `.extra`
        # under its ORIGINAL key (never consumed/removed here), so
        # nothing is lost by deriving a single first_author from it.
        if values.get("first_author") is None:
            direct = _get_first_present(record, "First_Author", "first_author")
            if direct:
                values["first_author"] = _clean(direct)
            else:
                authors_raw = _get_first_present(
                    record, "Authors", "authors", "Author", "author"
                )
                derived = _extract_first_author(authors_raw)
                if derived:
                    values["first_author"] = derived
                # authors_raw itself is intentionally left un-consumed —
                # it lands in `.extra` below, verbatim.

        # PHASE 2 (review round) bugfix — a key with a "falsy but
        # present" value (e.g. "EMA_Status": "", "Sample_Size": 0) must
        # still round-trip: many callers index a key expecting it to
        # exist even when empty (that's the whole point of
        # source_ingestion_engine.STANDARD_FIELDS always pre-populating
        # every key with a default). Only a truly ABSENT key is
        # legitimately left out of `.extra` — presence with an empty
        # value is not the same as absence, and must not be silently
        # dropped here the way it was before this fix (caught by
        # test_llm_ema_relevance_never_sets_ema_status, which indexes
        # result["EMA_Status"] and needs the key present even when "").
        extra = {k: v for k, v in record.items() if k not in consumed}

        return cls(extra=extra, **values)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def to_legacy_dict(self) -> Dict[str, Any]:
        """Render back into the legacy PascalCase dict shape existing
        callers (standardize_extracted_record, save_evidence_record,
        etc.) already expect. Every canonical field now has a legacy
        key it round-trips through (see _LEGACY_FIELD_MAP; first_author/
        preparation/dose were added in the Phase 2 review round
        specifically to close a prior round-trip data-loss gap — see
        test_canonical_to_legacy_to_canonical_round_trip_no_data_loss()).
        `.extra` contents are merged back in verbatim.
        """
        out: Dict[str, Any] = {}
        for canonical_field, legacy_key in _CANONICAL_TO_LEGACY.items():
            value = getattr(self, canonical_field, None)
            if value is not None:
                out[legacy_key] = value
        out.update(self.extra)
        return out

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe canonical-shape dict (own field names), for
        serialization / storage inside an already-JSON blob column (e.g.
        decision_records.records), never for replacing evidence_records'
        own SQL columns. Recursively converts dataclasses, datetime/date,
        Decimal, Enum, tuple/set, and (if numpy is installed) numpy
        scalars via _json_safe(); any other unrecognized object type is
        converted to str(...) rather than raising — see _json_safe()'s
        docstring for that policy.
        """
        data = {
            k: v for k, v in self.__dict__.items() if k != "extra"
        }
        if self.extra:
            data["extra"] = dict(self.extra)
        return _json_safe(data)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRecord":
        """Inverse of to_dict(); tolerant of missing keys."""
        if data is None:
            data = {}
        known = {f.name for f in cls.__dataclass_fields__.values()}
        kwargs = {k: v for k, v in data.items() if k in known and k != "extra"}
        extra = dict(data.get("extra") or {})
        return cls(extra=extra, **kwargs)


# ======================================================================
# PHASE 2 (review round, issue 1) — REAL production wiring point.
#
# canonicalize_evidence_record() is called from three actual boundaries
# in production code, not just demonstrated in tests:
#   - evidence_standardizer.standardize_extracted_record() — every
#     record returned by the platform's one standardization function
#     now passes through this before being handed back to its caller.
#   - database.save_evidence_record() — every record passed to the
#     platform's one evidence-insert function is canonicalized first.
#   - deduplication_engine._make_dedup_key() (used by
#     deduplicate_evidence(), the platform's one read-time dedup path) —
#     every row's dedup key is computed against its canonicalized form.
#
# See test_phase2_evidence_architecture.py's
# test_canonicalize_evidence_record_is_actually_called_in_production_paths
# for a spy-based proof (not just "the function exists and can be
# called manually") that all three boundaries actually invoke it.
# ======================================================================
def canonicalize_evidence_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Passes `record` through EvidenceRecord.from_legacy_dict() then
    .to_legacy_dict(), returning a legacy-compatible dict. This is the
    actual production adapter, not a demo helper — see the module-level
    note above for the three real call sites.

    Every field-name mapping, None-vs-missing normalization, and
    first_author derivation EvidenceRecord performs runs here. The
    returned dict has the exact same shape/keys a caller already
    receives today (nothing new is added that a legacy caller must
    learn to ignore) plus whatever first_author derivation newly
    surfaced from an Authors/authors field, if present.

    None in, None out (never fabricates a record from nothing).
    """
    if record is None:
        return record
    canonical = EvidenceRecord.from_legacy_dict(record)
    return canonical.to_legacy_dict()

