import sqlite3
import pandas as pd
from pathlib import Path

DB_FILE = "botanical_platform.db"

def get_connection():
    if not Path(DB_FILE).exists():
        raise FileNotFoundError(
            "Database file not found. Run database_builder.py first."
        )
    return sqlite3.connect(DB_FILE)

def load_table(table_name):
    conn = get_connection()
    df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
    conn.close()
    return df

def load_evidence_records():
    return load_table("evidence_records")

def load_plants():
    return load_table("plants")

def load_references():
    return load_table("references")

def load_decision_rules():
    return load_table("decision_rules")
