import pandas as pd
import indication_candidate_discovery as mod


class _Engine:
    def __init__(self, n=200):
        names = [f"Plantus species{i}" for i in range(n)]
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([
            {
                "Evidence_Record_ID": i,
                "Scientific_Name": name,
                "Title": f"{name} diabetes blood glucose clinical study",
                "Evidence_Level": "Human clinical trial",
                "Source_URL": f"https://example.org/{i}",
            }
            for i, name in enumerate(names)
        ])
        self._candidates = pd.DataFrame([
            {
                "Scientific_Name": name,
                "Known_Active_Compounds": "compound x",
                "Indications_Text": "diabetes",
            }
            for name in names
        ])

    def _candidate_frame(self):
        return self._candidates

    def _pick(self, row, names):
        for name in names:
            if name in row and pd.notna(row[name]):
                return str(row[name])
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        return "Human clinical evidence" if "clinical" in text.lower() else "Unknown"


def test_evidence_tables_are_indexed_once_per_discovery_run(monkeypatch):
    engine = _Engine()
    original = mod._build_plant_evidence_index
    calls = {"count": 0}

    def counted(e):
        calls["count"] += 1
        return original(e)

    monkeypatch.setattr(mod, "_build_plant_evidence_index", counted)
    out = mod.discover_indication_candidates(engine, "type 2 diabetes")

    assert calls["count"] == 1
    assert len(out) == 200
    assert out["Source_Record_IDs"].astype(str).str.len().gt(0).all()
