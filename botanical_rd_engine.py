"""
BotanicalRDCandidateEngine
===========================

Single, central decision-support engine for the platform.

Replaces (merges the logic of):
    - global_candidate_ranking_engine.py      (ranking)
    - market_intelligence_engine.py           (market)
    - white_space_discovery_engine.py         (white-space)
    - knowledge_extraction_engine.py          (knowledge extraction)
    - disease_target_engine.py                (target discovery)
    - mechanism_discovery_engine.py           (mechanism discovery)
    - target_compound_plant_engine.py         (target-compound-plant discovery)
    - target_compound_engine.py / compound_target_engine.py
    - botanical_substitution_engine.py        (botanical substitution)
    - rd_discovery_engine.py / botanical_brain_engine.py (discovery/scoring)

It does NOT replace: the raw per-source API connectors (pubchem_connector,
chembl_connector, europepmc_connector, clinicaltrials_connector, ...) or the
Supabase evidence store (database.py / evidence_database.py). Those stay as
the data-access layer; this engine is the single place that turns that data
into a decision.
"""

import re
import requests
import pandas as pd

from seed_data import PLANT_COMPOUNDS, COMPOUND_TARGETS, TARGET_DISEASES, SLEEP_TEA_EVIDENCE
from compound_occurrence_map import get_alternative_plants

DECISION_COLUMNS = [
    "Reference_Plant", "Reference_Compound", "Alternative_Plant",
    "Shared_or_Similar_Compound", "Target_or_Mechanism", "Concentration_Info",
    "Extraction_Method", "Co_Compounds", "Safety_Flags", "Interaction_Flags",
    "Evidence_Source", "Market_Status", "Novelty_Status",
    "R&D_Opportunity_Score", "Decision_Class", "Rationale",
]

_SAFETY_WORDS = [
    "toxicity", "toxic", "hepatotoxic", "cytotoxic", "adverse",
    "contraindication", "contraindicated", "pregnancy", "breastfeeding",
    "allergy", "warning", "caution",
]

_INTERACTION_WORDS = [
    "drug interaction", "interaction", "cyp", "cytochrome", "warfarin",
    "anticoagulant", "antiplatelet", "ssri", "maoi", "benzodiazepine",
    "sedative", "hypoglycemic", "antidiabetic", "antihypertensive",
]

_KNOWN_CO_COMPOUNDS = [
    "apigenin", "luteolin", "quercetin", "kaempferol", "rutin",
    "rosmarinic acid", "caffeic acid", "chlorogenic acid", "curcumin",
    "berberine", "resveratrol", "catechin", "egcg", "gallic acid",
    "ellagic acid", "hypericin", "hyperforin", "linalool",
    "valerenic acid", "thymol", "carvacrol", "menthol", "eugenol",
    "silymarin", "withanolides", "boswellic acids",
]

_EXTRACTION_KEYWORDS = {
    "Aqueous extraction": ["aqueous", "water extract", "hot water", "infusion", "decoction"],
    "Ethanolic extraction": ["ethanol", "ethanolic"],
    "Hydroalcoholic extraction": ["hydroalcoholic", "ethanol-water"],
    "Methanolic extraction": ["methanol", "methanolic"],
    "Supercritical CO2 extraction": ["supercritical", "co2"],
    "Steam distillation": ["steam distillation", "distillation"],
    "Essential oil extraction": ["essential oil", "volatile oil"],
}

_CONCENTRATION_PATTERNS = [
    r"\b\d+(?:\.\d+)?\s?%",
    r"\b\d+(?:\.\d+)?\s?mg/g\b",
    r"\b\d+(?:\.\d+)?\s?mg/kg\b",
    r"\b\d+(?:\.\d+)?\s?mg/100g\b",
    r"\b\d+(?:\.\d+)?\s?(?:µg|ug)/g\b",
    r"\b\d+(?:\.\d+)?\s?mg/ml\b",
]


def _clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    return "" if x.lower() in ("nan", "none", "null") else x


def _norm(x):
    return re.sub(r"\s+", " ", _clean(x).lower()).strip()


class BotanicalRDCandidateEngine:
    """
    Starts from a product/problem (indication) and returns a single R&D
    decision table of alternative/better botanical sources for the
    compounds already known to be relevant to that problem.
    """

    def __init__(self, evidence_df=None, max_live_results=6, use_live_search=True):
        self.evidence_df = evidence_df if evidence_df is not None else pd.DataFrame()
        self.max_live_results = max_live_results
        self.use_live_search = use_live_search

    # ------------------------------------------------------------------ #
    # 1. Known inventory: plants / compounds / targets / evidence
    # ------------------------------------------------------------------ #
    def known_inventory(self, indication: str):
        indication_n = _norm(indication)
        matched_targets = set()

        # 1. Exact match (covers every option in step_inputs.py's dropdown).
        for disease, targets in TARGET_DISEASES.items():
            if _norm(disease) == indication_n:
                matched_targets.update(targets.keys())

        # 2. Substring match (covers close variants typed as free text).
        if not matched_targets:
            for disease, targets in TARGET_DISEASES.items():
                if indication_n in _norm(disease) or _norm(disease) in indication_n:
                    matched_targets.update(targets.keys())

        # 3. Word-overlap fallback (keeps the engine useful for free-text
        # problems that don't exactly match a curated disease name).
        if not matched_targets:
            indication_words = {w for w in indication_n.split() if len(w) > 3}
            for disease, targets in TARGET_DISEASES.items():
                disease_words = set(_norm(disease).split())
                if indication_words & disease_words:
                    matched_targets.update(targets.keys())

        relevant_compounds = {
            compound
            for compound, targets in COMPOUND_TARGETS.items()
            if any(_norm(t) in matched_targets or t in matched_targets for t in targets)
        }

        inventory = []
        for plant, compounds in PLANT_COMPOUNDS.items():
            for compound_name, compound_class, extraction in compounds:
                if compound_name in relevant_compounds:
                    targets = COMPOUND_TARGETS.get(compound_name, [])
                    inventory.append({
                        "reference_plant": plant,
                        "reference_compound": compound_name,
                        "compound_class": compound_class,
                        "seed_extraction": extraction,
                        "target": "; ".join(targets) if targets else "Not established",
                    })
        return inventory

    # ------------------------------------------------------------------ #
    # 2. Alternative plant discovery for a given compound
    # ------------------------------------------------------------------ #
    def discover_alternatives(self, compound: str, indication: str = ""):
        rows = []

        # 2a. Curated offline knowledge base (instant, no network needed)
        for plant in get_alternative_plants(compound):
            rows.append({
                "alternative_plant": plant,
                "raw_text": f"Curated knowledge base entry: {plant} is a known source of {compound}.",
                "source_title": "Internal curated botanical knowledge base",
                "source_url": "",
                "evidence_source": "Curated knowledge base",
            })

        # 2b. Local evidence database (Supabase export), if available
        if self.evidence_df is not None and not self.evidence_df.empty:
            for _, row in self.evidence_df.iterrows():
                text = " ".join(_clean(v) for v in row.values)
                if _norm(compound) not in text.lower():
                    continue
                plant = self._first_present(row, ["Scientific_Name", "Plant", "scientific_name"])
                plant = plant or self._extract_plant_name(text)
                if not plant:
                    continue
                rows.append({
                    "alternative_plant": plant,
                    "raw_text": text,
                    "source_title": self._first_present(row, ["Source_Title", "Title"]),
                    "source_url": self._first_present(row, ["Source_URL", "URL"]),
                    "evidence_source": "Local evidence database",
                })

        # 2c. Live literature search (Europe PMC), best-effort
        if self.use_live_search:
            rows.extend(self._search_europepmc(compound, indication))

        return rows

    def _search_europepmc(self, compound, indication=""):
        query = f'"{compound}" medicinal plant phytochemical extraction concentration'
        if indication:
            query += f' "{indication}"'
        try:
            r = requests.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params={"query": query, "format": "json", "pageSize": self.max_live_results},
                timeout=20,
            )
            r.raise_for_status()
            items = r.json().get("resultList", {}).get("result", [])
        except Exception:
            return []

        rows = []
        for item in items:
            title = _clean(item.get("title", ""))
            abstract = _clean(item.get("abstractText", ""))
            pmid = _clean(item.get("pmid", ""))
            doi = _clean(item.get("doi", ""))
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (f"https://doi.org/{doi}" if doi else "")
            raw_text = f"{title}. {abstract}"
            plant = self._extract_plant_name(raw_text)
            if not plant:
                continue
            rows.append({
                "alternative_plant": plant,
                "raw_text": raw_text,
                "source_title": title,
                "source_url": url,
                "evidence_source": "Europe PMC",
            })
        return rows

    @staticmethod
    def _extract_plant_name(text):
        text = _clean(text)
        candidates = re.findall(r"\b[A-Z][a-z]+ [a-z]+(?:\s[a-z]+)?\b", text)
        bad = {"The aim", "The study", "The results", "This study", "United States", "European Union"}
        for c in candidates:
            if c not in bad:
                return c
        return ""

    @staticmethod
    def _first_present(row, cols):
        for c in cols:
            if c in row.index:
                v = _clean(row.get(c))
                if v:
                    return v
        return ""

    # ------------------------------------------------------------------ #
    # 3. Enrichment: concentration / extraction / co-compounds / safety
    # ------------------------------------------------------------------ #
    def _enrich(self, raw_text):
        return {
            "concentration": self._extract_concentration(raw_text),
            "extraction_method": self._extract_extraction(raw_text),
            "co_compounds": self._extract_co_compounds(raw_text),
            "safety_flags": self._extract_flags(raw_text, _SAFETY_WORDS),
            "interaction_flags": self._extract_flags(raw_text, _INTERACTION_WORDS),
        }

    @staticmethod
    def _extract_concentration(text):
        text = _clean(text)
        found = []
        for pattern in _CONCENTRATION_PATTERNS:
            found.extend(m.group(0) for m in re.finditer(pattern, text, flags=re.IGNORECASE))
        return "; ".join(sorted(set(found)))[:300]

    @staticmethod
    def _extract_extraction(text):
        t = _norm(text)
        methods = [label for label, keys in _EXTRACTION_KEYWORDS.items() if any(k in t for k in keys)]
        return "; ".join(methods)

    @staticmethod
    def _extract_co_compounds(text):
        t = _norm(text)
        found = [c for c in _KNOWN_CO_COMPOUNDS if c in t]
        return "; ".join(found)

    @staticmethod
    def _extract_flags(text, words):
        t = _norm(text)
        return "; ".join(sorted({w for w in words if w in t}))

    # ------------------------------------------------------------------ #
    # 4. Scoring / decision classification
    # ------------------------------------------------------------------ #
    def _score_extraction(self, extraction_method, dosage_form):
        e, d = _norm(extraction_method), _norm(dosage_form)
        if not e:
            return 5
        score = 15
        if any(k in e for k in ("water", "aqueous", "infusion")):
            score += 15
            if any(k in d for k in ("tea", "infusion", "herbal")):
                score += 15
        if any(k in e for k in ("ethanol", "hydroalcoholic", "methanol")):
            score += 15
            if any(k in d for k in ("extract", "capsule", "tablet")):
                score += 10
        if any(k in e for k in ("essential oil", "distillation")):
            score += 10
            if "essential oil" in d:
                score += 15
        return min(score, 40)

    def _curated_evidence_for(self, plant):
        """Real curated clinical/regulatory/market evidence, when available
        (currently populated from the sleep-tea research in seed_data.py;
        extend SLEEP_TEA_EVIDENCE there to cover other indications)."""
        for name, ev in SLEEP_TEA_EVIDENCE.items():
            if _norm(name) == _norm(plant):
                return ev
        return None

    def _market_status(self, alternative_plant, reference_plant):
        alt_n, ref_n = _norm(alternative_plant), _norm(reference_plant)
        known_seed_plants = {_norm(p) for p in PLANT_COMPOUNDS}

        curated = self._curated_evidence_for(alternative_plant)
        if curated:
            label = "Reference plant" if alt_n == ref_n else "Known alternative"
            return f"{label} — {curated['production_status']}, commercial attractiveness: {curated['commercial']}"

        if alt_n == ref_n:
            return "Reference plant / already known for this indication"
        if alt_n in known_seed_plants:
            return "Established alternative / possible market overlap"
        return "White-space / not yet in seed commercial set"

    def _novelty_status(self, alternative_plant, reference_compound):
        curated = {_norm(p) for p in get_alternative_plants(reference_compound)}
        if _norm(alternative_plant) in curated:
            return "Known pairing (already documented)"
        return "Novel plant-compound pairing (R&D candidate)"

    def _decision_class(self, score):
        if score >= 75:
            return "Strong R&D alternative"
        if score >= 55:
            return "Promising R&D candidate"
        if score >= 35:
            return "Early-stage candidate"
        return "Low priority / insufficient data"

    def _rd_score(self, concentration, extraction_score, co_compounds, safety_flags,
                  interaction_flags, is_reference, market_status):
        concentration_score = 25 if concentration else 5
        co_compound_score = min(25, 5 * len([c for c in co_compounds.split(";") if c.strip()]))
        safety_score = 25 if safety_flags else 5
        interaction_score = 25 if interaction_flags else 5
        novelty_score = 0 if is_reference else 25
        commercial_score = {
            "Reference plant / already known for this indication": 10,
            "White-space / not yet in seed commercial set": 30,
            "Established alternative / possible market overlap": 20,
        }.get(market_status, 15)

        score = (
            concentration_score + extraction_score + co_compound_score
            + novelty_score + commercial_score
            - safety_score * 0.3 - interaction_score * 0.3
        )
        return round(max(score, 0), 1)

    # ------------------------------------------------------------------ #
    # 5. Orchestration
    # ------------------------------------------------------------------ #
    def run(self, indication: str, dosage_form: str = "", market: str = "",
            reference_plant: str = "", reference_compound: str = "") -> pd.DataFrame:
        inventory = self.known_inventory(indication)

        if reference_plant:
            inventory = [i for i in inventory if _norm(i["reference_plant"]) == _norm(reference_plant)]
        if reference_compound:
            inventory = [i for i in inventory if _norm(i["reference_compound"]) == _norm(reference_compound)]

        if not inventory:
            return pd.DataFrame(columns=DECISION_COLUMNS)

        results = []
        seen = set()

        for item in inventory:
            ref_plant = item["reference_plant"]
            ref_compound = item["reference_compound"]
            target = item["target"]

            candidates = self.discover_alternatives(ref_compound, indication)

            candidates.insert(0, {
                "alternative_plant": ref_plant,
                "raw_text": f"{ref_plant} is the reference source of {ref_compound}. "
                            f"Seed extraction route: {item['seed_extraction']}.",
                "source_title": "Internal seed knowledge base",
                "source_url": "",
                "evidence_source": "Curated knowledge base",
            })

            for c in candidates:
                alt_plant = _clean(c["alternative_plant"])
                if not alt_plant:
                    continue

                dedup_key = (_norm(ref_compound), _norm(alt_plant), _norm(c.get("source_title", "")))
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                enriched = self._enrich(c["raw_text"])
                extraction_score = self._score_extraction(enriched["extraction_method"], dosage_form)
                market_status = self._market_status(alt_plant, ref_plant)
                novelty_status = self._novelty_status(alt_plant, ref_compound)
                is_reference = _norm(alt_plant) == _norm(ref_plant)

                curated = self._curated_evidence_for(alt_plant)
                if curated:
                    if not enriched["safety_flags"]:
                        enriched["safety_flags"] = curated["safety_desc"]
                    if not enriched["extraction_method"]:
                        enriched["extraction_method"] = curated["preparation_form"]
                    c["evidence_source"] = (
                        f"{c['evidence_source']}; Curated regulatory/clinical review "
                        f"(EMA: {curated['ema_status']}, WHO: {curated['who_status']}, "
                        f"ESCOP: {curated['escop_status']}) — {curated['outcome']}"
                    )

                rd_score = self._rd_score(
                    enriched["concentration"], extraction_score, enriched["co_compounds"],
                    enriched["safety_flags"], enriched["interaction_flags"],
                    is_reference, market_status,
                )

                evidence_source = c["evidence_source"]
                if c.get("source_title"):
                    evidence_source += f" — {c['source_title']}"
                if c.get("source_url"):
                    evidence_source += f" ({c['source_url']})"

                results.append({
                    "Reference_Plant": ref_plant,
                    "Reference_Compound": ref_compound,
                    "Alternative_Plant": alt_plant,
                    "Shared_or_Similar_Compound": ref_compound,
                    "Target_or_Mechanism": target,
                    "Concentration_Info": enriched["concentration"] or "Not reported",
                    "Extraction_Method": enriched["extraction_method"] or "Not reported",
                    "Co_Compounds": enriched["co_compounds"] or "None identified",
                    "Safety_Flags": enriched["safety_flags"] or "None identified",
                    "Interaction_Flags": enriched["interaction_flags"] or "None identified",
                    "Evidence_Source": evidence_source,
                    "Market_Status": market_status,
                    "Novelty_Status": novelty_status,
                    "R&D_Opportunity_Score": rd_score,
                    "Decision_Class": self._decision_class(rd_score),
                    "Rationale": (
                        f"{alt_plant} is a {'reference' if is_reference else 'candidate alternative'} "
                        f"source of {ref_compound} (target/mechanism: {target}). "
                        f"Extraction route: {enriched['extraction_method'] or 'not clearly reported'}. "
                        f"Market status: {market_status}."
                    ),
                })

        df = pd.DataFrame(results, columns=DECISION_COLUMNS)
        if df.empty:
            return df

        df = df.sort_values(by=["R&D_Opportunity_Score"], ascending=False).reset_index(drop=True)
        df.insert(0, "Rank", range(1, len(df) + 1))
        return df
