
from pathlib import Path

def test_database_persists_regulatory_authorization_status():
    text=Path("database.py").read_text()
    assert '"regulatory_authorization_status": record.get("Regulatory_Authorization_Status") or None' in text
    assert '"Regulatory_Authorization_Status": item.get("regulatory_authorization_status", "")' in text

def test_authorization_migration_exists():
    text=Path("migrations/0008_add_regulatory_authorization_status.sql").read_text().lower()
    assert "add column if not exists regulatory_authorization_status" in text
