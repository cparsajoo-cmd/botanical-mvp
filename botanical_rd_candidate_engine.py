import os
import re
import base64
import requests
from collections import defaultdict

import pandas as pd

from evidence_database import load_evidence_database
from global_candidate_ranking_engine import rank_global_candidates
from global_plant_candidate_database import GLOBAL_PLANT_CANDIDATES
from compound_occurrence_map import get_region
from supabase_data import (
    load_plant_compounds_df,
    load_compound_profiles_df,
    load_scientific_evidence_df,
)
from regulatory_frameworks import get_us_uk_status
from seed_data import (
    PLANT_COMPOUNDS,
    COMPOUND_TARGETS,
    TARGET_DISEASES,
    SLEEP_TEA_EVIDENCE,
)


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


# Generic/connector words that appear across many different indication
# names (e.g. "Joint & muscle comfort" and "Metabolic & blood sugar
# support" both contain "&" and "support"). These must be excluded from
# any token-overlap fallback matching, otherwise unrelated indications
# get falsely linked just because they share a filler word.
INDICATION_STOPWORDS = {
    "&", "/", "-", "and", "or", "of", "for", "in", "on", "the", "a", "to",
    "support", "health", "comfort", "care", "wellness", "relief",
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

    def __init__(
        self,
        evidence_df=None,
        candidate_data=None,
        use_live_search=True,
        plant_compounds_df=None,
        compound_profiles_df=None,
        scientific_evidence_df=None,
    ):
        self.evidence_df = self._to_dataframe(evidence_df)
        self.use_live_search = use_live_search

        # Real Supabase tables (806 / 310 / 47 records as of the last known
        # snapshot) are the primary data source. Any of them can be passed
        # in explicitly (e.g. for tests); otherwise they're fetched live.
        # If Supabase is unreachable, these come back empty and the engine
        # falls back to the small local seed dataset further below.
        self.plant_compounds_df = self._load_supabase_df(
            plant_compounds_df, load_plant_compounds_df
        )
        self.compound_profiles_df = self._load_supabase_df(
            compound_profiles_df, load_compound_profiles_df
        )
        self.scientific_evidence_df = self._load_supabase_df(
            scientific_evidence_df, load_scientific_evidence_df
        )

        if candidate_data is not None:
            self.candidate_data = candidate_data
            self.candidate_source = "override"
        elif not self.plant_compounds_df.empty:
            self.candidate_data = self._candidates_from_plant_compounds()
            self.candidate_source = "supabase"
        else:
            # GLOBAL_PLANT_CANDIDATES alone (35 plants, each hand-tagged
            # with Indications) is used for REFERENCE-plant selection.
            # But it's noticeably smaller than seed_data.PLANT_COMPOUNDS
            # (48+ plants) — so alternative-plant matching was silently
            # blind to any plant only present in PLANT_COMPOUNDS (e.g.
            # Eschscholzia californica never got considered as an
            # isoquinoline-alkaloid alternative to Berberis vulgaris).
            # Merge in every seed_data plant not already covered, with no
            # Indications tag (so it still can't be picked as a
            # reference plant via indication text-matching — only as an
            # alternative-plant match target), to make alt-plant search
            # cover the full local dataset.
            self.candidate_data = (
                GLOBAL_PLANT_CANDIDATES + self._seed_data_only_candidates()
            )
            self.candidate_source = "local_fallback"

        self.compound_to_class, self.compound_to_targets = (
            self._build_compound_indexes()
        )

    def run(
        self,
        indication,
        dosage_form="",
        market="",
        reference_plant="",
        reference_compound="",
        product_type=None,
        max_reference_plants=12,
    ):
        problem = indication
        product_type = product_type or (dosage_form or "botanical product")

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

            if reference_plant and self._norm(reference_plant) not in self._norm(ref_plant):
                continue

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

            if reference_compound:
                filtered = [
                    compound for compound in ref_compounds
                    if self._norm(reference_compound) in self._norm(compound)
                ]
                ref_compounds = filtered or [reference_compound]

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

                    matched_compound, match_quality = self._match_compounds(
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

                    has_real_evidence = bool(raw_evidence.strip())

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
                        match_quality=match_quality,
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
                        has_evidence=has_real_evidence,
                        match_quality=match_quality,
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
                                match_quality=match_quality,
                                has_evidence=has_real_evidence,
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

        # Sort by score first so, when two rows differ only by letter case in
        # the compound name (a real data-quality issue seen in some source
        # records — e.g. "Withanolide D" / "withanolide D" / "WITHANOLIDE
        # D" all meaning the same compound), the highest-scoring version is
        # the one kept.
        output = output.sort_values(
            by=["R&D_Opportunity_Score"],
            ascending=False,
        )

        dedup_key = pd.DataFrame({
            "Reference_Plant": output["Reference_Plant"].map(self._norm),
            "Reference_Compound": output["Reference_Compound"].map(self._norm),
            "Alternative_Plant": output["Alternative_Plant"].map(self._norm),
            "Shared_or_Similar_Compound": output["Shared_or_Similar_Compound"].map(self._norm),
        })

        output = output[~dedup_key.duplicated(keep="first")]

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
        if self.candidate_source == "supabase":
            direct = self._reference_plants_from_supabase(
                problem, max_reference_plants
            )
            if not direct.empty:
                return direct

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

        if ranked.empty:
            # Last resort: derive reference plants straight from the same
            # known_inventory chain (TARGET_DISEASES -> COMPOUND_TARGETS ->
            # PLANT_COMPOUNDS / Supabase plant_compounds) that Step 1
            # already successfully uses. Without this, an indication can
            # show a full "known inventory" in Step 1 and still return zero
            # rows in Step 2 just because no plant happened to be manually
            # tagged with that exact indication in GLOBAL_PLANT_CANDIDATES
            # (e.g. Ginkgo biloba / Bacopa monnieri were never tagged with
            # "Cognitive decline / Alzheimer's support").
            ranked = self._reference_plants_from_known_inventory(
                problem, max_reference_plants
            )

        return ranked.head(max_reference_plants)

    def _reference_plants_from_known_inventory(self, problem, max_reference_plants):
        inventory = self.known_inventory_df(problem)

        if inventory.empty:
            return pd.DataFrame()

        rows = []

        for plant, group in inventory.groupby("Known_Plant"):
            compounds = sorted(
                c for c in group["Known_Compound"].dropna().unique() if c
            )
            targets = sorted(
                t for t in group["Known_Target"].dropna().unique() if t
            )

            if not plant or not compounds:
                continue

            rows.append({
                "Scientific_Name": plant,
                "Known_Active_Compounds": ", ".join(compounds),
                "Known_Targets": "; ".join(targets),
            })

        return pd.DataFrame(rows).head(max_reference_plants)

    def _reference_plants_from_supabase(self, problem, max_reference_plants):
        """Reference plants selected directly from the real
        plant_compounds table's own `indication` column, instead of the
        small hardcoded GLOBAL_PLANT_CANDIDATES list. This is the primary
        path whenever Supabase data is available.
        """
        problem_norm = self._norm(problem)

        matched = [
            item for item in self.candidate_data
            if any(
                problem_norm in self._norm(indication)
                or self._norm(indication) in problem_norm
                for indication in item.get("Indications", [])
            )
        ]

        if not matched:
            problem_tokens = self._meaningful_tokens(problem_norm)
            matched = [
                item for item in self.candidate_data
                if problem_tokens
                and any(
                    problem_tokens & self._meaningful_tokens(self._norm(indication))
                    for indication in item.get("Indications", [])
                )
            ]

        if not matched:
            return pd.DataFrame()

        rows = []
        for item in matched[:max_reference_plants]:
            row = dict(item)
            row["Known_Active_Compounds"] = ", ".join(
                item.get("Known_Active_Compounds", [])
            )
            row["Known_Targets"] = ", ".join(item.get("Known_Targets", []))
            row["Indications_Text"] = ", ".join(item.get("Indications", []))
            rows.append(row)

        return pd.DataFrame(rows)

    @staticmethod
    def _load_supabase_df(explicit_df, loader):
        if explicit_df is not None:
            return BotanicalRDCandidateEngine._to_dataframe(explicit_df)

        try:
            loaded = loader()
        except Exception:
            return pd.DataFrame()

        return loaded if isinstance(loaded, pd.DataFrame) else pd.DataFrame()

    def _candidates_from_plant_compounds(self):
        """Build the GLOBAL_PLANT_CANDIDATES-shaped list directly from the
        real plant_compounds table (grouped by scientific_name), instead
        of the small hardcoded local list.
        """
        df = self.plant_compounds_df.copy()

        if "scientific_name" not in df.columns:
            return GLOBAL_PLANT_CANDIDATES

        df["scientific_name"] = df["scientific_name"].fillna("").astype(str).str.strip()
        df = df[df["scientific_name"] != ""]

        if df.empty:
            return GLOBAL_PLANT_CANDIDATES

        candidates = []

        for scientific_name, group in df.groupby("scientific_name"):
            candidates.append({
                "Scientific_Name": scientific_name,
                "Common_Name": self._first_non_empty(group.get("common_name")),
                "Region": get_region(scientific_name),
                "Indications": self._unique_clean_list(group.get("indication")),
                "Known_Active_Compounds": self._unique_clean_list(
                    group.get("compound_name")
                ),
                "Known_Targets": self._unique_clean_list(
                    self._split_series_terms(group.get("target"))
                ),
                "Plant_Part": self._first_non_empty(group.get("plant_part")),
                "Extraction_Method": self._first_non_empty(
                    group.get("extraction_method")
                ),
                "EMA_Status": "",
            })

        return candidates or GLOBAL_PLANT_CANDIDATES

    @staticmethod
    def _unique_clean_list(values):
        if values is None:
            return []

        seen = []
        for value in values:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"nan", "none", "null"} and text not in seen:
                seen.append(text)

        return seen

    @staticmethod
    def _first_non_empty(values):
        if values is None:
            return ""

        for value in values:
            text = str(value).strip() if value is not None else ""
            if text and text.lower() not in {"nan", "none", "null"}:
                return text

        return ""

    def _split_series_terms(self, values):
        if values is None:
            return []

        terms = []
        for value in values:
            terms.extend(self._split_terms(value))

        return terms

    @staticmethod
    def _seed_data_only_candidates():
        """Every plant in seed_data.PLANT_COMPOUNDS that ISN'T already in
        GLOBAL_PLANT_CANDIDATES, reshaped into the same candidate-dict
        format (Known_Active_Compounds / Known_Targets / Region), so it
        can be searched as an alternative-plant match target. No
        Indications tag on purpose — see the comment where this is called.
        """
        already_covered = {
            item["Scientific_Name"] for item in GLOBAL_PLANT_CANDIDATES
        }

        candidates = []

        for plant, compounds in PLANT_COMPOUNDS.items():
            if plant in already_covered:
                continue

            compound_names = [name for name, _cls, _extraction in compounds]
            targets = sorted({
                target
                for name in compound_names
                for target in COMPOUND_TARGETS.get(name, [])
            })
            extraction = next(
                (ext for _name, _cls, ext in compounds if ext), ""
            )

            candidates.append({
                "Scientific_Name": plant,
                "Common_Name": "",
                "Region": get_region(plant),
                "Indications": [],
                "Known_Active_Compounds": compound_names,
                "Known_Targets": targets,
                "Plant_Part": "",
                "Extraction_Method": extraction,
                "EMA_Status": "",
            })

        return candidates

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

        if not self.evidence_df.empty:
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

        if not self.scientific_evidence_df.empty:
            text_columns = [
                "title", "abstract", "decision_reason",
                "evidence_flags", "decision_class", "indication",
            ]

            for _, row in self.scientific_evidence_df.iterrows():
                text = " ".join(
                    str(row.get(col))
                    for col in text_columns
                    if pd.notna(row.get(col, None)) and str(row.get(col)).strip()
                )

                plant = str(row.get("plant") or "").strip()

                if plant:
                    index[self._norm(plant)] += " " + text

                for compound in self._known_compounds_from_text(text):
                    index[self._norm(compound)] += " " + text

        # Curated regulatory/clinical evidence (seed_data.SLEEP_TEA_EVIDENCE)
        # — this is the manually-verified EMA/WHO/ESCOP + cited-study
        # research Yalda already did for the sleep/anxiety plants. It must
        # count as real evidence, not be treated the same as "nothing
        # found", or every one of these plants gets its confidence capped
        # despite having genuinely reviewed sources.
        for plant, curated in SLEEP_TEA_EVIDENCE.items():
            text = (
                f"{curated.get('study_type', '')}. "
                f"{curated.get('outcome', '')} "
                f"EMA: {curated.get('ema_status', '')}. "
                f"WHO: {curated.get('who_status', '')}. "
                f"ESCOP: {curated.get('escop_status', '')}. "
                f"Safety: {curated.get('safety_desc', '')}."
            )
            index[self._norm(plant)] += " " + text

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
        """Returns (matched_compound_label, match_quality).

        match_quality is one of:
          "exact"           - the alternative plant contains the exact
                               same reference compound.
          "target_verified" - a different compound, in the same broad
                               chemical class, that ALSO shares a known
                               biological target with the reference
                               compound (per seed_data.COMPOUND_TARGETS).
          "class_only"       - a different compound sharing only the
                               broad chemical class label (e.g. both are
                               "flavonoids"), with no confirmed shared
                               target — a weak, hypothesis-level link.
          "none"             - no match at all.
        """
        ref = self._norm(reference_compound)

        alt_norm = {
            self._norm(compound): compound
            for compound in alternative_compounds
        }

        if ref in alt_norm:
            return alt_norm[ref], "exact"

        ref_class = self.compound_to_class.get(ref, "")

        if not ref_class:
            return "", "none"

        ref_targets = self.compound_to_targets.get(ref, set())

        class_matches = [
            alt_value
            for alt_key, alt_value in alt_norm.items()
            if self.compound_to_class.get(alt_key, "") == ref_class
        ]

        if not class_matches:
            return "", "none"

        if ref_targets:
            for alt_value in class_matches:
                alt_targets = self.compound_to_targets.get(
                    self._norm(alt_value), set()
                )
                if alt_targets & ref_targets:
                    return (
                        f"{alt_value} [similar: {ref_class}; shared target]",
                        "target_verified",
                    )

        return (
            f"{class_matches[0]} [similar: {ref_class}; class-only, "
            f"target not confirmed]",
            "class_only",
        )

    def _build_compound_indexes(self):
        """Returns (compound_to_class, compound_to_targets).

        Layered, cheapest/narrowest first so richer sources can override:
          1. seed_data.PLANT_COMPOUNDS's own per-compound chemical class
             (already collected there for every plant, e.g. "Isoquinoline
             alkaloid" for Berberine — previously computed but never fed
             into cross-plant matching, which silently starved newer
             indications like metabolic/energy of any alternative-plant
             results even when a real class match existed).
          2. SIMILAR_COMPOUND_GROUPS — a small hand-curated set of extra
             families for compounds not listed with a class anywhere else.
          3. The real Supabase `compound_profiles` table (310 records) —
             the richest, maintained source — wins over both when present.
        """
        class_index = {}

        for compounds in PLANT_COMPOUNDS.values():
            for compound_name, chem_class, _extraction in compounds:
                if chem_class:
                    class_index[self._norm(compound_name)] = chem_class

        for compound_class, compounds in SIMILAR_COMPOUND_GROUPS.items():
            for compound in compounds:
                class_index[self._norm(compound)] = compound_class

        target_index = defaultdict(set)

        for compound, targets in COMPOUND_TARGETS.items():
            for target in targets:
                target_index[self._norm(compound)].add(self._norm(target))

        if not self.compound_profiles_df.empty:
            for _, row in self.compound_profiles_df.iterrows():
                compound = self._norm(row.get("compound_name"))

                if not compound:
                    continue

                compound_class = str(row.get("compound_class") or "").strip()
                if compound_class:
                    # Supabase is the richer, maintained source — it wins
                    # over the small local class map when both exist.
                    class_index[compound] = compound_class

                for target in self._split_terms(row.get("major_target")):
                    target_index[compound].add(self._norm(target))

        return class_index, dict(target_index)

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
        match_quality,
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

        if match_quality == "exact":
            score += 18
        elif match_quality == "target_verified":
            score += 14
        else:
            # class_only: same broad chemical family, no confirmed shared
            # target — the weakest kind of compound link.
            score += 6

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
        has_evidence,
        match_quality,
    ):
        risky = bool(safety_flags) or bool(interaction_flags)

        if score >= 75 and not risky:
            base = "Strong R&D candidate"
        elif score >= 60:
            base = "Promising candidate; verify safety and standardization"
        elif score >= 45:
            base = "Early-stage candidate; more evidence needed"
        else:
            base = "Low priority / insufficient data"

        if has_evidence:
            return base

        # No real literature/evidence text was found for this plant/compound
        # pair — cap the confidence level so a purely heuristic chemical
        # link (or even an exact-compound match with zero literature
        # support yet) is never reported as a "Strong" candidate.
        order = [
            "Low priority / insufficient data",
            "Early-stage candidate; more evidence needed",
            "Promising candidate; verify safety and standardization",
            "Strong R&D candidate",
        ]

        if match_quality == "exact":
            ceiling = "Promising candidate; verify safety and standardization"
        elif match_quality == "target_verified":
            ceiling = "Early-stage candidate; more evidence needed"
        else:
            ceiling = "Low priority / insufficient data"

        if order.index(base) > order.index(ceiling):
            return ceiling

        return base

    def _rationale(
        self,
        product_type,
        problem,
        dosage_form,
        ref_plant,
        ref_compound,
        alt_plant,
        matched,
        match_quality,
        has_evidence,
        extraction,
        concentration,
        co_compounds,
        market_status,
        novelty_status,
        decision,
    ):
        basis = {
            "exact": "it contains the exact same reference compound",
            "target_verified": "it contains a chemically-related compound "
                                "that ALSO shares a validated biological "
                                "target with the reference compound",
            "class_only": "it contains a compound from the same broad "
                          "chemical family only — no shared biological "
                          "target has been confirmed yet, so this link is "
                          "a hypothesis, not evidence",
        }.get(match_quality, "an unspecified link")

        evidence_note = (
            "Real literature/evidence text was found for this pair."
            if has_evidence else
            "No literature evidence text was found yet for this "
            "plant/compound pair — this candidate's confidence has been "
            "capped accordingly until evidence is collected."
        )

        return (
            f"For {product_type} targeting {problem}, {alt_plant} is compared "
            f"with {ref_plant} because {basis} ({matched}), linked to the "
            f"reference compound {ref_compound}. Extraction fit for "
            f"{dosage_form}: {extraction or 'not clearly reported'}. "
            f"Concentration: {concentration or 'not clearly reported'}. "
            f"Co-compounds: {co_compounds or 'not clearly extracted'}. "
            f"Market: {market_status}. Novelty: {novelty_status}. "
            f"{evidence_note} Decision: {decision}."
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
        if self._curated_evidence_for(plant):
            return (
                "Curated regulatory & clinical evidence "
                "(EMA/WHO/ESCOP-reviewed, cited studies) — "
                "seed_data.SLEEP_TEA_EVIDENCE"
            )

        if evidence:
            return "Live-collected evidence (PubMed/Europe PMC/Supabase)"

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
    def _meaningful_tokens(text):
        """Word tokens from an indication string, with generic/connector
        words (&, support, health, ...) removed so token-overlap fallback
        matching only fires on genuinely distinctive shared words.
        """
        return {
            token for token in text.split()
            if token not in INDICATION_STOPWORDS and len(token) > 2
        }

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

    # ------------------------------------------------------------------ #
    # Known inventory: what is already known for this problem, before any
    # alternative-plant discovery runs. Pure offline lookup against
    # seed_data (PLANT_COMPOUNDS / COMPOUND_TARGETS / TARGET_DISEASES).
    # ------------------------------------------------------------------ #

    def known_inventory_df(self, indication):
        columns = [
            "Known_Plant",
            "Known_Compound",
            "Chemical_Class",
            "Known_Target",
            "Evidence_Level",
            "Typical_Extraction",
        ]

        indication_norm = self._norm(indication)

        if not indication_norm:
            return pd.DataFrame(columns=columns)

        if not self.plant_compounds_df.empty:
            supabase_result = self._known_inventory_from_supabase(
                indication_norm, columns
            )
            if not supabase_result.empty:
                return supabase_result

        return self._known_inventory_from_seed_data(indication_norm, columns)

    def _known_inventory_from_supabase(self, indication_norm, columns):
        """Primary path: filter the real plant_compounds table (806
        records) directly by its own `indication` column.
        """
        df = self.plant_compounds_df.copy()

        if "indication" not in df.columns:
            return pd.DataFrame(columns=columns)

        df["_indication_norm"] = df["indication"].fillna("").map(self._norm)

        mask = df["_indication_norm"].apply(
            lambda text: bool(text)
            and (indication_norm in text or text in indication_norm)
        )

        if not mask.any():
            indication_tokens = self._meaningful_tokens(indication_norm)
            mask = df["_indication_norm"].apply(
                lambda text: bool(
                    indication_tokens
                    and self._meaningful_tokens(text)
                    and indication_tokens & self._meaningful_tokens(text)
                )
                if text else False
            )

        matched = df[mask]

        if matched.empty:
            return pd.DataFrame(columns=columns)

        rows = []
        for _, row in matched.iterrows():
            known_plant = str(row.get("scientific_name") or "").strip()
            known_compound = str(row.get("compound_name") or "").strip()

            if not known_plant or not known_compound:
                continue

            rows.append({
                "Known_Plant": known_plant,
                "Known_Compound": known_compound,
                "Chemical_Class": str(row.get("compound_class") or "").strip(),
                "Known_Target": str(row.get("target") or "").strip(),
                "Evidence_Level": str(row.get("evidence_level") or "").strip(),
                "Typical_Extraction": str(row.get("extraction_method") or "").strip(),
            })

        if not rows:
            return pd.DataFrame(columns=columns)

        return (
            pd.DataFrame(rows)
            .drop_duplicates()
            .sort_values(["Known_Plant", "Known_Compound"])
            .reset_index(drop=True)
        )

    def _known_inventory_from_seed_data(self, indication_norm, columns):
        """Fallback path used only when Supabase data is unavailable:
        the small local seed_data.py dataset (~30 plants).
        """
        matched_diseases = [
            disease for disease in TARGET_DISEASES
            if indication_norm in self._norm(disease)
            or self._norm(disease) in indication_norm
        ]

        if not matched_diseases:
            indication_tokens = self._meaningful_tokens(indication_norm)
            for disease in TARGET_DISEASES:
                disease_tokens = self._meaningful_tokens(self._norm(disease))
                if indication_tokens and (indication_tokens & disease_tokens):
                    matched_diseases.append(disease)

        relevant_targets = {}
        for disease in matched_diseases:
            for target, level in TARGET_DISEASES[disease].items():
                relevant_targets[self._norm(target)] = level

        if not relevant_targets:
            return pd.DataFrame(columns=columns)

        rows = []
        for plant, compounds in PLANT_COMPOUNDS.items():
            for compound_name, chem_class, extraction in compounds:
                for target in COMPOUND_TARGETS.get(compound_name, []):
                    if self._norm(target) in relevant_targets:
                        rows.append({
                            "Known_Plant": plant,
                            "Known_Compound": compound_name,
                            "Chemical_Class": chem_class,
                            "Known_Target": target,
                            "Evidence_Level": relevant_targets[self._norm(target)],
                            "Typical_Extraction": extraction,
                        })

        if not rows:
            return pd.DataFrame(columns=columns)

        return (
            pd.DataFrame(rows)
            .drop_duplicates()
            .sort_values(["Known_Plant", "Known_Compound"])
            .reset_index(drop=True)
        )

    # ------------------------------------------------------------------ #
    # Market landscape: EU regulatory status, patents, retail products.
    #
    # This answers the "what already exists in the market" question and is
    # intentionally a SEPARATE table from run()'s decision table, not extra
    # columns bolted onto it — the OUTPUT_COLUMNS contract stays as-is.
    # ------------------------------------------------------------------ #

    def _curated_evidence_for(self, plant):
        plant_norm = self._norm(plant)
        for name, evidence in SLEEP_TEA_EVIDENCE.items():
            if self._norm(name) == plant_norm:
                return evidence
        return None

    def _eu_regulatory_status(self, plant):
        curated = self._curated_evidence_for(plant)
        if curated:
            return {
                "EMA_HMPC_Status": curated.get("ema_status", "Not evaluated"),
                "WHO_Status": curated.get("who_status", "Not listed"),
                "ESCOP_Status": curated.get("escop_status", "Not listed"),
                "Source": "Curated (seed_data.SLEEP_TEA_EVIDENCE) — manually verified",
            }
        return {
            "EMA_HMPC_Status": "Not yet verified",
            "WHO_Status": "Not yet verified",
            "ESCOP_Status": "Not yet verified",
            "Source": "No EMA HMPC bulk API exists (browse-only site) — "
                      "needs manual lookup at ema.europa.eu and adding to "
                      "seed_data.py, same pattern as the sleep-tea plants",
        }

    def _search_patents(self, query, max_results=5):
        """
        EPO Open Patent Services (OPS) — real free API, needs registration:
        https://developers.epo.org/ (free account -> consumer key/secret).
        Set env vars EPO_OPS_KEY and EPO_OPS_SECRET to activate.
        """
        if not self.use_live_search:
            return [{"status": "Skipped", "detail": "Live search disabled."}]

        key, secret = os.environ.get("EPO_OPS_KEY"), os.environ.get("EPO_OPS_SECRET")
        if not key or not secret:
            return [{
                "status": "Not configured",
                "detail": "Set EPO_OPS_KEY and EPO_OPS_SECRET (free registration "
                          "at https://developers.epo.org/) to enable patent search.",
            }]

        try:
            auth = base64.b64encode(f"{key}:{secret}".encode()).decode()
            token_r = requests.post(
                "https://ops.epo.org/3.2/auth/accesstoken",
                headers={"Authorization": f"Basic {auth}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials"},
                timeout=20,
            )
            token_r.raise_for_status()
            access_token = token_r.json().get("access_token")

            search_r = requests.get(
                "https://ops.epo.org/3.2/rest-services/published-data/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": f'ctxt="{query}"', "Range": f"1-{max_results}"},
                timeout=20,
            )
            search_r.raise_for_status()
            return [{"status": "OK", "raw_response": search_r.json()}]
        except Exception as e:
            return [{"status": "Error", "detail": str(e)}]

    def _search_retail_products(self, query):
        """
        Retail/brand product presence needs a paid web-search API (there is
        no free, structured, ToS-compliant source for 'which brands sell
        X'). Set SEARCH_API_KEY (+ optionally SEARCH_API_PROVIDER) to
        activate once you've picked a provider (Bing Web Search API,
        SerpAPI, etc.) — this function is the single place to wire it in.
        """
        if not self.use_live_search:
            return [{"status": "Skipped", "detail": "Live search disabled."}]

        api_key = os.environ.get("SEARCH_API_KEY")
        if not api_key:
            return [{
                "status": "Not configured",
                "detail": "Set SEARCH_API_KEY to a paid web-search provider "
                          "(e.g. Bing Web Search API, SerpAPI) to enable "
                          "retail/brand product scanning. No free source "
                          "exists for this data.",
            }]
        return [{
            "status": "Not implemented",
            "detail": "SEARCH_API_KEY is set, but no provider call is wired "
                      "in yet. Implement the request for your chosen "
                      "provider inside _search_retail_products().",
        }]

    def market_landscape(self, plant):
        """Single-plant market snapshot: regulatory + patents + retail."""
        return {
            "plant": plant,
            "region": get_region(plant),
            "regulatory": self._eu_regulatory_status(plant),
            "patents": self._search_patents(plant),
            "retail_products": self._search_retail_products(plant),
        }

    def market_landscape_df(self, plants):
        """Market landscape table: one row per plant."""
        rows = []
        for plant in plants:
            snap = self.market_landscape(plant)
            reg = snap["regulatory"]
            patents = snap["patents"]
            retail = snap["retail_products"]
            us_uk = get_us_uk_status(plant) or {}
            rows.append({
                "Plant": snap["plant"],
                "Region_of_Origin": snap["region"],
                "EMA_HMPC_Status": reg["EMA_HMPC_Status"],
                "WHO_Status": reg["WHO_Status"],
                "ESCOP_Status": reg["ESCOP_Status"],
                "Regulatory_Source": reg["Source"],
                "US_Status": us_uk.get(
                    "us_status", "Not yet catalogued for this plant"
                ),
                "UK_Status": us_uk.get(
                    "uk_status", "Not yet catalogued for this plant"
                ),
                "Patent_Search_Status": patents[0].get("status", "Unknown"),
                "Patent_Detail": patents[0].get("detail", patents[0].get("raw_response", "")),
                "Retail_Products_Status": retail[0].get("status", "Unknown"),
                "Retail_Products_Detail": retail[0].get("detail", ""),
            })
        return pd.DataFrame(rows)


def load_default_evidence():
    try:
        return pd.DataFrame(load_evidence_database())
    except Exception:
        return pd.DataFrame()
