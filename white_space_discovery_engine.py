import pandas as pd
from evidence_database import load_evidence_database


def _txt(x):
    if x is None:
        return ""
    return str(x).lower().strip()


class WhiteSpaceDiscoveryEngine:
    def __init__(self):
        try:
            self.evidence_df = load_evidence_database()
        except Exception:
            self.evidence_df = pd.DataFrame()

    def discover(self, ranking_df, inputs):
        if ranking_df is None or ranking_df.empty:
            return pd.DataFrame()

        if self.evidence_df is None or self.evidence_df.empty:
            return pd.DataFrame()

        df = self.evidence_df.copy()

        usable_cols = [
            c for c in df.columns
            if c.lower() in [
                "plant",
                "scientific_name",
                "common_name",
                "compound",
                "compound_name",
                "title",
                "source",
                "source_title",
                "source_url",
                "url",
                "abstract",
                "indication",
                "dosage_form",
            ]
        ]

        if not usable_cols:
            return pd.DataFrame()

        df["_text"] = (
            df[usable_cols]
            .fillna("")
            .astype(str)
            .apply(lambda x: " ".join(x.values.astype(str)), axis=1)
            .str.lower()
        )

        opportunities = []

        for _, row in ranking_df.iterrows():
            plant = row.get("Scientific_Name", "")
            common = row.get("Common_Name", "")
            compound = row.get("compound_name", "")

            if not compound or str(compound).lower() in ["nan", "none", ""]:
                continue

            compound_term = _txt(compound)
            plant_term = _txt(plant)

            compound_matches = df[
                df["_text"].str.contains(compound_term, case=False, na=False, regex=False)
            ].copy()

            if compound_matches.empty:
                continue

            candidate_plants = []

            for _, ev in compound_matches.iterrows():
                text = ev.get("_text", "")

                possible_plant = ""
                for col in ["plant", "scientific_name", "Plant", "Scientific_Name"]:
                    if col in ev.index and str(ev.get(col, "")).strip():
                        possible_plant = str(ev.get(col, "")).strip()
                        break

                if not possible_plant:
                    continue

                if _txt(possible_plant) == plant_term:
                    continue

                candidate_plants.append(possible_plant)

            candidate_plants = list(sorted(set(candidate_plants)))

            if not candidate_plants:
                continue

            for candidate in candidate_plants:
                candidate_text = _txt(candidate)

                candidate_records = compound_matches[
                    compound_matches["_text"].str.contains(
                        candidate_text,
                        case=False,
                        na=False,
                        regex=False,
                    )
                ]

                evidence_count = len(candidate_records)

                market_score = row.get("Market_Score", 0)
                try:
                    market_score = float(market_score)
                except Exception:
                    market_score = 0

                chemistry_score = row.get("Chemistry_Score_Unified", 0)
                evidence_score = row.get("Evidence_Score_Unified", 0)
                target_score = row.get("Target_Match_Score", 0)

                for v in ["chemistry_score", "evidence_score", "target_score"]:
                    pass

                try:
                    chemistry_score = float(chemistry_score)
                except Exception:
                    chemistry_score = 0

                try:
                    evidence_score = float(evidence_score)
                except Exception:
                    evidence_score = 0

                try:
                    target_score = float(target_score)
                except Exception:
                    target_score = 0

                white_space_score = round(
                    evidence_count * 8
                    + chemistry_score * 0.25
                    + evidence_score * 0.20
                    + target_score * 0.20
                    + max(0, 100 - market_score) * 0.25,
                    1,
                )

                white_space_score = min(100, white_space_score)

                if white_space_score >= 70:
                    category = "Strong white-space R&D candidate"
                elif white_space_score >= 45:
                    category = "Promising exploratory R&D candidate"
                else:
                    category = "Weak white-space signal"

                opportunities.append(
                    {
                        "Original_Known_Plant": plant,
                        "Known_Common_Name": common,
                        "Active_Compound": compound,
                        "New_Candidate_Plant": candidate,
                        "Evidence_Records_For_Compound": evidence_count,
                        "Known_Plant_Market_Score": market_score,
                        "White_Space_Score": white_space_score,
                        "White_Space_Category": category,
                        "Rationale": (
                            f"{candidate} appears in evidence records linked to {compound}. "
                            f"This may indicate a new plant-compound R&D opportunity beyond the already ranked plant."
                        ),
                    }
                )

        result = pd.DataFrame(opportunities)

        if result.empty:
            return result

        result = result.drop_duplicates(
            subset=["Active_Compound", "New_Candidate_Plant"],
            keep="first",
        )

        result = result.sort_values(
            by="White_Space_Score",
            ascending=False,
        ).reset_index(drop=True)

        result.insert(0, "Rank", range(1, len(result) + 1))

        return result
