import re
from collections import defaultdict

import pandas as pd

from evidence_database import load_evidence_database
from global_candidate_ranking_engine import rank_global_candidates
from global_plant_candidate_database import GLOBAL_PLANT_CANDIDATES


OUTPUT_COLUMNS = [
    "Reference_Plant",
    "Reference_Compound",
    "Alternative_Plant",
    "Shared_or_Similar_Compound",
    "Target_or_Mechanism",
    "Concentration_Info",
    "Extraction_Method",
    "Co_Compounds",
    "Safety_Flags",
    "Interaction_Flags",
    "Evidence_Source",
    "Market_Status",
    "Novelty_Status",
    "R&D_Opportunity_Score",
    "Decision_Class",
    "Rationale",
]


SIMILAR_COMPOUND_GROUPS = {
    "flavonoid": [
        "apigenin", "luteolin", "quercetin", "kaempferol", "rutin",
        "vitexin", "isovitexin", "orientin", "chrysin",
        "baicalin", "baicalein", "wogonin", "spinosin", "tiliroside",
    ],
    "phenolic acid": [
        "rosmarinic acid", "caffeic acid", "chlorogenic acid",
        "gallic acid", "ellagic acid",
    ],
    "terpene_or_volatile": [
        "linalool", "linalyl acetate", "citral", "bisabolol",
        "chamazulene", "thymol", "carvacrol", "menthol",
        "eugenol", "bornyl acetate", "terpinen-4-ol",
    ],
    "saponin": [
        "gypenosides", "saponins", "jujubosides", "sitoindosides",
    ],
    "lactone": [
        "kavalactones", "kavain", "yangonin",
        "valerenic acid", "valepotriates",
    ],
    "withanolide": [
        "withanolides", "withaferin a",
    ],
}


SAFETY_TERMS = [
    "toxicity", "toxic", "hepatotoxic", "cytotoxic", "adverse",
    "contraindication", "contraindicated", "pregnancy",
    "breastfeeding", "allergy", "warning", "caution",
]


INTERACTION_TERMS = [
    "drug interaction", "interaction", "cyp", "cytochrome",
    "warfarin", "anticoagulant", "antiplatelet", "ssri", "maoi",
    "benzodiazepine", "sedative", "hypoglycemic",
    "antidiabetic", "antihypertensive",
]


EXTRACTION_KEYWORDS = {
    "aqueous / infusion": [
        "aqueous", "water", "infusion", "decoction", "tea",
    ],
    "hydroalcoholic": [
        "hydroalcoholic", "hydroethanolic", "ethanol-water",
    ],
    "ethanolic": [
        "ethanol", "ethanolic",
    ],
    "essential oil / distillation": [
        "essential oil", "volatile oil", "steam distillation", "distillation",
    ],
    "co2 extract": [
        "co2", "supercritical",
    ],
}


class BotanicalRDCandidateEngine:
    """
    Central engine for botanical R&D candidate discovery.

    It starts from a product/problem and produces a decision table for
    alternative or better botanical R&D candidates.

    This engine replaces scattered logic from:
    ranking, market, white-space, knowledge extraction, target discovery,
    mechanism discovery, target-compound-plant discovery, graph, and
    botanical substitution.
    """

    def __init__(self, evidence_df=None, candidate_data=None):
        self.evidence_df = self._to_dataframe(evidence_df)
        self.candidate_data = candidate_data or GLOBAL_PLANT_CANDIDATES
        self.compound_to_class = self._build_compound_class_index()

    def run(
        self,
        product_type,
        problem,
        dosage_form,
        market,
        max_reference_plants=12,
    ):
        references = self._get_reference_plants(
            problem=problem,
            dosage_form=dosage_form,
            market=market,
            max_reference_plants=max_reference_plants,
        )

        if references.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        rows = []
        all_candidates = self._candidate_frame()
        evidence_index = self._build_evidence_text_index()

        for _, ref in references.iterrows():
            ref_plant = self._pick(
                ref,
                ["Scientific_Name", "scientific_name", "Plant", "plant"],
            )

            ref_compounds = self._split_terms(
                self._pick(
                    ref,
                    [
                        "Known_Active_Compounds",
                        "compound_name",
                        "Compound",
                        "compound",
                    ],
                )
            )

            ref_targets = self._split_terms(
                self._pick(
                    ref,
                    [
                        "Known_Targets",
                        "major_target",
                        "target",
                        "mechanism",
                    ],
                )
            )

            for ref_compound in ref_compounds:
                if not ref_compound:
                    continue

                for _, alt in all_candidates.iterrows():
                    alt_plant = self._pick(alt, ["Scientific_Name"])

                    if not alt_plant:
                        continue

                    alt_compounds = self._split_terms(
                        self._pick(alt, ["Known_Active_Compounds"])
                    )

                    matched_compound = self._match_compounds(
                        ref_compound,
                        alt_compounds,
                    )

                    if not matched_compound:
                        continue

                    raw_evidence = self._collect_raw_evidence(
                        evidence_index=evidence_index,
                        plant=alt_plant,
                        compound=matched_compound,
                        problem=problem,
                    )

                    extraction = self._best_extraction(alt, raw_evidence)
                    concentration = self._extract_concentration(raw_evidence)
                    co_compounds = self._co_compounds(
                        compounds=alt_compounds,
                        matched=matched_compound,
                    )

                    safety_flags = self._extract_flags(
                        raw_evidence,
                        SAFETY_TERMS,
                    )

                    interaction_flags = self._extract_flags(
                        raw_evidence,
                        INTERACTION_TERMS,
                    )

                    target = self._target_or_mechanism(ref_targets, alt)

                    market_status = self._market_status(
                        alt=alt,
                        evidence=raw_evidence,
                        market=market,
                    )

                    novelty_status = self._novelty_status(
                        ref_plant=ref_plant,
                        alt_plant=alt_plant,
                        matched=matched_compound,
                        ref_compound=ref_compound,
                        alt=alt,
                    )

                    score = self._score_candidate(
                        same_plant=self._norm(ref_plant) == self._norm(alt_plant),
                        matched_compound=matched_compound,
                        reference_compound=ref_compound,
                        concentration=concentration,
                        extraction=extraction,
                        dosage_form=dosage_form,
                        co_compounds=co_compounds,
                        safety_flags=safety_flags,
                        interaction_flags=interaction_flags,
                        market_status=market_status,
                        novelty_status=novelty_status,
                        target=target,
                        evidence=raw_evidence,
                    )

                    decision = self._decision_class(
                        score=score,
                        safety_flags=safety_flags,
                        interaction_flags=interaction_flags,
                    )

                    rows.append(
                        {
                            "Reference_Plant": ref_plant,
                            "Reference_Compound": ref_compound,
                            "Alternative_Plant": alt_plant,
                            "Shared_or_Similar_Compound": matched_compound,
                            "Target_or_Mechanism": target or "Not clearly extracted",
                            "Concentration_Info": concentration or "Not clearly reported",
                            "Extraction_Method": extraction or "Not clearly reported",
                            "Co_Compounds": co_compounds or "Not clearly extracted",
                            "Safety_Flags": safety_flags or "No explicit flag found",
                            "Interaction_Flags": interaction_flags or "No explicit flag found",
                            "Evidence_Source": self._evidence_source(
                                alt_plant,
                                matched_compound,
                                raw_evidence,
                            ),
                            "Market_Status": market_status,
                            "Novelty_Status": novelty_status,
                            "R&D_Opportunity_Score": score,
                            "Decision_Class": decision,
                            "Rationale": self._rationale(
                                product_type=product_type,
                                problem=problem,
                                dosage_form=dosage_form,
                                ref_plant=ref_plant,
                                ref_compound=ref_compound,
                                alt_plant=alt_plant,
                                matched=matched_compound,
                                extraction=extraction,
                                concentration=concentration,
                                co_compounds=co_compounds,
                                market_status=market_status,
                                novelty_status=novelty_status,
                                decision=decision,
                            ),
                        }
                    )

        if not rows:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        output = pd.DataFrame(rows)

        output = output.drop_duplicates(
            subset=[
                "Reference_Plant",
                "Reference_Compound",
                "Alternative_Plant",
                "Shared_or_Similar_Compound",
            ],
            keep="first",
        )

        output = output.sort_values(
            by=["R&D_Opportunity_Score"],
            ascending=False,
        ).reset_index(drop=True)

        return output[OUTPUT_COLUMNS]

    def _get_reference_plants(
        self,
        problem,
        dosage_form,
        market,
        max_reference_plants,
    ):
        try:
            ranked = rank_global_candidates(
                indication=problem,
                dosage_form=dosage_form,
                market=market,
                target_count=max_reference_plants,
            )
        except Exception:
            ranked = pd.DataFrame()

        ranked = self._to_dataframe(ranked)

        if ranked.empty:
            candidate_df = self._candidate_frame()
            problem_norm = self._norm(problem)

            ranked = candidate_df[
                candidate_df["Indications_Text_Norm"].str.contains(
                    problem_norm,
                    na=False,
                    regex=False,
                )
            ]

        return ranked.head(max_reference_plants)

    def _candidate_frame(self):
        rows = []

        for item in self.candidate_data:
            row = dict(item)

            row["Known_Active_Compounds"] = ", ".join(
                item.get("Known_Active_Compounds", [])
            )

            row["Known_Targets"] = ", ".join(
                item.get("Known_Targets", [])
            )

            row["Indications_Text"] = ", ".join(
                item.get("Indications", [])
            )

            row["Indications_Text_Norm"] = self._norm(
                row["Indications_Text"]
            )

            rows.append(row)

        return pd.DataFrame(rows)

    def _build_evidence_text_index(self):
        index = defaultdict(str)

        if self.evidence_df.empty:
            return index

        for _, row in self.evidence_df.iterrows():
            text = " ".join(
                str(value)
                for value in row.values
                if pd.notna(value)
            )

            plant = self._pick(
                row,
                [
                    "Scientific_Name",
                    "scientific_name",
                    "Plant",
                    "plant",
                    "Common_Name",
                    "common_name",
                ],
            )

            if plant:
                index[self._norm(plant)] += " " + text

            for compound in self._known_compounds_from_text(text):
                index[self._norm(compound)] += " " + text

        return index

    def _collect_raw_evidence(
        self,
        evidence_index,
        plant,
        compound,
        problem,
    ):
        compound_clean = compound.split("[")[0].strip()

        parts = [
            evidence_index.get(self._norm(plant), ""),
            evidence_index.get(self._norm(compound_clean), ""),
            evidence_index.get(self._norm(problem), ""),
        ]

        return " ".join(part for part in parts if part).strip()[:6000]

    def _match_compounds(
        self,
        reference_compound,
        alternative_compounds,
    ):
        ref = self._norm(reference_compound)

        alt_norm = {
            self._norm(compound): compound
            for compound in alternative_compounds
        }

        if ref in alt_norm:
            return alt_norm[ref]

        ref_class = self.compound_to_class.get(ref, "")

        if not ref_class:
            return ""

        for alt_key, alt_value in alt_norm.items():
            if self.compound_to_class.get(alt_key, "") == ref_class:
                return f"{alt_value} [similar: {ref_class}]"

        return ""

    def _build_compound_class_index(self):
        index = {}

        for compound_class, compounds in SIMILAR_COMPOUND_GROUPS.items():
            for compound in compounds:
                index[self._norm(compound)] = compound_class

        return index

    def _best_extraction(self, alt, evidence):
        base = self._pick(alt, ["Extraction_Method"])
        found = self._extract_extraction(evidence)

        if base and found:
            return f"{base}; evidence mentions: {found}"

        return base or found

    def _score_candidate(
        self,
        same_plant,
        matched_compound,
        reference_compound,
        concentration,
        extraction,
        dosage_form,
        co_compounds,
        safety_flags,
        interaction_flags,
        market_status,
        novelty_status,
        target,
        evidence,
    ):
        score = 0

        if self._norm(matched_compound) == self._norm(reference_compound):
            score += 18
        else:
            score += 11

        score += 12 if concentration else 3
        score += self._extraction_fit_score(extraction, dosage_form)
        score += min(12, len(self._split_terms(co_compounds)) * 3)
        score += 10 if target else 2
        score += 10 if evidence else 4

        if "Alternative" in novelty_status or "Cross-region" in novelty_status:
            score += 14
        else:
            score += 3

        market_lower = market_status.lower()

        if "saturated" in market_lower:
            score += 4
        elif "emerging" in market_lower or "white-space" in market_lower:
            score += 12
        else:
            score += 8

        if safety_flags:
            score -= 8

        if interaction_flags:
            score -= 6

        if same_plant:
            score -= 12

        return round(max(0, min(100, score)), 1)

    def _extraction_fit_score(self, extraction, dosage_form):
        extraction_norm = self._norm(extraction)
        dosage_norm = self._norm(dosage_form)

        if not extraction_norm:
            return 3

        score = 8

        if any(
            term in extraction_norm
            for term in ["aqueous", "water", "infusion", "decoction"]
        ):
            score += 10

            if any(
                term in dosage_norm
                for term in ["infusion", "tea", "herbal"]
            ):
                score += 8

        if any(
            term in extraction_norm
            for term in ["ethanol", "hydroalcoholic", "extract"]
        ):
            score += 8

            if any(
                term in dosage_norm
                for term in [
                    "capsule",
                    "tablet",
                    "extract",
                    "cream",
                    "gel",
                    "ointment",
                ]
            ):
                score += 6

        if any(
            term in extraction_norm
            for term in ["essential oil", "distillation"]
        ):
            score += 6

            if any(
                term in dosage_norm
                for term in ["cream", "gel", "essential oil"]
            ):
                score += 5

        return min(score, 26)

    def _market_status(self, alt, evidence, market):
        ema = self._pick(alt, ["EMA_Status"])
        text = self._norm(evidence)

        product_signal = any(
            term in text
            for term in [
                "product",
                "market",
                "label",
                "patent",
                "dailymed",
                "fda",
            ]
        )

        if ema == "Yes" or product_signal:
            return "Known / possibly saturated market"

        if self._norm(market) in self._norm(self._pick(alt, ["Region"])):
            return "Regional fit / emerging opportunity"

        return "Limited market signal / possible white-space"

    def _novelty_status(
        self,
        ref_plant,
        alt_plant,
        matched,
        ref_compound,
        alt,
    ):
        if self._norm(ref_plant) == self._norm(alt_plant):
            return "Reference plant / benchmark"

        matched_clean = matched.split("[")[0].strip()

        if self._norm(matched_clean) == self._norm(ref_compound):
            return "Alternative source with same compound"

        region = self._pick(alt, ["Region"])

        if region:
            return f"Cross-region similar-compound opportunity ({region})"

        return "Alternative source with similar compound"

    def _decision_class(
        self,
        score,
        safety_flags,
        interaction_flags,
    ):
        risky = bool(safety_flags) or bool(interaction_flags)

        if score >= 75 and not risky:
            return "Strong R&D candidate"

        if score >= 60:
            return "Promising candidate; verify safety and standardization"

        if score >= 45:
            return "Early-stage candidate; more evidence needed"

        return "Low priority / insufficient data"

    def _rationale(
        self,
        product_type,
        problem,
        dosage_form,
        ref_plant,
        ref_compound,
        alt_plant,
        matched,
        extraction,
        concentration,
        co_compounds,
        market_status,
        novelty_status,
        decision,
    ):
        return (
            f"For {product_type} targeting {problem}, {alt_plant} is compared "
            f"with {ref_plant} because it contains {matched}, linked to the "
            f"reference compound {ref_compound}. Extraction fit for "
            f"{dosage_form}: {extraction or 'not clearly reported'}. "
            f"Concentration: {concentration or 'not clearly reported'}. "
            f"Co-compounds: {co_compounds or 'not clearly extracted'}. "
            f"Market: {market_status}. Novelty: {novelty_status}. "
            f"Decision: {decision}."
        )

    def _target_or_mechanism(self, ref_targets, alt):
        alt_targets = self._split_terms(
            self._pick(alt, ["Known_Targets"])
        )

        ref_target_norms = {
            self._norm(target)
            for target in ref_targets
        }

        shared = [
            target
            for target in alt_targets
            if self._norm(target) in ref_target_norms
        ]

        if shared:
            return "; ".join(shared)

        return "; ".join(alt_targets or ref_targets)

    def _extract_concentration(self, text):
        patterns = [
            r"\b\d+(?:\.\d+)?\s?%",
            r"\b\d+(?:\.\d+)?\s?mg/g\b",
            r"\b\d+(?:\.\d+)?\s?mg/kg\b",
            r"\b\d+(?:\.\d+)?\s?mg/100g\b",
            r"\b\d+(?:\.\d+)?\s?(?:µg/g|ug/g)\b",
            r"\b\d+(?:\.\d+)?\s?mg/ml\b",
        ]

        matches = []

        for pattern in patterns:
            matches.extend(
                match.group(0)
                for match in re.finditer(
                    pattern,
                    text,
                    flags=re.IGNORECASE,
                )
            )

        return "; ".join(sorted(set(matches)))[:300]

    def _extract_extraction(self, text):
        text_norm = self._norm(text)
        found = []

        for label, keywords in EXTRACTION_KEYWORDS.items():
            if any(keyword in text_norm for keyword in keywords):
                found.append(label)

        return "; ".join(sorted(set(found)))

    def _co_compounds(self, compounds, matched):
        matched_base = self._norm(matched.split("[")[0])
        co_compounds = [
            compound
            for compound in compounds
            if self._norm(compound) != matched_base
        ]

        return "; ".join(co_compounds[:8])

    def _extract_flags(self, text, terms):
        text_norm = self._norm(text)

        found = [
            term
            for term in terms
            if term in text_norm
        ]

        return "; ".join(sorted(set(found)))

    def _evidence_source(self, plant, compound, evidence):
        if evidence:
            return "Local evidence database / extracted source text"

        return f"Seed candidate database: {plant} / {compound}"

    def _known_compounds_from_text(self, text):
        text_norm = self._norm(text)
        found = []

        for compound in self.compound_to_class:
            if compound in text_norm:
                found.append(compound)

        return found

    @staticmethod
    def _to_dataframe(data):
        if data is None:
            return pd.DataFrame()

        if isinstance(data, pd.DataFrame):
            return data.copy()

        return pd.DataFrame(data)

    @staticmethod
    def _norm(value):
        if value is None:
            return ""

        value = str(value).strip().lower()

        if value in {"nan", "none", "null"}:
            return ""

        return re.sub(r"\s+", " ", value)

    @staticmethod
    def _split_terms(value):
        if value is None:
            return []

        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = re.split(r"[,;|/]", str(value))

        clean_items = []

        for item in raw_items:
            item = str(item).strip()

            if item and item.lower() not in {"nan", "none", "null"}:
                clean_items.append(item)

        return clean_items

    @staticmethod
    def _pick(row, names):
        for name in names:
            try:
                value = row.get(name, "")
            except AttributeError:
                value = ""

            if (
                value is not None
                and str(value).strip()
                and str(value).lower() not in {"nan", "none", "null"}
            ):
                return str(value).strip()

        return ""


def load_default_evidence():
    try:
        return pd.DataFrame(load_evidence_database())
    except Exception:
        return pd.DataFrame()
