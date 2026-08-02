import pandas as pd

from indication_semantics import indication_terms, resolve_indication_semantics
from indication_candidate_discovery import discover_indication_candidates
from candidate_shortlisting import build_plant_candidate_shortlist


class _Engine:
    def __init__(self):
        self.evidence_df = pd.DataFrame()
        self.scientific_evidence_df = pd.DataFrame()
        self.evidence_records_df = pd.DataFrame([
            {
                "id": 1001,
                "plant": "Thymus vulgaris",
                "target_indication": "Acute bronchitis",
                "study_type": "Randomized human clinical trial",
                "primary_outcome": "Reduced cough frequency and cough severity",
                "result_direction": "positive benefit",
                "evidence_level": "Human RCT",
                "dosage_form": "Infusion",
                "source_url": "https://example.org/thymus-cough",
            },
            {
                "id": 1002,
                "plant": "Glycyrrhiza glabra",
                "target_indication": "Sore throat and productive cough",
                "study_type": "Human clinical study",
                "primary_outcome": "Improved cough score",
                "result_direction": "positive benefit",
                "evidence_level": "Human clinical evidence",
                "dosage_form": "Infusion",
                "source_url": "https://example.org/licorice-cough",
            },
            {
                "id": 1003,
                "plant": "Unrelated plant",
                "target_indication": "Type 2 diabetes",
                "study_type": "Randomized human clinical trial",
                "primary_outcome": "Reduced HbA1c",
                "result_direction": "positive benefit",
                "evidence_level": "Human RCT",
                "source_url": "https://example.org/diabetes",
            },
        ])

    def _candidate_frame(self):
        return pd.DataFrame([
            {"Scientific_Name": "Thymus vulgaris", "Known_Active_Compounds": "thymol", "Known_Targets": "expectorant; bronchorelaxant"},
            {"Scientific_Name": "Glycyrrhiza glabra", "Known_Active_Compounds": "glycyrrhizin", "Known_Targets": "demulcent; expectorant"},
            {"Scientific_Name": "Unrelated plant", "Known_Active_Compounds": "x", "Known_Targets": "AMPK"},
        ])

    def _pick(self, row, names):
        for name in names:
            if name in row and pd.notna(row[name]) and str(row[name]).strip():
                return str(row[name])
        return ""

    def _split_compound_terms(self, value):
        return [x.strip() for x in str(value).split(";") if x.strip()]

    def _evidence_level(self, text):
        return "Clinical / human evidence" if "human" in text.lower() or "randomized" in text.lower() else "Unknown"


def test_cough_has_nonliteral_clinical_and_mechanistic_semantics():
    direct, mechanistic = indication_terms("Cough")
    assert "antitussive" in direct
    assert "cough frequency" in direct
    assert "expectorant" in mechanistic
    assert "demulcent" in mechanistic


def test_all_ui_indications_resolve_to_a_semantic_family():
    ui_indications = [
        "Sleep and relaxation", "Anxiety", "Stress", "Inflammation",
        "Constipation", "Cough", "Digestive comfort", "Skin inflammation",
        "Dry mouth", "Allergic rhinitis", "IBS", "Wound healing",
        "Cognitive decline / Alzheimer's support", "Immune support",
        "Cardiovascular / circulation", "Liver support / detox",
        "Joint & muscle comfort", "Energy / fatigue",
        "Metabolic & blood sugar support", "Weight management",
        "Menopause support", "Menstrual / PMS support",
        "Prostate / men's health", "Urinary tract health",
        "Cold & flu / respiratory", "Headache / mood support",
        "Hair, skin & nail beauty-from-within", "Eye health",
    ]
    unresolved = [name for name in ui_indications if resolve_indication_semantics(name) is None]
    assert unresolved == []


def test_cough_discovery_finds_plant_specific_evidence_without_diabetes_leakage():
    out = discover_indication_candidates(_Engine(), "Cough", dosage_form="Infusion")
    assert set(out["Alternative_Plant"]) == {"Thymus vulgaris", "Glycyrrhiza glabra"}
    assert "Unrelated plant" not in set(out["Alternative_Plant"])
    assert all(out["Source_Record_IDs"].astype(str).isin({"1001", "1002"}))


def test_cough_candidates_survive_plant_level_indication_relevance_gate():
    raw = discover_indication_candidates(_Engine(), "Cough", dosage_form="Infusion")
    summary, _ = build_plant_candidate_shortlist(raw, indication="Cough", dosage_form="Infusion")
    selected = summary.set_index("Alternative_Plant")
    assert selected.loc["Thymus vulgaris", "Indication_Relevance_Score"] > 0
    assert selected.loc["Glycyrrhiza glabra", "Indication_Relevance_Score"] > 0
    assert selected.loc["Thymus vulgaris", "Scientific_Triage_Status"] in {"Shortlist", "Exploratory"}
