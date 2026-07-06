import pandas as pd
from evidence_database import load_evidence_database


def _txt(x):
    if x is None:
        return ""
    return str(x).lower().strip()


class MechanismDiscoveryEngine:
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
                "abstract",
                "source",
                "source_title",
                "source_url",
                "url",
                "indication",
                "mechanism",
                "target",
                "major_target",
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

        target_indication = _txt(inputs.get("indication", ""))

        opportunities = []

        for _, row in ranking_df.iterrows():
            known_plant = row.get("Scientific_Name", "")
            known_common = row.get("Common_Name", "")
            known_compound = row.get("compound_name", "")
            known_target = row.get("major_target", "")
            known_mechanism = row.get("mechanism", "")

            mechanism_terms = [
                _txt(known_target),
                _txt(known_mechanism),
                _txt(target_indication),
            ]

            mechanism_terms = [
                t for t in mechanism_terms
                if t and t not in ["nan", "none"]
            ]

            if not mechanism_terms:
                continue

            mask = pd.Series(False, index=df.index)

            for term in mechanism_terms:
                if len(term) >= 3:
                    mask = mask | df["_text"].str.contains(
                        term,
                        case=False,
                        na=False,
                        regex=False,
                    )

            matched = df[mask].copy()

            if matched.empty:
                continue

            for _, ev in matched.iterrows():
                candidate_plant = ""

                for col in [
                    "plant",
                    "scientific_name",
                    "Plant",
                    "Scientific_Name",
                    "common_name",
                    "Common_Name",
                ]:
                    if col in ev.index and str(ev.get(col, "")).strip():
                        candidate_plant = str(ev.get(col, "")).strip()
                        break

                if not candidate_plant:
                    continue

                if _txt(candidate_plant) == _txt(known_plant):
                    continue

                text = ev.get("_text", "")

                mechanism_hits = sum(
                    1 for term in mechanism_terms
                    if term and term in text
                )

                evidence_signal = mechanism_hits * 20

                scientific_score = row.get("Scientific_RnD_Potential", 0)
                if scientific_score is None:
                    scientific_score = row.get("Final_RnD_Score", 0)

                try:
                    scientific_score = float(scientific_score)
                except Exception:
                    scientific_score = 0

                market_score = row.get("Market_Score", 0)

                try:
                    market_score = float(market_score)
                except Exception:
                    market_score = 0

                novelty_bonus = max(0, 100 - market_score) * 0.25

                mechanism_score = min(
                    100,
                    round(
                        evidence_signal
                        + scientific_score * 0.35
                        + novelty_bonus,
                        1,
                    ),
                )

                if mechanism_score >= 70:
                    category = "Strong mechanism-based R&D candidate"
                elif mechanism_score >= 45:
                    category = "Promising mechanism-based candidate"
                else:
                    category = "Weak mechanism signal"

                opportunities.append(
                    {
                        "Known_Plant": known_plant,
                        "Known_Common_Name": known_common,
                        "Known_Compound": known_compound,
                        "Known_Target": known_target,
                        "Known_Mechanism": known_mechanism,
                        "New_Candidate_Plant": candidate_plant,
                        "Indication": inputs.get("indication", ""),
                        "Mechanism_Hits": mechanism_hits,
                        "Mechanism_Discovery_Score": mechanism_score,
                        "Mechanism_Category": category,
                        "Rationale": (
                            f"{candidate_plant} appears in evidence connected to the same indication, "
                            f"target, or mechanism as {known_plant}. This may represent a mechanism-based R&D opportunity."
                        ),
                    }
                )

        result = pd.DataFrame(opportunities)

        if result.empty:
            return result

        result = result.drop_duplicates(
            subset=["Known_Target", "New_Candidate_Plant"],
            keep="first",
        )

        result = result.sort_values(
            by="Mechanism_Discovery_Score",
            ascending=False,
        ).reset_index(drop=True)

        result.insert(0, "Rank", range(1, len(result) + 1))

        return result
