"""Conservative, plant-attributed safety and interaction extraction.

This module is intentionally stricter than keyword matching.  A sentence is
accepted only when it is attributable to the plant/intervention represented by
the evidence record and describes an actual adverse event, reassurance, or an
explicit drug-interaction relationship.  General statements about disease,
comparators, conventional medicines, protective effects, promotional copy, and
retracted material are rejected.
"""
from __future__ import annotations

import re
from typing import Iterable

_MISSING = {"", "none", "nan", "null", "{}", "[]", "unknown", "not assessed"}

_ADVERSE_PATTERNS = (
    r"\badverse (?:event|events|reaction|reactions|effect|effects)\b",
    r"\bside effect(?:s)?\b", r"\bhepatotox(?:ic|icity)\b",
    r"\bliver injur(?:y|ies)\b", r"\bbleeding\b", r"\bhemorrhag(?:e|ic|y)\b",
    r"\bhypoglyc(?:emia|aemia|emic|aemic)\b", r"\banaphyl(?:axis|actic)\b",
    r"\ballergic reaction(?:s)?\b", r"\bnausea\b", r"\bvomiting\b",
    r"\bdiarrh(?:ea|eas|oea)\b", r"\brash(?:es)?\b", r"\btoxicit(?:y|ies)\b",
    r"\bcontraindicat(?:ed|ion|ions)\b",
)
_REASSURANCE_PATTERNS = (
    r"\bwell tolerated\b", r"\bno serious adverse (?:event|events|reaction|reactions)\b",
    r"\bno severe adverse (?:event|events|reaction|reactions)\b",
    r"\bno treatment-related adverse (?:event|events)\b",
    r"\bno clinically significant adverse (?:event|events|effect|effects)\b",
    r"\bdid not cause (?:toxicity|adverse effects?)\b",
)
_INTERACTION_RELATION_PATTERNS = (
    r"\binteract(?:s|ed|ion|ions)? with\b", r"\bdrug[- ]interaction(?:s)?\b",
    r"\bconcomitant (?:use|administration)\b", r"\bco[- ]administr(?:ation|ed)\b",
    r"\bavoid (?:use )?with\b", r"\bcombined with\b", r"\bwhen taken with\b",
    r"\bmay (?:increase|decrease|potentiate|reduce) .{0,50}\b(?:effect|risk|level|exposure)\b",
    r"\binteraction(?:s)?\b",
)
_DRUG_TERMS = (
    "warfarin", "anticoagulant", "antiplatelet", "antidiabetic", "hypoglycemic agent",
    "hypoglycaemic agent", "insulin", "cyp3a4", "cyp2c9", "cytochrome p450",
    "p-glycoprotein", "p glycoprotein", "digoxin", "cyclosporine", "tacrolimus",
)
_COMPARATOR_NOISE = (
    "synthetic drugs", "conventional drugs", "current treatments", "standard treatment",
    "standard therapy", "existing medications", "other medications", "control drug",
    "comparator", "placebo caused", "disease itself", "patients with diabetes often",
)
_PROTECTIVE_OR_NEGATED = (
    "protects against", "protected against", "prevented liver injury", "reduced liver injury",
    "attenuated toxicity", "reduced toxicity", "anti-toxic", "not toxic", "non-toxic",
    "without toxicity", "did not increase toxicity", "no evidence of toxicity",
)
_LOW_QUALITY_SOURCE = (
    "retracted", "retraction", "advertisement", "sponsored content", "buy now",
    "shop now", "customer review", "affiliate", "promotional material",
)
_INTERVENTION_WORDS = (
    "extract", "preparation", "supplement", "intervention", "treatment group",
    "treated group", "administration", "administered", "capsule", "infusion", "tea",
)


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _split(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?;])\s+|\n+", text) if x.strip()]


def _plant_tokens(plant_name: str) -> tuple[str, ...]:
    words = re.findall(r"[a-zA-Z]+", _norm(plant_name))
    if len(words) >= 2:
        return (" ".join(words[:2]), words[0], words[1])
    return tuple(words)


def _has_plant_anchor(fragment: str, context: str, plant_name: str, structurally_linked: bool) -> bool:
    tokens = _plant_tokens(plant_name)
    combined = _norm(f"{context} {fragment}")
    if tokens:
        full = tokens[0]
        if full in combined:
            return True
        if len(tokens) >= 3 and tokens[1] in combined and tokens[2] in combined:
            return True
    elif structurally_linked:
        # Backward-compatible use for already plant-scoped records where the
        # caller has no name available. Production Step 5 always supplies it.
        return True
    # A structurally linked evidence row may use "the extract" rather than
    # repeating the botanical name in every sentence.  Accept only when the
    # source context names the plant and the sentence names the intervention.
    if structurally_linked and tokens and tokens[0] in _norm(context):
        return any(word in _norm(fragment) for word in _INTERVENTION_WORDS)
    return False


def _is_noise(fragment: str) -> bool:
    n = _norm(fragment)
    return any(term in n for term in _COMPARATOR_NOISE) or any(term in n for term in _LOW_QUALITY_SOURCE)


def _is_protective_or_negated(fragment: str) -> bool:
    n = _norm(fragment)
    return any(term in n for term in _PROTECTIVE_OR_NEGATED)


def _matches_any(fragment: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, fragment, flags=re.I) for pattern in patterns)


def _dedupe(values: Iterable[str], limit: int = 4) -> list[str]:
    seen: set[str] = set(); out: list[str] = []
    for value in values:
        key = _norm(value)
        if key and key not in seen:
            seen.add(key); out.append(value.strip())
    return out[:limit]


def extract_attributed_safety_interactions(
    text: object,
    plant_name: str = "",
    *,
    structurally_linked: bool = False,
) -> dict:
    """Return conservative adverse/reassurance/interaction statements.

    The return keys are ``adverse_events``, ``safety_reassurance``,
    ``interactions`` and ``safety_data_status``.  Empty findings never imply
    safety; the status is ``not_assessed`` unless a source carries an accepted
    statement.
    """
    raw = str(text or "").strip()
    if not raw or _norm(raw) in _MISSING:
        return {"adverse_events": [], "safety_reassurance": [], "interactions": [], "safety_data_status": "not_assessed"}
    if any(term in _norm(raw[:1000]) for term in _LOW_QUALITY_SOURCE):
        return {"adverse_events": [], "safety_reassurance": [], "interactions": [], "safety_data_status": "source_excluded"}

    fragments = _split(raw)
    adverse: list[str] = []; reassurance: list[str] = []; interactions: list[str] = []
    source_intro = " ".join(fragments[:2])[:800]
    for i, fragment in enumerate(fragments):
        context = " ".join(fragments[max(0, i-1):i+1])
        if _is_noise(fragment):
            continue
        # Reject a sentence explicitly naming a different botanical unless it
        # also names the target botanical. This prevents multi-plant reviews
        # from transferring another species' adverse events to the candidate.
        non_botanical_starters = {
            "the", "this", "that", "mild", "severe", "interaction", "concomitant",
            "adverse", "current", "standard", "synthetic", "clinical", "significant",
            "no", "well", "patients", "treatment", "extract",
        }
        binomials = {
            _norm(" ".join(m))
            for m in re.findall(r"\b([A-Z][a-z]+)\s+([a-z]{3,})\b", fragment)
            if m[0].lower() not in non_botanical_starters
        }
        target_full = _plant_tokens(plant_name)[0] if _plant_tokens(plant_name) else ""
        if binomials and target_full and target_full not in binomials:
            continue
        anchored = _has_plant_anchor(fragment, f"{source_intro} {context}", plant_name, structurally_linked)
        if not anchored:
            continue

        if _matches_any(fragment, _REASSURANCE_PATTERNS):
            reassurance.append(fragment)
        elif _matches_any(fragment, _ADVERSE_PATTERNS) and not _is_protective_or_negated(fragment):
            adverse.append(fragment)

        n = _norm(fragment)
        has_relation = _matches_any(fragment, _INTERACTION_RELATION_PATTERNS)
        has_drug = any(term in n for term in _DRUG_TERMS)
        # A drug name alone is not an interaction. Require an explicit relation
        # and a drug/drug-class object in the same attributed sentence.
        if has_relation and has_drug:
            interactions.append(fragment)

    adverse = _dedupe(adverse)
    reassurance = _dedupe(reassurance)
    interactions = _dedupe(interactions)
    if adverse:
        status = "adverse_signal_present"
    elif reassurance:
        status = "reassurance_reported"
    elif interactions:
        status = "interaction_signal_present"
    else:
        status = "not_assessed"
    return {
        "adverse_events": adverse,
        "safety_reassurance": reassurance,
        "interactions": interactions,
        "safety_data_status": status,
    }
