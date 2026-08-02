"""Shared indication semantics for evidence-centric Step 5 discovery.

This module is the single source of truth used by both raw candidate discovery
and plant-level shortlisting.  Terms are intentionally indication-specific:
generic antioxidant/anti-inflammatory language is not enough to establish a
direct indication match unless the selected indication itself is inflammation.
"""
from __future__ import annotations

import re
from typing import Iterable


def normalize_indication_text(value: object) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9αβγ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Keys mirror step_inputs.INDICATIONS.  ``aliases`` resolve free-text variants;
# ``direct`` identifies disease/outcome evidence; ``mechanistic`` is supportive
# only and never substitutes for direct efficacy evidence.
INDICATION_SEMANTICS: dict[str, dict[str, tuple[str, ...]]] = {
    "Sleep and relaxation": {
        "aliases": ("sleep", "insomnia", "relaxation"),
        "direct": ("insomnia", "sleep quality", "sleep latency", "sleep onset", "sleep duration", "sleep disturbance", "difficulty falling asleep"),
        "mechanistic": ("gaba", "gabaergic", "gabaa receptor", "melatonin", "benzodiazepine receptor", "sedative", "hypnotic", "adenosine receptor"),
    },
    "Anxiety": {
        "aliases": ("anxiety", "anxious", "anxiolytic"),
        "direct": ("anxiety", "anxious symptoms", "anxiolytic", "generalized anxiety", "state anxiety", "trait anxiety"),
        "mechanistic": ("gaba", "gabaergic", "5 ht1a", "serotonergic", "benzodiazepine receptor", "cortisol"),
    },
    "Stress": {
        "aliases": ("stress", "psychological stress", "mental stress"),
        "direct": ("psychological stress", "mental stress", "perceived stress", "stress score", "stress symptoms", "burnout"),
        "mechanistic": ("cortisol", "hpa axis", "adaptogen", "stress response"),
    },
    "Inflammation": {
        "aliases": ("inflammation", "inflammatory"),
        "direct": ("inflammation", "inflammatory condition", "inflammatory markers", "crp", "c reactive protein"),
        "mechanistic": ("nf kb", "cox 2", "tnf alpha", "il 6", "prostaglandin", "lipoxygenase"),
    },
    "Constipation": {
        "aliases": ("constipation", "irregular bowel", "laxative"),
        "direct": ("constipation", "bowel movement", "stool frequency", "stool consistency", "laxative", "colonic transit"),
        "mechanistic": ("intestinal motility", "colonic motility", "peristalsis", "bulk forming", "osmotic laxative"),
    },
    "Cough": {
        "aliases": ("cough", "antitussive"),
        "direct": ("cough", "antitussive", "cough frequency", "cough severity", "cough score", "productive cough", "dry cough", "acute cough", "chronic cough"),
        "mechanistic": ("expectorant", "demulcent", "mucolytic", "secretolytic", "bronchomucolytic", "bronchomucotropic", "bronchorelaxant", "bronchodilator", "tracheorelaxant", "airway smooth muscle", "mucus clearance"),
    },
    "Digestive comfort": {
        "aliases": ("digestive comfort", "digestion", "dyspepsia"),
        "direct": ("dyspepsia", "indigestion", "digestive discomfort", "abdominal discomfort", "bloating", "flatulence", "gastric emptying"),
        "mechanistic": ("carminative", "gastroprotective", "antispasmodic", "gastric motility", "bile secretion"),
    },
    "Skin inflammation": {
        "aliases": ("skin inflammation", "dermatitis", "eczema"),
        "direct": ("dermatitis", "eczema", "skin inflammation", "erythema", "pruritus", "atopic dermatitis"),
        "mechanistic": ("skin barrier", "mast cell", "histamine", "keratinocyte", "topical anti inflammatory"),
    },
    "Dry mouth": {
        "aliases": ("dry mouth", "xerostomia"),
        "direct": ("xerostomia", "dry mouth", "salivary flow", "saliva production"),
        "mechanistic": ("sialogogue", "salivary secretion", "muscarinic receptor"),
    },
    "Allergic rhinitis": {
        "aliases": ("allergic rhinitis", "hay fever"),
        "direct": ("allergic rhinitis", "hay fever", "nasal symptoms", "rhinorrhea", "nasal congestion", "sneezing"),
        "mechanistic": ("antihistamine", "histamine", "mast cell stabilizer", "ige", "leukotriene"),
    },
    "IBS": {
        "aliases": ("ibs", "irritable bowel"),
        "direct": ("irritable bowel syndrome", "ibs", "abdominal pain", "ibs symptom severity", "bowel habit"),
        "mechanistic": ("visceral hypersensitivity", "gut motility", "intestinal spasm", "gut brain axis", "microbiota"),
    },
    "Wound healing": {
        "aliases": ("wound healing", "wound care"),
        "direct": ("wound healing", "wound closure", "re epithelialization", "ulcer healing", "burn healing"),
        "mechanistic": ("collagen synthesis", "fibroblast", "angiogenesis", "granulation tissue", "matrix metalloproteinase"),
    },
    "Cognitive decline / Alzheimer's support": {
        "aliases": ("cognitive decline", "cognitive impairment", "alzheimer", "dementia", "memory support"),
        "direct": ("alzheimer disease", "alzheimer s disease", "dementia", "cognitive decline", "mild cognitive impairment", "memory impairment", "cognitive function"),
        "mechanistic": ("acetylcholinesterase", "amyloid beta", "tau protein", "neuroinflammation", "cholinergic", "bdnf", "neuroprotective"),
    },
    "Immune support": {
        "aliases": ("immune support", "immunity", "immune system"),
        "direct": ("immune function", "immune response", "infection incidence", "infection duration", "immunodeficiency"),
        "mechanistic": ("immunomodulator", "immunostimulant", "natural killer cell", "cytokine", "interferon"),
    },
    "Cardiovascular / circulation": {
        "aliases": ("cardiovascular", "circulation", "heart health"),
        "direct": ("cardiovascular", "blood pressure", "hypertension", "circulation", "peripheral arterial", "endothelial function", "blood flow"),
        "mechanistic": ("vasodilator", "ace inhibitor", "platelet aggregation", "endothelial nitric oxide", "lipid lowering"),
    },
    "Liver support / detox": {
        "aliases": ("liver support", "liver health", "hepatoprotective", "detox"),
        "direct": ("liver injury", "hepatic injury", "liver enzymes", "alt", "ast", "fatty liver", "hepatitis"),
        "mechanistic": ("hepatoprotective", "glutathione", "nrf2", "bile flow", "antifibrotic"),
    },
    "Joint & muscle comfort": {
        "aliases": ("joint", "muscle comfort", "joint pain"),
        "direct": ("joint pain", "osteoarthritis", "rheumatoid arthritis", "muscle pain", "myalgia", "stiffness"),
        "mechanistic": ("cox 2", "prostaglandin", "cartilage", "matrix metalloproteinase", "analgesic"),
    },
    "Energy / fatigue": {
        "aliases": ("energy", "fatigue", "tiredness"),
        "direct": ("fatigue", "tiredness", "vitality", "energy level", "physical performance", "mental fatigue"),
        "mechanistic": ("mitochondrial", "atp", "adaptogen", "oxygen utilization", "cortisol"),
    },
    "Metabolic & blood sugar support": {
        "aliases": ("blood sugar", "metabolic", "glycemic", "diabetes", "insulin resistance"),
        "direct": ("type 2 diabetes", "diabetes mellitus", "diabetic", "hyperglycemia", "hyperglycaemia", "blood glucose", "fasting glucose", "postprandial glucose", "hba1c", "glycemic control", "glycaemic control", "insulin resistance", "insulin sensitivity"),
        "mechanistic": ("ampk", "glut4", "ppar", "alpha glucosidase", "α glucosidase", "alpha amylase", "dpp 4", "insulin secretion", "insulin sensitivity", "glucose uptake", "hepatic gluconeogenesis"),
    },
    "Weight management": {
        "aliases": ("weight management", "weight loss", "obesity"),
        "direct": ("weight loss", "body weight", "body mass index", "bmi", "waist circumference", "obesity", "adiposity"),
        "mechanistic": ("lipolysis", "adipogenesis", "thermogenesis", "appetite suppression", "satiety", "ampk"),
    },
    "Menopause support": {
        "aliases": ("menopause", "menopausal"),
        "direct": ("menopause", "menopausal symptoms", "hot flashes", "hot flushes", "vasomotor symptoms", "night sweats"),
        "mechanistic": ("phytoestrogen", "estrogen receptor", "serm", "serotonin"),
    },
    "Menstrual / PMS support": {
        "aliases": ("menstrual", "pms", "premenstrual"),
        "direct": ("premenstrual syndrome", "pms", "dysmenorrhea", "menstrual pain", "menstrual symptoms"),
        "mechanistic": ("uterine spasm", "prostaglandin", "antispasmodic", "hormonal modulation"),
    },
    "Prostate / men's health": {
        "aliases": ("prostate", "men s health", "bph"),
        "direct": ("benign prostatic hyperplasia", "bph", "lower urinary tract symptoms", "prostate symptoms", "ipss"),
        "mechanistic": ("5 alpha reductase", "androgen receptor", "dihydrotestosterone", "prostatic inflammation"),
    },
    "Urinary tract health": {
        "aliases": ("urinary tract", "uti", "bladder health"),
        "direct": ("urinary tract infection", "uti", "cystitis", "dysuria", "recurrent urinary infection"),
        "mechanistic": ("antiadhesive", "urothelial", "urinary antiseptic", "diuretic", "escherichia coli adhesion"),
    },
    "Cold & flu / respiratory": {
        "aliases": ("cold and flu", "cold flu", "respiratory", "flu", "common cold"),
        "direct": ("common cold", "influenza", "flu", "upper respiratory tract infection", "respiratory infection", "bronchitis", "pharyngitis", "sore throat", "cold symptoms"),
        "mechanistic": ("antiviral", "antiflu", "decongestant", "expectorant", "mucolytic", "secretolytic", "bronchodilator", "immunostimulant"),
    },
    "Headache / mood support": {
        "aliases": ("headache", "mood support", "mood", "depression"),
        "direct": ("headache", "migraine", "depressive symptoms", "depression", "mood score", "mood disturbance"),
        "mechanistic": ("serotonin", "5 ht", "monoamine oxidase", "cgrp", "vasomodulation"),
    },
    "Hair, skin & nail beauty-from-within": {
        "aliases": ("hair skin nail", "beauty from within", "skin aging", "photoaging"),
        "direct": ("skin aging", "skin ageing", "photoaging", "wrinkle", "skin elasticity", "hair growth", "hair loss", "nail strength"),
        "mechanistic": ("collagen synthesis", "elastin", "mmp 1", "fibroblast", "keratin", "antioxidant"),
    },
    "Eye health": {
        "aliases": ("eye health", "vision", "ocular"),
        "direct": ("eye health", "visual function", "vision", "glaucoma", "cataract", "macular degeneration", "diabetic retinopathy", "dry eye"),
        "mechanistic": ("retinal", "ocular blood flow", "rhodopsin", "macular pigment", "antioxidant retina"),
    },
}


def resolve_indication_semantics(indication: str) -> dict[str, tuple[str, ...]] | None:
    """Resolve a canonical or free-text indication to one semantic family."""
    query = normalize_indication_text(indication)
    if not query:
        return None

    # Exact canonical match is authoritative and avoids collisions such as
    # Skin inflammation vs general Inflammation.
    for canonical, family in INDICATION_SEMANTICS.items():
        if normalize_indication_text(canonical) == query:
            return family

    best = None
    best_score = 0
    for canonical, family in INDICATION_SEMANTICS.items():
        candidates: Iterable[str] = (canonical, *family.get("aliases", ()))
        score = 0
        for phrase in candidates:
            norm = normalize_indication_text(phrase)
            if norm and (norm in query or query in norm):
                score = max(score, len(norm.split()))
        if score > best_score:
            best, best_score = family, score
    return best


def indication_terms(indication: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    family = resolve_indication_semantics(indication)
    if family:
        return family["direct"], family["mechanistic"]
    query = normalize_indication_text(indication)
    tokens = tuple(t for t in query.split() if len(t) >= 4 and t not in {"support", "comfort", "health"})
    return tokens, ()
