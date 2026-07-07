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


def _get(row, names):
    for n in names:
        if n in row.index:
            v = _clean(row.get(n, ""))
            if v:
                return v
    return ""


class TargetCompoundPlantEngine:
    def discover(self, knowledge_df, ranking_df=None, target_df=None, inputs=None):
        if inputs is None:
            inputs = {}

        if knowledge_df is None or knowledge_df.empty:
            return pd.DataFrame()

        knowledge = knowledge_df.copy()

        # -------- target list from Step 8.95 --------
        target_terms = set()
        if target_df is not None and not target_df.empty:
            for _, r in target_df.iterrows():
                t = _get(r, ["target", "Target"])
                if t:
                    target_terms.add(_lower(t))

        # -------- build plant -> compounds from ranking --------
        plant_to_compounds = {}

        if ranking_df is not None and not ranking_df.empty:
            for _, r in ranking_df.iterrows():
                plant = _get(r, ["Scientific_Name", "Plant", "plant"])
                common = _get(r, ["Common_Name", "common_name"])
                compound = _get(r, ["compound_name", "Compound", "compound"])

                if compound:
                    if plant:
                        plant_to_compounds.setdefault(_lower(plant), set()).add(compound)
                    if common:
                        plant_to_compounds.setdefault(_lower(common), set()).add(compound)

        # -------- marketed plants --------
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

        records = []

        for _, row in knowledge.iterrows():
            plant = _get(row, ["Plant", "plant", "Scientific_Name", "scientific_name"])
            compound = _get(row, ["Compound", "compound", "compound_name", "Compound_Name"])
            target = _get(row, ["Target", "target", "major_target", "Major_Target"])
            mechanism = _get(row, ["Mechanism", "mechanism"])
            indication = _get(row, ["Indication", "indication"])
            evidence_type = _get(row, ["Evidence_Type", "evidence_type"])
            confidence = _get(row, ["Confidence", "confidence"])
            title = _get(row, ["Title", "title"])
            url = _get(row, ["URL", "url", "Source_URL", "source_url"])

            try:
                confidence = float(confidence)
            except Exception:
                confidence = 0

            if not plant or not target:
                continue

            # اگر target_df داریم، فقط همان targetهای کشف‌شده را نگه دار
            if target_terms and _lower(target) not in target_terms:
                continue

            compounds = []

            if compound:
                compounds.append(compound)

            # اگر compound در knowledge خالی بود، از ranking برای همان گیاه بردار
            ranking_compounds = plant_to_compounds.get(_lower(plant), set())
            for c in ranking_compounds:
                if c not in compounds:
                    compounds.append(c)

            # اگر هنوز compound نداریم، حذف نکن؛ به عنوان unknown نگه دار
            if not compounds:
                compounds = ["Unknown compound — needs extraction"]

            for comp in compounds:
                already_marketed = _lower(plant) in marketed_plants

                evidence_count = len(
                    knowledge[
                        knowledge.apply(
                            lambda x: _lower(_get(x, ["Plant", "plant", "Scientific_Name", "scientific_name"])) == _lower(plant),
                            axis=1,
                        )
                        &
                        knowledge.apply(
                            lambda x: _lower(_get(x, ["Target", "target", "major_target"])) == _lower(target),
                            axis=1,
                        )
                    ]
                )

                novelty_bonus = 0 if already_marketed else 25

                score = (
                    min(35, evidence_count * 7)
                    + min(35, confidence * 0.35)
                    + novelty_bonus
                )

                if comp != "Unknown compound — needs extraction":
                    score += 15

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
                        "Compound": comp,
                        "Candidate_Plant": plant,
                        "Mechanism": mechanism,
                        "Indication": indication,
                        "Evidence_Type": evidence_type,
                        "Evidence_Count": evidence_count,
                        "Confidence": confidence,
                        "Already_Marketed": already_marketed,
                        "Target_Compound_Plant_Score": score,
                        "Opportunity_Category": category,
                        "Title": title,
                        "URL": url,
                        "Rationale": (
                            f"{target} is linked to {plant}. "
                            f"Compound route: {comp}. "
                            f"This creates a target → compound → plant discovery path."
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
