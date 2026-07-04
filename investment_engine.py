import pandas as pd


def build_investment_report(decision_df):

    if decision_df is None or decision_df.empty:
        return pd.DataFrame()

    reports = []

    for plant, g in decision_df.groupby("Scientific_Name"):

        score = g["Evidence_Score"].max()

        ema = "Yes" if (g["EMA_Status"] == "Yes").any() else "No"
        who = "Yes" if (g["WHO_Status"] == "Yes").any() else "No"
        escop = "Yes" if (g["ESCOP_Status"] == "Yes").any() else "No"

        meta = (
            g["Study_Type"]
            .fillna("")
            .str.contains("meta", case=False)
            .sum()
        )

        systematic = (
            g["Study_Type"]
            .fillna("")
            .str.contains("systematic", case=False)
            .sum()
        )

        rct = (
            g["Study_Type"]
            .fillna("")
            .str.contains("random", case=False)
            .sum()
        )

        clinical = (
            g["Study_Model"]
            .fillna("")
            .str.contains("human|patient", case=False)
            .sum()
        )

        animal = (
            g["Study_Model"]
            .fillna("")
            .str.contains("animal|rat|mouse|mice", case=False)
            .sum()
        )

        invitro = (
            g["Study_Model"]
            .fillna("")
            .str.contains("vitro|cell", case=False)
            .sum()
        )

        quality = round(g["Evidence_Quality_Score"].mean(), 1)

        reports.append({

            "Scientific_Name": plant,

            "Investment_Score": score,

            "EMA": ema,

            "WHO": who,

            "ESCOP": escop,

            "Meta_Analyses": int(meta),

            "Systematic_Reviews": int(systematic),

            "RCTs": int(rct),

            "Human_Studies": int(clinical),

            "Animal_Studies": int(animal),

            "InVitro_Studies": int(invitro),

            "Average_Quality": quality

        })

    report = pd.DataFrame(reports)

    report = report.sort_values(
        "Investment_Score",
        ascending=False
    )

    return report.reset_index(drop=True)
