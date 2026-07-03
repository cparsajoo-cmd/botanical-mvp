import pandas as pd
from pathlib import Path

def load_evidence_database():

    excel_files = sorted(Path(".").glob("*.xlsx"))

    if len(excel_files) == 0:
        raise FileNotFoundError(
            "No Excel file (*.xlsx) was found in the repository."
        )

    excel_file = excel_files[0]

    print("Using Excel file:", excel_file)

    return pd.read_excel(
        excel_file,
        sheet_name="Evidence_Table"
    )
