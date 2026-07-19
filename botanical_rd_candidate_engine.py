import os
import re
import base64
import requests
from collections import defaultdict

import pandas as pd

try:
    from evidence_database import load_evidence_database
except Exception:
    def load_evidence_database():
        return []

try:
    from global_candidate_ranking_engine import rank_global_candidates
except Exception:
    def rank_global_candidates(*args, **kwargs):
        return pd.DataFrame()

from global_plant_candidate_database import GLOBAL_PLANT_CANDIDATES
from compound_occurrence_map import get_region

try:
    from supabase_data import (
        load_plant_compounds_df,
        load_compound_profiles_df,
        load_scientific_evidence_df,
    )
except Exception:
    def load_plant_compounds_df():
        return pd.DataFrame()

    def load_compound_profiles_df():
        return pd.DataFrame()

    def load_scientific_evidence_df():
        return pd.DataFrame()

try:
    from regulatory_frameworks import get_us_uk_status
except Exception:
    def get_us_uk_status(plant):
        return {}
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
    "Evidence_Level",
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


# Dr. Duke's own Known_Target/activity vocabulary already documents some
# compounds as having concerning properties (e.g. "Lithogenic" = promotes
# kidney stone formation, "Emetic" = induces vomiting) — this is
# structured data already present in every row, not something that needs
# a literature search to discover. Previously, safety flagging only
# scanned free-text evidence collected from PubMed/EMA/etc, so a
# compound could be labelled "Lithogenic; Inflammatory" in its own
# Target_or_Mechanism column and still be presented as an unflagged
# "Recommended" candidate. These terms are checked against the
# mechanism/target text directly, in addition to SAFETY_TERMS being
# checked against free-text evidence — for any compound, any plant, any
# indication.
DB_ACTIVITY_SAFETY_TERMS = [
    "lithogenic", "emetic", "hepatotoxic", "nephrotoxic", "neurotoxic",
    "carcinogenic", "mutagenic", "teratogenic", "abortifacient",
    "convulsant", "narcotic", "poison", "vesicant", "hemolytic",
    "nephrotoxin", "hepatotoxin", "genotoxic", "embryotoxic",
    "cardiotoxic", "irritant",
]

# Two tiers, because these are not equally trustworthy signals:
#
# HARD_SAFETY_TERMS — a clear, direct physiological/organ mechanism
# (kidney stones, liver/kidney/nerve/heart damage, induced abortion,
# convulsions, blistering, poisoning). A candidate carrying one of these
# must never appear under "Recommended", regardless of score.
#
# CONTROVERSIAL_SAFETY_TERMS — the genotoxicity-assay family
# (carcinogenic/mutagenic/genotoxic). Dr. Duke's data pulls these from
# decades-old in-vitro/bacterial (Ames-test-style) or high-dose animal
# studies, largely without real-world dose or exposure context. This is
# exactly why everyday, GRAS-recognized dietary compounds — quercetin
# (apples, onions, tea) is the clearest example in this database — carry
# these tags despite EMA/WHO/EFSA still recognizing them as safe
# traditional/food ingredients: the old assay finding is real, but on
# its own it doesn't mean the same thing clinically that, say,
# "Lithogenic" or "Hepatotoxic" does. These stay flagged and visible
# (Safety_Flags, Rationale, and a capped score) but do NOT auto-exclude
# a candidate from "Recommended" the way HARD_SAFETY_TERMS does — a
# human reviewer needs to weigh dose/context, not have it decided for
# them by a 1970s Ames test result. "Emetic" and "Irritant" are milder
# still and are excluded from both hard tiers for the same reason.
HARD_SAFETY_TERMS = set(DB_ACTIVITY_SAFETY_TERMS) - {
    "emetic", "irritant", "carcinogenic", "mutagenic", "genotoxic",
}
CONTROVERSIAL_SAFETY_TERMS = {"carcinogenic", "mutagenic", "genotoxic"}


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

# Precomputed once at import time so _curated_evidence_for() is an O(1)
# dict lookup instead of a linear scan (with a _norm() call per item)
# repeated on every single output row.
_SLEEP_TEA_EVIDENCE_NORM_MAP = {
    re.sub(r"\s+", " ", name.strip().lower()): evidence
    for name, evidence in SLEEP_TEA_EVIDENCE.items()
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

        self.target_compound_count, self.target_genericity_threshold = (
            self._build_target_frequency_index(self.compound_to_targets)
        )

        # Compound "commonality" index: for every compound, how many
        # DISTINCT plants (across the whole database, regardless of
        # indication) contain it. This is deliberately generic — it is
        # not tied to any specific plant, compound, or indication, so it
        # applies the same way whether the query is about sleep, cough,
        # skin, metabolic health, or anything else added later.
        #
        # The problem this fixes: a compound like an abundant, widely
        # distributed flavonoid can appear in hundreds/thousands of
        # unrelated plants. Before this, an "exact" name match on such a
        # compound scored identically to an exact match on a genuinely
        # rare, differentiating compound — so ubiquitous compounds
        # silently dominated Step 5/6 results for ANY indication, not
        # just one. The threshold below is derived from the actual
        # distribution of compound frequencies in whatever database is
        # loaded (90th percentile), so it self-adjusts as the database
        # grows or shrinks instead of being a hardcoded number tuned to
        # today's data.
        self.compound_plant_count, self.compound_commonality_threshold = (
            self._build_compound_frequency_index()
        )

        # A compound-specific (NOT plant-pooled) target/activity index,
        # built directly from Dr. Duke's raw data: compound -> the set of
        # activities recorded for THAT compound specifically, across
        # every plant it appears in. This is deliberately separate from
        # self.compound_to_targets (the small hand-curated
        # COMPOUND_TARGETS/compound_profiles set used for class-based
        # "target_verified" matching) — that dict doesn't cover most of
        # Dr. Duke's ~2,000+ plant database, so using it for safety
        # flagging would silently miss real DB-documented hazards like
        # Calcium Oxalate's "Lithogenic" tag. This index is used ONLY for
        # safety-flag lookups, scoped to the one compound actually
        # matched in each row — not the alternative plant's entire pooled
        # activity profile across all of its other, unrelated compounds.
        self.compound_own_targets = self._build_compound_target_index()

    def _build_compound_target_index(self):
        df = self.plant_compounds_df

        if (
            df is None or df.empty
            or "compound_name" not in df.columns
            or "target" not in df.columns
        ):
            return {}

        index = defaultdict(set)
        grouped = df.groupby(
            df["compound_name"].fillna("").map(self._norm)
        )["target"]

        for compound_norm, values in grouped:
            if not compound_norm:
                continue
            index[compound_norm].update(self._split_series_terms(values))

        return dict(index)

    def _build_compound_frequency_index(self):
        df = self.plant_compounds_df

        if (
            df is None or df.empty
            or "scientific_name" not in df.columns
            or "compound_name" not in df.columns
        ):
            return {}, None

        work = df[["scientific_name", "compound_name"]].copy()
        work["scientific_name"] = work["scientific_name"].fillna("").astype(str).str.strip()
        work["compound_norm"] = work["compound_name"].fillna("").map(self._norm)
        work = work[(work["scientific_name"] != "") & (work["compound_norm"] != "")]

        if work.empty:
            return {}, None

        counts = (
            work.drop_duplicates(["scientific_name", "compound_norm"])
            .groupby("compound_norm")["scientific_name"]
            .nunique()
        )

        plant_count_map = counts.to_dict()

        # 90th percentile of how many distinct plants each compound
        # appears in = "this compound is in the top 10% most common
        # compounds in our own database". A small floor keeps this
        # meaningful even on a tiny/sparse database (avoids flagging
        # compounds as "common" just because everything is rare so far).
        if len(counts) >= 5:
            threshold = max(float(counts.quantile(0.90)), 8.0)
        else:
            threshold = max(float(counts.max()) + 1, 8.0)

        return plant_count_map, threshold

    def _compound_commonality(self, compound_label):
        """Returns (plant_count, is_common) for a compound label that may
        include the '[similar: ...]' suffix added by _match_compounds."""
        if not compound_label:
            return 0, False

        clean = compound_label.split("[")[0].strip()
        count = self.compound_plant_count.get(self._norm(clean), 0)

        is_common = (
            self.compound_commonality_threshold is not None
            and count >= self.compound_commonality_threshold
        )

        return count, is_common

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

        # Precompute the alternative-candidate list ONCE, outside the
        # reference/compound loops below. Previously `all_candidates
        # .iterrows()` re-ran inside the innermost loop — once per
        # (reference plant × reference compound) — rebuilding pandas
        # Series objects for every one of the (now 2,000+, since the
        # Dr. Duke's import) alt-candidate rows on every single
        # iteration. With dozens of reference compounds that meant this
        # full scan happened dozens of times instead of once, which is
        # what made run() take minutes instead of seconds at this scale.
        alt_candidate_records = []
        for _, alt in all_candidates.iterrows():
            alt_plant = self._pick(alt, ["Scientific_Name"])
            if not alt_plant:
                continue
            alt_targets = self._split_terms(
                self._pick(alt, ["Known_Targets"])
            )
            alt_compounds = self._split_terms(
                self._pick(alt, ["Known_Active_Compounds"])
            )
            alt_compound_norms = [self._norm(c) for c in alt_compounds]
            alt_candidate_records.append({
                "alt_plant": alt_plant,
                "alt_compounds": alt_compounds,
                "alt_compound_norms": alt_compound_norms,
                "alt_compound_norm_map": dict(
                    zip(alt_compound_norms, alt_compounds)
                ),
                "alt_targets": alt_targets,
                "alt_target_norms": [self._norm(t) for t in alt_targets],
                "row": alt,
            })

        # Index alt-candidates by exact compound name and by chemical
        # class, so matching a single reference compound is a couple of
        # dict lookups instead of a full scan of every alt-candidate (now
        # 2,000+ since the Dr. Duke's import). _match_compounds() itself
        # is left completely unchanged below — any alt-candidate NOT
        # reachable through either index is guaranteed to return "none"
        # from it anyway (no exact-string match and no shared chemical
        # class), so this is a pure speed-up, not a behavior change.
        exact_compound_index = defaultdict(set)
        class_compound_index = defaultdict(set)
        for alt_idx, rec in enumerate(alt_candidate_records):
            for norm_c in rec["alt_compound_norms"]:
                exact_compound_index[norm_c].add(alt_idx)
                cls = self.compound_to_class.get(norm_c, "")
                if cls:
                    class_compound_index[cls].add(alt_idx)

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
            ref_target_norms = {self._norm(t) for t in ref_targets}

            for ref_compound in ref_compounds:
                if not ref_compound:
                    continue

                ref_norm = self._norm(ref_compound)
                ref_class = self.compound_to_class.get(ref_norm, "")

                candidate_idxs = set(exact_compound_index.get(ref_norm, ()))
                if ref_class:
                    candidate_idxs |= class_compound_index.get(ref_class, set())

                for alt_idx in candidate_idxs:
                    alt_record = alt_candidate_records[alt_idx]
                    alt_plant = alt_record["alt_plant"]
                    alt_compounds = alt_record["alt_compounds"]
                    alt = alt_record["row"]

                    matched_compound, match_quality, target_specificity = (
                        self._match_compounds(
                            ref_compound,
                            alt_compounds,
                            alt_norm=alt_record["alt_compound_norm_map"],
                        )
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
                    evidence_level = self._evidence_level(raw_evidence)

                    extraction = self._best_extraction(alt, raw_evidence)
                    concentration = self._extract_concentration(raw_evidence)
                    co_compounds = self._co_compounds(
                        compounds=alt_compounds,
                        matched=matched_compound,
                        compound_norms=alt_record["alt_compound_norms"],
                    )

                    target = self._target_or_mechanism_fast(
                        ref_targets,
                        ref_target_norms,
                        alt_record["alt_targets"],
                        alt_record["alt_target_norms"],
                    )

                    # Free-text safety terms found in collected literature
                    # evidence, PLUS concerning activities the database
                    # itself already documents for the SPECIFIC matched
                    # compound (e.g. "Lithogenic", "Emetic").
                    #
                    # Deliberately NOT using `target` here: for
                    # "class_only" matches (no confirmed shared target),
                    # `target` falls back to the alt plant's WHOLE pooled
                    # activity list across every compound it has — not
                    # just the one that's actually shared/matched. Using
                    # that broad fallback for a safety decision meant one
                    # unrelated compound out of dozens in a plant's full
                    # profile (Dr. Duke's data tags compounds with every
                    # activity ever reported anywhere, including from
                    # old/edge-case studies) could flag every single
                    # candidate row for that plant as a "safety concern",
                    # regardless of whether the flagged activity had
                    # anything to do with the compound actually being
                    # proposed. Looking up only the matched compound's own
                    # known activities keeps this precise, for any
                    # compound, any plant, any indication.
                    matched_clean = matched_compound.split("[")[0].strip()
                    matched_own_targets = self.compound_own_targets.get(
                        self._norm(matched_clean), set()
                    )

                    safety_flags = self._extract_flags(
                        raw_evidence,
                        SAFETY_TERMS,
                    )
                    db_safety_flags = self._extract_flags(
                        "; ".join(matched_own_targets),
                        DB_ACTIVITY_SAFETY_TERMS,
                    )
                    if db_safety_flags:
                        pieces = []
                        if safety_flags:
                            pieces.extend(safety_flags.split("; "))
                        pieces.extend(db_safety_flags.split("; "))
                        safety_flags = "; ".join(sorted(set(pieces)))

                    interaction_flags = self._extract_flags(
                        raw_evidence,
                        INTERACTION_TERMS,
                    )

                    market_status = self._market_status(
                        alt=alt,
                        evidence=raw_evidence,
                        market=market,
                    )

                    # How many distinct plants (in the WHOLE database,
                    # independent of this indication) already contain the
                    # matched compound. This is the generic signal used
                    # below to stop ubiquitous compounds (found across
                    # hundreds/thousands of unrelated species) from being
                    # scored/labelled as if they were a specific,
                    # differentiating match — for any indication, any
                    # plant, any compound.
                    compound_plant_count, compound_is_common = (
                        self._compound_commonality(matched_compound)
                    )

                    novelty_status = self._novelty_status(
                        ref_plant=ref_plant,
                        alt_plant=alt_plant,
                        matched=matched_compound,
                        ref_compound=ref_compound,
                        alt=alt,
                        compound_is_common=compound_is_common,
                        compound_plant_count=compound_plant_count,
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
                        evidence_level=evidence_level,
                        compound_plant_count=compound_plant_count,
                        target_specificity=target_specificity,
                    )

                    decision = self._decision_class(
                        score=score,
                        safety_flags=safety_flags,
                        interaction_flags=interaction_flags,
                        has_evidence=has_real_evidence,
                        match_quality=match_quality,
                        evidence_level=evidence_level,
                        compound_is_common=compound_is_common,
                        target_specificity=target_specificity,
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
                            "Evidence_Level": evidence_level,
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
                                evidence_level=evidence_level,
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

        output = self._merge_multi_compound_matches(output)

        output = output.sort_values(
            by=["R&D_Opportunity_Score"],
            ascending=False,
        ).reset_index(drop=True)

        return output[OUTPUT_COLUMNS]

    def _merge_multi_compound_matches(self, output):
        """When the SAME alternative plant matches the SAME reference
        plant on more than one distinct compound (e.g. it independently
        contains both reference compound X and reference compound Z), that
        is a materially stronger candidate than one that only shares a
        single compound — it means multiple active substances line up, not
        just one. Previously each compound match became its own separate
        row with no acknowledgment that they came from the same
        plant/plant pairing. This merges those rows into one, combines the
        matched compounds into a single field, and adds a score bonus per
        additional independently-matched compound (capped, and still
        subject to the same safety/evidence caps as any other candidate).
        """
        if output.empty:
            return output

        group_keys = (
            output["Reference_Plant"].map(self._norm)
            + "||" + output["Alternative_Plant"].map(self._norm)
        )

        order = [
            "Low priority / insufficient data",
            "Early-stage candidate; more evidence needed",
            "Promising candidate; verify safety and standardization",
            "Strong R&D candidate",
        ]

        merged_rows = []

        for _, group in output.groupby(group_keys, sort=False):
            if len(group) == 1:
                merged_rows.append(group.iloc[0].to_dict())
                continue

            group = group.sort_values("R&D_Opportunity_Score", ascending=False)
            best = group.iloc[0].to_dict()

            distinct_ref_compounds = self._unique_clean_list(group["Reference_Compound"])
            distinct_matched = self._unique_clean_list(group["Shared_or_Similar_Compound"])
            num_matches = len(distinct_matched)

            if num_matches <= 1:
                merged_rows.append(best)
                continue

            bonus = min(20, (num_matches - 1) * 10)
            new_score = round(min(100, best["R&D_Opportunity_Score"] + bonus), 1)

            risky = any(
                str(v).strip() and str(v).strip() != "No explicit flag found"
                for v in group["Safety_Flags"]
            ) or any(
                str(v).strip() and str(v).strip() != "No explicit flag found"
                for v in group["Interaction_Flags"]
            )

            if new_score >= 78 and not risky:
                new_decision = "Strong R&D candidate"
            elif new_score >= 62:
                new_decision = "Promising candidate; verify safety and standardization"
            elif new_score >= 45:
                new_decision = "Early-stage candidate; more evidence needed"
            else:
                new_decision = "Low priority / insufficient data"

            # Stay conservative: never let the merge produce a HIGHER
            # confidence tier than the most cautious individual match
            # already earned (e.g. if one of the matches has no real
            # evidence behind it, the merged row shouldn't claim more
            # confidence than that).
            tightest = min(
                (str(d) for d in group["Decision_Class"]),
                key=lambda d: order.index(d) if d in order else 0,
            )
            if order.index(new_decision) > order.index(tightest):
                new_decision = tightest

            best["Reference_Compound"] = "; ".join(distinct_ref_compounds)
            best["Shared_or_Similar_Compound"] = "; ".join(distinct_matched)
            best["R&D_Opportunity_Score"] = new_score
            best["Decision_Class"] = new_decision
            best["Rationale"] = (
                f"Matches {num_matches} independent reference compounds "
                f"({', '.join(distinct_matched)}) — a materially stronger "
                f"signal than a single shared compound. " + str(best["Rationale"])
            )

            merged_rows.append(best)

        return pd.DataFrame(merged_rows)

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
                return direct.head(max_reference_plants)

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

        # Also check the known_inventory-based fallback (TARGET_DISEASES ->
        # COMPOUND_TARGETS -> PLANT_COMPOUNDS / Supabase plant_compounds) —
        # the same chain Step 1/Step 4 ("Existing Scientific Knowledge")
        # already uses successfully. A plant only gets manually tagged with
        # an exact indication in GLOBAL_PLANT_CANDIDATES for a handful of
        # cases (e.g. only Centella asiatica is tagged "Wound healing",
        # even though 20+ other plants have wound-healing-relevant
        # compounds per COMPOUND_TARGETS). Whichever source finds MORE
        # reference plants wins, instead of always stopping at the first
        # non-empty one — otherwise a single narrowly-tagged plant silently
        # shadows a much richer, already-working result.
        from_inventory = self._reference_plants_from_known_inventory(
            problem, max_reference_plants
        )

        if len(from_inventory) > len(ranked):
            ranked = from_inventory

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
        """Reference plants AND their reference compounds, both selected
        directly from the real plant_compounds table's own `indication`
        column — not from the pre-aggregated, whole-plant candidate_data.

        This matters because a single plant can have dozens of compound
        rows spanning many unrelated conditions (e.g. one of Valeriana
        officinalis's compounds is linked, through Dr. Duke's broad
        activity->condition chain, to 90+ conditions from Cancer to
        Wrinkles). Grouping by plant alone and using ALL of its known
        compounds as "reference compounds" for whatever indication is
        being queried would pull in compounds that have nothing to do
        with that specific indication. Filtering the raw rows FIRST means
        only compounds actually tagged for THIS indication become
        reference compounds — exactly the "only the active compound
        relevant to this specific disease" behavior the discovery
        pipeline is meant to have.
        """
        problem_norm = self._norm(problem)

        df = self.plant_compounds_df

        if (
            df is None or df.empty
            or "indication" not in df.columns
            or "scientific_name" not in df.columns
            or "compound_name" not in df.columns
        ):
            return self._reference_plants_from_candidate_data(
                problem, max_reference_plants
            )

        indication_norm = df["indication"].fillna("").map(self._norm)

        mask = indication_norm.apply(
            lambda text: bool(text)
            and (problem_norm in text or text in problem_norm)
        )

        # Always ALSO compute the token-overlap mask and OR it in, rather
        # than only falling back to it when the exact/substring mask found
        # literally nothing. A single old/narrow row whose indication text
        # happens to substring-match the query (e.g. one legacy row tagged
        # exactly "Menstrual / PMS support") was enough to make mask.any()
        # True, which silently discarded hundreds of better token-matched
        # rows that would otherwise have been found — collapsing 991
        # matched plants down to just the 1 behind that narrow match.
        problem_tokens = self._meaningful_tokens(problem_norm)
        token_mask = indication_norm.apply(
            lambda text: bool(text)
            and self._tokens_overlap(
                problem_tokens, self._meaningful_tokens(text)
            )
        )
        mask = mask | token_mask

        matched_rows = df[mask]

        if matched_rows.empty:
            return pd.DataFrame()

        rows = []
        for plant, group in matched_rows.groupby("scientific_name"):
            compounds = self._unique_clean_list(group["compound_name"])
            if not compounds:
                continue

            targets = []
            if "target" in group.columns:
                targets = self._unique_clean_list(
                    self._split_series_terms(group["target"])
                )

            rows.append({
                "Scientific_Name": plant,
                "Known_Active_Compounds": ", ".join(compounds),
                "Known_Targets": "; ".join(targets),
                # Specificity proxy: how many indication-matched compound
                # rows this plant has for THIS query — used only as a
                # tiebreaker below, smaller/more-focused first.
                "_num_matched_rows": len(group),
            })

        if not rows:
            return pd.DataFrame()

        rows.sort(key=lambda r: r["_num_matched_rows"])

        for r in rows:
            del r["_num_matched_rows"]

        return pd.DataFrame(rows[:max_reference_plants])

    def _reference_plants_from_candidate_data(self, problem, max_reference_plants):
        """Fallback used only when the raw plant_compounds_df doesn't have
        the columns needed for row-level indication filtering (e.g. a
        candidate_data override was supplied directly instead of a real
        Supabase table). Less precise than the row-level method above —
        this works off whole-plant aggregated compound lists — but keeps
        old override-based usage working.
        """
        problem_norm = self._norm(problem)

        exact_matched = [
            item for item in self.candidate_data
            if any(
                problem_norm in self._norm(indication)
                or self._norm(indication) in problem_norm
                for indication in item.get("Indications", [])
            )
        ]

        problem_tokens = self._meaningful_tokens(problem_norm)
        token_matched = [
            item for item in self.candidate_data
            if problem_tokens
            and any(
                self._tokens_overlap(
                    problem_tokens,
                    self._meaningful_tokens(self._norm(indication)),
                )
                for indication in item.get("Indications", [])
            )
        ]

        # Union both, preserving order, deduplicated by Scientific_Name.
        # As with _reference_plants_from_supabase above: a single narrow
        # exact-substring match must not suppress the (usually much
        # richer) token-overlap matches.
        seen_names = set()
        matched = []
        for item in exact_matched + token_matched:
            name = item.get("Scientific_Name")
            if name not in seen_names:
                seen_names.add(name)
                matched.append(item)

        if not matched:
            return pd.DataFrame()

        def _specificity_key(item):
            indications_text = "; ".join(item.get("Indications", []))
            return len(indications_text)

        matched = sorted(matched, key=_specificity_key)

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
        alt_norm=None,
    ):
        """Returns (matched_compound_label, match_quality, target_specificity).

        match_quality is one of:
          "exact"           - the alternative plant contains the exact
                               same reference compound.
          "target_verified" - a different compound, in the same broad
                               chemical class, that ALSO shares a known
                               biological target with the reference
                               compound (per seed_data.COMPOUND_TARGETS).
                               How MUCH this is worth is not a yes/no —
                               see target_specificity below.
          "class_only"       - a different compound sharing only the
                               broad chemical class label (e.g. both are
                               "flavonoids"), with no shared target at
                               all — a weak, hypothesis-level link.
          "none"             - no match at all.

        target_specificity is the number of DISTINCT compounds (across
        the whole COMPOUND_TARGETS / compound_profiles knowledge base)
        that carry the best (rarest) shared target — or None when
        match_quality isn't "target_verified". This is deliberately a
        continuous count, not a binary "generic vs specific" classifier:
        an early version used a single statistical cutoff (90th
        percentile of target frequency) to split target_verified into a
        "strong" and "weak" tier, but on a database this size that
        cutoff has a hard edge — a pathway shared by 5 compounds got a
        full score, one shared by 6 got almost none, even though neither
        is meaningfully more specific than the other. The count is
        instead fed into _score_candidate, which discounts the
        chemical-link bonus smoothly as the shared target gets less
        specific (see there), for any pathway, any chemical class, any
        indication — no hardcoded cutoff to sit right next to.

        `alt_norm` (norm(compound) -> original compound) can be passed in
        precomputed once per alt-candidate, instead of being rebuilt from
        `alternative_compounds` on every call — at Dr. Duke's data scale
        this function is called millions of times per run(), and rebuilding
        this dict every time was a major hot spot.
        """
        ref = self._norm(reference_compound)

        if alt_norm is None:
            alt_norm = {
                self._norm(compound): compound
                for compound in alternative_compounds
            }

        if ref in alt_norm:
            return alt_norm[ref], "exact", None

        ref_class = self.compound_to_class.get(ref, "")

        if not ref_class:
            return "", "none", None

        ref_targets = self.compound_to_targets.get(ref, set())

        class_matches = [
            alt_value
            for alt_key, alt_value in alt_norm.items()
            if self.compound_to_class.get(alt_key, "") == ref_class
        ]

        if not class_matches:
            return "", "none", None

        if ref_targets:
            # Across every class-mate, find whichever shared target is
            # the RAREST (lowest compound_count) — that is the strongest
            # possible confirmation available for this pair, and its
            # count is what determines how much it's actually worth.
            best = None  # (alt_value, target, count)

            for alt_value in class_matches:
                alt_targets = self.compound_to_targets.get(
                    self._norm(alt_value), set()
                )
                shared = alt_targets & ref_targets
                for target in shared:
                    count, _ = self._target_specificity(target)
                    if best is None or count < best[2]:
                        best = (alt_value, target, count)

            if best is not None:
                alt_value, target, count = best
                return (
                    f"{alt_value} [similar: {ref_class}; shared target: "
                    f"{target} (shared by {count} known compounds)]",
                    "target_verified",
                    count,
                )

        return (
            f"{class_matches[0]} [similar: {ref_class}; class-only, "
            f"target not confirmed]",
            "class_only",
            None,
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

    def _build_target_frequency_index(self, compound_to_targets):
        """Same idea as _build_compound_frequency_index, but for TARGETS
        instead of compound names.

        Why this is needed: fixing compound-name commonality alone (e.g.
        for an abundant flavonoid matched by exact name) does not fix a
        second, independent source of over-matching — "target_verified"
        matches confirmed only through a broad mechanism/pathway label
        (e.g. "NF-kB", "Anti-inflammatory pathways", "Oxidative stress
        pathways") that dozens of unrelated compounds in the same broad
        chemical class ALSO happen to be tagged with. Two flavonoids
        sharing a pathway that most flavonoids share is not a specific,
        differentiating confirmation — it is nearly as generic as bare
        class membership. This applies to any chemical class or
        indication, not just flavonoids, so the threshold is again
        derived from the actual data rather than a hardcoded pathway
        list.
        """
        target_to_compounds = defaultdict(set)
        for compound, targets in compound_to_targets.items():
            for target in targets:
                target_to_compounds[target].add(compound)

        counts = {t: len(compounds) for t, compounds in target_to_compounds.items()}

        if not counts:
            return counts, None

        values = sorted(counts.values())
        n = len(values)
        if n >= 5:
            idx = int(round(0.90 * (n - 1)))
            threshold = max(float(values[idx]), 4.0)
        else:
            threshold = max(float(values[-1]) + 1, 4.0)

        return counts, threshold

    def _target_specificity(self, target_norm):
        """Returns (compound_count, is_generic) for a single normalized
        target/pathway label."""
        count = self.target_compound_count.get(target_norm, 0)
        is_generic = (
            self.target_genericity_threshold is not None
            and count >= self.target_genericity_threshold
        )
        return count, is_generic

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
        evidence_level="No direct evidence",
        compound_plant_count=0,
        target_specificity=None,
    ):
        score = 0

        # 1) Chemical/mechanistic link. Exact shared compound is strong;
        # target-verified similarity is moderate; class-only similarity
        # is weak. The target-verified bonus below is further scaled by
        # HOW specific the confirming shared target actually is.
        if match_quality == "exact":
            chem_bonus = 22
        elif match_quality == "target_verified":
            chem_bonus = 15
        else:
            chem_bonus = 5

        # A "target_verified" match is only as informative as the target
        # itself is specific. Two compounds sharing a pathway that only
        # 2 compounds in the whole knowledge base carry is a real,
        # differentiating confirmation. Two compounds sharing a pathway
        # that 20 compounds carry (e.g. "Anti-inflammatory pathways") is
        # barely more informative than bare class membership. This is
        # deliberately a smooth 1/count decay rather than a single
        # "generic vs specific" statistical cutoff — a fixed cutoff has
        # a hard edge (a target shared by 5 compounds scored completely
        # differently from one shared by 6), which doesn't reflect
        # reality and doesn't generalize well to a knowledge base this
        # size. This applies the same way to any pathway, any chemical
        # class, any indication.
        if match_quality == "target_verified" and target_specificity:
            # Full bonus only when the shared target is carried by 2
            # compounds (the minimum for it to be "shared" at all);
            # decays smoothly as more compounds carry it.
            chem_bonus *= min(1.0, 2.0 / target_specificity)

        # A compound found in only a handful of plants IS the strong
        # signal this score is meant to reward — two species sharing a
        # rare, specific compound is genuinely informative. A compound
        # found across hundreds/thousands of unrelated plants tells you
        # almost nothing about THIS pair, no matter which two plants it
        # is (any indication, any species) — so its contribution is
        # scaled down smoothly as commonality grows, using the same
        # database-derived threshold everywhere in the engine, rather
        # than being capped by a fixed number of "known common
        # compounds".
        threshold = self.compound_commonality_threshold
        if threshold and compound_plant_count > 0:
            # 1x threshold -> no penalty yet; 4x threshold or more -> up
            # to ~80% of the chemical-link bonus removed.
            overage = max(0.0, (compound_plant_count / threshold) - 1.0)
            penalty_ratio = min(0.8, overage / 3.0)
            chem_bonus = chem_bonus * (1 - penalty_ratio)

        score += chem_bonus

        # 2) Evidence quality. The previous engine rewarded any text too much.
        # Here weak/no evidence cannot produce a high-confidence candidate.
        evidence_points = {
            "Clinical / human evidence": 24,
            "Regulatory / monograph evidence": 20,
            "Preclinical / mechanistic evidence": 12,
            "General literature signal": 7,
            "No direct evidence": 0,
        }
        score += evidence_points.get(evidence_level, 0)

        # 3) Product-development fit. These matter, but they must not
        # overpower poor evidence.
        score += 10 if concentration else 2
        score += min(18, self._extraction_fit_score(extraction, dosage_form))
        score += min(8, len(self._split_terms(co_compounds)) * 2)
        score += 8 if target else 1

        # 4) Novelty is valuable only after some scientific basis exists.
        # A "common compound" novelty label (see _novelty_status) must
        # NOT collect this bonus — a compound found everywhere is the
        # opposite of a novel, differentiating finding.
        if evidence_level != "No direct evidence":
            if "Common" in novelty_status or "non-specific" in novelty_status:
                score += 0
            elif "Alternative" in novelty_status or "Cross-region" in novelty_status:
                score += 10
            else:
                score += 2

        # 5) Market signal is a small modifier, not the core scientific score.
        market_lower = market_status.lower()
        if "saturated" in market_lower:
            score += 1
        elif "emerging" in market_lower or "white-space" in market_lower:
            score += 6
        else:
            score += 3

        # 6) Penalize safety and interaction flags strongly. A candidate with
        # clear safety issues should not be presented as attractive without
        # qualification.
        if safety_flags:
            score -= 14

        if interaction_flags:
            score -= 10

        if same_plant:
            score -= 15

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
        compound_is_common=False,
        compound_plant_count=0,
    ):
        if self._norm(ref_plant) == self._norm(alt_plant):
            return "Reference plant / benchmark"

        matched_clean = matched.split("[")[0].strip()

        # A compound this common tells you almost nothing about THIS
        # specific plant pair, whatever indication or species are
        # involved — so it must not be labelled as if it were a
        # meaningful "alternative source" finding.
        if compound_is_common:
            return (
                f"Common/non-specific compound — found in "
                f"{compound_plant_count}+ plants database-wide, "
                f"low differentiation value"
            )

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
        evidence_level="No direct evidence",
        compound_is_common=False,
        target_specificity=None,
    ):
        # A documented serious toxicity (kidney-stone formation,
        # carcinogenicity, organ toxicity, etc.) is a hard stop: no score,
        # no amount of "shared compound" chemistry, and no evidence level
        # should ever let such a candidate be labelled "Strong" or
        # "Promising" and surface under "Recommended". Previously this
        # only capped the ceiling at "Promising candidate; verify safety
        # and standardization" — but that string still contains the word
        # "promising", so the Step 6 UI's keyword filter kept showing
        # candidates like calcium oxalate (documented as "Lithogenic") in
        # the Recommended table. This check happens first and overrides
        # everything else below, for any compound, any plant, any
        # indication.
        flagged_terms = {
            term.strip() for term in safety_flags.split("; ") if term.strip()
        }
        if flagged_terms & HARD_SAFETY_TERMS:
            return "Safety concern — not suitable without expert review"

        # Controversial-only flags (carcinogenic/mutagenic/genotoxic with
        # no accompanying hard-tier term) fall straight through past the
        # hard-exclusion check above — they don't force exclusion. They
        # still can't reach "Strong" on their own: `safety_flags` being
        # non-empty already makes `risky` True below, which caps the
        # ceiling at "Promising candidate; verify safety and
        # standardization" — visible and capped, but a human still gets
        # to see and weigh it rather than having it silently excluded.
        risky = bool(safety_flags) or bool(interaction_flags)

        if score >= 78 and not risky:
            base = "Strong R&D candidate"
        elif score >= 62:
            base = "Promising candidate; verify safety and standardization"
        elif score >= 45:
            base = "Early-stage candidate; more evidence needed"
        else:
            base = "Low priority / insufficient data"

        order = [
            "Low priority / insufficient data",
            "Early-stage candidate; more evidence needed",
            "Promising candidate; verify safety and standardization",
            "Strong R&D candidate",
        ]

        # Confidence caps make the output scientifically defensible.
        if not has_evidence or evidence_level == "No direct evidence":
            ceiling = (
                "Promising candidate; verify safety and standardization"
                if match_quality == "exact"
                else "Early-stage candidate; more evidence needed"
            )
        elif evidence_level in {"General literature signal", "Preclinical / mechanistic evidence"}:
            ceiling = "Promising candidate; verify safety and standardization"
        elif risky:
            ceiling = "Promising candidate; verify safety and standardization"
        else:
            ceiling = "Strong R&D candidate"

        # A match resting on a compound found across hundreds/thousands
        # of unrelated plants database-wide is not, by itself, strong
        # enough scientific grounds for a top-tier recommendation —
        # regardless of which plant, compound, or indication is involved.
        # Genuinely strong independent evidence (clinical or regulatory)
        # can still carry a candidate to "Strong", since that no longer
        # relies on the compound match being specific. The same applies
        # to a "target_verified" match whose confirming shared target is
        # carried by several other compounds too — a weak confirmation,
        # even if not literally "generic" by any fixed cutoff.
        weak_target_match = (
            match_quality == "target_verified"
            and target_specificity
            and target_specificity > 4
        )
        needs_cap = compound_is_common or weak_target_match
        if needs_cap and evidence_level not in {
            "Clinical / human evidence",
            "Regulatory / monograph evidence",
        }:
            common_ceiling = "Early-stage candidate; more evidence needed"
            if order.index(common_ceiling) < order.index(ceiling):
                ceiling = common_ceiling

        if order.index(base) > order.index(ceiling):
            return ceiling

        return base

    def _evidence_level(self, evidence):
        text = self._norm(evidence)
        if not text:
            return "No direct evidence"

        # Specific, multi-word phrases that actually indicate a real
        # clinical study design — deliberately NOT single common words
        # like "human", "patient", "subjects", or "participants". Those
        # generic words show up constantly in evidence text that has
        # NOTHING to do with an actual clinical trial (safety
        # disclaimers, food-use history, unrelated abstracts pooled in
        # from other records about the same plant) — using them as
        # triggers was silently classifying the vast majority of
        # candidates as having "Clinical / human evidence" regardless of
        # whether any such evidence actually existed.
        clinical_terms = [
            "clinical trial", "randomized controlled trial",
            "randomised controlled trial", "double-blind", "double blind",
            "placebo-controlled", "placebo controlled", "human trial",
            "human study", "clinical study", "cohort study",
            "case-control study", "phase i trial", "phase ii trial",
            "phase iii trial", "meta-analysis", "systematic review",
            "clinicaltrials.gov",
        ]
        regulatory_terms = [
            "ema", "hmpc", "hmcp", "escop", "who monograph", "monograph",
            "traditional use", "well-established use",
        ]
        preclinical_terms = [
            "in vitro", "in vivo", "animal model", "mouse model",
            "rat model", "mechanism of action", "signaling pathway",
            "receptor binding", "enzyme inhibition",
        ]

        # A term immediately preceded by a negation cue within a short
        # word window doesn't count as positive evidence — "no clinical
        # trials have been conducted" and "insufficient human studies"
        # should not be scored the same as an actual reported trial.
        negation_cues = (
            "no ", "not ", "lack of ", "lacks ", "insufficient ",
            "absence of ", "without ", "none found", "no evidence of ",
            "no direct ", "unproven", "unconfirmed", "no reported ",
        )

        def _has_term(terms):
            for term in terms:
                idx = text.find(term)
                while idx != -1:
                    window_start = max(0, idx - 40)
                    preceding = text[window_start:idx]
                    if not any(cue in preceding[-25:] for cue in negation_cues):
                        return True
                    idx = text.find(term, idx + 1)
            return False

        if _has_term(clinical_terms):
            return "Clinical / human evidence"
        if _has_term(regulatory_terms):
            return "Regulatory / monograph evidence"
        if _has_term(preclinical_terms):
            return "Preclinical / mechanistic evidence"
        return "General literature signal"

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
        evidence_level,
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
                                "target with the reference compound (see "
                                "the compound column for how many other "
                                "known compounds also carry that target — "
                                "fewer means a more specific, meaningful "
                                "link)",
            "class_only": "it contains a compound from the same broad "
                          "chemical family only — no shared biological "
                          "target has been confirmed yet, so this link is "
                          "a hypothesis, not evidence",
        }.get(match_quality, "an unspecified link")

        evidence_note = (
            f"Evidence level: {evidence_level}."
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

    @staticmethod
    def _target_or_mechanism_fast(
        ref_targets, ref_target_norms, alt_targets, alt_target_norms
    ):
        """Same result as _target_or_mechanism, but takes pre-normalized
        target lists so it does zero _norm() calls itself. At Dr. Duke's
        scale, target lists can be long (a compound's activities list),
        and re-normalizing both sides on every single (reference, alt)
        pair — instead of once per reference and once per alt-candidate —
        was responsible for the vast majority of run()'s runtime (tens of
        millions of redundant _norm() calls for a single indication).
        """
        shared = [
            target
            for target, norm in zip(alt_targets, alt_target_norms)
            if norm in ref_target_norms
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

    def _co_compounds(self, compounds, matched, compound_norms=None):
        matched_base = self._norm(matched.split("[")[0])

        if compound_norms is None:
            compound_norms = [self._norm(c) for c in compounds]

        co_compounds = [
            compound
            for compound, norm in zip(compounds, compound_norms)
            if norm != matched_base
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

        Splits on ANY run of non-alphanumeric characters, not just
        whitespace — e.g. Dr. Duke's "Premenstrual Syndrome/PMS" must
        become the two separate tokens "syndrome" and "pms", not one
        glued "syndrome/pms" token that can never match a standalone
        "pms" query token.
        """
        raw_tokens = re.split(r"[^a-z0-9]+", text)
        return {
            token for token in raw_tokens
            if token not in INDICATION_STOPWORDS and len(token) > 2
        }

    @staticmethod
    def _tokens_overlap(tokens_a, tokens_b):
        """True on exact token overlap OR when one token is a substring
        of another (both >=5 chars, to avoid noisy short-string false
        positives). Plain set intersection alone misses real matches like
        "menstrual" vs "premenstrual" — same underlying condition, just a
        prefixed spelling — which silently starved indications of any
        Supabase-backed match and fell back to a single old manually
        curated plant instead of the real, much richer dataset.
        """
        if not tokens_a or not tokens_b:
            return False
        if tokens_a & tokens_b:
            return True
        for a in tokens_a:
            for b in tokens_b:
                if len(a) >= 5 and len(b) >= 5 and (a in b or b in a):
                    return True
        return False

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

        indication_tokens = self._meaningful_tokens(indication_norm)
        token_mask = df["_indication_norm"].apply(
            lambda text: bool(text)
            and self._tokens_overlap(
                indication_tokens, self._meaningful_tokens(text)
            )
        )
        mask = mask | token_mask

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

        indication_tokens = self._meaningful_tokens(indication_norm)
        for disease in TARGET_DISEASES:
            if disease in matched_diseases:
                continue
            disease_tokens = self._meaningful_tokens(self._norm(disease))
            if self._tokens_overlap(indication_tokens, disease_tokens):
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
        return _SLEEP_TEA_EVIDENCE_NORM_MAP.get(self._norm(plant))

    def _eu_regulatory_status(self, plant):
        curated = self._curated_evidence_for(plant)
        if curated:
            return {
                "EMA_HMPC_Status": curated.get("ema_status", "Not evaluated"),
                "WHO_Status": curated.get("who_status", "Not listed"),
                "ESCOP_Status": curated.get("escop_status", "Not listed"),
                "Source": "Curated (seed_data.SLEEP_TEA_EVIDENCE) — manually verified",
            }

        try:
            from ema_regulatory_connector import search_regulatory_sources_real
            records = search_regulatory_sources_real(plant)
            if records:
                r = records[0]
                return {
                    "EMA_HMPC_Status": r.get("EMA_Status", "Not yet verified"),
                    "WHO_Status": r.get("WHO_Status", "Not yet verified"),
                    "ESCOP_Status": r.get("ESCOP_Status", "Not yet verified"),
                    "Source": r.get("Notes", "") + f" ({r.get('Source_URL', '')})",
                }
        except Exception:
            pass

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
