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
    "synthetic drugs", "conventional drugs", "current treatments", "current therapeutic regimen",
    "therapeutic regimen", "conventional therapy", "standard treatment",
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

# Terms indicating that a hypoglyc* mention describes intended pharmacological
# activity rather than an adverse event.  These are deliberately evaluated only
# for hypoglycaemia-like tokens; they do not suppress genuine adverse-event terms.
_HYPOGLYCEMIC_EFFICACY_CONTEXT = (
    "hypoglycemic activity", "hypoglycaemic activity",
    "hypoglycemic effect", "hypoglycaemic effect",
    "hypoglycemic properties", "hypoglycaemic properties",
    "hypoglycemic potential", "hypoglycaemic potential",
    "glucose-lowering activity", "antidiabetic activity",
)
# Many abstracts coordinate several efficacy adjectives before one shared noun,
# e.g. "hypoglycemic, antioxidant and anti-inflammatory properties".  Exact
# phrase matching misses that syntax, so these patterns capture intended
# pharmacological activity without suppressing true hypoglycaemia events.
_HYPOGLYCEMIC_EFFICACY_PATTERNS = (
    r"\bhypoglyc(?:emic|aemic)\b.{0,80}\b(?:activit(?:y|ies)|effect(?:s)?|propert(?:y|ies)|potential)\b",
    r"\b(?:glucose[- ]lowering|antidiabetic)\b.{0,80}\b(?:activit(?:y|ies)|effect(?:s)?|propert(?:y|ies)|potential)\b",
)
_HYPOGLYCEMIA_EVENT_CONTEXT = (
    "risk", "event", "events", "episode", "episodes", "symptom", "symptoms",
    "occurred", "reported", "developed", "adverse", "severe", "clinically significant",
)
_INTERVENTION_REFERENCES = (
    "the extract", "this extract", "the preparation", "this preparation",
    "the supplement", "this supplement", "the intervention", "the treated group",
    "participants receiving", "patients receiving", "subjects receiving",
    "interaction with", "interacts with", "concomitant use", "co-administration",
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


def _has_plant_anchor(fragment: str, previous_fragment: str, plant_name: str, structurally_linked: bool) -> bool:
    """Require a local plant/intervention anchor, never a document-wide one.

    A plant name in an abstract's opening sentence must not license every later
    sentence as plant-attributed.  Pronoun/intervention anchoring is accepted
    only when the immediately preceding sentence names the target plant and the
    current sentence explicitly refers to that intervention.
    """
    tokens = _plant_tokens(plant_name)
    frag_n = _norm(fragment)
    prev_n = _norm(previous_fragment)
    if tokens:
        full = tokens[0]
        if full in frag_n:
            return True
        if len(tokens) >= 3 and tokens[1] in frag_n and tokens[2] in frag_n:
            return True
    elif structurally_linked:
        return True

    if structurally_linked and tokens and tokens[0] in prev_n:
        if any(ref in frag_n for ref in _INTERVENTION_REFERENCES):
            return True
        # Abstracts commonly name the intervention in one sentence and report
        # adverse events in the immediately following sentence. Accept that
        # narrow pattern only when the current sentence uses explicit
        # observation/reporting language—not generic discussion of therapy.
        causal_report_terms = (
            "were reported", "was reported", "occurred", "were observed",
            "was observed", "was associated", "were associated",
            "participants experienced", "patients experienced",
        )
        if any(term in frag_n for term in causal_report_terms):
            return True
    return False


def _is_noise(fragment: str) -> bool:
    n = _norm(fragment)
    return any(term in n for term in _COMPARATOR_NOISE) or any(term in n for term in _LOW_QUALITY_SOURCE)


def _is_protective_or_negated(fragment: str) -> bool:
    n = _norm(fragment)
    return any(term in n for term in _PROTECTIVE_OR_NEGATED)


def _is_adverse_statement(fragment: str) -> bool:
    """Distinguish adverse outcomes from intended pharmacological activity."""
    n = _norm(fragment)
    if not _matches_any_basic(fragment, _ADVERSE_PATTERNS):
        return False
    if "hypoglyc" in n:
        efficacy_context = (
            any(term in n for term in _HYPOGLYCEMIC_EFFICACY_CONTEXT)
            or _matches_any_basic(fragment, _HYPOGLYCEMIC_EFFICACY_PATTERNS)
        )
        event_context = any(term in n for term in _HYPOGLYCEMIA_EVENT_CONTEXT)
        if efficacy_context and not event_context:
            return False
    return True


def _matches_any_basic(fragment: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, fragment, flags=re.I) for pattern in patterns)


def _matches_any(fragment: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, fragment, flags=re.I) for pattern in patterns)


def _dedupe(values: Iterable[str], limit: int = 4) -> list[str]:
    seen: set[str] = set(); out: list[str] = []
    for value in values:
        key = _norm(value)
        if key and key not in seen:
            seen.add(key); out.append(value.strip())
    return out[:limit]


def extract_structured_safety_interactions(
    safety_value: object,
    interaction_value: object,
    plant_name: str = "",
) -> dict:
    """Interpret already-structured fields without reapplying raw-text rules.

    The field names themselves provide the semantic relationship.  Consequently
    a structured interaction value such as ``anticoagulants`` is retained even
    without prose saying "interacts with".  Safety values still undergo a small
    semantic guard so efficacy phrases such as "hypoglycemic activity" cannot
    become adverse-event flags.
    """
    def items(value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, dict):
            return [f"{k}: {v}" if str(v).strip() else str(k) for k, v in value.items()]
        if isinstance(value, (list, tuple, set)):
            return [str(v).strip() for v in value if str(v).strip()]
        text = str(value).strip()
        if not text or _norm(text) in _MISSING:
            return []
        return [x.strip() for x in re.split(r";|\n", text) if x.strip()]

    adverse: list[str] = []
    reassurance: list[str] = []
    for value in items(safety_value):
        if _is_noise(value) or _is_protective_or_negated(value):
            continue
        if _matches_any(value, _REASSURANCE_PATTERNS):
            reassurance.append(value)
        elif _is_adverse_statement(value):
            adverse.append(value)
        else:
            # Structured adverse-event fields may contain concise coded values
            # (e.g. "bleeding: reported concern") that do not form a sentence.
            n = _norm(value)
            coded_terms = ("bleeding", "hemorrhage", "hepatotoxic", "liver injury",
                           "nausea", "vomiting", "diarrhea", "diarrhoea", "rash",
                           "anaphylaxis", "allergic reaction", "toxicity")
            if any(term in n for term in coded_terms):
                adverse.append(value)

    interactions: list[str] = []
    for value in items(interaction_value):
        n = _norm(value)
        if not n or n in _MISSING or _is_noise(value):
            continue
        # Structured interaction fields are already relational. Preserve drug
        # classes/names and explicit interaction statements, but not generic
        # efficacy or safety prose accidentally placed in the field.
        if any(term in n for term in _DRUG_TERMS) or _matches_any(value, _INTERACTION_RELATION_PATTERNS):
            interactions.append(value)

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
    for i, fragment in enumerate(fragments):
        previous_fragment = " ".join(fragments[max(0, i - 2):i])
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
        anchored = _has_plant_anchor(fragment, previous_fragment, plant_name, structurally_linked)
        if not anchored:
            continue

        if _matches_any(fragment, _REASSURANCE_PATTERNS):
            reassurance.append(fragment)
        elif _is_adverse_statement(fragment) and not _is_protective_or_negated(fragment):
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
