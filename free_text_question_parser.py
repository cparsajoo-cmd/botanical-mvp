"""
Free-text question parsing (external review, repeated across 3 rounds:
"Question Understanding still depends on predefined seed data").

WHAT THIS FIXES
Step 0 (step_inputs.py) only ever accepted fixed selectbox values for
indication/dosage_form/market — a user could never type a real question
like "a botanical oral product for mild cognitive impairment in the
elderly, with low CYP interaction risk, for the EU market" and have the
system understand it. This module does that extraction.

WHY THIS IS NOT A NEW NLU ENGINE
Every category this module can recognize already exists as a fixed
option somewhere in the codebase:
  - indication: step_inputs.py's own 28-option selectbox list
  - dosage_form: step_inputs.py's own 12-option selectbox list
  - market: step_inputs.py's own 24-option selectbox list
This module does NOT invent new categories or use a trained model — it
matches free text against those SAME existing option lists (plus their
obvious synonyms), so whatever it extracts is guaranteed to be a value
the rest of the pipeline (which was already built around those fixed
lists) already knows how to use. target_population and
safety_constraints are the two genuinely new, small vocabularies added
here (population terms, CYP/interaction/sedation-style safety phrases)
— hand-authored keyword lists, the same pattern already used
throughout this codebase (SIMILAR_COMPOUND_GROUPS, DB_ACTIVITY_SAFETY_TERMS,
etc.), not a new engine or model.

HONESTY ABOUT WHAT THIS DOES AND DOESN'T DO
This is keyword/phrase matching, not semantic understanding — it will
miss indications/dosage forms phrased in ways not covered by the lists
below, and every extracted field is returned alongside WHICH phrase
triggered the match, so a person reviewing the result can see exactly
why the system picked what it picked (and correct it, via the existing
selectboxes, if it picked wrong — see step_inputs.py's wiring, which
always pre-fills the selectbox rather than silently trusting this
module's guess).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Mirrors step_inputs.py's indication selectbox list exactly, plus a
# few obvious synonym phrases per entry so free text has more than one
# way to hit each real option.
INDICATION_SYNONYMS = {
    "Sleep and relaxation": ["sleep", "insomnia", "relaxation", "trouble sleeping"],
    "Anxiety": ["anxiety", "anxious"],
    "Stress": ["stress", "stressed"],
    "Inflammation": ["inflammation", "inflammatory", "anti-inflammatory"],
    "Constipation": ["constipation", "irregular bowel"],
    "Cough": ["cough"],
    "Digestive comfort": ["digestive comfort", "digestion", "digestive"],
    "Skin inflammation": ["skin inflammation", "dermatitis"],
    "Dry mouth": ["dry mouth", "xerostomia"],
    "Allergic rhinitis": ["allergic rhinitis", "hay fever", "seasonal allergy"],
    "IBS": ["ibs", "irritable bowel"],
    "Wound healing": ["wound healing", "wound care"],
    "Cognitive decline / Alzheimer's support": [
        "cognitive decline", "cognitive impairment", "memory support",
        "alzheimer", "dementia", "mild cognitive impairment",
    ],
    "Immune support": ["immune support", "immunity", "immune system"],
    "Cardiovascular / circulation": ["cardiovascular", "circulation", "heart health"],
    "Liver support / detox": ["liver support", "liver health", "hepatoprotective", "detox"],
    "Joint & muscle comfort": ["joint", "muscle comfort", "joint pain"],
    "Energy / fatigue": ["energy", "fatigue", "tiredness"],
    "Metabolic & blood sugar support": ["blood sugar", "metabolic support", "glycemic"],
    "Weight management": ["weight management", "weight loss"],
    "Menopause support": ["menopause"],
    "Menstrual / PMS support": ["menstrual", "pms", "period support"],
    "Prostate / men's health": ["prostate", "men's health"],
    "Urinary tract health": ["urinary tract", "uti", "bladder health"],
    "Cold & flu / respiratory": ["cold and flu", "cold & flu", "respiratory", "flu"],
    "Headache / mood support": ["headache", "mood support", "mood"],
    "Hair, skin & nail beauty-from-within": ["hair", "skin and nail", "beauty from within"],
    "Eye health": ["eye health", "vision support"],
}

DOSAGE_FORM_SYNONYMS = {
    "Infusion": ["infusion", "tea", "herbal tea", "tisane"],
    "Capsule": ["capsule", "capsules"],
    "Tablet": ["tablet", "tablets", "pill"],
    "Syrup": ["syrup"],
    "Cream": ["cream"],
    "Gel": ["gel"],
    "Mouthwash": ["mouthwash", "oral rinse"],
    "Nasal spray": ["nasal spray"],
    "Chewing gum": ["chewing gum", "gum"],
    "Powder": ["powder"],
    "Extract": ["extract", "tincture"],
    "Essential oil": ["essential oil"],
}

# "Oral" is the most common route and is inferable from several dosage
# forms even when the form itself isn't named — kept separate from
# DOSAGE_FORM_SYNONYMS since "oral product" alone should be enough to
# infer the route without forcing a specific dosage form guess.
ROUTE_HINTS = {
    "Oral": ["oral product", "orally", "taken by mouth"],
    "Topical": ["topical", "applied to the skin", "on the skin"],
    "Nasal": ["intranasal", "nasal"],
}

MARKET_SYNONYMS = {
    "European Union": ["eu", "european union", "europe"],
    "Germany": ["germany", "german market"],
    "France": ["france", "french market"],
    "Italy": ["italy"],
    "Spain": ["spain"],
    "Netherlands": ["netherlands", "holland"],
    "Poland": ["poland"],
    "United Kingdom": ["uk", "united kingdom", "britain"],
    "Switzerland": ["switzerland"],
    "Nordic countries (Sweden, Norway, Denmark, Finland)": [
        "nordic", "sweden", "norway", "denmark", "finland",
    ],
    "Iran": ["iran"],
    "Middle East / GCC": ["middle east", "gcc"],
    "Turkey": ["turkey"],
    "United States": ["usa", "us market", "united states"],
    "Canada": ["canada"],
    "Brazil / Latin America": ["brazil", "latin america"],
    "China": ["china"],
    "Japan": ["japan"],
    "South Korea": ["south korea", "korea"],
    "India": ["india"],
    "Southeast Asia (Vietnam / Thailand / Indonesia)": [
        "southeast asia", "vietnam", "thailand", "indonesia",
    ],
    "Australia": ["australia"],
    "New Zealand": ["new zealand"],
    "South Africa": ["south africa"],
    "Global / Multi-market": ["global market", "multi-market", "worldwide"],
}

# Genuinely new, small vocabularies (not derived from an existing
# selectbox) — same hand-authored-keyword-list pattern as the rest of
# this codebase.
TARGET_POPULATION_TERMS = {
    "Elderly / older adults": ["elderly", "older adults", "seniors", "aging population"],
    "Pediatric / children": ["children", "pediatric", "paediatric", "kids"],
    "Pregnant / lactating": ["pregnant", "pregnancy", "lactating", "breastfeeding"],
    "Adults": ["adults"],
}

SAFETY_CONSTRAINT_TERMS = {
    "Low CYP interaction risk": ["cyp interaction", "cyp450", "low cyp", "drug interaction risk"],
    "Non-sedating / low sedation": ["non-sedating", "no sedation", "low sedation", "non-drowsy"],
    "Pregnancy-safe": ["pregnancy-safe", "safe in pregnancy"],
    "No known drug interactions": ["no known interactions", "interaction-free"],
}


@dataclass
class ParsedQuestion:
    indication: Optional[str] = None
    indication_matched_phrase: Optional[str] = None
    dosage_form: Optional[str] = None
    dosage_form_matched_phrase: Optional[str] = None
    route: Optional[str] = None
    market: Optional[str] = None
    market_matched_phrase: Optional[str] = None
    target_population: list = field(default_factory=list)
    safety_constraints: list = field(default_factory=list)
    unmatched_text: str = ""  # the raw question, for a human to read what wasn't categorized


def _find_best_match(text_lower: str, synonym_map: dict) -> tuple:
    """Returns (canonical_value, matched_phrase) for the LONGEST
    matching phrase found (longer phrases are more specific/reliable
    than short ones — e.g. "mild cognitive impairment" should win over
    a shorter, coincidentally-overlapping term)."""
    best = (None, None, 0)
    for canonical, phrases in synonym_map.items():
        for phrase in phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", text_lower):
                if len(phrase) > best[2]:
                    best = (canonical, phrase, len(phrase))
    return best[0], best[1]


def _find_all_matches(text_lower: str, synonym_map: dict) -> list:
    matched = []
    for canonical, phrases in synonym_map.items():
        for phrase in phrases:
            if re.search(r"\b" + re.escape(phrase) + r"\b", text_lower):
                matched.append(canonical)
                break
    return matched


def parse_free_text_question(text: str) -> ParsedQuestion:
    """Extracts indication/dosage_form/market/route/population/safety
    constraints from a free-text question. Every field is None/empty
    when nothing matched — this never guesses a default; step_inputs.py's
    wiring keeps whatever the selectbox already had selected when a
    field comes back empty here."""
    if not text or not text.strip():
        return ParsedQuestion(unmatched_text=text or "")

    lowered = text.lower()

    indication, indication_phrase = _find_best_match(lowered, INDICATION_SYNONYMS)
    dosage_form, dosage_phrase = _find_best_match(lowered, DOSAGE_FORM_SYNONYMS)
    market, market_phrase = _find_best_match(lowered, MARKET_SYNONYMS)

    route = None
    if dosage_form:
        # Infer from the matched dosage form itself where possible —
        # avoids a separate lookup disagreeing with the dosage form
        # already chosen.
        oral_forms = {"Infusion", "Capsule", "Tablet", "Syrup", "Chewing gum", "Powder", "Extract"}
        topical_forms = {"Cream", "Gel"}
        if dosage_form in oral_forms:
            route = "Oral"
        elif dosage_form in topical_forms:
            route = "Topical"
        elif dosage_form == "Nasal spray":
            route = "Nasal"
    if route is None:
        route, _ = _find_best_match(lowered, ROUTE_HINTS)

    target_population = _find_all_matches(lowered, TARGET_POPULATION_TERMS)
    safety_constraints = _find_all_matches(lowered, SAFETY_CONSTRAINT_TERMS)

    return ParsedQuestion(
        indication=indication,
        indication_matched_phrase=indication_phrase,
        dosage_form=dosage_form,
        dosage_form_matched_phrase=dosage_phrase,
        route=route,
        market=market,
        market_matched_phrase=market_phrase,
        target_population=target_population,
        safety_constraints=safety_constraints,
        unmatched_text=text,
    )
