import difflib
import hashlib
import re
import unicodedata

import pandas as pd

from standard_evidence_schema import canonicalize_evidence_record


# ======================================================================
# PHASE 2 — canonical article/evidence identity.
#
# See PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md §3d/§5 for the "before" state
# (three independent, DOI/PMID/NCT-blind dedup implementations). This
# section adds ONE shared identity policy, used by:
#   - deduplicate_evidence() below (read-time defensive dedup — existing
#     behavior, now internally driven by compute_article_identity())
#   - database._find_existing_evidence_by_identity() (insert-time dedup,
#     additive, called before the existing URL/title lookup)
#   - score_breakdown_schema.score_contribution_key() (score-level guard)
#
# Priority, per the Phase 2 brief, exactly:
#   1. DOI
#   2. PMID
#   3. Trial Registration (NCT ID)
#   4. normalized title + publication year + normalized first author
#   5. heuristic fallback (URL / title / notes snippet — the pre-existing
#      _make_dedup_key() logic), only when none of the above are usable.
# A URL by itself is explicitly NOT given higher priority than DOI/PMID/
# NCT — it only ever participates via the heuristic fallback tier, same
# as before this phase.
# ======================================================================


def normalize_doi(value):
    """Lowercase, strip doi.org URL prefixes and 'doi:' labels, trim.

    Returns None for empty/whitespace-only input — an empty DOI must
    never produce a valid dedup key.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.lower()
    text = re.sub(r"^https?://(dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    text = text.strip().strip("/")
    return text or None


def normalize_pmid(value):
    """Trim, strip a 'PMID:' prefix, keep only the identifier itself."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"^pmid:\s*", "", text, flags=re.IGNORECASE).strip()
    return text or None


def normalize_trial_registration(value):
    """Normalize a ClinicalTrials.gov NCT identifier (or, unchanged,
    pass through any other registry id — this phase only guarantees NCT
    normalization, per the brief's "at least NCT IDs" requirement).

    Case-insensitive, strips whitespace and a redundant 'NCT ' label
    before the digits are reattached to the canonical 'NCT########' form
    for genuine NCT ids; a different registration must never be folded
    into another one's key.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    upper = text.upper().replace(" ", "")
    match = re.match(r"^NCT0*([0-9]+)$", upper)
    if match:
        digits = match.group(1)
        return f"NCT{digits.zfill(8)}"
    return upper or None


def _normalize_title(value):
    """Lowercase, unicode-normalize, drop punctuation, collapse
    whitespace. Pure/deterministic — no locale/env dependence.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_author(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_year(value):
    if value in (None, ""):
        return ""
    match = re.search(r"(1[5-9]\d{2}|20\d{2})", str(value))
    return match.group(1) if match else str(value).strip()


def _get_any(record, *keys):
    """First non-empty value among several possible legacy/canonical
    key spellings for the same concept (record may be a dict-like row
    or an EvidenceRecord; both support attribute-style .get via the
    dict branch, so callers normalize to a dict before calling this).
    """
    for key in keys:
        value = record.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


# Public alias — other modules (e.g. database.py's fuzzy-title insert
# fallback) need the same "first non-empty value among aliases" lookup
# and should not reach into a leading-underscore name across a module
# boundary.
get_first_present = _get_any


def compute_article_identity(record):
    """Deterministic identity for "which article/source is this",
    independent of which connector produced the record and independent
    of which plant/indication/dosage_form this particular row is about.

    `record` may be a plain legacy dict (Source_Title/DOI/PMID/...), a
    canonical-shaped dict (EvidenceRecord.to_dict()), or an EvidenceRecord
    instance itself. It is passed through canonicalize_evidence_record()
    first (PHASE 2 review round, issue 1) so identity is always computed
    against the same normalized shape the rest of the pipeline uses —
    not a second, independent reading of the raw legacy keys.

    Returns a tuple (tier, key) where tier is one of
    "doi"|"pmid"|"trial_registration"|"title"|"heuristic", so callers can
    tell which precedence level actually matched (useful for testing and
    for `.extra` diagnostics). `key` is a stable string suitable for
    equality comparison; it is intentionally not a hash by itself so it
    stays debuggable — see `stable_identity_hash()` for a SHA-256 digest
    when an opaque, fixed-length id is needed instead.
    """
    if hasattr(record, "to_dict"):
        row = record.to_dict()
    else:
        row = canonicalize_evidence_record(dict(record or {})) or {}

    doi = normalize_doi(_get_any(row, "doi", "DOI"))
    if doi:
        return ("doi", f"doi::{doi}")

    pmid = normalize_pmid(_get_any(row, "pmid", "PMID"))
    if pmid:
        return ("pmid", f"pmid::{pmid}")

    trial_id = normalize_trial_registration(
        _get_any(row, "trial_registration", "NCT_ID", "nct_id")
    )
    if trial_id:
        return ("trial_registration", f"trial::{trial_id}")

    title = _normalize_title(_get_any(row, "article_title", "Source_Title"))
    if title:
        year = _normalize_year(_get_any(row, "publication_year", "Source_Year"))
        author = _normalize_author(_get_any(row, "first_author", "First_Author"))
        return ("title", f"title::{title}|{year}|{author}")

    # Heuristic fallback — deterministic, same fields the pre-existing
    # _make_dedup_key() already used (URL -> title[already tried above,
    # kept here only as a defensive no-op] -> Notes snippet), so
    # behavior for records with none of DOI/PMID/NCT/title is unchanged
    # from before this phase.
    url = _clean_text(_get_any(row, "article_identifier", "Source_URL"))
    if url:
        return ("heuristic", f"url::{url}")

    notes = _clean_text(_get_any(row, "supporting_sentence", "Notes"))
    notes_short = " ".join(notes.split()[:25])
    return ("heuristic", f"notes::{notes_short}")


# ======================================================================
# PHASE 2 (review round, issue 3) — expanded evidence identity.
#
# The original evidence_identity (article + species + indication +
# dosage_form + preparation) could collapse two genuinely different
# scientific claims from the same article (e.g. two different outcomes,
# or a positive and a negative finding). Expanded to also consider:
# plant_part, dose, population, outcome, study_design, evidence_direction,
# and a normalized+hashed fingerprint of the supporting sentence/claim
# text (never the raw text itself, and never used alone — only as one
# more component of the full identity string).
#
# No merge rule exists today for "same claim, different direction" —
# per the review brief, that stays a genuinely different evidence
# identity unless a documented merge rule is added later; none is
# added in this phase.
# ======================================================================
def _claim_fingerprint(text):
    """Normalizes (lowercase, Unicode-normalize, strip punctuation,
    collapse whitespace — same normalization as _normalize_title(), so
    pure formatting differences never produce a different fingerprint)
    then returns a short, deterministic hash. Never stores or exposes
    the raw text itself as part of an identity key — only this
    fingerprint. Empty/missing text produces "" (not a fabricated hash
    of nothing), so two evidence rows that both lack any supporting
    text are not falsely distinguished by this component alone.
    """
    normalized = _normalize_title(text)
    if not normalized:
        return ""
    return stable_identity_hash(normalized)[:16]


def _evidence_context_components(row):
    """Every scientifically material dimension of an evidence row,
    EXCLUDING article identity — shared by compute_evidence_identity()
    (which prefixes these with the article key) and
    evidence_contexts_equivalent() (which compares them directly,
    without requiring an exact article key match — see that function's
    docstring for why).
    """
    species = _clean_text(_get_any(row, "plant_species", "Scientific_Name"))
    indication = _clean_text(_get_any(row, "indication", "Target_Indication"))
    dosage_form = _clean_text(_get_any(row, "dosage_form", "Dosage_Form"))
    preparation = _clean_text(_get_any(row, "preparation", "Preparation"))
    plant_part = _clean_text(_get_any(row, "plant_part", "Plant_Part"))
    dose = _clean_text(_get_any(row, "dose", "Dose"))
    population = _clean_text(_get_any(row, "population", "Population"))
    outcome = _clean_text(_get_any(row, "outcome", "Primary_Outcome"))
    study_design = _clean_text(_get_any(row, "study_design", "Study_Type"))
    evidence_direction = _clean_text(
        _get_any(row, "evidence_direction", "Result_Direction")
    )
    claim_fp = _claim_fingerprint(
        _get_any(row, "supporting_sentence", "Notes")
    )
    return (
        species, indication, dosage_form, preparation, plant_part, dose,
        population, outcome, study_design, evidence_direction, claim_fp,
    )


def compute_evidence_identity(record):
    """Identity for "which specific scientific claim/context, from which
    article, is this" — article_identity plus every scientifically
    material dimension available in the schema: plant species,
    indication, dosage form, preparation, plant part, dose, population,
    outcome, study design, evidence direction, and a claim fingerprint
    derived from the supporting sentence.

    Two rows can share article_identity but have different
    evidence_identity (the same article, two plants; the same article/
    plant, two indications; the same article/plant/indication, two
    outcomes or two directions) and must not be collapsed by
    article-level dedup. Two rows describing the exact same claim, with
    only formatting differences in the supporting text, DO share the
    same evidence_identity (see _claim_fingerprint()'s normalization).
    """
    if hasattr(record, "to_dict"):
        row = record.to_dict()
    else:
        row = canonicalize_evidence_record(dict(record or {})) or {}

    _, article_key = compute_article_identity(row)
    components = _evidence_context_components(row)

    return "|".join([article_key, *components])


def evidence_contexts_equivalent(a, b):
    """PHASE 2 (review round 3, issue 2) — compares the SAME scientific
    dimensions compute_evidence_identity() does (species, indication,
    dosage form, preparation, plant part, dose, population, outcome,
    study design, evidence direction, claim fingerprint), WITHOUT
    requiring an exact article-identity match.

    This is the second half of the fuzzy-dedup rule the review brief
    requires:

        fuzzy-equivalent article + equivalent evidence context = duplicate
        fuzzy-equivalent article + different outcome/direction/population/
            plant part/dose/claim = two independent Evidence records

    articles_equivalent() alone only ever decides "is this the same
    published source" — it must never, by itself, decide "is this the
    same Evidence". Callers (e.g. deduplication_engine's
    _fuzzy_collapse_remaining()) must require BOTH
    articles_equivalent(a, b) AND evidence_contexts_equivalent(a, b)
    before treating two rows as one Evidence.
    """
    row_a = a.to_dict() if hasattr(a, "to_dict") else canonicalize_evidence_record(dict(a or {})) or {}
    row_b = b.to_dict() if hasattr(b, "to_dict") else canonicalize_evidence_record(dict(b or {})) or {}
    return _evidence_context_components(row_a) == _evidence_context_components(row_b)



def compute_source_record_identity(record):
    """Identity for the concrete source/evidence record itself.

    Prefer the platform's persisted evidence_record_id when available; fall
    back to article identity otherwise.  This keeps two separately curated
    synthesis records distinct even when sparse metadata prevents robust
    article identification.
    """
    if hasattr(record, "to_dict"):
        row = record.to_dict()
    else:
        row = canonicalize_evidence_record(dict(record or {})) or {}

    record_id = _clean_text(_get_any(row, "evidence_record_id", "Evidence_Record_ID"))
    if record_id:
        return ("evidence_record", f"record::{record_id}")
    article_tier, article_key = compute_article_identity(row)
    return ("article", f"article::{article_tier}::{article_key}")


def _is_synthesis_record(row):
    """Return True for evidence objects that synthesize multiple studies.

    Study linkage must never collapse a systematic review/meta-analysis onto
    one of its included trials merely because the review record happens to
    carry or mention that trial's registration identifier.  This helper uses
    structured source/design fields only; it does not mine free text for NCT
    identifiers.
    """
    source_type = _clean_text(_get_any(row, "source_type", "Source_Type"))
    study_design = _clean_text(_get_any(row, "study_design", "Study_Type"))
    signal = f"{source_type} {study_design}"
    return any(term in signal for term in (
        "systematic review", "systematic_review", "meta analysis",
        "meta_analysis", "meta-analysis",
    ))


def compute_study_identity(record):
    """Deterministic identity for the underlying study/dependency unit.

    This is deliberately different from :func:`compute_article_identity`:
    a trial-registry record and one or more publications can be distinct
    evidence/source objects while still depending on the SAME underlying
    clinical trial.  When a structured trial registration is available,
    direct trial evidence is therefore linked by that registration.

    Systematic reviews/meta-analyses remain distinct evidence objects even if
    they carry a trial id, because they synthesize a broader evidence body and
    are not duplicates of any single included study.  Records without a
    structured trial registration fall back conservatively to article
    identity; no study relationship is guessed from title or free text.
    """
    if hasattr(record, "to_dict"):
        row = record.to_dict()
    else:
        row = canonicalize_evidence_record(dict(record or {})) or {}

    source_tier, source_key = compute_source_record_identity(row)
    if _is_synthesis_record(row):
        return ("synthesis", f"synthesis::{source_key}")

    linked_trial = normalize_trial_registration(
        _get_any(
            row,
            "linked_trial_id", "Linked_Trial_ID",
            "trial_registration", "NCT_ID", "nct_id",
        )
    )
    if linked_trial:
        return ("trial", f"trial::{linked_trial}")

    return (source_tier, source_key)


def stable_identity_hash(identity_key):
    """SHA-256 hex digest of a compute_*_identity() key, for callers
    that need a fixed-length, persistence-safe id (e.g. a score
    contribution guard's dict/set key) rather than the raw debuggable
    string. Deliberately NOT Python's built-in hash() — that is
    randomized per-process (PYTHONHASHSEED) and unsuitable for anything
    that must compare stable across runs or persist.
    """
    return hashlib.sha256(str(identity_key).encode("utf-8")).hexdigest()


# ======================================================================
# PHASE 2 (review round, issue 4) — controlled fuzzy title matching.
#
# compute_article_identity()'s "title" tier already requires an EXACT
# normalized title+year+author match. articles_equivalent() adds a
# bounded, documented fuzzy fallback for the case where two records
# describe the same article but the title differs only cosmetically
# (subtitle punctuation, a trailing period, etc.) — WITHOUT ever
# consulting fuzzy matching when either side has a strong identifier
# (DOI/PMID/Trial Registration), and without ever fuzzy-matching short
# or generic titles.
# ======================================================================

# Documented constants (per the review brief's "threshold must be a
# documented constant" requirement).
FUZZY_TITLE_SIMILARITY_THRESHOLD = 0.92

# PHASE 2 (review round 3, issue 4) — used whenever first author cannot
# be verified on BOTH sides of a comparison (the common case for
# insert-time dedup, since the `sources` table has no author column at
# all — see database._find_existing_evidence_by_fuzzy_title()). Higher
# than FUZZY_TITLE_SIMILARITY_THRESHOLD: with one of the three normal
# guards (author match) unavailable, the title-similarity bar is raised
# instead of silently proceeding at the same threshold as when author
# WAS verified — this is what makes the "author guard" honest rather
# than a parameter that exists in a function signature but never
# actually constrains anything.
FUZZY_TITLE_SIMILARITY_THRESHOLD_UNVERIFIED_AUTHOR = 0.97
MIN_FUZZY_TITLE_TOKEN_COUNT = 4


def articles_equivalent(a, b):
    """True if `a` and `b` should be treated as the same article.

    Order-independent: articles_equivalent(a, b) == articles_equivalent(b, a)
    for every input (verified by test; every comparison below — set
    equality, string equality, SequenceMatcher.ratio() — is itself
    symmetric).

    Decision path:
      1. If either record has a strong identifier (DOI/PMID/Trial
         Registration — compute_article_identity() tier in
         {"doi","pmid","trial_registration"}), equivalence is decided
         EXACTLY by canonical identity; fuzzy matching is never
         consulted in this case (a strong identifier always outranks
         a fuzzy title guess).
      2. If canonical identity keys already match exactly (same DOI/
         PMID/NCT, or same normalized title+year+author), True.
      3. Otherwise — ONLY reachable when NEITHER record has a strong
         identifier — a bounded, guarded fuzzy title comparison runs:
         both titles must have at least MIN_FUZZY_TITLE_TOKEN_COUNT
         normalized tokens (short/generic titles are never fuzzy-
         deduplicated); years must match when both are present.
         FIRST AUTHOR (PHASE 2, review round 3): when a first author is
         verifiable on BOTH sides, they must match, and the normal
         FUZZY_TITLE_SIMILARITY_THRESHOLD applies. When a first author
         is NOT verifiable on at least one side (e.g. the insert-time
         `sources` table lookup, which carries no author column), the
         author check cannot meaningfully run — instead of silently
         skipping it (the bug identified in the review round 3 audit),
         the required title similarity is raised to the stricter
         FUZZY_TITLE_SIMILARITY_THRESHOLD_UNVERIFIED_AUTHOR, so an
         unverifiable author costs precision rather than being a silent
         no-op guard.
    """
    row_a = a.to_dict() if hasattr(a, "to_dict") else canonicalize_evidence_record(dict(a or {})) or {}
    row_b = b.to_dict() if hasattr(b, "to_dict") else canonicalize_evidence_record(dict(b or {})) or {}

    tier_a, key_a = compute_article_identity(row_a)
    tier_b, key_b = compute_article_identity(row_b)

    strong_tiers = {"doi", "pmid", "trial_registration"}
    if tier_a in strong_tiers or tier_b in strong_tiers:
        return key_a == key_b

    if key_a == key_b:
        return True

    title_a = _normalize_title(_get_any(row_a, "article_title", "Source_Title"))
    title_b = _normalize_title(_get_any(row_b, "article_title", "Source_Title"))
    if not title_a or not title_b:
        return False

    if (
        len(set(title_a.split())) < MIN_FUZZY_TITLE_TOKEN_COUNT
        or len(set(title_b.split())) < MIN_FUZZY_TITLE_TOKEN_COUNT
    ):
        return False

    year_a = _normalize_year(_get_any(row_a, "publication_year", "Source_Year"))
    year_b = _normalize_year(_get_any(row_b, "publication_year", "Source_Year"))
    if year_a and year_b and year_a != year_b:
        return False

    author_a = _normalize_author(_get_any(row_a, "first_author", "First_Author"))
    author_b = _normalize_author(_get_any(row_b, "first_author", "First_Author"))
    if author_a and author_b:
        if author_a != author_b:
            return False
        required_threshold = FUZZY_TITLE_SIMILARITY_THRESHOLD
    else:
        # Author unverifiable on at least one side — see docstring.
        # Never silently treated as "no constraint"; the bar goes up
        # instead.
        required_threshold = FUZZY_TITLE_SIMILARITY_THRESHOLD_UNVERIFIED_AUTHOR

    similarity = difflib.SequenceMatcher(None, title_a, title_b).ratio()
    return similarity >= required_threshold


def _clean_text(x):
    if x is None:
        return ""
    x = str(x).lower().strip()
    x = re.sub(r"<.*?>", " ", x)
    x = re.sub(r"[^a-z0-9\s]", " ", x)
    x = re.sub(r"\s+", " ", x)
    return x


def _make_dedup_key(row):
    """Read-time defensive dedup key.

    PHASE 2 CHANGE: this now delegates to compute_evidence_identity(),
    the same canonical DOI > PMID > Trial Registration > title+year+
    author > heuristic priority used by insert-time dedup
    (database._find_existing_evidence_by_identity()) and by the score
    guard (score_breakdown_schema.score_contribution_key()) — closing
    the "three independent dedup implementations" gap documented in
    PHASE2_EVIDENCE_ARCHITECTURE_AUDIT.md sections 3d/5.

    Backward compatible for every row shape the pre-Phase-2 version
    handled: a row with Source_URL still produces a URL-based
    ("heuristic" tier) key whenever DOI/PMID/NCT_ID are absent (the
    common case for rows carrying only a URL) — see
    test_evidence_database_deduplication.py, unchanged by this refactor.
    """
    return compute_evidence_identity(row)


def _evidence_context_key(row_dict):
    """Plant/indication/dosage_form bucket used to scope the fuzzy
    title pass below to comparisons that could plausibly matter — never
    a full cross-product comparison across the whole DataFrame.
    """
    return (
        _clean_text(_get_any(row_dict, "plant_species", "Scientific_Name")),
        _clean_text(_get_any(row_dict, "indication", "Target_Indication")),
        _clean_text(_get_any(row_dict, "dosage_form", "Dosage_Form")),
    )


def _fuzzy_collapse_remaining(data):
    """PHASE 2 (review round 3, issue 2 fix) — second dedup pass, after
    the exact-key pass in deduplicate_evidence() already ran. Only
    compares rows whose article identity fell back to the "title" or
    "heuristic" tier (i.e., no DOI/PMID/NCT_ID) — a row with a strong
    identifier already got its exact match in the first pass and is
    never reconsidered here. Comparisons are scoped to rows sharing the
    same plant/indication/dosage_form bucket (bounded cost — no full
    cross-product scan), and `data` is assumed already sorted by
    descending score, so the first row seen in a bucket is the one kept
    on a match.

    TWO conditions are now both required before two rows collapse:
    articles_equivalent() (fuzzy article-level match) AND
    evidence_contexts_equivalent() (same scientific claim/context —
    outcome, direction, population, plant part, dose, claim
    fingerprint, etc.). Fuzzy article equivalence alone is no longer
    sufficient — this is the exact bug the review round 3 audit found:
    two rows about the same fuzzy-matched article but with genuinely
    different outcomes/directions were being incorrectly collapsed to
    one row. Now they are not.
    """
    if data.empty:
        return data

    buckets = {}
    keep_mask = []

    for _, row in data.iterrows():
        row_dict = canonicalize_evidence_record(dict(row))
        tier, _ = compute_article_identity(row_dict)
        context = _evidence_context_key(row_dict)

        is_duplicate = False
        if tier in ("title", "heuristic"):
            for kept_row in buckets.get(context, []):
                if articles_equivalent(row_dict, kept_row) and evidence_contexts_equivalent(row_dict, kept_row):
                    is_duplicate = True
                    break

        if is_duplicate:
            keep_mask.append(False)
        else:
            keep_mask.append(True)
            buckets.setdefault(context, []).append(row_dict)

    return data[keep_mask].reset_index(drop=True)


def deduplicate_evidence(df):
    if df is None or df.empty:
        return df

    data = df.copy()
    data["_dedup_key"] = data.apply(_make_dedup_key, axis=1)

    if "Evidence_Score" not in data.columns:
        data["Evidence_Score"] = 0

    if "Evidence_Quality_Score" not in data.columns:
        data["Evidence_Quality_Score"] = 0

    data["_sort_score"] = (
        pd.to_numeric(data["Evidence_Score"], errors="coerce").fillna(0)
        + pd.to_numeric(data["Evidence_Quality_Score"], errors="coerce").fillna(0)
    )

    data = (
        data.sort_values("_sort_score", ascending=False)
        .drop_duplicates(subset=["_dedup_key"], keep="first")
        .reset_index(drop=True)
    )

    # PHASE 2 (review round, issue 4) — controlled fuzzy title fallback,
    # only reached for rows the exact-key pass above did not already
    # collapse. See _fuzzy_collapse_remaining()'s docstring.
    data = _fuzzy_collapse_remaining(data)

    return data.drop(columns=["_dedup_key", "_sort_score"], errors="ignore").reset_index(drop=True)
