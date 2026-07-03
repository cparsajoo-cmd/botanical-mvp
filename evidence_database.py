import pandas as pd
from pathlib import Path

def load_evidence_database():
    excel_files = list(Path(".").glob("*.xlsx"))

    if not excel_files:
        raise FileNotFoundError("No Excel file found in the repository.")

    return pd.read_excel(
        excel_files[0],
        sheet_name="Evidence_Table"
    )
