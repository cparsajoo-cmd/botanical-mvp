import pandas as pd
from pathlib import Path

DATABASE_FILE = "Botanical_Platform_Data_Model_v3.xlsx"

def load_evidence_database():
    if Path(DATABASE_FILE).exists():
        return pd.read_excel(
            DATABASE_FILE,
            sheet_name="Evidence_Records"
        )

    excel_files = sorted(Path(".").glob("*.xlsx"))

    if not excel_files:
        raise FileNotFoundError("No Excel database file found.")

    return pd.read_excel(
        excel_files[0],
        sheet_name="Evidence_Records"
    )


def load_sheet(sheet_name):
    if Path(DATABASE_FILE).exists():
        return pd.read_excel(DATABASE_FILE, sheet_name=sheet_name)

    excel_files = sorted(Path(".").glob("*.xlsx"))

    if not excel_files:
        raise FileNotFoundError("No Excel database file found.")

    return pd.read_excel(excel_files[0], sheet_name=sheet_name)
