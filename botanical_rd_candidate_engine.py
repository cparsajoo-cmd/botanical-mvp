import os
import re
import base64
import requests
from collections import defaultdict

import pandas as pd

from concentration_normalizer import parse_concentration, format_concentration_info
from evidence_hierarchy_classifier import classify_evidence_hierarchy
from negative_evidence_classifier import classify_negative_evidence
from evidence_confidence import compute_evidence_confidence, confidence_adjusted_framing_note
from decision_class_ah import classify_decision_ah
from white_space_classifier import classify_white_space

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
    "Target_Provenance",
    "Concentration_Info",
    "Extraction_Method",
    "Co_Compounds",
    "Safety_Flags",
    "Interaction_Flags",
    "Evidence_Source",
    "Source_Record_IDs",
    "Occurrence_Corroboration",
    "Evidence_Level",
    "Evidence_Hierarchy_Detail",
    "Has_Negative_Evidence",
    "Negative_Evidence_Types",
    "Market_Status",
    "Novelty_Status",
    "R&D_Opportunity_Score",
    "Evidence_Confidence",
    "Decision_Class",
    "Decision_Class_AH",
    "White_Space_Type",
    "Confidence_Note",
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
# HARD_SAFETY_TERMS — a clear, direct physiological/mechanical/
# reproductive mechanism with no common "protective against" research
# framing to confuse it with (kidney stones, induced abortion,
# convulsions, blistering, poisoning, blood-cell destruction). A
# candidate carrying one of these must never appear under "Recommended",
# regardless of score.
#
# CONTROVERSIAL_SAFETY_TERMS — two distinct families that share the same
# underlying problem: Dr. Duke's activity tags are extracted from
# publication text without distinguishing "compound X CAUSES this" from
# "compound X PROTECTS AGAINST this caused by something else".
#   1. The genotoxicity-assay family (carcinogenic/mutagenic/genotoxic)
#      — typically from decades-old in-vitro/bacterial (Ames-test-style)
#      or high-dose animal studies, without real-world dose/exposure
#      context.
#   2. The organ-toxicity family (hepatotoxic/nephrotoxic/cardiotoxic/
#      neurotoxic) — verified this is a real, systematic mislabeling
#      risk, not a one-off: "flavonoid protects against
#      doxorubicin-induced cardiotoxicity", "...cisplatin-induced
#      nephrotoxicity", "...against drug-induced hepatotoxicity" are
#      each themselves extremely common, standard study designs across
#      hundreds of published papers on plant compounds — a naive
#      extraction pass over that literature will tag the PROTECTIVE
#      compound with the organ-toxicity word just as readily as it would
#      tag an actual causative agent. Quercetin is the clearest confirmed
#      case (LiverTox/NIH: "well tolerated... not linked to serum enzyme
#      elevations or clinically apparent liver injury... likelihood
#      score E [unlikely cause]", while numerous studies show it
#      protecting against hepatotoxicity induced by other agents) — but
#      the same "protects against X-induced Y-toxicity" paradigm is
#      equally standard for nephro-, cardio-, and neuro-toxicity, so the
#      same risk applies to all four, for any compound, not just this
#      one.
# These stay flagged and visible (Safety_Flags, Rationale, and a capped
# score — never "Strong") but do NOT auto-exclude a candidate from
# "Recommended" the way HARD_SAFETY_TERMS does — a human reviewer needs
# to read the actual finding and weigh dose/context/causal direction,
# not have it decided for them by a keyword co-occurrence. "Emetic" and
# "Irritant" are milder still and are excluded from both hard tiers for
# the same reason.
HARD_SAFETY_TERMS = set(DB_ACTIVITY_SAFETY_TERMS) - {
    "emetic", "irritant",
    "carcinogenic", "mutagenic", "genotoxic",
    "hepatotoxic", "hepatotoxin", "nephrotoxic", "nephrotoxin",
    "cardiotoxic", "neurotoxic",
}
CONTROVERSIAL_SAFETY_TERMS = {
    "carcinogenic", "mutagenic", "genotoxic",
    "hepatotoxic", "hepatotoxin", "nephrotoxic", "nephrotoxin",
    "cardiotoxic", "neurotoxic",
}


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

        self.compound_to_class, self.compound_to_targets, self.compound_to_target_sources = (
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

        all_candidates = self._candidate_frame()

        if reference_plant:
            # A user who explicitly names a reference plant already knows
            # their starting point — they shouldn't be at the mercy of
            # whatever (at most `max_reference_plants`, default 12)
            # plants the indication-based selection happens to surface
            # first. Previously this searched only within that small,
            # indication-restricted shortlist post-hoc (line below used
            # to be `for _, ref in references.iterrows()` where
            # `references` came from _get_reference_plants() BEFORE this
            # name filter ran) — if the named plant wasn't among those
            # first ~12 candidates, EVERY row got filtered out and Step 5
            # silently returned "No R&D candidates found", regardless of
            # whether the plant actually exists in the database at all.
            # Searching the full, unrestricted candidate universe here
            # instead means an explicitly-named reference plant is found
            # whenever it exists anywhere in the database, for any
            # indication, any plant.
            #
            # _norm_taxon (not just _norm) is used for this comparison:
            # many real botanical database entries use full taxonomic
            # nomenclature — a hybrid marker ("×"/" x ") and
            # infraspecific rank qualifiers ("subsp.", "var.", "f.",
            # "cv.") — that a person typing a common working name (e.g.
            # "Mentha piperita" for what the database has filed as
            # "Mentha x piperita subsp. nothosubsp. piperita") won't
            # include. Plain substring matching breaks here because the
            # hybrid marker sits in the middle, splitting what would
            # otherwise be a clean substring match. Stripping these
            # taxonomic embellishments before comparing (for matching
            # purposes only — the database's full name is still what's
            # displayed and used downstream) fixes this for any hybrid
            # or infraspecific taxon, not just this one species.
            name_norm = self._norm_taxon(reference_plant)
            references = all_candidates[
                all_candidates["Scientific_Name"].map(self._norm_taxon).apply(
                    lambda n: name_norm in n or n in name_norm
                )
            ]
        else:
            references = self._get_reference_plants(
                problem=problem,
                dosage_form=dosage_form,
                market=market,
                max_reference_plants=max_reference_plants,
            )

        if references.empty:
            return pd.DataFrame(columns=OUTPUT_COLUMNS)

        rows = []
        evidence_index, evidence_source_index = self._build_evidence_text_index()

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
            alt_compounds = self._split_compound_terms(
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

            # No further reference_plant filtering needed here — the
            # `references` DataFrame built above (via _norm_taxon) is
            # already exactly the reference-plant-restricted set. An
            # older version of this function re-checked `reference_plant`
            # here too, using plain _norm instead of _norm_taxon — which
            # silently re-excluded the very row that had just been
            # correctly matched upstream whenever the database's full
            # taxonomic name (hybrid marker, subspecies, etc.) didn't
            # literally contain the plain user-typed name as a substring
            # (e.g. "Mentha piperita" vs "Mentha x piperita subsp.
            # nothosubsp. piperita"). Keeping a second, inconsistent
            # filter here defeats the fix above for any hybrid or
            # infraspecific taxon, not just this one.

            ref_compounds = self._split_compound_terms(
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

                    matched_compound, match_quality, target_specificity, target_provenance = (
                        self._match_compounds(
                            ref_compound,
                            alt_compounds,
                            alt_norm=alt_record["alt_compound_norm_map"],
                        )
                    )

                    if not matched_compound:
                        continue

                    raw_evidence, evidence_source_ids = self._collect_raw_evidence(
                        evidence_index=evidence_index,
                        plant=alt_plant,
                        compound=matched_compound,
                        problem=problem,
                        source_index=evidence_source_index,
                    )

                    has_real_evidence = bool(raw_evidence.strip())
                    evidence_level = self._evidence_level(raw_evidence)
                    evidence_hierarchy_detail = classify_evidence_hierarchy(raw_evidence)
                    negative_evidence = classify_negative_evidence(raw_evidence)

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

                    safety_flags = self._extract_flags_negation_aware(
                        raw_evidence,
                        SAFETY_TERMS,
                    )
                    db_safety_flags = self._extract_hazard_flags_exact(
                        matched_own_targets,
                        DB_ACTIVITY_SAFETY_TERMS,
                    )
                    if db_safety_flags:
                        pieces = []
                        if safety_flags:
                            pieces.extend(safety_flags.split("; "))
                        pieces.extend(db_safety_flags.split("; "))
                        safety_flags = "; ".join(sorted(set(pieces)))

                    interaction_flags = self._extract_flags_negation_aware(
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
                        same_plant=self._norm(ref_plant) == self._norm(alt_plant),
                    )

                    evidence_confidence = compute_evidence_confidence(
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                        evidence_level=evidence_level,
                        has_negative_evidence=negative_evidence.is_negative,
                    )
                    confidence_note = confidence_adjusted_framing_note(
                        rd_opportunity_score=score,
                        evidence_confidence=evidence_confidence,
                    )
                    decision_class_ah = classify_decision_ah(
                        existing_decision_class=decision,
                        evidence_confidence=evidence_confidence,
                        rd_opportunity_score=score,
                        market_status=market_status,
                        match_quality=match_quality,
                        same_plant=self._norm(ref_plant) == self._norm(alt_plant),
                    )
                    white_space_type = classify_white_space(
                        evidence_confidence=evidence_confidence,
                        market_status=market_status,
                        use_live_search=self.use_live_search,
                    )

                    rows.append(
                        {
                            "Reference_Plant": ref_plant,
                            "Reference_Compound": ref_compound,
                            "Alternative_Plant": alt_plant,
                            "Shared_or_Similar_Compound": matched_compound,
                            "Target_or_Mechanism": target or "Not clearly extracted",
                            "Target_Provenance": target_provenance or "Not applicable (no shared-target claim for this match type)",
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
                            "Source_Record_IDs": "; ".join(evidence_source_ids) if evidence_source_ids else "No specific source record identified",
                            "Occurrence_Corroboration": self._occurrence_corroboration(evidence_source_ids),
                            "Evidence_Level": evidence_level,
                            "Evidence_Hierarchy_Detail": evidence_hierarchy_detail or "Unclassified",
                            "Has_Negative_Evidence": negative_evidence.is_negative,
                            "Negative_Evidence_Types": "; ".join(negative_evidence.finding_types),
                            "Market_Status": market_status,
                            "Novelty_Status": novelty_status,
                            "R&D_Opportunity_Score": score,
                            "Evidence_Confidence": evidence_confidence,
                            "Decision_Class": decision,
                            "Decision_Class_AH": decision_class_ah,
                            "White_Space_Type": white_space_type or "",
                            "Confidence_Note": confidence_note or "",
                            # Internal-only — used by _merge_multi_compound_matches
                            # to correctly recompute Decision_Class_AH after a
                            # merge, then dropped by the final
                            # output[OUTPUT_COLUMNS] selection at the end of
                            # run(). Never reaches the CSV.
                            "_match_quality": match_quality,
                            "_same_plant": self._norm(ref_plant) == self._norm(alt_plant),
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

        # Ranked worst-to-best. "Safety concern" sits below "Low priority"
        # since it's a harder, more certain reason to deprioritize a
        # candidate than merely having a weak/generic match. This list
        # must stay in sync with every Decision_Class string
        # _decision_class() can produce — an earlier version of this list
        # didn't know about "Safety concern — not suitable without expert
        # review" (added later, see _decision_class), which crashed
        # order.index() below the moment any duplicate-reference-plant
        # group contained a safety-flagged row.
        order = [
            "Safety concern — not suitable without expert review",
            "Low priority / insufficient data",
            "Early-stage candidate; more evidence needed",
            "Promising candidate; verify safety and standardization",
            "Strong R&D candidate",
        ]

        def _rank(decision):
            decision = str(decision)
            return order.index(decision) if decision in order else 0

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
            # confidence tier than the most cautious *informative*
            # individual match already earned (e.g. if one of the matches
            # has no real evidence behind it, the merged row shouldn't
            # claim more confidence than that).
            #
            # BUT: a sub-row whose own match rests on a common,
            # non-specific compound (the same "found in dozens/hundreds
            # of unrelated plants database-wide" signal _score_candidate
            # and _decision_class already penalize on that sub-row itself
            # — see the "Common"/"non-specific" checks elsewhere in this
            # file) is not informative about the OVERALL multi-compound
            # candidate. Letting it also act as a veto on the merged
            # result is double-penalizing the same weak signal, and once
            # a candidate matches on enough distinct compounds (which is
            # exactly what should make it a STRONGER candidate), at least
            # one such common/trace compound is almost always present —
            # silently dragging nearly every multi-compound match down to
            # "Low priority" regardless of how strong the rest of the
            # evidence is. Only sub-rows that aren't themselves flagged
            # as common/non-specific get a vote in the conservative cap.
            # If every sub-row in the group is common/non-specific, none
            # of them are informative, so the cap falls back to the full,
            # unfiltered group — the conservative behavior is preserved
            # exactly for the case it exists for: a group with no strong
            # signal at all.
            def _is_common_match(novelty_status):
                text = str(novelty_status)
                return "Common" in text or "non-specific" in text

            informative = group[~group["Novelty_Status"].map(_is_common_match)]
            tightest_pool = informative if not informative.empty else group

            tightest = min(
                (str(d) for d in tightest_pool["Decision_Class"]),
                key=_rank,
            )
            if _rank(new_decision) > _rank(tightest):
                new_decision = tightest

            best["Reference_Compound"] = "; ".join(distinct_ref_compounds)
            best["Shared_or_Similar_Compound"] = "; ".join(distinct_matched)
            best["R&D_Opportunity_Score"] = new_score
            best["Decision_Class"] = new_decision

            # The decision above already accounts for flags anywhere in
            # the group, not just on the single highest-scoring sub-row
            # ("best"). The displayed Safety_Flags/Interaction_Flags must
            # do the same — otherwise a merged row can show "Safety
            # concern" with a Safety_Flags column that says "No explicit
            # flag found", because that column silently kept whichever
            # value the (unflagged) top-scoring sub-row happened to have
            # while a DIFFERENT, lower-scoring sub-row in the same group
            # was the one that actually carried the flag. A decision the
            # displayed columns can't explain isn't trustworthy, for any
            # plant, any compound, any indication.
            def _merged_flags(column):
                pieces = []
                for v in group[column]:
                    v = str(v).strip()
                    if v and v != "No explicit flag found":
                        pieces.extend(p.strip() for p in v.split("; ") if p.strip())
                return "; ".join(sorted(set(pieces))) if pieces else "No explicit flag found"

            best["Safety_Flags"] = _merged_flags("Safety_Flags")
            best["Interaction_Flags"] = _merged_flags("Interaction_Flags")

            # Same reasoning as Safety_Flags/Interaction_Flags just
            # above, applied to negative evidence (audit 4.15): if ANY
            # sub-row in this group carries a negative/contradictory
            # finding, the merged row must show it — a negative finding
            # attached to one of several matched compounds silently
            # vanishing because a DIFFERENT compound's sub-row happened
            # to score higher is exactly the confirmation-bias failure
            # mode this column exists to prevent.
            if "Has_Negative_Evidence" in group.columns:
                best["Has_Negative_Evidence"] = bool(group["Has_Negative_Evidence"].any())
            if "Negative_Evidence_Types" in group.columns:
                types = []
                for v in group["Negative_Evidence_Types"]:
                    v = str(v).strip()
                    if v:
                        types.extend(t.strip() for t in v.split("; ") if t.strip())
                best["Negative_Evidence_Types"] = "; ".join(sorted(set(types)))

            # Gap 1 (traceability): union every source ID cited by ANY
            # sub-row in this group, same reasoning as
            # Negative_Evidence_Types just above — a citation backing
            # one of several matched compounds must not vanish because
            # a different compound's sub-row happened to score higher.
            if "Source_Record_IDs" in group.columns:
                ids = []
                for v in group["Source_Record_IDs"]:
                    v = str(v).strip()
                    if v and v != "No specific source record identified":
                        ids.extend(i.strip() for i in v.split("; ") if i.strip())
                best["Source_Record_IDs"] = (
                    "; ".join(sorted(set(ids))) if ids else "No specific source record identified"
                )
                # Gap 3: recompute corroboration from the just-unioned
                # source list — merging can genuinely INCREASE
                # corroboration (multiple matched compounds can each
                # bring their own independent source), so this must be
                # derived AFTER the union above, not carried over from
                # whichever single sub-row happened to score highest.
                best["Occurrence_Corroboration"] = self._occurrence_corroboration(ids)

            # Evidence_Confidence and Confidence_Note (Phase 6, audit
            # 4.16) must be recomputed here too — otherwise they'd stay
            # frozen at whatever the single pre-merge "best" sub-row had,
            # silently going stale the moment new_score (just above)
            # differs from that sub-row's original score. Confidence
            # itself uses the MAX across the group's sub-rows: if any one
            # matched compound has strong evidence behind it, that's a
            # genuine, real signal about the candidate as a whole, the
            # same "any sub-row can contribute a real positive" logic
            # already used for Has_Negative_Evidence above (just the
            # positive-signal direction of it).
            if "Evidence_Confidence" in group.columns:
                best["Evidence_Confidence"] = float(group["Evidence_Confidence"].max())
                best["Confidence_Note"] = confidence_adjusted_framing_note(
                    rd_opportunity_score=new_score,
                    evidence_confidence=best["Evidence_Confidence"],
                ) or ""

            if "Decision_Class_AH" in group.columns:
                # best's own _match_quality/_same_plant (from the
                # highest-scoring sub-row) are reused here — same
                # "best sub-row's own values, recombined with the
                # group-level recomputed score/decision" pattern the
                # rest of this merge function already uses.
                best["Decision_Class_AH"] = classify_decision_ah(
                    existing_decision_class=new_decision,
                    evidence_confidence=best["Evidence_Confidence"],
                    rd_opportunity_score=new_score,
                    market_status=str(best.get("Market_Status", "")),
                    match_quality=str(best.get("_match_quality", "")),
                    same_plant=bool(best.get("_same_plant", False)),
                )

            if "White_Space_Type" in group.columns:
                best["White_Space_Type"] = classify_white_space(
                    evidence_confidence=best["Evidence_Confidence"],
                    market_status=str(best.get("Market_Status", "")),
                    use_live_search=self.use_live_search,
                ) or ""

            # The pre-merge Rationale text (from _rationale(), on the
            # single "best" sub-row) ends with a hardcoded
            # "Decision: <that sub-row's own decision>." sentence. If the
            # group-level recompute above changed the decision (e.g. a
            # DIFFERENT sub-row's safety flag pulled the merged result
            # down to "Safety concern"), that trailing sentence goes
            # stale — the Rationale text would keep saying "Decision:
            # Strong R&D candidate" even though the Decision_Class column
            # right next to it says "Safety concern". Replacing it here
            # keeps the free text and the structured column in agreement,
            # for any decision change, not just this one.
            old_rationale = str(best["Rationale"])
            best["Rationale"] = re.sub(
                r"Decision: .+\.$",
                f"Decision: {new_decision}.",
                old_rationale,
            )

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
                "Known_Active_Compounds": "; ".join(compounds),
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
                "Known_Active_Compounds": "; ".join(compounds),
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
            row["Known_Active_Compounds"] = "; ".join(
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

            row["Known_Active_Compounds"] = "; ".join(
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
        """Returns (text_index, source_index).

        text_index: unchanged from before Gap 1 — dict of
        normalized_key -> concatenated evidence text, used for
        Evidence_Level/safety-flag/hierarchy extraction.

        source_index: NEW (audit "Gap 1: traceability"). Every
        connector that saves evidence to Supabase already writes a real
        Source_URL for that specific record (pubmed_connector.py:
        https://pubmed.ncbi.nlm.nih.gov/{pmid}/, and the same pattern in
        chembl_connector.py, clinicaltrials_connector.py,
        crossref_connector.py, chebi_connector.py, etc.) — that URL was
        previously discarded the moment a row got folded into the flat
        text_index string. source_index keeps the SAME normalized_key
        structure as text_index, but maps to a list of the specific
        Source_URLs that contributed to that key, so a downstream
        candidate row can cite exactly which record(s) it came from
        instead of only a generic "Live-collected evidence" label.
        """
        index = defaultdict(str)
        source_index = defaultdict(list)

        def _record_source(key, row):
            url = self._pick(row, ["Source_URL", "source_url", "URL", "url"])
            if url:
                source_index[key].append(url)

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
                    plant_key = self._norm(plant)
                    index[plant_key] += " " + text
                    _record_source(plant_key, row)

                for compound in self._known_compounds_from_text(text):
                    compound_key = self._norm(compound)
                    index[compound_key] += " " + text
                    _record_source(compound_key, row)

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
                    plant_key = self._norm(plant)
                    index[plant_key] += " " + text
                    _record_source(plant_key, row)

                for compound in self._known_compounds_from_text(text):
                    compound_key = self._norm(compound)
                    index[compound_key] += " " + text
                    _record_source(compound_key, row)

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
            plant_key = self._norm(plant)
            index[plant_key] += " " + text
            # Curated evidence has no per-record URL, but it does have a
            # named, citable source — record that instead of leaving
            # this key's source list empty.
            source_index[plant_key].append("seed_data.SLEEP_TEA_EVIDENCE")

        return index, source_index

    def _collect_raw_evidence(
        self,
        evidence_index,
        plant,
        compound,
        problem,
        source_index=None,
    ):
        """Builds the evidence text used to determine Evidence_Level and
        safety flags for one candidate row, and (Gap 1) the specific
        source identifiers that back it.

        `evidence_index` has two kinds of entries per record: one bucket
        keyed by PLANT (every evidence record tied to that plant, however
        many different compounds those records are actually about), and
        one bucket keyed by COMPOUND (every evidence record whose text
        mentions that specific compound, across whichever plants). The
        compound bucket is the one that's actually scoped to what this
        row's claim is about; the plant bucket is not — it was the
        source of the whole-plant-pooling cross-contamination problem
        (a plant's evidence about an unrelated compound getting credited
        to a completely different compound match just because it's the
        "same plant").
        
        So: compound- and problem-specific text is used as the PRIMARY
        signal. The whole-plant bucket is only added as a fallback when
        there is no compound-specific evidence at all for this compound
        — better than nothing when that's genuinely all there is, but no
        longer blended in unconditionally on every row regardless of
        whether it's actually relevant to the compound being evaluated.

        Returns (text, source_ids) — source_ids empty list when
        source_index isn't provided (keeps this callable exactly as
        before for any other caller that only wants the text).
        """
        source_index = source_index or {}
        compound_clean = compound.split("[")[0].strip()

        compound_key = self._norm(compound_clean)
        problem_key = self._norm(problem)

        compound_text = evidence_index.get(compound_key, "")
        problem_text = evidence_index.get(problem_key, "")

        primary = " ".join(part for part in (compound_text, problem_text) if part).strip()

        if primary:
            sources = list(dict.fromkeys(
                source_index.get(compound_key, []) + source_index.get(problem_key, [])
            ))
            return primary[:6000], sources

        # No compound-specific evidence found anywhere — fall back to
        # whatever's known about the plant in general, clearly weaker
        # but still better than treating it as zero evidence outright.
        plant_key = self._norm(plant)
        plant_text = evidence_index.get(plant_key, "")
        return plant_text.strip()[:6000], list(dict.fromkeys(source_index.get(plant_key, [])))

    def _match_compounds(
        self,
        reference_compound,
        alternative_compounds,
        alt_norm=None,
    ):
        """Returns (matched_compound_label, match_quality, target_specificity,
        target_provenance).

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

        target_provenance (Gap 5, "target relationship provenance"):
        which source(s) — the hardcoded seed_data.COMPOUND_TARGETS
        knowledge base, the real/maintained Supabase compound_profiles
        table, or both — actually asserted the shared target that
        earned this match its "target_verified" quality. Empty string
        when match_quality isn't "target_verified" (there's no specific
        target claim to attribute for an exact or class-only match).

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
            return alt_norm[ref], "exact", None, ""

        ref_class = self.compound_to_class.get(ref, "")

        if not ref_class:
            return "", "none", None, ""

        ref_targets = self.compound_to_targets.get(ref, set())

        class_matches = [
            alt_value
            for alt_key, alt_value in alt_norm.items()
            if self.compound_to_class.get(alt_key, "") == ref_class
        ]

        if not class_matches:
            return "", "none", None, ""

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
                sources = self.compound_to_target_sources.get(
                    self._norm(alt_value), {}
                ).get(target, frozenset())
                provenance = "; ".join(sorted(sources)) if sources else "Source not tracked"
                return (
                    f"{alt_value} [similar: {ref_class}; shared target: "
                    f"{target} (shared by {count} known compounds)]",
                    "target_verified",
                    count,
                    provenance,
                )

        return (
            f"{class_matches[0]} [similar: {ref_class}; class-only, "
            f"target not confirmed]",
            "class_only",
            None,
            "",
        )


    def _build_compound_indexes(self):
        """Returns (compound_to_class, compound_to_targets, compound_to_target_sources).

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

        compound_to_target_sources (Gap 5, "target relationship
        provenance"): a target claim from the hardcoded seed dict
        (COMPOUND_TARGETS) and one confirmed by a real, maintained
        Supabase record (compound_profiles.major_target) are very
        different claims — one is an editorial judgment call baked into
        this codebase, the other is a specific database record someone
        can go look up. Both used to get unioned into the same
        compound_to_targets set with no way to tell which was which.
        This parallel index keeps that distinction: for every
        (compound, target) pair, which source(s) actually asserted it.
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
        target_source_index = defaultdict(lambda: defaultdict(set))

        SEED_SOURCE_LABEL = "seed_data.COMPOUND_TARGETS (hardcoded knowledge base, not a specific study/database record)"
        SUPABASE_SOURCE_LABEL = "Supabase compound_profiles.major_target (maintained database record)"

        for compound, targets in COMPOUND_TARGETS.items():
            compound_key = self._norm(compound)
            for target in targets:
                target_key = self._norm(target)
                target_index[compound_key].add(target_key)
                target_source_index[compound_key][target_key].add(SEED_SOURCE_LABEL)

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
                    target_key = self._norm(target)
                    target_index[compound].add(target_key)
                    target_source_index[compound][target_key].add(SUPABASE_SOURCE_LABEL)

        # Convert the nested defaultdict to plain dicts of frozensets so
        # this behaves like a normal, picklable, easily-tested data
        # structure once construction is done.
        plain_target_source_index = {
            compound: {target: frozenset(sources) for target, sources in targets.items()}
            for compound, targets in target_source_index.items()
        }

        return class_index, dict(target_index), plain_target_source_index

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
        """R&D_Opportunity_Score (0-100). See evidence_confidence.py for
        the SEPARATE Evidence_Confidence score (audit 4.16) — this
        function is intentionally untouched by that split; every weight
        below is exactly what it was before Phase 6.

        COMPLETE WEIGHTS TABLE (audit 4.16: "تمام weightها مستند شوند").
        All numbers below are verified against the code in this function
        as of Phase 6 — this docstring documents, it does not define;
        if the code below changes, this table must be updated with it.

        1) Chemical/mechanistic link (base, before the two modifiers
           below):
             exact match                    22
             target_verified match          15
             class-only/similar match        5
           target_verified modifier: multiplied by min(1.0, 2.0 /
             target_specificity) — full bonus only when the shared
             target is carried by just 2 compounds DB-wide, decaying
             smoothly as more compounds share it.
           commonality modifier: multiplied by (1 - penalty_ratio),
             where penalty_ratio = min(0.8, overage / 3.0) and
             overage = max(0, compound_plant_count/threshold - 1.0) —
             no penalty at or below the DB's own commonality threshold,
             up to 80% removed at 4x that threshold or more.

        2) Evidence quality (evidence_points, by Evidence_Level):
             Clinical / human evidence         24
             Regulatory / monograph evidence   20
             Preclinical / mechanistic ev.     12
             General literature signal          7
             No direct evidence                 0

        3) Product-development fit:
             concentration reported            +10  (else +2)
             extraction fit                     up to +18 (see
                                                  _extraction_fit_score's
                                                  own weights below)
             co-compounds (2 pts each)          up to +8
             target/mechanism identified        +8   (else +1)

        4) Novelty (only awarded when evidence_level != "No direct
           evidence" — novelty on an unevidenced candidate isn't a real
           finding yet):
             "Common"/"non-specific" novelty     +0
             "Alternative"/"Cross-region"        +10
             anything else                       +2

        5) Market signal (small modifier; matches the
           MarketVerificationStatus vocabulary from _market_status(),
           Phase 5/audit 4.6-4.7):
             "Verified marketed product"         +1
             "Regulatory monograph exists" /
               "Traditional-use status"          +2
             "Commercial evidence reported..."   +2
             "No verified product found"         +6   (currently a dead
                                                  code path — no real
                                                  retail/patent search
                                                  is wired in yet, so
                                                  _market_status never
                                                  actually returns this)
             "Search not performed" / "Source
               unavailable" / "Unknown"          +3   (neutral default)

        6) Safety/interaction/self-row penalties:
             any safety flag                    -14
             any interaction flag               -10
             same_plant (reference-vs-itself)   -15

        Final score: round(max(0, min(100, sum_of_above)), 1).

        _extraction_fit_score's own internal weights (feeds into #3
        above, capped there at 18):
             no extraction method reported        3
             any extraction method reported       8  (base)
             aqueous/water/infusion/decoction    +10 (+8 more if dosage
                                                   form is infusion/tea/
                                                   herbal)
             ethanol/hydroalcoholic/extract       +8 (+6 more if dosage
                                                   form is capsule/
                                                   tablet/extract/cream/
                                                   gel/ointment)
             essential oil/distillation           +6 (+5 more if dosage
                                                   form is cream/gel/
                                                   essential oil)
        """
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
        score += min(8, len(self._split_compound_terms(co_compounds)) * 2)
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
        # Matches the MarketVerificationStatus vocabulary from
        # _market_status() (audit 4.6/4.7, extended Gap 2). "Search not
        # performed" is deliberately neutral, not a white-space bonus —
        # a real product/patent search hasn't actually been run, so
        # this must not be scored as if emptiness had been confirmed.
        # "No verified product found" (only returned once a real
        # retail/patent search is wired in — currently dead code path,
        # kept for forward compatibility) is the only status that earns
        # the white-space-style bonus, because it's the only one that
        # reflects an actual completed search.
        market_lower = market_status.lower()
        if "verified marketed product" in market_lower:
            score += 1
        elif "regulatory monograph" in market_lower or "traditional-use" in market_lower:
            score += 2
        elif "commercial evidence reported" in market_lower:
            score += 2
        elif "no verified product found" in market_lower:
            score += 6
        elif "conflicting market evidence" in market_lower:
            # A real, detected disagreement between two signals (e.g.
            # regulatory recognition vs. a discontinuation mention) is
            # worth flagging with a small penalty, not treated as
            # neutral — it means the market picture for this candidate
            # genuinely needs a human to resolve before acting on it.
            score -= 2
        elif "search incomplete" in market_lower:
            # Slightly more informative than "not performed" (a live
            # search did run this session), but still no market signal
            # was actually found — same neutral treatment as "not
            # performed", not a bonus.
            score += 3
        else:  # "Search not performed", "Source unavailable", "Unknown"
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
        """Market status, using the same controlled vocabulary as
        data_contracts.MarketVerificationStatus (audit 4.6/4.7), plus
        two additional honest states (Gap 2, "Market Intelligence
        completeness"): "Conflicting market evidence" and "Search
        incomplete" — both built from signals this function already
        computes, not from any new data source.

        HONESTY CONSTRAINT: this engine has no real retail-product or
        patent-database connection wired into this per-row path — see
        _search_retail_products() below, which literally returns "Not
        implemented", and the patent connector, which only activates
        with EPO_OPS_KEY/EPO_OPS_SECRET env vars set (those two DO run,
        but on a separate, per-plant "market landscape" panel —
        market_landscape() below — not per candidate row; calling them
        here would mean a live network/API call for every single
        alternative-plant row in a run, which is a cost/latency
        decision that deserves its own review, not a side effect of
        this fix). So "Verified marketed product" and "No verified
        product found" remain unreachable from this function specifically
        — kept in the vocabulary for forward compatibility with
        market_landscape()'s own, separately-verified results.

        "Conflicting market evidence": when two of this function's OWN
        signals disagree — e.g. EMA_Status says "Yes" (a regulatory
        monograph exists) but the same evidence text explicitly says
        the product has been discontinued/withdrawn. That's a genuine,
        detectable disagreement between two real, present signals, not
        a guess.

        "Search incomplete": distinguishes "a live search ran this
        session but returned nothing about this SPECIFIC candidate"
        (self.use_live_search is True, evidence is still empty) from
        "no search was ever attempted for this candidate at all"
        (self.use_live_search is False — a curated/seed-only run). The
        old version treated both as identically "Search not performed",
        which overstated how little was actually done for the
        live-search case.
        """
        ema = self._pick(alt, ["EMA_Status"])
        text = self._norm(evidence)

        # Narrow, multi-word phrase patterns — not bare words like
        # "product" or "market", which show up constantly in text that
        # has nothing to do with a real commercial product ("the
        # product of this reaction", "on the world market for herbal
        # teas in general").
        commercial_phrase_patterns = [
            r"\bmarketed as\b", r"\bmarketed product\b",
            r"\bavailable as a supplement\b", r"\bavailable as an? product\b",
            r"\bcommercially available\b", r"\bsold as\b", r"\bbranded as\b",
        ]
        commercial_signal = any(re.search(p, text) for p in commercial_phrase_patterns)

        discontinued_patterns = [
            r"\bdiscontinued\b", r"\bwithdrawn from the market\b",
            r"\bno longer (?:available|marketed|sold)\b",
            r"\bnot currently (?:available|marketed|sold)\b",
            r"\bproduct recall\b",
        ]
        discontinued_signal = any(re.search(p, text) for p in discontinued_patterns)

        # A real disagreement: something asserts market presence
        # (regulatory recognition or a commercial-phrase mention) AND
        # something else in the SAME evidence asserts the product is
        # gone/unavailable. Checked first — this is more informative to
        # surface than picking one side and silently discarding the other.
        if (ema == "Yes" or commercial_signal) and discontinued_signal:
            return "Conflicting market evidence"

        if ema == "Yes":
            return "Regulatory monograph exists"

        if commercial_signal:
            return "Commercial evidence reported, not independently verified"

        traditional_use_patterns = [
            r"\btraditional(?:ly)? use\b", r"\bwell-established use\b",
            r"\btraditional medicine\b",
        ]
        if any(re.search(p, text) for p in traditional_use_patterns):
            return "Traditional-use status"

        if self.use_live_search:
            # A live search ran this session (Step 2 was used), but
            # nothing turned up about THIS specific candidate — a
            # genuinely different, more-informative claim than "no
            # search was ever attempted."
            return "Search incomplete"

        return "Search not performed"

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
        same_plant=False,
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
        #
        # EXCEPT for the reference plant matched to itself (same_plant).
        # That row isn't a candidate being proposed as an alternative —
        # it's a description of the reference plant's own baseline
        # compound profile, which the merge step (see the row-merging
        # function) can combine dozens of that plant's compounds into.
        # If even one minor/trace compound out of dozens carries a hard
        # safety term, the reference plant itself — which may be a
        # long-established, widely-used herb — would get labelled
        # "Safety concern — not suitable", which is misleading: it reads
        # as a judgment on the whole plant, when it's really a flag on
        # one of many minor constituents. The flags themselves are still
        # shown either way (Safety_Flags column, Rationale) — only the
        # hard auto-exclusion is skipped for the self-row, for any
        # plant, not a special case for any one species.
        flagged_terms = {
            term.strip() for term in safety_flags.split("; ") if term.strip()
        }
        if (flagged_terms & HARD_SAFETY_TERMS) and not same_plant:
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
                # Word-boundary match, not a bare substring search — a
                # short term like "ema" otherwise matches inside
                # unrelated words ("hematology", "remain"). Same bug
                # class as the anti-X collision already fixed for
                # DB_ACTIVITY_SAFETY_TERMS elsewhere in this file.
                pattern = re.compile(r"\b" + re.escape(term) + r"\b")
                for match in pattern.finditer(text):
                    window_start = max(0, match.start() - 40)
                    preceding = text[window_start:match.start()]
                    if not any(cue in preceding[-25:] for cue in negation_cues):
                        return True
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
        # Was: a flat set of regexes joined into one string with no
        # indication of WHAT BASIS each number was on (see audit 4.10 —
        # "0.5%; 3 mg/g" tells a reader nothing about whether those two
        # numbers are even meant to sit side by side). Now: every value
        # is classified by basis, and if a single text mixes bases, the
        # returned string says so explicitly instead of leaving it to
        # the reader to notice. See concentration_normalizer.py.
        #
        # Returns "" (not a placeholder string) when nothing is found —
        # existing callers rely on that falsiness: the score-presence
        # bonus ("score += 10 if concentration else 2") and the two
        # "concentration or 'not clearly reported'" display fallbacks
        # elsewhere in this file both break if this always returns a
        # non-empty string.
        parsed = parse_concentration(text)
        if not parsed:
            return ""
        return format_concentration_info(parsed)[:300]

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

    # Negation cues that flip a nearby hazard word from "present" to
    # "explicitly absent" — "no adverse events", "without toxicity",
    # "lacks contraindications" should not be flagged the same as an
    # actual reported hazard. Shared with _evidence_level's own
    # negation handling below (same technique, same reasoning).
    _NEGATION_CUES = (
        "no ", "not ", "lack of ", "lacks ", "insufficient ",
        "absence of ", "without ", "none found", "no evidence of ",
        "no direct ", "unproven", "unconfirmed", "no reported ",
        "did not show", "did not exhibit", "devoid of",
    )

    @classmethod
    def _extract_flags_negation_aware(cls, text, terms):
        """Like _extract_flags, but for free prose (paper abstracts,
        regulatory notes) rather than a database's own structured
        activity list. Two independent ways a hazard word's plain
        substring can mean the OPPOSITE of a hazard, both very common in
        safety-literature phrasing:
          1. A negation phrase just before it: "no adverse events",
             "without toxicity", "did not show hepatotoxicity".
          2. An "anti-" prefix fused directly onto the word with no
             space: "antitoxic", "antihepatotoxic" — the same collision
             already found and fixed for Dr. Duke's own structured
             activity tags (e.g. "anticonvulsant"), but free text needs
             its own check since it isn't a clean list of discrete terms
             to exact-match against.
        Applies to every term in `terms`, not a special case for any one
        word or compound.
        """
        text_norm = cls._norm(text)
        if not text_norm:
            return ""

        found = []
        for term in terms:
            idx = text_norm.find(term)
            while idx != -1:
                anti_fused = text_norm[max(0, idx - 4):idx] == "anti"
                window_start = max(0, idx - 40)
                preceding = text_norm[window_start:idx]
                negated = anti_fused or any(
                    cue in preceding[-25:] for cue in cls._NEGATION_CUES
                )
                if not negated:
                    found.append(term)
                    break
                idx = text_norm.find(term, idx + 1)

        return "; ".join(sorted(set(found)))

    @staticmethod
    def _extract_hazard_flags_exact(known_terms, hazard_terms):
        """For matching against a DISCRETE set of known activity terms
        (e.g. a compound's own Dr. Duke's Known_Target list, already
        split into individual named activities) rather than free-text
        prose. Checks each term for an EXACT match (after normalizing)
        against the hazard vocabulary, instead of substring-searching a
        joined blob.

        This distinction matters: Dr. Duke's own vocabulary includes
        both a hazard term AND its protective opposite as separate,
        deliberate entries — "Convulsant" and "Anticonvulsant",
        "Carcinogenic" and "Anticarcinogenic", "Mutagenic" and
        "Antimutagenic", "Hepatotoxic" and "Antihepatotoxic", "Emetic"
        and "Antiemetic", "Genotoxic" and "Antigenotoxic", "Hemolytic"
        and "Antihemolytic" all coexist in the same database. Substring
        matching (`"convulsant" in text`) can't tell these apart —
        "convulsant" is trivially a substring of "anticonvulsant", so a
        compound extensively documented as PROTECTIVE against seizures
        (linalool has a substantial body of published anticonvulsant
        research) was being flagged as if it caused them. Comparing
        each already-discrete term for an exact match closes this off
        for every hazard term with an "anti-" counterpart, not just
        this one compound or this one term.
        """
        known_norm = {BotanicalRDCandidateEngine._norm(t) for t in known_terms}
        found = [
            term for term in hazard_terms
            if term in known_norm
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

    @staticmethod
    def _occurrence_corroboration(evidence_source_ids):
        """Gap 3, "Alternative Source scientific defensibility": how many
        INDEPENDENT sources actually back this row's concentration/
        extraction/co-compound claims, not just whether any text was
        found at all. Built directly from Gap 1's evidence_source_ids
        (the distinct Source_URLs that contributed to this row's
        raw_evidence) — no new data collection, just an honest count of
        what's already there.

        This does NOT attempt to attribute individual claims (e.g.
        "concentration came from source A, extraction from source B")
        to specific sources — that would require preserving per-record
        text boundaries all the way through _build_evidence_text_index's
        flattening step, a larger change than this one. What this DOES
        give: a row backed by 3 independent papers is honestly
        distinguishable from a row backed by 1, or by none at all —
        the single most important defensibility signal missing before
        this, at the cost of the smallest possible change.
        """
        count = len(evidence_source_ids) if evidence_source_ids else 0
        if count == 0:
            return "No independent source identified — not corroborated"
        if count == 1:
            return "Single-source claim — not independently corroborated"
        return f"Corroborated by {count} independent sources"

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

    @classmethod
    def _norm_taxon(cls, value):
        """Like _norm, but also strips botanical-nomenclature tokens
        (the hybrid marker "×"/standalone "x", and infraspecific rank
        abbreviations subsp./ssp./var./f./cv./nothosubsp.) that a
        database's full taxonomic name carries but a person's everyday
        working name for the same plant usually won't. Used only for
        MATCHING a user-supplied plant name against the database — the
        database's actual full name is still what gets displayed and
        used everywhere else."""
        text = cls._norm(value)
        text = text.replace("×", " x ")
        text = re.sub(
            r"\b(x|subsp|ssp|nothosubsp|var|f|cv)\b\.?",
            " ",
            text,
        )
        return re.sub(r"\s+", " ", text).strip()

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
    def _split_compound_terms(value):
        """Like _split_terms, but for lists of COMPOUND NAMES
        specifically. Chemical nomenclature routinely uses a comma as
        part of a single compound's own name — "1,8-Cineole",
        "2,3-dihydrobenzofuran", "3,4-Dihydroxyphenylacetic acid" are all
        one compound each. _split_terms splitting on "," was fragmenting
        these into nonsense tokens (a bare "1" plus "8-Cineole" as two
        separate "compounds") every time a compound list got serialized
        and re-parsed. This splits only on ";" and "|" — real delimiters
        this codebase actually uses between distinct compounds in a
        list — never on "," or "/", for any compound name, not just the
        ones that happened to surface this."""
        if value is None:
            return []

        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = re.split(r"[;|]", str(value))

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
