import pandas as pd

from target_knowledge_base import (
    get_compounds_for_target,
    get_plants_for_compound,
    get_all_target_compound_plant_links,
)


def _clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.lower() in ["nan", "none", "null", ""]:
        return ""
    return x


def _lower(x):
    return _clean(x).lower()


def _get(row, names):
    for n in names:
        if n in row.index:
            v = _clean(row.get(n, ""))
            if v:
                return v
    return ""


class TargetCompoundPlantEngine:
    def discover(self, knowledge_df=None, ranking_df=None, target_df=None, inputs=None):
        if inputs is None:
            inputs = {}

        records = []

        target_terms = set()

        if target_df is not None and not target_df.empty:
            for _, r in target_df.iterrows():
                target = _get(r, ["target", "Target"])
                if target:
                    target_terms.add(target)

        if not target_terms and knowledge_df is not None and not knowledge_df.empty:
            for _, r in knowledge_df.iterrows():
                target = _get(r, ["Target", "target"])
                if target:
                    target_terms.add(target)

        if not target_terms:
            return pd.DataFrame()

        marketed_plants = set()

        if ranking_df is not None and not ranking_df.empty:
            for _, r in ranking_df.iterrows():
                plant = _get(r, ["Scientific_Name", "Plant", "plant"])
                decision = _get(r, ["Decision_Category", "Final_Class", "Market_Status"])
                market_score = _get(r, ["Market_Score"])

                try:
                    market_score = float(market_score)
                except Exception:
                    market_score = 0

                if (
                    "marketed" in _lower(decision)
                    or "commercial" in _lower(decision)
                    or market_score >= 60
                ):
                    marketed_plants.add(_lower(plant))

        for target in target_terms:
            compounds = get_compounds_for_target(target)

            for compound in compounds:
                plants = get_plants_for_compound(compound)

                for plant in plants:
                    already_marketed = _lower(plant) in marketed_plants

                    evidence_score = self._knowledge_support_score(
                        knowledge_df=knowledge_df,
                        target=target,
                        compound=compound,
                        plant=plant,
                    )

                    novelty_bonus = 0 if already_marketed else 25

                    score = 35 + evidence_score + novelty_bonus

                    if compound:
                        score += 15

                    score = round(min(100, score), 1)

                    if already_marketed:
                        category = "Known commercial target-compound-plant route"
                    elif score >= 75:
                        category = "Strong new R&D opportunity"
                    elif score >= 50:
                        category = "Promising new R&D opportunity"
                    else:
                        category = "Weak signal"

                    records.append(
                        {
                            "Target": target,
                            "Compound": compound,
                            "Candidate_Plant": plant,
                            "Already_Marketed": already_marketed,
                            "Knowledge_Support_Score": evidence_score,
                            "Target_Compound_Plant_Score": score,
                            "Opportunity_Category": category,
                            "Rationale": (
                                f"{target} is linked to {compound}; "
                                f"{compound} is reported in {plant}. "
                                f"This creates a disease → target → compound → plant discovery path."
                            ),
                        }
                    )

        result = pd.DataFrame(records)

        if result.empty:
            return result

        result = result.drop_duplicates(
            subset=["Target", "Compound", "Candidate_Plant"],
            keep="first",
        )

        result = result.sort_values(
            by="Target_Compound_Plant_Score",
            ascending=False,
        ).reset_index(drop=True)

        result.insert(0, "Rank", range(1, len(result) + 1))

        return result

    def _knowledge_support_score(self, knowledge_df, target, compound, plant):
        if knowledge_df is None or knowledge_df.empty:
            return 0

        df = knowledge_df.copy()

        score = 0

        for _, r in df.iterrows():
            text = " ".join(
                [
                    _get(r, ["Target", "target"]),
                    _get(r, ["Compound", "compound"]),
                    _get(r, ["Plant", "plant"]),
                    _get(r, ["Mechanism", "mechanism"]),
                    _get(r, ["Indication", "indication"]),
                    _get(r, ["Title", "title"]),
                ]
            ).lower()

            if _lower(target) and _lower(target) in text:
                score += 5

            if _lower(compound) and _lower(compound) in text:
                score += 5

            if _lower(plant) and _lower(plant) in text:
                score += 5

        return min(25, score)
