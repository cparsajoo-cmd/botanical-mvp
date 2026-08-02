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
