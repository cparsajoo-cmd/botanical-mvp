import sqlite3
import pandas as pd
from pathlib import Path

EXCEL_FILE = "Botanical_Platform_Data_Model_v3.xlsx"
DB_FILE = "botanical_platform.db"


def build_database_if_needed():
    if Path(DB_FILE).exists():
        return

    if not Path(EXCEL_FILE).exists():
        raise FileNotFoundError(f"{EXCEL_FILE} not found.")

    excel = pd.ExcelFile(EXCEL_FILE)
    conn = sqlite3.connect(DB_FILE)

    for sheet in excel.sheet_names:
        df = pd.read_excel(EXCEL_FILE, sheet_name=sheet)
        table_name = sheet.lower()
        df.to_sql(table_name, conn, if_exists="replace", index=False)

    conn.close()


def load_evidence_database():
    build_database_if_needed()

    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM evidence_records", conn)
    conn.close()

    return df


def load_sheet(sheet_name):
    build_database_if_needed()

    conn = sqlite3.connect(DB_FILE)
    table_name = sheet_name.lower()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()

    return df
