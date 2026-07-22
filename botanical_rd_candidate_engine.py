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
from structured_rationale import (
    go_investigate_hold_no_go,
    scientific_rationale,
    commercial_regulatory_rationale,
    evidence_strengths,
    evidence_weaknesses,
    next_experiment_suggestion,
)

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
    "Score_Breakdown",
    "Evidence_Confidence",
    "Decision_Class",
    "Decision_Class_AH",
    "White_Space_Type",
    "Confidence_Note",
    "Go_Investigate_Hold_NoGo",
    "Scientific_Rationale",
    "Commercial_Regulatory_Rationale",
    "Evidence_Strengths",
    "Evidence_Weaknesses",
    "Next_Experiment_Suggestion",
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

                    score, score_components = self._score_candidate(
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
                    occurrence_corroboration = self._occurrence_corroboration(evidence_source_ids)

                    # Gap 6 + Gap 8: structured rationale, built purely
                    # from signals already computed above — no new data
                    # collection, no LLM call. See structured_rationale.py.
                    go_call = go_investigate_hold_no_go(decision_class_ah)
                    sci_rationale = scientific_rationale(
                        match_quality=match_quality,
                        target_provenance=target_provenance,
                        evidence_hierarchy_detail=evidence_hierarchy_detail,
                        occurrence_corroboration=occurrence_corroboration,
                        has_negative_evidence=negative_evidence.is_negative,
                    )
                    comm_reg_rationale = commercial_regulatory_rationale(
                        market_status=market_status,
                        white_space_type=white_space_type or "",
                    )
                    strengths = evidence_strengths(
                        match_quality=match_quality,
                        evidence_confidence=evidence_confidence,
                        occurrence_corroboration=occurrence_corroboration,
                        market_status=market_status,
                    )
                    weaknesses = evidence_weaknesses(
                        evidence_confidence=evidence_confidence,
                        occurrence_corroboration=occurrence_corroboration,
                        has_negative_evidence=negative_evidence.is_negative,
                        negative_evidence_types="; ".join(negative_evidence.finding_types),
                        safety_flags=safety_flags or "No explicit flag found",
                        market_status=market_status,
                    )
                    next_experiment = next_experiment_suggestion(
                        decision_class_ah=decision_class_ah,
                        evidence_weaknesses_list=weaknesses,
                        alt_plant=alt_plant,
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
                            "Occurrence_Corroboration": occurrence_corroboration,
                            "Evidence_Level": evidence_level,
                            "Evidence_Hierarchy_Detail": evidence_hierarchy_detail or "Unclassified",
                            "Has_Negative_Evidence": negative_evidence.is_negative,
                            "Negative_Evidence_Types": "; ".join(negative_evidence.finding_types),
                            "Market_Status": market_status,
                            "Novelty_Status": novelty_status,
                            "R&D_Opportunity_Score": score,
                            "Score_Breakdown": self._format_score_breakdown(score_components),
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
                            "Go_Investigate_Hold_NoGo": go_call,
                            "Scientific_Rationale": sci_rationale,
                            "Commercial_Regulatory_Rationale": comm_reg_rationale,
                            "Evidence_Strengths": "; ".join(strengths) if strengths else "None identified",
                            "Evidence_Weaknesses": "; ".join(weaknesses) if weaknesses else "None identified",
                            "Next_Experiment_Suggestion": next_experiment,
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
            if "Score_Breakdown" in best and bonus:
                # The merge bonus is a real, separate contribution to
                # the final score (rewarding multiple independent
                # compound matches) that _score_candidate never saw —
                # append it explicitly rather than letting
                # Score_Breakdown silently under-report new_score's
                # actual composition.
                best["Score_Breakdown"] = (
                    f"{best['Score_Breakdown']}; Multi-compound match bonus: +{bonus:.1f}"
                )

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

            if "Go_Investigate_Hold_NoGo" in group.columns:
                # Recomputed from the just-updated Decision_Class_AH,
                # Evidence_Confidence, Market_Status, White_Space_Type,
                # etc. — the same staleness concern as every other
                # merge-recomputed field above: these must reflect the
                # GROUP-level merged result, not whichever single
                # sub-row happened to score highest before merging.
                best["Go_Investigate_Hold_NoGo"] = go_investigate_hold_no_go(
                    str(best.get("Decision_Class_AH", ""))
                )
                best["Scientific_Rationale"] = scientific_rationale(
                    match_quality=str(best.get("_match_quality", "")),
                    target_provenance=str(best.get("Target_Provenance", "")),
                    evidence_hierarchy_detail=str(best.get("Evidence_Hierarchy_Detail", "")),
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                )
                best["Commercial_Regulatory_Rationale"] = commercial_regulatory_rationale(
                    market_status=str(best.get("Market_Status", "")),
                    white_space_type=str(best.get("White_Space_Type", "")),
                )
                merged_strengths = evidence_strengths(
                    match_quality=str(best.get("_match_quality", "")),
                    evidence_confidence=best["Evidence_Confidence"],
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    market_status=str(best.get("Market_Status", "")),
                )
                merged_weaknesses = evidence_weaknesses(
                    evidence_confidence=best["Evidence_Confidence"],
                    occurrence_corroboration=str(best.get("Occurrence_Corroboration", "")),
                    has_negative_evidence=bool(best.get("Has_Negative_Evidence", False)),
                    negative_evidence_types=str(best.get("Negative_Evidence_Types", "")),
                    safety_flags=str(best.get("Safety_Flags", "")),
                    market_status=str(best.get("Market_Status", "")),
                )
                best["Evidence_Strengths"] = "; ".join(merged_strengths) if merged_strengths else "None identified"
                best["Evidence_Weaknesses"] = "; ".join(merged_weaknesses) if merged_weaknesses else "None identified"
                best["Next_Experiment_Suggestion"] = next_experiment_suggestion(
                    decision_class_ah=str(best.get("Decision_Class_AH", "")),
                    evidence_weaknesses_list=merged_weaknesses,
                    alt_plant=str(best.get("Alternative_Plant", "")),
                )

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
        """Returns (score, components).

        score: R&D_Opportunity_Score (0-100). See evidence_confidence.py
        for the SEPARATE Evidence_Confidence score (audit 4.16) — this
        function is intentionally untouched by that split; every weight
        below is exactly what it was before Phase 6.

        components: dict of {section name: points contributed by that
        section}, summing to `score` before the final 0-100 clamp.
        Added to answer the architecture-audit question "which evidence
        contributed MOST to this score?" — previously only the summed
        total was ever returned, so a row's score couldn't be decomposed
        without recomputing this whole function a second time (which
        would have meant duplicating this logic in a second place —
        exactly what was avoided by extending this function's return
        value instead of writing a parallel scoring function).

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
        components = {}

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
            chem_bonus *= min
