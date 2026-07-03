import sqlite3
import pandas as pd
from pathlib import Path

EXCEL_FILE = "Botanical_Platform_Data_Model_v3.xlsx"
DB_FILE = "botanical_platform.db"

def build_database():
    if not Path(EXCEL_FILE).exists():
        raise FileNotFoundError(f"{EXCEL_FILE} not found.")

    excel = pd.ExcelFile(EXCEL_FILE)
    conn = sqlite3.connect(DB_FILE)

    for sheet in excel.sheet_names:
        df = pd.read_excel(EXCEL_FILE, sheet_name=sheet)
        table_name = sheet.lower()
        df.to_sql(table_name, conn, if_exists="replace", index=False)

    conn.close()
    print(f"Database created: {DB_FILE}")

if __name__ == "__main__":
    build_database()
