import pandas as pd


def _txt(x):
    if x is None:
        return ""
    return str(x).lower().strip()


class MechanismDiscoveryEngine:
    def discover(self, knowledge_df, inputs=None):
        if inputs is None:
            inputs = {}

        if knowledge_df is None or knowledge_df.empty:
            return pd.DataFrame()

        df = knowledge_df.copy()

        required_cols = ["Plant", "Target", "Mechanism", "Indication", "Confidence"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""

        df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0)

        records = []

        for i, row in df.iterrows():
            source_plant = row.get("Plant", "")
            source_compound = row.get("Compound", "")
            source_target = row.get("Target", "")
            source_mechanism = row.get("Mechanism", "")
            source_indication = row.get("Indication", "")
            source_confidence = row.get("Confidence", 0)

            if not source_plant:
                continue

            for j, candidate in df.iterrows():
                if i == j:
                    continue

                candidate_plant = candidate.get("Plant", "")
                candidate_compound = candidate.get("Compound", "")
                candidate_target = candidate.get("Target", "")
                candidate_mechanism = candidate.get("Mechanism", "")
                candidate_indication = candidate.get("Indication", "")
                candidate_confidence = candidate.get("Confidence", 0)

                if not candidate_plant:
                    continue

                if _txt(candidate_plant) == _txt(source_plant):
                    continue

                shared_target = (
                    source_target
                    and candidate_target
                    and _txt(source_target) == _txt(candidate_target)
                )

                shared_mechanism = (
                    source_mechanism
                    and candidate_mechanism
                    and _txt(source_mechanism) == _txt(candidate_mechanism)
                )

                shared_indication = (
                    source_indication
                    and candidate_indication
                    and _txt(source_indication) == _txt(candidate_indication)
                )

                if not shared_target and not shared_mechanism and not shared_indication:
                    continue

                score = 0

                if shared_target:
                    score += 40

                if shared_mechanism:
                    score += 35

                if shared_indication:
                    score += 10

                score += min(15, float(candidate_confidence) * 0.15)

                score = round(min(100, score), 1)

                if score >= 75:
                    category = "Strong mechanism-based R&D candidate"
                elif score >= 50:
                    category = "Promising mechanism-based candidate"
                else:
                    category = "Weak mechanism signal"

                records.append(
                    {
                        "Source_Plant": source_plant,
                        "Source_Compound": source_compound,
                        "New_Candidate_Plant": candidate_plant,
                        "Candidate_Compound": candidate_compound,
                        "Shared_Target": source_target if shared_target else "",
                        "Shared_Mechanism": source_mechanism if shared_mechanism else "",
                        "Shared_Indication": source_indication if shared_indication else "",
                        "Candidate_Confidence": candidate_confidence,
                        "Mechanism_Discovery_Score": score,
                        "Mechanism_Category": category,
                        "Rationale": (
                            f"{candidate_plant} shares "
                            f"{'target; ' if shared_target else ''}"
                            f"{'mechanism; ' if shared_mechanism else ''}"
                            f"{'indication; ' if shared_indication else ''}"
                            f"with {source_plant}. This may represent a mechanism-based R&D opportunity."
                        ),
                    }
                )

        result = pd.DataFrame(records)

        if result.empty:
            return result

        result = result.drop_duplicates(
            subset=[
                "Source_Plant",
                "New_Candidate_Plant",
                "Shared_Target",
                "Shared_Mechanism",
            ],
            keep="first",
        )

        result = result.sort_values(
            by="Mechanism_Discovery_Score",
            ascending=False,
        ).reset_index(drop=True)

        result.insert(0, "Rank", range(1, len(result) + 1))

        return result
