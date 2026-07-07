"""
Disease expansion helper
=========================

Given a NEW disease/problem name (not yet in seed_data.TARGET_DISEASES),
suggests candidate targets, compounds and plants for a human to review and
approve — instead of hand-writing TARGET_DISEASES/COMPOUND_TARGETS entries
from scratch.

It never writes to seed_data.py automatically. It only proposes; a human
confirms, then generate_seed_data_snippet() prints ready-to-paste code.
"""

import re
import requests
import pandas as pd

from seed_data import COMPOUND_TARGETS, PLANT_COMPOUNDS, TARGET_DISEASES

_TARGET_PATTERNS = [
    r"\b[A-Za-z0-9\-]+ receptor\b",
    r"\b[A-Za-z0-9\-]+ pathway\b",
    r"\b[A-Za-z0-9\-]+ channel\b",
    r"\bNF-[kK]B\b",
    r"\bCOX-\d\b",
    r"\bTRP[A-Z0-9]*\b",
    r"\b[A-Za-z]+ axis\b",
    r"\b[A-Za-z]+ system\b",
]

ALL_KNOWN_TARGETS = sorted({t for targets in COMPOUND_TARGETS.values() for t in targets})

# Light synonym groups so everyday problem names ("memory loss", "joint pain")
# still connect to the medical category words already used in TARGET_DISEASES
# ("cognitive", "anti-inflammatory"). Not exhaustive by design — this is a
# cheap bridge, the live literature search is the real discovery mechanism.
_SYNONYM_GROUPS = [
    {"alzheimer", "alzheimer's", "dementia", "memory", "cognitive", "cognition"},
    {"joint", "arthritis", "arthritic", "inflammation", "inflammatory", "anti-inflammatory"},
    {"skin", "dermatitis", "eczema", "psoriasis"},
    {"stomach", "gut", "digestive", "digestion", "ibs", "bowel"},
    {"immune", "immunity", "cold", "flu", "infection"},
    {"liver", "hepatic", "hepatoprotective"},
    {"heart", "cardiovascular", "cardiac", "circulation"},
    {"mouth", "oral", "salivary"},
    {"throat", "cough", "respiratory", "expectorant"},
    {"nose", "rhinitis", "allergy", "allergic", "histamine"},
    {"sleep", "insomnia", "relaxation"},
    {"stress", "anxiety", "cortisol"},
    {"metabolic", "diabetes", "blood sugar", "glucose", "insulin"},
]


def _expand_with_synonyms(words):
    expanded = set(words)
    for group in _SYNONYM_GROUPS:
        if words & group:
            expanded |= group
    return expanded


def _norm(x):
    return re.sub(r"\s+", " ", str(x or "").strip().lower())


def _extract_plant_name(text):
    candidates = re.findall(r"\b[A-Z][a-z]+ [a-z]+(?:\s[a-z]+)?\b", text)
    bad = {"The aim", "The study", "The results", "This study", "United States", "European Union"}
    for c in candidates:
        if c not in bad:
            return c
    return ""


def reuse_from_known_kb(disease_name):
    """Offline, zero-risk: which already-known targets/compounds look
    relevant to `disease_name`, either by direct word overlap with target
    names, or via an existing TARGET_DISEASES category that already covers
    a related problem."""
    base_words = {w for w in _norm(disease_name).split() if len(w) > 3}
    words = _expand_with_synonyms(base_words)

    hits = []

    for target in ALL_KNOWN_TARGETS:
        if words & set(_norm(target).split()):
            compounds = [c for c, t in COMPOUND_TARGETS.items() if target in t]
            hits.append({
                "Target": target,
                "Matched_via": "Direct target-name overlap",
                "Compounds_already_in_KB": "; ".join(compounds),
            })

    for existing_disease, targets in TARGET_DISEASES.items():
        disease_words = set(_norm(existing_disease).split())
        if words & disease_words:
            for target, relevance in targets.items():
                compounds = [c for c, t in COMPOUND_TARGETS.items() if target in t]
                hits.append({
                    "Target": target,
                    "Matched_via": f"Related existing category: '{existing_disease}' ({relevance})",
                    "Compounds_already_in_KB": "; ".join(compounds),
                })

    df = pd.DataFrame(hits)
    if not df.empty:
        df = df.drop_duplicates(subset=["Target", "Matched_via"])
    return df


def literature_candidates(disease_name, max_results=8):
    """Live, best-effort: candidate NEW targets + plants from Europe PMC.
    Everything returned here is UNVERIFIED and must be reviewed."""
    query = f'"{disease_name}" medicinal plant mechanism target review'
    try:
        r = requests.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": query, "format": "json", "pageSize": max_results},
            timeout=20,
        )
        r.raise_for_status()
        items = r.json().get("resultList", {}).get("result", [])
    except Exception:
        return pd.DataFrame(columns=["Candidate_Target", "Candidate_Plant", "Source_Title", "Source_URL"])

    rows = []
    for item in items:
        title = str(item.get("title", ""))
        abstract = str(item.get("abstractText", ""))
        text = f"{title}. {abstract}"
        pmid = str(item.get("pmid", ""))
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

        found_targets = set()
        for pattern in _TARGET_PATTERNS:
            found_targets.update(m.group(0) for m in re.finditer(pattern, text, flags=re.IGNORECASE))

        plant = _extract_plant_name(text)

        for target in found_targets:
            already_known = any(_norm(target) == _norm(t) for t in ALL_KNOWN_TARGETS)
            rows.append({
                "Candidate_Target": target,
                "Already_In_KB": "Yes — reuse this exact name" if already_known else "No — NEW, needs review",
                "Candidate_Plant": plant or "Not extracted",
                "Source_Title": title,
                "Source_URL": url,
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["Candidate_Target", "Candidate_Plant", "Source_Title"])
    return df


def suggest_indication_expansion(disease_name, use_live_search=True, max_results=8):
    """
    Returns (reuse_df, literature_df) for a human to review before adding
    `disease_name` to seed_data.TARGET_DISEASES.
    """
    reuse_df = reuse_from_known_kb(disease_name)
    lit_df = literature_candidates(disease_name, max_results) if use_live_search else pd.DataFrame()
    return reuse_df, lit_df


def generate_seed_data_snippet(disease_name, approved_targets: dict):
    """
    approved_targets: dict like {"NF-kB": "established", "COX-2": "probable"}
    -- i.e. exactly what the human confirmed after reviewing the suggestions.

    Prints a ready-to-paste block for seed_data.TARGET_DISEASES.
    """
    lines = [f'    "{disease_name}": {{']
    for target, relevance in approved_targets.items():
        lines.append(f'        "{target}": "{relevance}",')
    lines.append("    },")
    snippet = "\n".join(lines)
    print(snippet)
    return snippet
