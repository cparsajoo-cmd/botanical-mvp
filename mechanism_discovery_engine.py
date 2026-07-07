import pandas as pd


def _txt(x):
    if x is None:
        return ""
    return str(x).strip().lower()


def _clean(x):
    if x is None:
        return ""
    x = str(x).strip()
    if x.lower() in ["nan", "none", "null"]:
        return ""
    return x


class MechanismDiscoveryEngine:
    def discover(self, knowledge_df, inputs=None):
        if inputs is None:
            inputs = {}

        if knowledge_df is None or knowledge_df.empty:
            return pd.DataFrame()

        df = knowledge_df.copy()

        for col in ["Plant", "Compound", "Target", "Mechanism", "Indication", "Evidence_Type", "Confidence"]:
            if col not in df.columns:
                df[col] = ""

        df["Plant"] = df["Plant"].apply(_clean)
        df["Compound"] = df["Compound"].apply(_clean)
        df["Target"] = df["Target"].apply(_clean)
        df["Mechanism"] = df["Mechanism"].apply(_clean)
        df["Indication"] = df["Indication"].apply(_clean)

        default_indication = inputs.get("indication", "")
        df["Indication"] = df["Indication"].replace("", default_indication)

        df["Confidence"] = pd.to_numeric(df["Confidence"], errors="coerce").fillna(0)

        df = df[df["Plant"] != ""].copy()

        if df.empty:
            return pd.DataFrame()

        records = []

        for i, source in df.iterrows():
            source_plant = source["Plant"]
            source_compound = source["Compound"]
            source_target = source["Target"]
            source_mechanism = source["Mechanism"]
            source_indication = source["Indication"]
            source_confidence = source["Confidence"]

            for j, candidate in df.iterrows():
                if i == j:
                    continue

                candidate_plant = candidate["Plant"]
                candidate_compound = candidate["Compound"]
                candidate_target = candidate["Target"]
                candidate_mechanism = candidate["Mechanism"]
                candidate_indication = candidate["Indication"]
                candidate_confidence = candidate["Confidence"]

                if _txt(source_plant) == _txt(candidate_plant):
                    continue

                shared_target = bool(source_target and candidate_target and _txt(source_target) == _txt(candidate_target))
                shared_mechanism = bool(source_mechanism and candidate_mechanism and _txt(source_mechanism) == _txt(candidate_mechanism))
                shared_indication = bool(source_indication and candidate_indication and _txt(source_indication) == _txt(candidate_indication))

                if not shared_target and not shared_mechanism and not shared_indication:
                    continue

                score = 0
                match_parts = []

                if shared_target:
                    score += 45
                    match_parts.append("shared target")

                if shared_mechanism:
                    score += 35
                    match_parts.append("shared mechanism")

                if shared_indication:
                    score += 10
                    match_parts.append("shared indication")

                score += min(10, float(candidate_confidence) * 0.10)
                score = round(min(100, score), 1)

                if shared_target and shared_mechanism:
                    category = "Strong mechanism-based R&D candidate"
                elif shared_target or shared_mechanism:
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
                        "Match_Type": ", ".join(match_parts),
                        "Source_Confidence": source_confidence,
                        "Candidate_Confidence": candidate_confidence,
                        "Mechanism_Discovery_Score": score,
                        "Mechanism_Category": category,
                        "Rationale": (
                            f"{candidate_plant} shares {', '.join(match_parts)} with {source_plant}. "
                            f"This may represent a mechanism-based R&D opportunity."
                        ),
                    }
                )

        result = pd.DataFrame(records)

        if result.empty:
            return result

        result = result.sort_values(
            by="Mechanism_Discovery_Score",
            ascending=False,
        )

        result = result.drop_duplicates(
            subset=[
                "Source_Plant",
                "New_Candidate_Plant",
                "Shared_Target",
                "Shared_Mechanism",
                "Shared_Indication",
            ],
            keep="first",
        ).reset_index(drop=True)

        result.insert(0, "Rank", range(1, len(result) + 1))

        return result
