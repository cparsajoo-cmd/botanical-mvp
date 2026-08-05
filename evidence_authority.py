"""Phase 3 — centralized Source Authority module.

WHY THIS MODULE EXISTS
See PHASE3_SOURCE_AUTHORITY_AUDIT.md for the full "before" trace. In
summary: `source_registry.py`'s `authority_weight` is generated at
collection time (`multi_source_collector.py`), survives standardization,
maps onto `EvidenceRecord.source_authority` (`standard_evidence_schema.py`)
— and is then silently dropped before the `evidence_records` insert
(`database.py::save_evidence_record`), never persisted, never read back,
and never used by any scoring path. Separately, `candidate_shortlisting.py`
(the live scoring path that actually determines `Evidence_Quality_Score`,
capped at 30.0 inside `Overall_Score`) has no concept of Source Authority
at all, and `evidence_interpretation.py` (the live Phase 1 module used by
`botanical_rd_candidate_engine.py`) likewise has no authority concept.

This module is the SINGLE place both live pipelines classify a piece of
evidence's Source Authority and combine it with Study Quality / Evidence
Direction / Applicability into a signed contribution. Per the Phase 3
brief, no second, parallel authority or quality classifier may be created
elsewhere — every caller imports from here.

CONCEPTS KEPT DELIBERATELY INDEPENDENT
  Source Authority   -- credibility of the ORGANIZATION/PUBLISHER/registry
                         behind a piece of evidence (EMA HMPC, WHO, ESCOP,
                         Cochrane, peer-reviewed literature tiered by
                         study type when no organizational identity is
                         available, commercial website, blog, unknown).
  Study Design /
  Evidence Quality    -- methodological strength of the STUDY ITSELF.
                         Sourced from evidence_interpretation.py (Phase 1)
                         — NOT redefined here. A negative RCT is still a
                         high-quality RCT; Source Authority never touches
                         this.
  Evidence Direction  -- what the study FOUND (positive/negative/null/
                         mixed/unclear). Sourced from evidence_interpretation.py.
                         Source Authority NEVER changes direction or its
                         sign.
  Applicability       -- whether the evidence is a completed, directly
                          reported study vs. a future/protocol/registration
                          -only mention. Sourced from evidence_interpretation.py.

Formula this module implements (documented, testable, not scattered):

    evidence_strength = study_quality_factor
                         x source_authority_factor
                         x applicability_factor

    signed_evidence_contribution = evidence_strength x direction_sign

Source Authority contributes ONLY as a magnitude/confidence multiplier on
`evidence_strength`. It can never flip `direction_sign`, and it can never,
by itself, turn null/unclear evidence into a positive contribution.

STANDARD LIBRARY ONLY (re, dataclasses, types, typing) — no new
dependency, consistent with evidence_interpretation.py's own scope
constraint. Classification functions here take plain keyword
arguments/Mapping objects, never a DataFrame, so every one of them is
unit-testable with zero pandas dependency (Phase 3 brief requirement).
"""

from __future__ import annotations

import re
import types
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

# ---------------------------------------------------------------------
# Reused, not redefined: Study Design / Evidence Direction / Evidence
# Quality / Applicability constants and factor tables live in
# evidence_interpretation.py (Phase 1). Per the Phase 3 brief ("دو
# classifier مستقل نساز"), this module imports them rather than creating
# a second, parallel vocabulary.
# ---------------------------------------------------------------------
from evidence_interpretation import (  # noqa: F401 (re-exported for callers)
    STUDY_DESIGN_RCT,
    STUDY_DESIGN_CLINICAL_TRIAL_PROTOCOL,
    STUDY_DESIGN_CLINICAL_TRIAL,
    STUDY_DESIGN_REVIEW,
    STUDY_DESIGN_ANIMAL_STUDY,
    STUDY_DESIGN_IN_VITRO_STUDY,
    STUDY_DESIGN_UNSPECIFIED,
    DIRECTION_POSITIVE,
    DIRECTION_NEGATIVE,
    DIRECTION_NULL,
    DIRECTION_MIXED,
    DIRECTION_UNCLEAR,
    QUALITY_HIGH,
    QUALITY_MODERATE,
    QUALITY_LOW,
    QUALITY_UNKNOWN,
    QUALITY_FACTOR,
    APPLICABILITY_DIRECT,
    APPLICABILITY_CONTEXTUAL_OR_FUTURE,
    APPLICABILITY_FACTOR,
)

# =======================================================================
# Source Authority taxonomy
# =======================================================================
AUTHORITY_EMA_HMPC_MONOGRAPH = "EMA HMPC Monograph"
AUTHORITY_WHO_MONOGRAPH = "WHO Monograph"
AUTHORITY_ESCOP_MONOGRAPH = "ESCOP Monograph"
AUTHORITY_COCHRANE_REVIEW = "Cochrane Review"
AUTHORITY_SYSTEMATIC_REVIEW = "Systematic Review & Meta-analysis"
AUTHORITY_RCT = "Randomized Controlled Trial"
AUTHORITY_CONTROLLED_CLINICAL_TRIAL = "Controlled Clinical Trial"
AUTHORITY_OBSERVATIONAL_STUDY = "Observational Study"
AUTHORITY_CASE_REPORT = "Case Report"
AUTHORITY_ANIMAL_STUDY = "Animal Study"
AUTHORITY_IN_VITRO_STUDY = "In-vitro Study"
AUTHORITY_COMMERCIAL_WEBSITE = "Commercial Website"
AUTHORITY_BLOG = "Blog"
AUTHORITY_UNKNOWN = "Unknown Source"

# Detection precedence (see classify_source_authority): organizational
# identity first (most specific, least ambiguous), then provenance red
# flags (commercial/blog), then a peer-reviewed-literature fallback tiered
# by study type, then Unknown. Exposed as a tuple so tests/design docs can
# assert the exact order without re-deriving it from the function body.
AUTHORITY_LABELS = (
    AUTHORITY_EMA_HMPC_MONOGRAPH,
    AUTHORITY_WHO_MONOGRAPH,
    AUTHORITY_ESCOP_MONOGRAPH,
    AUTHORITY_COCHRANE_REVIEW,
    AUTHORITY_COMMERCIAL_WEBSITE,
    AUTHORITY_BLOG,
    AUTHORITY_SYSTEMATIC_REVIEW,
    AUTHORITY_RCT,
    AUTHORITY_CONTROLLED_CLINICAL_TRIAL,
    AUTHORITY_OBSERVATIONAL_STUDY,
    AUTHORITY_CASE_REPORT,
    AUTHORITY_ANIMAL_STUDY,
    AUTHORITY_IN_VITRO_STUDY,
    AUTHORITY_UNKNOWN,
)

# Numeric authority factors, centralized and documented (Phase 3 brief:
# "تمام coefficients و mappings را در یک ساختار configuration متمرکز و
# نام‌گذاری‌شده قرار بده"). Every value is a considered, ordered choice,
# not an independently invented magic number:
#   - EMA HMPC / WHO / ESCOP monographs and Cochrane reviews sit at the
#     top (0.90-1.00): these are the specific organizational identities
#     the Phase 3 brief calls out as strictly more authoritative than a
#     blog, and this module can only assign them when metadata actually
#     names the organization (see classify_source_authority) -- so a
#     high factor here is never a guess.
#   - Peer-reviewed-literature-by-study-type (0.35-0.85) is the fallback
#     used when no specific organizational identity is detected but the
#     text still describes a recognizable scientific study design. These
#     mirror, but do NOT reuse the numeric values of,
#     evidence_interpretation.QUALITY_FACTOR — that table scales
#     Evidence Quality (methodology), this one scales Source Authority
#     (provenance credibility); the two are independent axes that happen
#     to both correlate loosely with study design when no publisher
#     identity is available.
#   - Unknown Source (0.50) is a deliberately conservative middle value —
#     "نه صفر مطلق و نه وزن بالا" — sitting below any confirmed peer-reviewed
#     tier but above Commercial Website/Blog.
#   - Commercial Website / Blog (0.15-0.20) are the lowest tiers: real,
#     non-zero (a commercial monograph can still cite real data) but never
#     competitive with any confirmed scientific or regulatory source.
AUTHORITY_FACTORS: Mapping[str, float] = types.MappingProxyType({
    AUTHORITY_EMA_HMPC_MONOGRAPH: 1.00,
    AUTHORITY_WHO_MONOGRAPH: 0.97,
    AUTHORITY_ESCOP_MONOGRAPH: 0.93,
    AUTHORITY_COCHRANE_REVIEW: 0.93,
    AUTHORITY_SYSTEMATIC_REVIEW: 0.85,
    AUTHORITY_RCT: 0.80,
    AUTHORITY_CONTROLLED_CLINICAL_TRIAL: 0.72,
    AUTHORITY_OBSERVATIONAL_STUDY: 0.60,
    AUTHORITY_UNKNOWN: 0.50,
    AUTHORITY_CASE_REPORT: 0.45,
    AUTHORITY_ANIMAL_STUDY: 0.40,
    AUTHORITY_IN_VITRO_STUDY: 0.35,
    AUTHORITY_COMMERCIAL_WEBSITE: 0.20,
    AUTHORITY_BLOG: 0.15,
})


@dataclass(frozen=True)
class AuthorityClassification:
    """Immutable result of classify_source_authority()."""
    label: str
    score: float
    reason: str


# =======================================================================
# Deterministic, word-boundary-safe phrase matching (bounded, no NLP —
# consistent with evidence_interpretation.py's own _find()/_has() style
# and the Phase 3 brief's "از matcherهای قابل اعتماد موجود پروژه یا
# normalization دقیق استفاده کن" instruction).
# =======================================================================

def _norm(value: Optional[Any]) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _contains_phrase(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    words = phrase.split(" ")
    body = r"\s+".join(re.escape(w) for w in words)
    return re.search(r"\b" + body + r"\b", text) is not None


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


# Organizational-identity phrase tables. EMA and WHO deliberately require
# compound phrases (never a bare "ema" or "who") because
# source_registry.py's own combined connector entry is literally named
# "EMA/WHO/ESCOP Regulatory" — a bare substring match on "ema" or "who"
# would false-positive on that connector name for every regulatory record
# regardless of which specific organization actually authored it (see
# PHASE3_SOURCE_AUTHORITY_AUDIT.md §1.1). ESCOP and Cochrane are
# distinctive enough proper nouns to be safe as bounded single-word
# matches.
_EMA_PHRASES = (
    "ema hmpc",
    "hmpc monograph",
    "committee on herbal medicinal products",
    "european medicines agency",
    "community herbal monograph",
)
_WHO_PHRASES = (
    "who monograph",
    "world health organization",
    "who monographs on selected medicinal plants",
)
_ESCOP_PHRASES = (
    "escop monograph",
    "escop monographs",
    "european scientific cooperative on phytotherapy",
)
# NOTE: deliberately no bare "escop" phrase. source_registry.py's own
# combined connector entry is literally named "EMA/WHO/ESCOP Regulatory",
# so a bare-token match on "escop" would false-positive on that generic
# bucket name alone (verified during module smoke-testing) exactly the
# same way a bare "ema"/"who" match would — see the _EMA_PHRASES /
# _WHO_PHRASES comment above. ESCOP therefore requires the same
# compound-phrase specificity as EMA/WHO.
_COCHRANE_PHRASES = (
    "cochrane review",
    "cochrane database",
    "cochrane systematic review",
    "cochrane",
)

_COMMERCIAL_URL_MARKERS = (
    "shop", "store", "buy", "cart", "checkout", "product-page",
    "myshopify", "amazon.", "etsy.",
)
_COMMERCIAL_TYPE_PHRASES = ("commercial website", "commercial", "vendor", "retailer")
_BLOG_URL_MARKERS = ("/blog/", "blog.", "blogspot", "wordpress.com", "medium.com")
_BLOG_TYPE_PHRASES = ("blog", "weblog")

# Peer-reviewed-literature fallback tiers (used only when no
# organizational identity and no commercial/blog signal is found).
_SYSTEMATIC_REVIEW_PHRASES = ("systematic review", "meta-analysis", "meta analysis")
_RCT_PHRASES = (
    "randomized controlled trial", "randomised controlled trial",
    "randomized", "randomised", "rct",
)
_CONTROLLED_TRIAL_PHRASES = ("controlled clinical trial", "controlled trial", "clinical trial")
_OBSERVATIONAL_PHRASES = (
    "cohort study", "case-control study", "case control study",
    "observational study", "cross-sectional study",
)
_CASE_REPORT_PHRASES = ("case report", "case series")
_ANIMAL_PHRASES = ("animal study", "in vivo", "rat model", "mouse model", "murine", "rodent")
_IN_VITRO_PHRASES = ("in vitro", "cell line", "cell culture")


def _looks_commercial(url_text: str, type_category_text: str) -> bool:
    if any(marker in url_text for marker in _COMMERCIAL_URL_MARKERS):
        return True
    return _contains_any(type_category_text, _COMMERCIAL_TYPE_PHRASES)


def _looks_blog(url_text: str, type_category_text: str) -> bool:
    if any(marker in url_text for marker in _BLOG_URL_MARKERS):
        return True
    return _contains_any(type_category_text, _BLOG_TYPE_PHRASES)


def classify_source_authority(
    *,
    source_organization: Optional[str] = None,
    source_type: Optional[str] = None,
    source_category: Optional[str] = None,
    source_title: Optional[str] = None,
    source_url: Optional[str] = None,
    connector_name: Optional[str] = None,
    supporting_text: Optional[str] = None,
) -> AuthorityClassification:
    """Deterministically classify one piece of evidence's Source Authority.

    Precedence (see AUTHORITY_LABELS): EMA HMPC > WHO Monograph > ESCOP
    Monograph > Cochrane Review > Commercial Website > Blog > peer-reviewed
    -literature-by-study-type (Systematic Review down to In-vitro Study)
    > Unknown Source (conservative default — never zero, never high).

    Every argument is optional; only non-empty values are consulted.
    Never guesses: absence of a recognizable signal in the metadata
    provided always resolves to AUTHORITY_UNKNOWN, never to a fabricated
    high- or zero-authority label.
    """
    org_signal = " ".join([
        _norm(source_organization), _norm(source_title), _norm(supporting_text),
    ]).strip()
    connector_text = _norm(connector_name)
    url_text = _norm(source_url)
    type_category_text = " ".join([_norm(source_type), _norm(source_category)]).strip()

    if _contains_any(org_signal, _EMA_PHRASES) or _contains_any(connector_text, _EMA_PHRASES):
        return AuthorityClassification(
            AUTHORITY_EMA_HMPC_MONOGRAPH,
            AUTHORITY_FACTORS[AUTHORITY_EMA_HMPC_MONOGRAPH],
            "Matched EMA/HMPC monograph terminology in source organization/title/connector metadata.",
        )
    if _contains_any(org_signal, _WHO_PHRASES) or _contains_any(connector_text, _WHO_PHRASES):
        return AuthorityClassification(
            AUTHORITY_WHO_MONOGRAPH,
            AUTHORITY_FACTORS[AUTHORITY_WHO_MONOGRAPH],
            "Matched WHO monograph terminology in source organization/title/connector metadata.",
        )
    if _contains_any(org_signal, _ESCOP_PHRASES) or _contains_any(connector_text, _ESCOP_PHRASES):
        return AuthorityClassification(
            AUTHORITY_ESCOP_MONOGRAPH,
            AUTHORITY_FACTORS[AUTHORITY_ESCOP_MONOGRAPH],
            "Matched ESCOP monograph terminology in source organization/title/connector metadata.",
        )
    if _contains_any(org_signal, _COCHRANE_PHRASES) or _contains_any(connector_text, _COCHRANE_PHRASES):
        return AuthorityClassification(
            AUTHORITY_COCHRANE_REVIEW,
            AUTHORITY_FACTORS[AUTHORITY_COCHRANE_REVIEW],
            "Matched Cochrane review terminology in source organization/title/connector metadata.",
        )
    if _looks_commercial(url_text, type_category_text):
        return AuthorityClassification(
            AUTHORITY_COMMERCIAL_WEBSITE,
            AUTHORITY_FACTORS[AUTHORITY_COMMERCIAL_WEBSITE],
            "Source URL/type/category matched commercial-website markers.",
        )
    if _looks_blog(url_text, type_category_text):
        return AuthorityClassification(
            AUTHORITY_BLOG,
            AUTHORITY_FACTORS[AUTHORITY_BLOG],
            "Source URL/type/category matched blog markers.",
        )

    literature_text = " ".join([org_signal, connector_text, type_category_text]).strip()
    if _contains_any(literature_text, _SYSTEMATIC_REVIEW_PHRASES):
        return AuthorityClassification(
            AUTHORITY_SYSTEMATIC_REVIEW,
            AUTHORITY_FACTORS[AUTHORITY_SYSTEMATIC_REVIEW],
            "No specific organizational identity found; peer-reviewed-literature fallback matched systematic review / meta-analysis wording.",
        )
    if _contains_any(literature_text, _RCT_PHRASES):
        return AuthorityClassification(
            AUTHORITY_RCT,
            AUTHORITY_FACTORS[AUTHORITY_RCT],
            "No specific organizational identity found; peer-reviewed-literature fallback matched randomized-controlled-trial wording.",
        )
    if _contains_any(literature_text, _CONTROLLED_TRIAL_PHRASES):
        return AuthorityClassification(
            AUTHORITY_CONTROLLED_CLINICAL_TRIAL,
            AUTHORITY_FACTORS[AUTHORITY_CONTROLLED_CLINICAL_TRIAL],
            "No specific organizational identity found; peer-reviewed-literature fallback matched controlled/clinical-trial wording.",
        )
    if _contains_any(literature_text, _OBSERVATIONAL_PHRASES):
        return AuthorityClassification(
            AUTHORITY_OBSERVATIONAL_STUDY,
            AUTHORITY_FACTORS[AUTHORITY_OBSERVATIONAL_STUDY],
            "No specific organizational identity found; peer-reviewed-literature fallback matched observational-study wording.",
        )
    if _contains_any(literature_text, _CASE_REPORT_PHRASES):
        return AuthorityClassification(
            AUTHORITY_CASE_REPORT,
            AUTHORITY_FACTORS[AUTHORITY_CASE_REPORT],
            "No specific organizational identity found; peer-reviewed-literature fallback matched case-report/case-series wording.",
        )
    if _contains_any(literature_text, _ANIMAL_PHRASES):
        return AuthorityClassification(
            AUTHORITY_ANIMAL_STUDY,
            AUTHORITY_FACTORS[AUTHORITY_ANIMAL_STUDY],
            "No specific organizational identity found; peer-reviewed-literature fallback matched animal-study wording.",
        )
    if _contains_any(literature_text, _IN_VITRO_PHRASES):
        return AuthorityClassification(
            AUTHORITY_IN_VITRO_STUDY,
            AUTHORITY_FACTORS[AUTHORITY_IN_VITRO_STUDY],
            "No specific organizational identity found; peer-reviewed-literature fallback matched in-vitro-study wording.",
        )

    return AuthorityClassification(
        AUTHORITY_UNKNOWN,
        AUTHORITY_FACTORS[AUTHORITY_UNKNOWN],
        "No deterministic organizational, commercial/blog, or study-type signal found in the provided metadata; conservative fallback applied.",
    )


def _row_get(row: Any, *keys: str) -> Optional[Any]:
    """Read the first present, non-empty value for any of `keys` from a
    dict, pandas.Series, or any other Mapping-like object exposing
    .get(). Never raises on a missing key."""
    getter = getattr(row, "get", None)
    if getter is None:
        return None
    for key in keys:
        value = getter(key)
        if value not in (None, ""):
            return value
    return None


def classify_source_authority_from_row(row: Any) -> AuthorityClassification:
    """Convenience wrapper for callers holding a dict-like/Series "row"
    rather than discrete keyword arguments.

    Recognizes BOTH of the two live pipelines' row shapes without
    guessing between them:
      - the ingestion/database shape (Source_Organization, Source_Type,
        Source_Category, Source_Title, Source_URL — see database.py's
        load_evidence_records()/save_evidence_record());
      - candidate_shortlisting.py's post-processing shape, which does not
        carry Source_Organization/Source_URL at all, but does carry
        Evidence_Source (a connector/provenance description string),
        Evidence_Hierarchy_Detail, Candidate_Evidence_Strength_Tier,
        GRADE_Certainty, and Evidence_Level as free-text signals.
    """
    return classify_source_authority(
        source_organization=_row_get(row, "Source_Organization", "source_organization"),
        source_type=_row_get(row, "Source_Type", "source_type"),
        source_category=_row_get(row, "Source_Category", "source_category"),
        source_title=_row_get(row, "Source_Title", "source_title", "article_title"),
        source_url=_row_get(row, "Source_URL", "source_url", "article_identifier"),
        connector_name=_row_get(
            row, "Evidence_Source", "Source_Priority", "connector", "connector_name",
        ),
        supporting_text=_row_get(
            row,
            "Evidence_Hierarchy_Detail",
            "Candidate_Evidence_Strength_Tier",
            "GRADE_Certainty",
            "Notes",
            "Evidence_Level",
            "supporting_sentence",
        ),
    )


# =======================================================================
# Combination formulas — the ONE place "evidence strength" and "signed
# evidence contribution" are computed (Phase 3 brief: "این مقادیر را در
# یک محل مشخص و قابل تست تعریف کن").
# =======================================================================

# Direction -> sign/magnitude used only for the final signed contribution
# step. Mirrors, but is independent from,
# evidence_interpretation.DIRECTION_CONTRIBUTION_RATIO (that table also
# folds in a clinical-tier base weight specific to
# botanical_rd_candidate_engine.py; this one is a pure sign/magnitude
# factor usable by any live pipeline's own point scale).
DIRECTION_SIGN: Mapping[str, float] = types.MappingProxyType({
    DIRECTION_POSITIVE: 1.0,
    DIRECTION_MIXED: 0.3,
    DIRECTION_NULL: 0.0,
    DIRECTION_UNCLEAR: 0.0,
    DIRECTION_NEGATIVE: -1.0,
})


def direction_sign(direction: Optional[str]) -> float:
    """Sign/magnitude for a given Evidence_Direction label. Unrecognized
    or missing direction is treated as 0.0 (no contribution), never as
    positive."""
    return DIRECTION_SIGN.get(direction, 0.0)


def study_quality_factor(evidence_quality_label: Optional[str]) -> float:
    """Reuses evidence_interpretation.QUALITY_FACTOR — the existing,
    single source of truth for how a methodology-quality label scales a
    contribution's magnitude. Not redefined here."""
    return QUALITY_FACTOR.get(evidence_quality_label, 1.0)


def source_authority_factor(label: Optional[str]) -> float:
    """Numeric factor for a given Source Authority label, defaulting to
    the Unknown-Source conservative factor for any unrecognized label
    (never 0.0, never the maximum)."""
    return AUTHORITY_FACTORS.get(label, AUTHORITY_FACTORS[AUTHORITY_UNKNOWN])


def evidence_applicability_factor(label: Optional[str]) -> float:
    """Reuses evidence_interpretation.APPLICABILITY_FACTOR."""
    return APPLICABILITY_FACTOR.get(label, 1.0)


def weighted_evidence_strength(
    quality_factor: float,
    authority_factor: float,
    applicability_factor_value: float = 1.0,
) -> float:
    """evidence_strength = study_quality_factor x source_authority_factor
    x applicability_factor

    Deliberately outcome/direction-free: this is "how much this piece of
    evidence should count", independent of what it found.
    """
    return quality_factor * authority_factor * applicability_factor_value


def signed_evidence_contribution(strength: float, direction: Optional[str]) -> float:
    """signed_evidence_contribution = evidence_strength x direction_sign

    This is the ONLY step where direction is applied. Source Authority
    and Evidence Quality never appear on this line except pre-multiplied
    into `strength` — neither can change the sign here.
    """
    return strength * direction_sign(direction)


def summarize_authority_distribution(labels: Iterable[Optional[str]]) -> "dict[str, int]":
    """Aggregate-level explainability helper: counts of each Source
    Authority label actually observed across a candidate's evidence set.
    Missing/None labels are counted under AUTHORITY_UNKNOWN, never
    dropped silently."""
    counts: "dict[str, int]" = {}
    for label in labels:
        key = label or AUTHORITY_UNKNOWN
        counts[key] = counts.get(key, 0) + 1
    return counts
