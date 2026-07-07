import pandas as pd


class TargetCompoundEngine:

    def __init__(self, knowledge_df, plant_df):
        self.knowledge = knowledge_df.copy()
        self.plants = plant_df.copy()

    def discover(self):

        results = []

        # تمام Target ها
        targets = self.knowledge["target"].dropna().unique()

        for target in targets:

            target_rows = self.knowledge[
                self.knowledge["target"] == target
            ]

            compounds = target_rows["compound"].dropna().unique()

            for compound in compounds:

                plant_rows = self.plants[
                    self.plants["compound_name"]
                    .str.lower()
                    .str.contains(compound.lower(), na=False)
                ]

                for _, p in plant_rows.iterrows():

                    evidence = len(
                        target_rows[
                            target_rows["compound"] == compound
                        ]
                    )

                    confidence = min(100, evidence * 20)

                    if confidence >= 90:
                        level = "High"
                    elif confidence >= 70:
                        level = "Medium"
                    else:
                        level = "Weak"

                    results.append({

                        "Target": target,

                        "Compound": compound,

                        "Plant": p["Scientific_Name"],

                        "Common_Name": p["Common_Name"],

                        "Evidence": evidence,

                        "Confidence": confidence,

                        "Priority": level

                    })

        if len(results) == 0:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        df = df.sort_values(
            "Confidence",
            ascending=False
        )

        return df.drop_duplicates(
            subset=[
                "Target",
                "Compound",
                "Plant"
            ]
        )
