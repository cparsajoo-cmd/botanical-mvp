import pandas as pd


def _clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.lower() in ["nan", "none", "null", ""]:
        return ""
    return x


def _lower(x):
    return _clean(x).lower()


def _get(row, possible_names):
    for name in possible_names:
        if name in row.index:
            value = _clean(row.get(name, ""))
            if value:
                return value
    return ""


class TargetCompoundPlantEngine:
    def discover(self, knowledge_df, ranking_df=None, target_df=None, inputs=None):
        if inputs is None:
            inputs = {}

        if knowledge_df is None or knowledge_df.empty:
            return pd.DataFrame()

        knowledge = knowledge_df.copy()

        # Normalize knowledge columns
        for col in [
            "Plant", "plant",
            "Compound", "compound",
            "Target", "target",
            "Mechanism", "mechanism",
            "Indication", "indication",
            "Evidence_Type", "evidence_type",
            "Confidence", "confidence",
        ]:
            if col not in knowledge.columns:
                knowledge[col] = ""

        records = []

        # Target filter from Disease → Target step if available
        target_terms = set()

        if target_df is not None and not target_df.empty:
            for _, r in target_df.iterrows():
                t = _get(r, ["target", "Target"])
                if t:
                    target_terms.add(_lower(t))

        if not target_terms:
            indication = _lower(inputs.get("indication", ""))
        else:
            indication = ""

        # Build known marketed plants
        marketed_plants = set()

        if ranking_df is not None and not ranking_df.empty:
            ranking = ranking_df.copy()

            for _, r in ranking.iterrows():
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

        for _, row in knowledge.iterrows():
            plant = _get(row, ["Plant", "plant", "Scientific_Name", "scientific_name"])
            compound = _get(row, ["Compound", "compound", "compound_name", "Compound_Name"])
            target = _get(row, ["Target", "target", "major_target", "Major_Target"])
            mechanism = _get(row, ["Mechanism", "mechanism"])
            ind = _get(row, ["Indication", "indication"])
            evidence_type = _get(row, ["Evidence_Type", "evidence_type"])
            confidence = _get(row, ["Confidence", "confidence"])

            try:
                confidence = float(confidence)
            except Exception:
                confidence = 0

            if not plant or not compound or not target:
                continue

            # If target_df exists, keep only discovered targets
            if target_terms and _lower(target) not in target_terms:
                continue

            # Otherwise use indication relevance
            if indication:
                combined = " ".join([_lower(ind), _lower(mechanism), _lower(target)])
                if indication not in combined:
                    pass

            already_marketed = _lower(plant) in marketed_plants

            evidence_count = len(
                knowledge[
                    (
                        knowledge.apply(
                            lambda x: _lower(_get(x, ["Target", "target"])) == _lower(target),
                            axis=1,
                        )
                    )
                    &
                    (
                        knowledge.apply(
                            lambda x: _lower(_get(x, ["Compound", "compound", "compound_name"])) == _lower(compound),
                            axis=1,
                        )
                    )
                    &
                    (
                        knowledge.apply(
                            lambda x: _lower(_get(x, ["Plant", "plant", "Scientific_Name"])) == _lower(plant),
                            axis=1,
                        )
                    )
                ]
            )

            novelty_bonus = 0 if already_marketed else 25

            score = (
                min(35, evidence_count * 7)
                + min(35, confidence * 0.35)
                + novelty_bonus
            )

            if mechanism:
                score += 10

            score = round(min(100, score), 1)

            if already_marketed:
                category = "Known commercial target-compound-plant route"
            elif score >= 70:
                category = "Strong new R&D opportunity"
            elif score >= 45:
                category = "Promising new R&D opportunity"
            else:
                category = "Weak signal"

            records.append(
                {
                    "Target": target,
                    "Compound": compound,
                    "Candidate_Plant": plant,
                    "Mechanism": mechanism,
                    "Indication": ind,
                    "Evidence_Type": evidence_type,
                    "Evidence_Count": evidence_count,
                    "Confidence": confidence,
                    "Already_Marketed": already_marketed,
                    "Target_Compound_Plant_Score": score,
                    "Opportunity_Category": category,
                    "Rationale": (
                        f"{target} is linked to {compound}, and {compound} is linked to {plant}. "
                        f"This creates a target → compound → plant R&D route."
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
