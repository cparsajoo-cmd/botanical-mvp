import sqlite3
import pandas as pd
from pathlib import Path

DB_FILE = "botanical_platform.db"


def get_connection():
    if not Path(DB_FILE).exists():
        from evidence_database import build_database_if_needed
        build_database_if_needed()

    return sqlite3.connect(DB_FILE)


def load_table(table_name):
    conn = get_connection()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()
    return df


def save_evidence_record(record):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(evidence_records)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    for column in record.keys():
        if column not in existing_columns:
            cursor.execute(f'ALTER TABLE evidence_records ADD COLUMN "{column}" TEXT')

    columns = list(record.keys())
    placeholders = ", ".join(["?"] * len(columns))
    column_names = ", ".join([f'"{c}"' for c in columns])

    values = [record[c] for c in columns]

    cursor.execute(
        f"INSERT INTO evidence_records ({column_names}) VALUES ({placeholders})",
        values
    )

    conn.commit()
    row_id = cursor.lastrowid
    conn.close()

    return row_id
