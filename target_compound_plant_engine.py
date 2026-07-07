import pandas as pd


def _clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.lower() in ["nan", "none", "null"]:
        return ""
    return x


def _txt(x):
    return _clean(x).lower()


class TargetCompoundPlantEngine:
    def discover(self, knowledge_df, ranking_df=None, inputs=None):
        if inputs is None:
            inputs = {}

        if knowledge_df is None or knowledge_df.empty:
            return pd.DataFrame()

        df = knowledge_df.copy()

        for col in [
            "Plant",
            "Compound",
            "Target",
            "Mechanism",
            "Indication",
            "Evidence_Type",
            "Confidence",
            "Title",
            "URL",
        ]:
            if col not in df.columns:
                df[col] = ""

        for col in ["Plant", "Compound", "Target", "Mechanism", "Indication"]:
            df[col] = df[col].apply(_clean)

        df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0)

        target_indication = _txt(inputs.get("indication", ""))

        if target_indication:
            relevant = df[
                df["Indication"].astype(str).str.lower().str.contains(
                    target_indication, na=False, regex=False
                )
                | df["Mechanism"].astype(str).str.lower().str.contains(
                    target_indication, na=False, regex=False
                )
            ].copy()
        else:
            relevant = df.copy()

        if relevant.empty:
            relevant = df.copy()

        known_marketed_plants = set()

        if ranking_df is not None and not ranking_df.empty:
            r = ranking_df.copy()

            if "Scientific_Name" in r.columns:
                if "Decision_Category" in r.columns:
                    marketed = r[
                        r["Decision_Category"]
                        .astype(str)
                        .str.contains("marketed|commercial", case=False, na=False)
                    ]
                    known_marketed_plants = set(
                        marketed["Scientific_Name"].astype(str).str.strip()
                    )

                elif "Market_Score" in r.columns:
                    r["Market_Score"] = pd.to_numeric(
                        r["Market_Score"], errors="coerce"
                    ).fillna(0)

                    known_marketed_plants = set(
                        r[r["Market_Score"] >= 60]["Scientific_Name"]
                        .astype(str)
                        .str.strip()
                    )

        records = []

        grouped = relevant.groupby(["Target", "Compound", "Plant"], dropna=False)

        for (target, compound, plant), group in grouped:
            target = _clean(target)
            compound = _clean(compound)
            plant = _clean(plant)

            if not target or not compound or not plant:
                continue

            confidence_mean = group["Confidence"].mean()
            evidence_count = len(group)

            mechanisms = sorted(
                set([_clean(x) for x in group["Mechanism"].tolist() if _clean(x)])
            )

            evidence_types = sorted(
                set([_clean(x) for x in group["Evidence_Type"].tolist() if _clean(x)])
            )

            is_marketed = plant in known_marketed_plants

            novelty_score = 10 if is_marketed else 30

            score = (
                min(30, evidence_count * 5)
                + min(30, confidence_mean * 0.30)
                + min(20, len(mechanisms) * 5)
                + novelty_score
            )

            score = round(min(100, score), 1)

            if is_marketed:
                category = "Known commercial mechanism candidate"
            elif score >= 70:
                category = "Strong target-to-plant R&D opportunity"
            elif score >= 45:
                category = "Promising target-to-plant opportunity"
            else:
                category = "Weak target-to-plant signal"

            records.append(
                {
                    "Target": target,
                    "Active_Compound": compound,
                    "Candidate_Plant": plant,
                    "Mechanisms": "; ".join(mechanisms),
                    "Evidence_Types": "; ".join(evidence_types),
                    "Evidence_Count": evidence_count,
                    "Mean_Confidence": round(confidence_mean, 1),
                    "Already_Marketed": is_marketed,
                    "Target_Compound_Plant_Score": score,
                    "Opportunity_Category": category,
                    "Rationale": (
                        f"{compound} is linked to {target}. "
                        f"{plant} appears as a plant source or evidence-linked candidate. "
                        f"This suggests a target → compound → plant development route."
                    ),
                }
            )

        result = pd.DataFrame(records)

        if result.empty:
            return result

        result = result.sort_values(
            by="Target_Compound_Plant_Score",
            ascending=False,
        ).reset_index(drop=True)

        result.insert(0, "Rank", range(1, len(result) + 1))

        return result
