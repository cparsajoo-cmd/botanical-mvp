import pandas as pd


TARGET_COMPOUND_PLANT_KB = [
    # Alzheimer / AChE
    {"Target": "Acetylcholinesterase", "Mechanism": "enzyme inhibition", "Compound": "Huperzine A", "Plant": "Huperzia serrata", "Evidence_Level": 90},
    {"Target": "Acetylcholinesterase", "Mechanism": "enzyme inhibition", "Compound": "Galantamine", "Plant": "Galanthus nivalis", "Evidence_Level": 95},
    {"Target": "Acetylcholinesterase", "Mechanism": "enzyme inhibition", "Compound": "Berberine", "Plant": "Berberis vulgaris", "Evidence_Level": 75},
    {"Target": "Acetylcholinesterase", "Mechanism": "enzyme inhibition", "Compound": "Rosmarinic acid", "Plant": "Melissa officinalis", "Evidence_Level": 70},
    {"Target": "Acetylcholinesterase", "Mechanism": "enzyme inhibition", "Compound": "Apigenin", "Plant": "Matricaria chamomilla", "Evidence_Level": 65},
    {"Target": "Acetylcholinesterase", "Mechanism": "enzyme inhibition", "Compound": "Luteolin", "Plant": "Salvia officinalis", "Evidence_Level": 65},

    # Sleep / GABA
    {"Target": "GABA-A receptor", "Mechanism": "positive modulation", "Compound": "Valerenic acid", "Plant": "Valeriana officinalis", "Evidence_Level": 85},
    {"Target": "GABA-A receptor", "Mechanism": "positive modulation", "Compound": "Apigenin", "Plant": "Matricaria chamomilla", "Evidence_Level": 80},
    {"Target": "GABA-A receptor", "Mechanism": "positive modulation", "Compound": "Linalool", "Plant": "Lavandula angustifolia", "Evidence_Level": 80},
    {"Target": "GABA-A receptor", "Mechanism": "positive modulation", "Compound": "Chrysin", "Plant": "Passiflora incarnata", "Evidence_Level": 70},
    {"Target": "GABA-A receptor", "Mechanism": "positive modulation", "Compound": "Honokiol", "Plant": "Magnolia officinalis", "Evidence_Level": 75},
    {"Target": "GABA-A receptor", "Mechanism": "positive modulation", "Compound": "Magnolol", "Plant": "Magnolia officinalis", "Evidence_Level": 75},

    # Inflammation
    {"Target": "NF-kB pathway", "Mechanism": "inhibition", "Compound": "Curcumin", "Plant": "Curcuma longa", "Evidence_Level": 90},
    {"Target": "NF-kB pathway", "Mechanism": "inhibition", "Compound": "Boswellic acids", "Plant": "Boswellia serrata", "Evidence_Level": 85},
    {"Target": "NF-kB pathway", "Mechanism": "inhibition", "Compound": "Withanolides", "Plant": "Withania somnifera", "Evidence_Level": 75},
    {"Target": "COX pathway", "Mechanism": "inhibition", "Compound": "Apigenin", "Plant": "Matricaria chamomilla", "Evidence_Level": 70},
    {"Target": "COX pathway", "Mechanism": "inhibition", "Compound": "Rosmarinic acid", "Plant": "Rosmarinus officinalis", "Evidence_Level": 70},
    {"Target": "COX pathway", "Mechanism": "inhibition", "Compound": "Quercetin", "Plant": "Sophora japonica", "Evidence_Level": 70},
]


class BotanicalBrainEngine:
    def __init__(self):
        self.kb = pd.DataFrame(TARGET_COMPOUND_PLANT_KB)

    def discover_from_compound(self, compound_name):
        compound_name = str(compound_name).strip().lower()

        if not compound_name:
            return pd.DataFrame()

        seed_rows = self.kb[
            self.kb["Compound"].str.lower() == compound_name
        ]

        if seed_rows.empty:
            seed_rows = self.kb[
                self.kb["Compound"].str.lower().str.contains(compound_name, na=False)
            ]

        if seed_rows.empty:
            return pd.DataFrame()

        targets = seed_rows["Target"].unique().tolist()
        mechanisms = seed_rows["Mechanism"].unique().tolist()

        candidate_rows = self.kb[
            self.kb["Target"].isin(targets)
        ].copy()

        candidate_rows["Input_Compound"] = compound_name
        candidate_rows["Shared_Target"] = candidate_rows["Target"]
        candidate_rows["Shared_Mechanism"] = candidate_rows["Mechanism"]

        candidate_rows["Is_Original_Compound"] = (
            candidate_rows["Compound"].str.lower() == compound_name
        )

        candidate_rows["Novelty_Bonus"] = candidate_rows["Is_Original_Compound"].apply(
            lambda x: 0 if x else 20
        )

        candidate_rows["Mechanism_Match_Bonus"] = candidate_rows["Mechanism"].apply(
            lambda x: 15 if x in mechanisms else 5
        )

        candidate_rows["Botanical_Brain_Score"] = (
            candidate_rows["Evidence_Level"]
            + candidate_rows["Novelty_Bonus"]
            + candidate_rows["Mechanism_Match_Bonus"]
        ).clip(upper=100)

        candidate_rows["Discovery_Rationale"] = candidate_rows.apply(
            lambda r: (
                f"{r['Compound']} and the input compound share the target "
                f"{r['Target']} through {r['Mechanism']}. "
                f"{r['Compound']} is linked to {r['Plant']}."
            ),
            axis=1,
        )

        out = candidate_rows[
            [
                "Input_Compound",
                "Shared_Target",
                "Shared_Mechanism",
                "Compound",
                "Plant",
                "Evidence_Level",
                "Botanical_Brain_Score",
                "Is_Original_Compound",
                "Discovery_Rationale",
            ]
        ].drop_duplicates()

        out = out.sort_values(
            "Botanical_Brain_Score",
            ascending=False
        ).reset_index(drop=True)

        out.insert(0, "Rank", range(1, len(out) + 1))

        return out

    def discover_from_target(self, target_name):
        target_name = str(target_name).strip().lower()

        if not target_name:
            return pd.DataFrame()

        rows = self.kb[
            self.kb["Target"].str.lower().str.contains(target_name, na=False)
        ].copy()

        if rows.empty:
            return pd.DataFrame()

        rows["Botanical_Brain_Score"] = rows["Evidence_Level"]

        rows["Discovery_Rationale"] = rows.apply(
            lambda r: (
                f"{r['Compound']} acts on {r['Target']} via {r['Mechanism']} "
                f"and is linked to {r['Plant']}."
            ),
            axis=1,
        )

        out = rows[
            [
                "Target",
                "Mechanism",
                "Compound",
                "Plant",
                "Evidence_Level",
                "Botanical_Brain_Score",
                "Discovery_Rationale",
            ]
        ].drop_duplicates()

        out = out.sort_values(
            "Botanical_Brain_Score",
            ascending=False
        ).reset_index(drop=True)

        out.insert(0, "Rank", range(1, len(out) + 1))

        return out
