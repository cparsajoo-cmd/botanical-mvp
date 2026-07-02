import pandas as pd

def load_evidence_database():
    return pd.read_excel(
        "Botanical_Evidence_Database_Professional_Template.xlsx",
        sheet_name="Evidence_Table"
    )
