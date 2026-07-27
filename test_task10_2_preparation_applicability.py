"""
Task 10.2 — Evidence-level Preparation Applicability. Regression tests.

WHAT THIS COVERS
1. standard_evidence_builder.classify_evidence_applicability() /
   build_standard_evidence() — the conservative dimension-based
   classifier, and that Direct_For_Selected_Product/Directness_Reason
   are preserved byte-for-byte.
2. database.save_evidence_record()/load_evidence_records() — the full
   round trip through a fake Supabase client (no real network/DB
   dependency, same pattern as test_telemetry_persistence.py's
   _FakeSupabaseClient).
3. botanical_rd_candidate_engine.py — the candidate-level
   Applicability_Summary (single-compound and multi-compound-merge
   paths), the _build_evidence_text_index() allowlist fix, and the
   non-regression guarantees (score/ranking/gates/Decision_Class_AH
   unchanged).
4. repo_dependency_audit — no legacy module (scientific_evidence_collector.py,
   dosage_classifier.py) became reachable from production.

HOW TO RUN
    pytest -q test_task10_2_preparation_applicability.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
import database
import repo_dependency_audit
from data_contracts import EvidenceApplicability
from standard_evidence_builder import build_standard_evidence, classify_evidence_applicability
from test_botanical_rd_candidate_engine import make_engine


# ======================================================================
# Fake Supabase client — same style as test_telemetry_persistence.py's
# _FakeSupabaseClient, extended to support the select/eq/limit/insert
# chains database.py's save_evidence_record()/load_evidence_records()
# actually issue. No real network/DB dependency.
# ======================================================================

class _FakeResponse:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FakeQuery:
    def __init__(self, client, table_name):
        self._client = client
        self._table_name = table_name
        self._insert_payload = None

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def range(self, *args, **kwargs):
        return self

    def insert(self, payload):
        self._insert_payload = payload
        return self

    def execute(self):
        if self._insert_payload is not None:
            return self._client._handle_insert(self._table_name, self._insert_payload)
        return self._client._handle_select(self._table_name)


class _FakeSupabaseClient:
    """Always reports existing-source/existing-plant lookups as "not
    found" (i.e. every save is treated as a brand-new evidence item) —
    correct for these tests, which never exercise the dedup path.
    load_evidence_records()'s single `select("*, plants(...), sources(...))`
    is reconstructed from the stored rows, joining in the matching
    plants/sources row exactly like real PostgREST embedding would.
    """
    def __init__(self):
        self.tables = {"plants": [], "sources": [], "evidence_records": []}
        self._next_id = {"plants": 1, "sources": 1, "evidence_records": 1}

    def table(self, name):
        return _FakeQuery(self, name)

    def _handle_insert(self, table_name, payload):
        new_id = self._next_id[table_name]
        self._next_id[table_name] += 1
        row = dict(payload)
        row["id"] = new_id
        self.tables[table_name].append(row)
        return _FakeResponse([row])

    def _handle_select(self, table_name):
        if table_name == "evidence_records":
            rows = []
            for r in self.tables["evidence_records"]:
                row = dict(r)
                plant = next(
                    (p for p in self.tables["plants"] if p["id"] == row.get("plant_id")), {}
                )
                source = next(
                    (s for s in self.tables["sources"] if s["id"] == row.get("source_id")), {}
                )
                row["plants"] = {
                    "scientific_name": plant.get("scientific_name", ""),
                    "common_name": plant.get("common_name", ""),
                }
                row["sources"] = dict(source)
                rows.append(row)
            return _FakeResponse(rows)
        return _FakeResponse([])


def _patch_supabase(monkeypatch, client):
    monkeypatch.setattr(database, "get_supabase_client", lambda: client)


# ======================================================================
# 1) classify_evidence_applicability() — conservative rules
# ======================================================================

def _record(**overrides):
    base = {
        "Scientific_Name": "PlantAlt",
        "Dosage_Form": "Infusion",
        "Target_Indication": "Sleep support",
        "Detected_Dosage_Forms": "",
        "Detected_Indications": "",
    }
    base.update(overrides)
    return base


def test_missing_preparation_information_yields_not_assessable():
    record = _record(Detected_Dosage_Forms="", Detected_Indications="")
    result = classify_evidence_applicability(
        record=record,
        selected_form="infusion",
        selected_indication="sleep support",
        detected_form="",
        detected_indication="",
    )
    assert result["classification"] == EvidenceApplicability.NOT_ASSESSABLE.value


def test_confirmed_mismatch_yields_not_applicable():
    record = _record()
    result = classify_evidence_applicability(
        record=record,
        selected_form="infusion",
        selected_indication="sleep support",
        detected_form="infusion",
        detected_indication="acne",
    )
    assert result["classification"] == EvidenceApplicability.NOT_APPLICABLE.value
    assert any("indication" in m for m in result["detected_mismatches"])


def test_indication_and_dosage_form_match_alone_cannot_yield_directly_applicable():
    record = _record()
    result = classify_evidence_applicability(
        record=record,
        selected_form="infusion",
        selected_indication="sleep support",
        detected_form="infusion",
        detected_indication="sleep support",
    )
    assert result["classification"] != EvidenceApplicability.DIRECTLY_APPLICABLE.value
    assert result["classification"] == EvidenceApplicability.PARTIALLY_APPLICABLE.value


def test_directly_applicable_is_not_reachable_under_current_schema():
    """Documents, as a locked regression, that plant_part/extraction
    are always "missing" today (no column exists anywhere in the
    active evidence_records schema) — so even a record with every
    field this function CAN read populated and matching never reaches
    DIRECTLY_APPLICABLE. See standard_evidence_builder.py's module
    docstring."""
    record = _record(Plant_Part="Leaf", Extraction_Method="Infusion")
    result = classify_evidence_applicability(
        record=record,
        selected_form="infusion",
        selected_indication="sleep support",
        detected_form="infusion",
        detected_indication="sleep support",
    )
    # Even with Plant_Part/Extraction_Method populated on the record,
    # there is no SELECTED counterpart to compare them against anywhere
    # in the active pipeline (see module docstring) — so these two
    # dimensions are always "missing", not "matched".
    assert result["classification"] == EvidenceApplicability.PARTIALLY_APPLICABLE.value
    assert "plant_part" in " ".join(result["missing_dimensions"])
    assert "extraction_or_solvent" in " ".join(result["missing_dimensions"])


def test_rationale_identifies_evaluated_missing_and_mismatched_dimensions():
    record = _record()
    result = classify_evidence_applicability(
        record=record,
        selected_form="infusion",
        selected_indication="sleep support",
        detected_form="capsule",
        detected_indication="sleep support",
    )
    assert "indication" in result["rationale"]
    assert "dosage_form" in result["rationale"]
    assert "plant_part" in result["rationale"]
    assert "NOT_APPLICABLE" in result["rationale"]


def test_direct_for_selected_product_and_directness_reason_unchanged():
    """Locks build_standard_evidence()'s pre-existing two branches to
    their exact pre-Task-10.2 strings, independent of the new
    Applicability_Classification logic."""
    match = build_standard_evidence(_record(Detected_Dosage_Forms="Infusion tea"))
    assert match["Direct_For_Selected_Product"] == "Yes"
    assert match["Directness_Reason"] == "Detected dosage form matches selected product dosage form."

    mismatch = build_standard_evidence(_record(Detected_Dosage_Forms="Capsule"))
    assert mismatch["Direct_For_Selected_Product"] == "No"
    assert mismatch["Directness_Reason"] == "Detected dosage form differs: Capsule"

    unknown = build_standard_evidence(_record(Detected_Dosage_Forms=""))
    assert unknown["Direct_For_Selected_Product"] == "Unknown"
    assert unknown["Directness_Reason"] == "Dosage form not clearly detected."

    # New fields are present and additive, never having overwritten the
    # two above.
    for row in (match, mismatch, unknown):
        assert "Applicability_Classification" in row
        assert row["Applicability_Classification"] in {m.value for m in EvidenceApplicability}


# ======================================================================
# 2) Full save -> load round trip (fake Supabase client)
# ======================================================================

def test_applicability_fields_survive_build_save_load_round_trip(monkeypatch):
    client = _FakeSupabaseClient()
    _patch_supabase(monkeypatch, client)

    raw = {
        "Scientific_Name": "PlantAlt",
        "Common_Name": "",
        "Dosage_Form": "Infusion",
        "Target_Indication": "Sleep support",
        "Detected_Dosage_Forms": "Infusion tea",
        "Detected_Indications": "Sleep support",
        "Source_URL": "https://example.org/study1",
        "Source_Title": "Study 1",
    }
    standardized = build_standard_evidence(raw)
    expected_classification = standardized["Applicability_Classification"]
    expected_rationale = standardized["Applicability_Rationale"]

    row_id = database.save_evidence_record(standardized)
    assert row_id is not None

    loaded_df = database.load_evidence_records()
    loaded = loaded_df[loaded_df["Source_Title"] == "Study 1"].iloc[0]

    assert loaded["Applicability_Classification"] == expected_classification
    assert loaded["Applicability_Rationale"] == expected_rationale
    assert loaded["Applicability_Evaluated_Dimensions"] == standardized["Applicability_Evaluated_Dimensions"]
    assert loaded["Applicability_Missing_Dimensions"] == standardized["Applicability_Missing_Dimensions"]
    assert loaded["Applicability_Detected_Mismatches"] == standardized["Applicability_Detected_Mismatches"]
    # Task 10.2 — previously-discarded primary key now round-trips too.
    assert loaded["Evidence_Record_ID"] == row_id
    assert loaded["Direct_For_Selected_Product"] == "Yes"


def test_existing_callers_backward_compatible_when_new_columns_absent(monkeypatch):
    """Simulates a Supabase evidence_records table that has NOT yet had
    the five new columns added (item dicts simply lack those keys,
    exactly like a real not-yet-migrated PostgREST response) — must
    not raise, and must degrade to empty string, per database.py's own
    documented behavior."""
    client = _FakeSupabaseClient()
    _patch_supabase(monkeypatch, client)

    old_style_row = {
        "id": 999,
        "plant_id": 1,
        "source_id": 1,
        "dosage_form": "Infusion",
        "target_indication": "Sleep support",
        "direct_for_selected_product": "Yes",
        "directness_reason": "Detected dosage form matches selected product dosage form.",
        # No applicability_* keys at all — pre-Task-10.2 row shape.
    }
    client.tables["plants"].append({"id": 1, "scientific_name": "PlantAlt", "common_name": ""})
    client.tables["sources"].append({"id": 1})
    client.tables["evidence_records"].append(old_style_row)

    loaded_df = database.load_evidence_records()
    loaded = loaded_df.iloc[0]

    assert loaded["Applicability_Classification"] == ""
    assert loaded["Applicability_Rationale"] == ""
    assert loaded["Direct_For_Selected_Product"] == "Yes"


# ======================================================================
# 3) Candidate-level Applicability_Summary via the engine
# ======================================================================

def _base_plant_compound_rows():
    return [
        dict(scientific_name="PlantRef", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
        dict(scientific_name="PlantAlt", compound_name="RefCompoundA",
             indication="TestIndication", target="Laxative",
             common_name="", plant_part="", extraction_method=""),
    ]


def _evidence_row(evidence_record_id, classification, rationale="", text=""):
    return {
        "Scientific_Name": "PlantAlt",
        "Plant": "PlantAlt",
        "Notes": f"RefCompoundA {text}".strip(),
        "Primary_Outcome": f"RefCompoundA {text}".strip(),
        "Evidence_Record_ID": evidence_record_id,
        "Applicability_Classification": classification,
        "Applicability_Rationale": rationale,
        "Applicability_Evaluated_Dimensions": "indication; dosage_form",
        "Applicability_Missing_Dimensions": "plant_part; extraction_or_solvent",
        "Applicability_Detected_Mismatches": "",
    }


def test_candidate_summary_contains_exact_evidence_record_identifiers():
    evidence_df = pd.DataFrame([
        _evidence_row("ev-1", EvidenceApplicability.PARTIALLY_APPLICABLE.value),
    ])
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(
            _base_plant_compound_rows() +
            [dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
                  indication="background", target="Antioxidant",
                  common_name="", plant_part="", extraction_method="")
             for i in range(25)]
        ),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=False,
    )
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    alt_row = result[result["Alternative_Plant"] == "PlantAlt"].iloc[0]

    summary = alt_row["Applicability_Summary"]
    assert isinstance(summary, dict)
    assert "ev-1" in summary["evidence_record_ids"]
    assert summary["total_evidence_items"] == 1
    assert summary["counts"][EvidenceApplicability.PARTIALLY_APPLICABLE.value] == 1


def test_multiple_evidence_records_remain_individually_traceable():
    evidence_df = pd.DataFrame([
        _evidence_row("ev-1", EvidenceApplicability.PARTIALLY_APPLICABLE.value, text="study one"),
        _evidence_row("ev-2", EvidenceApplicability.NOT_APPLICABLE.value, text="study two"),
    ])
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(
            _base_plant_compound_rows() +
            [dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
                  indication="background", target="Antioxidant",
                  common_name="", plant_part="", extraction_method="")
             for i in range(25)]
        ),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=False,
    )
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    alt_row = result[result["Alternative_Plant"] == "PlantAlt"].iloc[0]

    summary = alt_row["Applicability_Summary"]
    assert set(summary["evidence_record_ids"]) == {"ev-1", "ev-2"}
    assert summary["total_evidence_items"] == 2
    assert summary["counts"][EvidenceApplicability.PARTIALLY_APPLICABLE.value] == 1
    assert summary["counts"][EvidenceApplicability.NOT_APPLICABLE.value] == 1
    assert summary["strongest_category"] == EvidenceApplicability.PARTIALLY_APPLICABLE.value


# ======================================================================
# 4) Non-regression: scores/ranking/gates/Decision_Class_AH unchanged
# ======================================================================

def _run_result(evidence_df):
    rows = _base_plant_compound_rows() + [
        dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
             indication="background", target="Antioxidant",
             common_name="", plant_part="", extraction_method="")
        for i in range(25)
    ]
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(rows),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=False,
    )
    result = engine.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    return result[result["Alternative_Plant"] == "PlantAlt"].iloc[0]


def test_realistic_applicability_text_does_not_alter_scoring_or_classification():
    """Same underlying evidence content in both runs (a clinical-trial-
    shaped Notes string); the second run additionally carries rich,
    deliberately keyword-loaded Applicability_Rationale/_Classification
    text designed to collide with classify_evidence_hierarchy()'s own
    keyword list ('systematic review', 'meta-analysis') — if the
    allowlist fix in _build_evidence_text_index() were missing, this
    text leaking into the classifier's input could change
    Evidence_Hierarchy_Detail even though nothing about the actual
    study changed."""
    shared_text = "randomized controlled trial RefCompoundA outcome improved"

    without_applicability = pd.DataFrame([{
        "Scientific_Name": "PlantAlt",
        "Plant": "PlantAlt",
        "Notes": shared_text,
        "Primary_Outcome": shared_text,
    }])

    with_applicability = pd.DataFrame([{
        "Scientific_Name": "PlantAlt",
        "Plant": "PlantAlt",
        "Notes": shared_text,
        "Primary_Outcome": shared_text,
        "Evidence_Record_ID": "ev-stress-1",
        "Applicability_Classification": EvidenceApplicability.NOT_APPLICABLE.value,
        "Applicability_Rationale": (
            "NOT_APPLICABLE: this is a systematic review / meta-analysis grade "
            "rationale string deliberately loaded with hierarchy-classifier "
            "keywords to stress-test the text-index allowlist. clinical trial "
            "randomized controlled trial observational human evidence"
        ),
        "Applicability_Evaluated_Dimensions": "indication; dosage_form",
        "Applicability_Missing_Dimensions": "plant_part; extraction_or_solvent",
        "Applicability_Detected_Mismatches": "indication (detected 'acne' vs selected 'sleep support')",
    }])

    row_a = _run_result(without_applicability)
    row_b = _run_result(with_applicability)

    assert row_a["R&D_Opportunity_Score"] == row_b["R&D_Opportunity_Score"]
    assert row_a["Decision_Class"] == row_b["Decision_Class"]
    assert row_a["Decision_Class_AH"] == row_b["Decision_Class_AH"]
    assert row_a["Evidence_Hierarchy_Detail"] == row_b["Evidence_Hierarchy_Detail"]
    assert row_a["Has_Negative_Evidence"] == row_b["Has_Negative_Evidence"]
    assert row_a["Gate_Results"] == row_b["Gate_Results"]
    assert row_a["Go_Investigate_Hold_NoGo"] == row_b["Go_Investigate_Hold_NoGo"]


def test_build_evidence_text_index_excludes_platform_generated_fields():
    marker = "UNIQUEAPPLICABILITYMARKERSTRING123"
    evidence_df = pd.DataFrame([{
        "Scientific_Name": "PlantAlt",
        "Plant": "PlantAlt",
        "Notes": "RefCompoundA genuine source text",
        "Direct_For_Selected_Product": "Yes",
        "Directness_Reason": marker + "_directness",
        "Applicability_Classification": marker + "_classification",
        "Applicability_Rationale": marker + "_rationale",
        "Applicability_Evaluated_Dimensions": marker + "_evaluated",
        "Applicability_Missing_Dimensions": marker + "_missing",
        "Applicability_Detected_Mismatches": marker + "_mismatch",
    }])
    engine = eng.BotanicalRDCandidateEngine(
        plant_compounds_df=pd.DataFrame(_base_plant_compound_rows()),
        compound_profiles_df=pd.DataFrame(),
        scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df,
        use_live_search=False,
    )
    text_index, _source_index, applicability_index = engine._build_evidence_text_index()

    all_text = " ".join(text_index.values())
    assert marker not in all_text
    assert "genuine source text" in all_text

    # The structured applicability_index, in contrast, DOES carry the
    # classification/rationale — just not folded into the free-text
    # blob classifiers read.
    plant_key = engine._norm("PlantAlt")
    assert any(
        marker + "_classification" == item["classification"]
        for item in applicability_index.get(plant_key, [])
    )


# ======================================================================
# 5) No legacy module reachable from production
# ======================================================================

def test_no_legacy_preparation_or_dosage_module_becomes_production_reachable():
    sets = repo_dependency_audit.compute_dependency_sets(".")
    assert "scientific_evidence_collector" not in sets.production_active
    assert "scientific_evidence_collector" in sets.legacy_candidates
    assert "dosage_classifier" not in sets.production_active
    assert "dosage_classifier" in sets.legacy_candidates
    # The Task 10.2 modules that WERE changed must remain production-active.
    assert "standard_evidence_builder" in sets.production_active
    assert "botanical_rd_candidate_engine" in sets.production_active
    assert "database" in sets.production_active
    assert "data_contracts" in sets.production_active
    assert "candidate_output_adapter" in sets.production_active
