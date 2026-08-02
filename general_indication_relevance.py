"""General, corpus-adaptive indication relevance for botanical evidence.

The matcher deliberately contains no disease-specific vocabulary.  It builds a
query profile from the evidence corpus at runtime:

1. exact query words identify seed records;
2. discriminative terms and phrases that repeatedly co-occur in those seed
   records are learned automatically;
3. every evidence record is scored against the query and learned profile.

This allows a free-text query such as ``cough`` to discover evidence phrased as
``antitussive`` or ``expectorant`` when those concepts co-occur with cough in
other records, without adding a cough-specific rule to the source code.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
import re
from typing import Iterable, Sequence


_STOPWORDS = {
    "about", "after", "against", "also", "among", "based", "been", "being",
    "between", "botanical", "clinical", "compound", "control", "data", "disease",
    "during", "effect", "effects", "evidence", "extract", "from", "group", "health",
    "human", "indication", "intervention", "investigate", "medical", "medicine",
    "model", "outcome", "patient", "patients", "plant", "plants", "product",
    "reported", "research", "result", "results", "review", "selected", "significant",
    "study", "studies", "support", "systematic", "target", "treatment", "trial",
    "using", "with", "without", "which", "were", "this", "that", "their", "there",
    "these", "those", "into", "over", "under", "than", "then", "have", "has",
    "had", "not", "and", "the", "for", "are", "was", "may", "can", "could",
    # Generic outcome-direction words. These describe the direction of
    # virtually any clinical result ("reduced X", "improved Y") regardless of
    # what X or Y is, so they carry no indication-specific information and
    # must never become a discriminative corpus-derived expansion term (see
    # constraint: matching only generic words must never create a relevant
    # candidate). Without this, a shared word like "reduced" could link a
    # diabetes record ("Reduced HbA1c") to an unrelated cough query merely
    # because both records happen to report a reduction in something.
    "reduced", "reduce", "reduces", "reducing", "reduction", "reductions",
    "increased", "increase", "increases", "increasing",
    "improved", "improve", "improves", "improving", "improvement", "improvements",
    "decreased", "decrease", "decreases", "decreasing",
    "elevated", "elevate", "elevates", "elevating",
    "lower", "lowered", "lowering", "lowers",
    "higher", "raised", "raising", "raises",
    "changes", "change", "changed", "following", "prior", "versus", "compared",
    "baseline", "placebo", "administered", "administration",
    # Generic clinical-trial-methodology words. These describe HOW a study
    # was conducted, not WHAT it studied, so they are just as indication-
    # agnostic as the outcome-direction words above -- an RCT for diabetes
    # and an RCT for cough share this vocabulary purely because both are
    # RCTs. Without this, "randomized"/"rct" leaked a diabetes record into
    # a cough query via shared study-design wording in Study_Type/
    # Evidence_Level text (test_cough_indication_generalization.py).
    "randomized", "randomised", "rct", "controlled", "blind", "blinded",
    "crossover", "cohort", "multicenter", "multicentre", "phase", "pilot",
    "label", "open", "arm", "arms",
    # Generic mechanism buzzwords that appear across a huge share of
    # botanical evidence regardless of indication (almost every plant
    # extract is tested for antioxidant activity at some point). Domain-
    # appropriate-but-common words that DO carry indication-specific
    # meaning (e.g. "inflammatory" for the Inflammation indication) are
    # deliberately NOT added here -- those are still correctly filtered by
    # the corpus-ubiquity check in build_indication_profile() when they
    # really are ubiquitous in a given corpus, without losing their
    # legitimate discriminative value when they are not.
    "antioxidant", "antioxidants", "oxidative", "scavenging",
}





def normalize_text(value: object) -> str:
    text = str(value or "").lower()
    text = text.replace("α", " alpha ").replace("β", " beta ").replace("γ", " gamma ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: object) -> list[str]:
    return [
        token for token in normalize_text(value).split()
        if len(token) >= 3 and token not in _STOPWORDS and not token.isdigit()
    ]


def _features(value: object) -> set[str]:
    tokens = _tokens(value)
    features = set(tokens)
    features.update(
        f"{tokens[i]} {tokens[i + 1]}"
        for i in range(len(tokens) - 1)
        if tokens[i] != tokens[i + 1]
    )
    return features


@dataclass(frozen=True)
class RelevanceMatch:
    score: float
    match_type: str
    matched_terms: tuple[str, ...]
    reason: str
    confidence: float = 0.0


@dataclass(frozen=True)
class IndicationProfile:
    query: str
    query_tokens: tuple[str, ...]
    expansion_weights: tuple[tuple[str, float], ...]
    seed_count: int
    corpus_size: int

    def match(self, text: object) -> RelevanceMatch:
        normalized = normalize_text(text)
        if not normalized or not self.query_tokens:
            return RelevanceMatch(0.0, "none", (), "No usable query or evidence text")

        doc_features = _features(normalized)
        query_features = set(self.query_tokens)
        phrase_exact = bool(self.query and self.query in normalized)
        exact_hits = sorted(term for term in query_features if term in doc_features)
        token_coverage = len(exact_hits) / max(1, len(query_features))

        weighted_hits: list[tuple[str, float]] = [
            (term, weight)
            for term, weight in self.expansion_weights
            if term in doc_features
        ]
        max_expansion_weight = max((weight for _, weight in self.expansion_weights), default=1.0)
        # One highly discriminative learned term (for example ``antitussive``
        # learned from records that also say ``cough``) is enough to establish
        # exploratory semantic relevance.  Dividing by the sum of every learned
        # term diluted such a match to almost zero in large profiles.
        expansion_strength = 0.0
        if weighted_hits:
            strongest = max(weight for _, weight in weighted_hits) / max_expansion_weight
            cumulative = min(1.0, sum(weight for _, weight in weighted_hits) / max_expansion_weight)
            expansion_strength = 0.7 * strongest + 0.3 * cumulative

        # Exact language remains strongest. Corpus-learned concepts can establish
        # relevance, but their contribution is capped below an exact phrase match.
        score = 0.0
        if phrase_exact:
            score = 1.0
        else:
            score = min(0.78, token_coverage * 0.78)
            score = max(score, min(0.68, expansion_strength * 0.68))
            if exact_hits and weighted_hits:
                score = min(0.92, score + 0.12)

        matched = tuple(exact_hits + [term for term, _ in weighted_hits[:8]])
        if phrase_exact or token_coverage >= 0.999:
            match_type = "direct lexical"
        elif exact_hits:
            match_type = "partial lexical"
        elif weighted_hits:
            match_type = "corpus-semantic"
        else:
            match_type = "none"

        reason = (
            f"{match_type}; score={score:.3f}; matched=" + (", ".join(matched) or "none")
        )
        return RelevanceMatch(round(float(score), 4), match_type, matched, reason)


def build_indication_profile(query: str, corpus_texts: Sequence[object]) -> IndicationProfile:
    """Build a disease-agnostic relevance profile from the current evidence corpus."""
    query_norm = normalize_text(query)
    query_tokens = tuple(dict.fromkeys(_tokens(query_norm)))
    corpus = [normalize_text(text) for text in corpus_texts if normalize_text(text)]
    corpus_features = [_features(text) for text in corpus]
    corpus_size = len(corpus_features)

    if not query_tokens or not corpus_features:
        return IndicationProfile(query_norm, query_tokens, (), 0, corpus_size)

    query_set = set(query_tokens)
    seeds = [features for features in corpus_features if features & query_set or query_norm in " ".join(features)]
    if not seeds:
        return IndicationProfile(query_norm, query_tokens, (), 0, corpus_size)

    corpus_df: Counter[str] = Counter()
    seed_df: Counter[str] = Counter()
    for features in corpus_features:
        corpus_df.update(features)
    for features in seeds:
        seed_df.update(features)

    minimum_seed_df = 1 if len(seeds) <= 3 else 2
    ranked: list[tuple[str, float]] = []
    for term, count in seed_df.items():
        if term in query_set or term in _STOPWORDS:
            continue
        if count < minimum_seed_df:
            continue
        # Reject ubiquitous corpus terms and terms unique to nearly every record.
        global_df = corpus_df[term]
        if global_df / max(1, corpus_size) > 0.80:
            continue
        seed_prevalence = count / len(seeds)
        specificity = math.log((corpus_size + 1.0) / (global_df + 1.0)) + 1.0
        phrase_bonus = 1.25 if " " in term else 1.0
        weight = seed_prevalence * specificity * phrase_bonus
        if weight >= 0.35:
            ranked.append((term, weight))

    ranked.sort(key=lambda item: (-item[1], item[0]))
    top = ranked[:32]
    total = sum(weight for _, weight in top) or 1.0
    normalized_weights = tuple((term, weight / total) for term, weight in top)
    return IndicationProfile(query_norm, query_tokens, normalized_weights, len(seeds), corpus_size)


def corpus_texts_from_records(records_by_plant: dict[str, list[dict]]) -> list[str]:
    return [
        str(record.get("text") or "")
        for records in records_by_plant.values()
        for record in records
        if str(record.get("text") or "").strip()
    ]


# ---------------------------------------------------------------------------
# Field-aware, single-authoritative record-level relevance.
#
# This is the production entry point: one function, one scoring path, used by
# both indication_candidate_discovery.py (record-level gating) and
# candidate_shortlisting.py (plant-level scoring), so the two stages cannot
# disagree by recomputing relevance with different rules.
# ---------------------------------------------------------------------------

ENGINE_VERSION = "1.0-general-corpus-adaptive"

# Required match_type categories (see module docstring / architecture notes).
# Listed in descending strength order.
MATCH_EXACT_INDICATION = "exact_indication"
MATCH_EXPLICIT_FIELD_OVERLAP = "explicit_field_overlap"
MATCH_OUTCOME_OR_MECHANISM_SUPPORT = "outcome_or_mechanism_support"
MATCH_CORPUS_DERIVED_SEMANTIC = "corpus_derived_semantic"
MATCH_WEAK_LEXICAL = "weak_lexical"
MATCH_CURATED_ASSIST_FALLBACK = "curated_assist_fallback"
MATCH_NO_MATCH = "no_match"

# A record's evidence text is split into three reliability tiers before
# scoring. Tier 1 (explicit indication fields) is authoritative: a match
# there outranks any match found only in outcome/mechanism fields or free
# source text, regardless of how that match was found.
TIER1_FIELDS = ("target_indication", "extracted_indication", "target_indication_detected")
TIER2_FIELDS = ("primary_outcome", "result_direction", "mechanism", "target")
TIER3_FIELDS = ("title", "abstract", "notes", "source_raw_text", "study_type", "evidence_type")

# Score ceilings enforce strict tier ordering: any non-zero Tier 1 match
# outranks any Tier 2 match, which outranks any Tier 3 match, which outranks
# the curated fallback. "Exact indication matches should be stronger than
# inferred semantic matches" (constraint 7) and "A direct match in Tier 1
# must score higher than a match found only in free text" both fall out of
# these ceilings directly, not from ad hoc per-case logic.
_TIER1_CEILING = 0.95   # 1.0 is reserved for a literal exact-phrase match
_TIER2_CEILING = 0.70
_TIER3_SEMANTIC_CEILING = 0.50
_TIER3_LEXICAL_CEILING = 0.35
_ASSIST_CEILING = 0.30

_CONFIDENCE_BY_TYPE = {
    MATCH_EXACT_INDICATION: 95.0,
    MATCH_EXPLICIT_FIELD_OVERLAP: 80.0,
    MATCH_OUTCOME_OR_MECHANISM_SUPPORT: 60.0,
    MATCH_CORPUS_DERIVED_SEMANTIC: 50.0,
    MATCH_WEAK_LEXICAL: 25.0,
    MATCH_CURATED_ASSIST_FALLBACK: 20.0,
    MATCH_NO_MATCH: 0.0,
}


def score_record_relevance(
    profile: IndicationProfile,
    tier1_text: object = "",
    tier2_text: object = "",
    tier3_text: object = "",
    assist_terms: Sequence[str] = (),
) -> RelevanceMatch:
    """Score one evidence record's indication relevance from field-tiered text.

    This is the single authoritative scoring function. ``profile`` is built
    once per query from the current evidence corpus (see
    :func:`build_indication_profile`) and contains no disease-specific
    vocabulary of its own -- it is derived entirely from the query and the
    corpus at hand.

    Priority is strength-first, tier-second: a full/exact literal query-phrase
    match is strong evidence wherever it is found (most real evidence records
    name their indication in a title or abstract, not a separate structured
    field), but Tier 1 (explicit indication fields) always scores strictly
    higher than the same strength of match found only in Tier 2 or Tier 3,
    and a literal match always outranks a corpus-learned (non-literal)
    expansion-term match, wherever either is found.

    ``assist_terms`` is the ONLY place a curated vocabulary (e.g.
    indication_semantics.py) may contribute. It is consulted only after the
    corpus-adaptive engine finds nothing at all, its contribution is capped
    below every corpus-adaptive match type, and its use is always disclosed
    in ``reason`` -- it never overrides or is required for a corpus-adaptive
    match.
    """
    m1 = profile.match(tier1_text)
    m2 = profile.match(tier2_text)
    m3 = profile.match(tier3_text)
    literal_types = ("direct lexical", "partial lexical")

    # 1. Tier 1 full/exact literal match -- the strongest possible signal.
    if m1.match_type == "direct lexical":
        return RelevanceMatch(
            1.0, MATCH_EXACT_INDICATION, m1.matched_terms,
            "Exact indication phrase matched an explicit indication field "
            f"(target_indication/extracted_indication); matched={', '.join(m1.matched_terms) or 'query phrase'}",
            _CONFIDENCE_BY_TYPE[MATCH_EXACT_INDICATION],
        )

    # 2. Any literal (non-corpus-derived) full/exact match found only in Tier
    #    2 or Tier 3 -- most real evidence names its indication in a title or
    #    abstract, not a separate structured field, so this is still strong,
    #    directly-stated evidence. Scored below every Tier 1 result.
    if m2.match_type == "direct lexical" or m3.match_type == "direct lexical":
        best = m2 if m2.match_type == "direct lexical" else m3
        tier_label = "outcome/mechanism fields" if best is m2 else "source text (title/abstract/notes)"
        score = round(min(_TIER2_CEILING if best is m2 else _TIER2_CEILING - 0.05, best.score * 0.85), 4)
        return RelevanceMatch(
            score, MATCH_EXPLICIT_FIELD_OVERLAP, best.matched_terms,
            f"Exact indication phrase matched in {tier_label} rather than an explicit indication "
            f"field; matched={', '.join(best.matched_terms) or 'query phrase'}",
            _CONFIDENCE_BY_TYPE[MATCH_EXPLICIT_FIELD_OVERLAP],
        )

    # 3. Tier 1 partial literal overlap (some but not all query tokens).
    if m1.score > 0:
        score = round(min(_TIER1_CEILING, m1.score), 4)
        return RelevanceMatch(
            score, MATCH_EXPLICIT_FIELD_OVERLAP, m1.matched_terms,
            f"Query terms overlapped an explicit indication field without a full exact phrase; matched={', '.join(m1.matched_terms)}",
            _CONFIDENCE_BY_TYPE[MATCH_EXPLICIT_FIELD_OVERLAP],
        )

    # 4. Tier 2 partial literal overlap, or corpus-learned terms in Tier 2.
    if m2.score > 0:
        score = round(min(_TIER2_CEILING, m2.score * 0.85), 4)
        match_type = (
            MATCH_OUTCOME_OR_MECHANISM_SUPPORT if m2.match_type in literal_types
            else MATCH_CORPUS_DERIVED_SEMANTIC
        )
        reason = (
            "Query terms matched in outcome/mechanism fields (primary_outcome/mechanism/target)"
            if match_type == MATCH_OUTCOME_OR_MECHANISM_SUPPORT
            else "Corpus-learned terms co-occurring with the query matched in outcome/mechanism fields"
        )
        return RelevanceMatch(
            score, match_type, m2.matched_terms,
            f"{reason}; matched={', '.join(m2.matched_terms)}",
            _CONFIDENCE_BY_TYPE[match_type],
        )

    # 5. Corpus-learned (non-literal) terms found only in Tier 3 source text.
    if m3.match_type == "corpus-semantic" and m3.score > 0:
        score = round(min(_TIER3_SEMANTIC_CEILING, m3.score * 0.6), 4)
        return RelevanceMatch(
            score, MATCH_CORPUS_DERIVED_SEMANTIC, m3.matched_terms,
            f"Corpus-learned terms co-occurring with the query matched only in source text; matched={', '.join(m3.matched_terms)}",
            _CONFIDENCE_BY_TYPE[MATCH_CORPUS_DERIVED_SEMANTIC],
        )
    # 6. Weak partial literal overlap in Tier 3 source text only.
    if m3.score > 0:
        score = round(min(_TIER3_LEXICAL_CEILING, m3.score * 0.4), 4)
        return RelevanceMatch(
            score, MATCH_WEAK_LEXICAL, m3.matched_terms,
            f"Only weak literal term overlap in free source text; matched={', '.join(m3.matched_terms)}",
            _CONFIDENCE_BY_TYPE[MATCH_WEAK_LEXICAL],
        )

    # 7. Strictly-capped, disclosed backward-compatibility fallback.
    if assist_terms:
        combined = " ".join(str(t) for t in (tier1_text, tier2_text, tier3_text) if t)
        combined_norm = normalize_text(combined)
        hits = sorted({
            term for term in assist_terms
            if term and normalize_text(term) and normalize_text(term) in combined_norm
        })
        if hits:
            score = round(min(_ASSIST_CEILING, 0.12 + 0.04 * len(hits)), 4)
            return RelevanceMatch(
                score, MATCH_CURATED_ASSIST_FALLBACK, tuple(hits),
                "No corpus-adaptive match; matched curated indication_semantics.py "
                f"term(s) as a capped backward-compatibility fallback: {', '.join(hits)}",
                _CONFIDENCE_BY_TYPE[MATCH_CURATED_ASSIST_FALLBACK],
            )

    return RelevanceMatch(
        0.0, MATCH_NO_MATCH, (), "No matching indication terms found in any evidence field",
        _CONFIDENCE_BY_TYPE[MATCH_NO_MATCH],
    )


# ---------------------------------------------------------------------------
# Hybrid engine: deterministic lexical/corpus-adaptive engine (above, fully
# unchanged) plus an optional embedding-similarity component.
#
# score_record_relevance() above remains the complete, self-sufficient
# deterministic engine and every existing caller/test of it is unaffected.
# score_record_relevance_hybrid() below is purely additive: it calls the
# same profile.match() computations, adds an optional embedding_similarity
# input (a plain float, injected by the caller -- this module makes no
# network call and has no OpenAI/Supabase dependency of its own), and
# combines them under one centralized, versioned weight configuration.
# When embedding_similarity is None (embedding provider/RPC unavailable,
# or simply not supplied), this degrades EXACTLY to the deterministic
# engine's own answer, with weights renormalized across the remaining
# three components -- see HybridScore.fallback_mode.
# ---------------------------------------------------------------------------

MATCH_HYBRID_SEMANTIC = "hybrid_semantic"
MATCH_EMBEDDING_SEMANTIC = "embedding_semantic"

HYBRID_CONFIG_VERSION = "hybrid-1.0"

# Centralized, versioned weights (requirement: "weights and thresholds must
# be centralized in one versioned configuration and validated through
# tests/Gold Cases"). These are the requested INITIAL values -- explicitly
# not yet calibrated against real embeddings (see
# EMBEDDING_THRESHOLD_CALIBRATION.md). Changing these numbers is a
# configuration change, not a code change, and should be done in one place.
HYBRID_WEIGHTS = {
    "explicit_indication": 0.35,
    "embedding_similarity": 0.45,
    "outcome_mechanism": 0.15,
    "lexical_fallback": 0.05,
}

# Below this cosine similarity, an embedding match contributes nothing --
# prevents low-confidence embedding noise from ever entering the score.
# PROVISIONAL default; see EMBEDDING_THRESHOLD_CALIBRATION.md.
EMBEDDING_MIN_CONTRIBUTION = 0.55
# At or above this cosine similarity, with no other supporting signal, an
# embedding match alone is strong enough to be labelled embedding_semantic
# (never "direct evidence" -- rule 2). PROVISIONAL default.
EMBEDDING_SEMANTIC_THRESHOLD = 0.82
# At or above this (lower) cosine similarity, COMBINED with at least some
# deterministic support (outcome/mechanism or lexical), the record is
# labelled hybrid_semantic. PROVISIONAL default.
HYBRID_SEMANTIC_THRESHOLD = 0.65

_HYBRID_CONFIDENCE_BY_TYPE = dict(_CONFIDENCE_BY_TYPE)
_HYBRID_CONFIDENCE_BY_TYPE[MATCH_HYBRID_SEMANTIC] = 55.0
_HYBRID_CONFIDENCE_BY_TYPE[MATCH_EMBEDDING_SEMANTIC] = 45.0


@dataclass(frozen=True)
class HybridScore:
    final_relevance_score: float
    match_type: str
    matched_terms: tuple[str, ...]
    reason: str
    confidence: float
    explicit_indication_score: float
    embedding_similarity: float | None
    outcome_mechanism_score: float
    lexical_fallback_score: float
    fallback_mode: bool  # True when embedding_similarity was unavailable


def score_record_relevance_hybrid(
    profile: IndicationProfile,
    tier1_text: object = "",
    tier2_text: object = "",
    tier3_text: object = "",
    assist_terms: Sequence[str] = (),
    embedding_similarity: float | None = None,
    weights: dict[str, float] | None = None,
) -> HybridScore:
    """Score one record combining the deterministic lexical/corpus-adaptive
    engine with an optional embedding-similarity signal.

    Rules enforced here (see module docstring for the full architecture):

    1. A literal Tier-1 exact-phrase match remains the strongest possible
       evidence regardless of embedding_similarity.
    2. A high embedding_similarity alone is never labelled as strong as an
       explicit field match -- it is labelled embedding_semantic or
       hybrid_semantic, both scored and gated below explicit matches, and
       both grouped with the "supportive", not "strong", match types by
       every caller (indication_candidate_discovery.py,
       candidate_shortlisting.py).
    3. embedding_similarity is supplied by the caller for THIS record only
       -- this function has no mechanism to look at any other record, so it
       cannot transfer evidence between plants by construction.
    4. Generic semantic similarity does not by itself create a candidate:
       EMBEDDING_MIN_CONTRIBUTION and EMBEDDING_SEMANTIC_THRESHOLD gate how
       much a similarity score can contribute and whether it can stand
       alone.
    5. Generic mechanism-only support: outcome_mechanism_score comes from
       the same corpus-adaptive engine as score_record_relevance(), whose
       stopword list already excludes generic mechanism buzzwords
       (antioxidant, oxidative, scavenging) from ever becoming a
       discriminative learned term.
    """
    w = weights or HYBRID_WEIGHTS

    m1 = profile.match(tier1_text)
    m2 = profile.match(tier2_text)
    m3 = profile.match(tier3_text)

    explicit_score = m1.score
    outcome_score = m2.score
    lexical_score = m3.score

    # Rule 1: literal Tier-1 exact phrase always wins outright.
    if m1.match_type == "direct lexical":
        return HybridScore(
            1.0, MATCH_EXACT_INDICATION, m1.matched_terms,
            "Exact indication phrase matched an explicit indication field; "
            f"matched={', '.join(m1.matched_terms) or 'query phrase'}",
            _HYBRID_CONFIDENCE_BY_TYPE[MATCH_EXACT_INDICATION],
            explicit_score, embedding_similarity, outcome_score, lexical_score,
            fallback_mode=embedding_similarity is None,
        )

    # Any other literal (non-corpus-derived) full/exact match, in Tier 1
    # partial or Tier 2/3 full -- delegate entirely to the deterministic
    # engine's own strong-match handling (identical priority ordering to
    # score_record_relevance(), reused rather than re-implemented).
    deterministic = score_record_relevance(profile, tier1_text, tier2_text, tier3_text, assist_terms)
    if deterministic.match_type in (MATCH_EXACT_INDICATION, MATCH_EXPLICIT_FIELD_OVERLAP):
        return HybridScore(
            deterministic.score, deterministic.match_type, deterministic.matched_terms,
            deterministic.reason, _HYBRID_CONFIDENCE_BY_TYPE[deterministic.match_type],
            explicit_score, embedding_similarity, outcome_score, lexical_score,
            fallback_mode=embedding_similarity is None,
        )

    # From here, no literal explicit-field match exists. Embedding
    # similarity, if available and above the minimum contribution
    # threshold, is combined with whatever deterministic signal exists.
    effective_embedding = (
        embedding_similarity
        if embedding_similarity is not None and embedding_similarity >= EMBEDDING_MIN_CONTRIBUTION
        else None
    )

    has_deterministic_support = deterministic.match_type not in (MATCH_NO_MATCH, MATCH_CURATED_ASSIST_FALLBACK)

    if effective_embedding is not None:
        if effective_embedding >= EMBEDDING_SEMANTIC_THRESHOLD and not has_deterministic_support:
            combined = (
                w["explicit_indication"] * explicit_score
                + w["embedding_similarity"] * effective_embedding
                + w["outcome_mechanism"] * outcome_score
                + w["lexical_fallback"] * lexical_score
            )
            return HybridScore(
                round(min(0.80, combined), 4), MATCH_EMBEDDING_SEMANTIC, (),
                f"Embedding similarity ({effective_embedding:.3f}) alone matched no explicit "
                "lexical/corpus-derived term in any tier; treated as exploratory semantic "
                "relevance, never as direct evidence",
                _HYBRID_CONFIDENCE_BY_TYPE[MATCH_EMBEDDING_SEMANTIC],
                explicit_score, embedding_similarity, outcome_score, lexical_score,
                fallback_mode=False,
            )
        if effective_embedding >= HYBRID_SEMANTIC_THRESHOLD and has_deterministic_support:
            combined = (
                w["explicit_indication"] * explicit_score
                + w["embedding_similarity"] * effective_embedding
                + w["outcome_mechanism"] * outcome_score
                + w["lexical_fallback"] * lexical_score
            )
            matched = tuple(dict.fromkeys(m2.matched_terms + m3.matched_terms))
            return HybridScore(
                round(min(0.85, combined), 4), MATCH_HYBRID_SEMANTIC, matched,
                f"Embedding similarity ({effective_embedding:.3f}) combined with deterministic "
                f"{deterministic.match_type} support; matched={', '.join(matched) or 'none'}",
                _HYBRID_CONFIDENCE_BY_TYPE[MATCH_HYBRID_SEMANTIC],
                explicit_score, embedding_similarity, outcome_score, lexical_score,
                fallback_mode=False,
            )

    # No embedding contribution (unavailable, below threshold, or did not
    # clear either gate) -- deterministic engine's own answer stands,
    # unchanged, with weights renormalized across the three components
    # that remain meaningful (fallback_mode=True whenever
    # embedding_similarity itself was None, i.e. the provider/RPC was
    # unavailable for this run, as opposed to merely scoring low).
    return HybridScore(
        deterministic.score, deterministic.match_type, deterministic.matched_terms,
        deterministic.reason, _HYBRID_CONFIDENCE_BY_TYPE.get(deterministic.match_type, deterministic.confidence),
        explicit_score, embedding_similarity, outcome_score, lexical_score,
        fallback_mode=embedding_similarity is None,
    )
