import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "botanical_platform.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS plants (
    plant_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scientific_name      TEXT NOT NULL UNIQUE,
    common_name          TEXT,
    family               TEXT,
    region               TEXT,
    traditional_system   TEXT,
    plant_part_used      TEXT,
    cultivation_status   TEXT
);

CREATE TABLE IF NOT EXISTS compounds (
    compound_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    compound_name         TEXT NOT NULL UNIQUE,
    compound_class        TEXT
);

CREATE TABLE IF NOT EXISTS targets (
    target_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    target_name           TEXT NOT NULL UNIQUE,
    organ_system            TEXT
);

CREATE TABLE IF NOT EXISTS diseases (
    disease_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    disease_name           TEXT NOT NULL UNIQUE,
    category                TEXT
);

CREATE TABLE IF NOT EXISTS plant_compounds (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id               INTEGER REFERENCES plants(plant_id) ON DELETE CASCADE,
    compound_id             INTEGER REFERENCES compounds(compound_id) ON DELETE CASCADE,
    plant_part               TEXT,
    extraction_method         TEXT,
    UNIQUE(plant_id, compound_id, extraction_method)
);

CREATE TABLE IF NOT EXISTS compound_targets (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    compound_id             INTEGER REFERENCES compounds(compound_id) ON DELETE CASCADE,
    target_id                INTEGER REFERENCES targets(target_id) ON DELETE CASCADE,
    mechanism                 TEXT,
    UNIQUE(compound_id, target_id)
);

CREATE TABLE IF NOT EXISTS target_diseases (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id                INTEGER REFERENCES targets(target_id) ON DELETE CASCADE,
    disease_id                INTEGER REFERENCES diseases(disease_id) ON DELETE CASCADE,
    relevance_level             TEXT,
    UNIQUE(target_id, disease_id)
);

CREATE TABLE IF NOT EXISTS clinical_evidence (
    evidence_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id                INTEGER REFERENCES plants(plant_id) ON DELETE CASCADE,
    disease_id                INTEGER REFERENCES diseases(disease_id) ON DELETE CASCADE,
    study_type                 TEXT,
    preparation_form              TEXT,
    outcome                        TEXT,
    reference                       TEXT
);

CREATE TABLE IF NOT EXISTS regulatory_status (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id                INTEGER REFERENCES plants(plant_id) ON DELETE CASCADE,
    agency                    TEXT,
    status                      TEXT,
    approved_indication            TEXT,
    approved_preparation_form        TEXT
);

CREATE TABLE IF NOT EXISTS safety_profile (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id                INTEGER REFERENCES plants(plant_id) ON DELETE CASCADE,
    severity                  TEXT,
    description                 TEXT
);

CREATE TABLE IF NOT EXISTS market_information (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_id                INTEGER REFERENCES plants(plant_id) ON DELETE CASCADE,
    production_status          TEXT,
    commercial_attractiveness    TEXT
);

CREATE INDEX IF NOT EXISTS idx_pc_plant ON plant_compounds(plant_id);
CREATE INDEX IF NOT EXISTS idx_pc_compound ON plant_compounds(compound_id);
CREATE INDEX IF NOT EXISTS idx_ct_compound ON compound_targets(compound_id);
CREATE INDEX IF NOT EXISTS idx_ct_target ON compound_targets(target_id);
CREATE INDEX IF NOT EXISTS idx_td_target ON target_diseases(target_id);
CREATE INDEX IF NOT EXISTS idx_td_disease ON target_diseases(disease_id);
CREATE INDEX IF NOT EXISTS idx_ce_plant ON clinical_evidence(plant_id);
CREATE INDEX IF NOT EXISTS idx_ce_disease ON clinical_evidence(disease_id);
CREATE INDEX IF NOT EXISTS idx_reg_plant ON regulatory_status(plant_id);
CREATE INDEX IF NOT EXISTS idx_safety_plant ON safety_profile(plant_id);
CREATE INDEX IF NOT EXISTS idx_market_plant ON market_information(plant_id);
"""


def init_schema(reset=False):
    conn = get_connection()
    if reset:
        cur = conn.cursor()
        cur.executescript("""
            DROP TABLE IF EXISTS market_information;
            DROP TABLE IF EXISTS safety_profile;
            DROP TABLE IF EXISTS regulatory_status;
            DROP TABLE IF EXISTS clinical_evidence;
            DROP TABLE IF EXISTS target_diseases;
            DROP TABLE IF EXISTS compound_targets;
            DROP TABLE IF EXISTS plant_compounds;
            DROP TABLE IF EXISTS diseases;
            DROP TABLE IF EXISTS targets;
            DROP TABLE IF EXISTS compounds;
            DROP TABLE IF EXISTS plants;
        """)
        conn.commit()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_schema(reset=True)
    print(f"Schema created at {DB_PATH}")
