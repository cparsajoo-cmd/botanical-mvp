"""
Task 14.1 — Activate RegulatoryRecord for EMA/HMPC Inventory Records.

WHAT THIS COVERS
standard_evidence_builder.build_regulatory_record() — the narrow,
Source_Type-gated adapter from an active evidence_records row into
data_contracts.RegulatoryRecord. No engine, no database, no
Streamlit, no scoring/gates/reports — this file tests exactly one
pure function.

WHY THE ELIGIBILITY TESTS MATTER MOST
The Task 14 audit found three independent, differently-reliable
mechanisms that can set EMA_Status on an evidence row (a confirmed
false-positive-prone keyword substring match, an LLM's subjective
relevance judgment, and the real EMA/HMPC connector). This builder's
entire safety rests on the Source_Type=="Regulatory" gate excluding
the first two — the tests below exercise that gate directly against
realistic shapes of all three mechanisms' actual output, not just
hypothetical inputs.

HOW TO RUN
    pytest -q test_task14_1_regulatory_record_activation.py
    (or `pytest -q` from the repo root — auto-discovered)
"""

import pandas as pd

import botanical_rd_candidate_engine as eng
from data_contracts import MarketVerificationStatus, RegulatoryRecord
from standard_evidence_builder import build_regulatory_record


# ---------------------------------------------------------------------
# Realistic fixtures, matching the ACTUAL output shape of each of the
# three mechanisms the Task 14 audit traced.
# ---------------------------------------------------------------------

def _ema_inventory_listed_row(**overrides):
    """Matches ema_regulatory_connector.search_regulatory_sources_real()'s
    real "found" branch verbatim."""
    row = {
        "Scientific_Name": "Valeriana officinalis",
        "Source_Type": "Regulatory",
        "Source_Organization": "EMA HMPC — Inventory of herbal substances for assessment",
        "Source_Title": "EMA HMPC inventory of herbal substances — Valeriana officinalis",
        "Source_URL": "https://www.ema.europa.eu/en/documents/other/inventory-herbal-substances-assessment_en.pdf#plant=Valeriana_officinalis",
        "Source_Year": "2021",
        "Evidence_Level": "Listed in official EMA HMPC inventory",
        "Target_Market": "European Union",
        "Evidence_Record_ID": "ev-101",
    }
    row.update(overrides)
    return row


def _ema_checked_not_found_row(**overrides):
    row = {
        "Source_Type": "Regulatory",
        "Source_Organization": "EMA HMPC — Inventory of herbal substances for assessment",
        "Evidence_Level": "Checked, not found",
        "Target_Market": "European Union",
        "Evidence_Record_ID": "ev-102",
    }
    row.update(overrides)
    return row


def _ema_source_unavailable_row(**overrides):
    row = {
        "Source_Type": "Regulatory",
        "Source_Organization": "EMA HMPC (live fetch failed)",
        "Evidence_Level": "Not available",
        "Evidence_Record_ID": "ev-103",
    }
    row.update(overrides)
    return row


def _pubmed_row_mentioning_ema(**overrides):
    """Matches evidence_extractor.py's naive substring path AND
    evidence_standardizer.py's LLM-relevance path — an ordinary
    scientific article that happens to trigger EMA_Status via either
    of the two confirmed-unreliable mechanisms."""
    row = {
        "Scientific_Name": "Valeriana officinalis",
        "Source_Type": "PubMed",
        "Source_Organization": "NCBI PubMed",
        "Notes": (
            "A randomized controlled trial following a strict enema "
            "preparation schema, discussing the European Medicines "
            "Agency's broader regulatory context for herbal products."
        ),
        "EMA_Status": "Yes",
        "Regulatory_Status": "EMA/HMPC evidence detected",
        "Evidence_Level": "Unknown",
        "Evidence_Record_ID": "ev-201",
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------
# 1) A genuine EMA/HMPC Source_Type=="Regulatory" inventory record
#    creates a real RegulatoryRecord.
# ---------------------------------------------------------------------

def test_genuine_ema_inventory_row_creates_a_real_regulatory_record():
    result = build_regulatory_record(_ema_inventory_listed_row())
    assert isinstance(result, RegulatoryRecord)
    assert result.source_record_ids == ["ev-101"]
    assert result.jurisdiction_or_market == "European Union"
    assert result.monograph_source == "EMA/HMPC"


# ---------------------------------------------------------------------
# Task 14.1 correction — tightened EMA/HMPC organization identification.
# monograph_source must be set only for the real connector's actual
# organization strings (a strict "starts with EMA HMPC" match), never
# a loose "contains ema" substring match.
# ---------------------------------------------------------------------

def test_ema_hmpc_inventory_organization_string_maps_to_ema_hmpc():
    result = build_regulatory_record(_ema_inventory_listed_row(
        Source_Organization="EMA HMPC — Inventory of herbal substances for assessment",
    ))
    assert result.monograph_source == "EMA/HMPC"


def test_ema_hmpc_live_fetch_failed_organization_string_maps_to_ema_hmpc():
    result = build_regulatory_record(_ema_inventory_listed_row(
        Source_Organization="EMA HMPC (live fetch failed)",
    ))
    assert result.monograph_source == "EMA/HMPC"


def test_schema_regulatory_authority_organization_does_not_map_to_ema_hmpc():
    """The exact false-positive shape the loose "contains ema" check
    would have wrongly matched — "Schema" contains "ema" as a
    substring, but is obviously not an EMA/HMPC organization."""
    result = build_regulatory_record(_ema_inventory_listed_row(
        Source_Organization="Schema Regulatory Authority",
    ))
    assert result.monograph_source is None


def test_organization_merely_mentioning_ema_mid_text_does_not_map_to_ema_hmpc():
    result = build_regulatory_record(_ema_inventory_listed_row(
        Source_Organization="Some Authority mentioning EMA in the middle of unrelated text",
    ))
    assert result.monograph_source is None


def test_missing_organization_leaves_monograph_source_none():
    row = _ema_inventory_listed_row()
    del row["Source_Organization"]
    result = build_regulatory_record(row)
    assert result.monograph_source is None


# ---------------------------------------------------------------------
# 2) Inventory listing maps to REGULATORY_ASSESSMENT_INVENTORY_LISTED,
#    not REGULATORY_MONOGRAPH_EXISTS.
# ---------------------------------------------------------------------

def test_inventory_listing_maps_to_inventory_listed_not_monograph_exists():
    result = build_regulatory_record(_ema_inventory_listed_row())
    assert result.status == MarketVerificationStatus.REGULATORY_ASSESSMENT_INVENTORY_LISTED
    assert result.status != MarketVerificationStatus.REGULATORY_MONOGRAPH_EXISTS


# ---------------------------------------------------------------------
# 3) Explicit checked-not-found maps conservatively.
# ---------------------------------------------------------------------

def test_checked_not_found_maps_to_no_verified_product_found():
    result = build_regulatory_record(_ema_checked_not_found_row())
    assert result.status == MarketVerificationStatus.NO_VERIFIED_PRODUCT_FOUND


# ---------------------------------------------------------------------
# 4) Explicit source-unavailable maps conservatively.
# ---------------------------------------------------------------------

def test_source_unavailable_maps_to_source_unavailable():
    result = build_regulatory_record(_ema_source_unavailable_row())
    assert result.status == MarketVerificationStatus.SOURCE_UNAVAILABLE


# ---------------------------------------------------------------------
# 5) Unknown eligible regulatory wording maps to UNKNOWN, never guessed.
# ---------------------------------------------------------------------

def test_unmapped_evidence_level_on_an_eligible_row_maps_to_unknown():
    result = build_regulatory_record(_ema_inventory_listed_row(
        Evidence_Level="Some future connector wording this table doesn't know about"
    ))
    assert result.status == MarketVerificationStatus.UNKNOWN


def test_missing_evidence_level_on_an_eligible_row_maps_to_unknown():
    row = _ema_inventory_listed_row()
    del row["Evidence_Level"]
    result = build_regulatory_record(row)
    assert result.status == MarketVerificationStatus.UNKNOWN


# ---------------------------------------------------------------------
# 6) Evidence_Record_ID and lowercase alias are both supported.
# ---------------------------------------------------------------------

def test_evidence_record_id_supported():
    result = build_regulatory_record(_ema_inventory_listed_row(Evidence_Record_ID="ev-999"))
    assert result.source_record_ids == ["ev-999"]


def test_lowercase_evidence_record_id_alias_supported():
    row = _ema_inventory_listed_row()
    del row["Evidence_Record_ID"]
    row["evidence_record_id"] = "ev-lower"
    result = build_regulatory_record(row)
    assert result.source_record_ids == ["ev-lower"]


# ---------------------------------------------------------------------
# 7) A missing stable ID returns None.
# ---------------------------------------------------------------------

def test_missing_stable_id_returns_none():
    row = _ema_inventory_listed_row()
    del row["Evidence_Record_ID"]
    assert build_regulatory_record(row) is None


# ---------------------------------------------------------------------
# 8) A PubMed / ordinary scientific row returns None, even when it
#    mentions EMA, contains "schema"/"enema", has EMA_Status=="Yes",
#    or an LLM relevance field says yes.
# ---------------------------------------------------------------------

def test_pubmed_row_mentioning_ema_and_containing_schema_enema_returns_none():
    result = build_regulatory_record(_pubmed_row_mentioning_ema())
    assert result is None


def test_ema_status_yes_alone_never_creates_a_record():
    row = _pubmed_row_mentioning_ema(Notes="Ordinary abstract text with no special words.")
    assert row["EMA_Status"] == "Yes"
    assert build_regulatory_record(row) is None


def test_llm_ema_relevance_field_never_creates_a_record():
    row = _pubmed_row_mentioning_ema(
        Notes="Ordinary abstract.", LLM_EMA_Relevance="yes", ema_relevance="yes",
    )
    assert build_regulatory_record(row) is None


def test_source_type_regulatory_like_but_not_exact_is_rejected():
    """Only an EXACT (case-insensitive) match to "regulatory" is
    eligible — a near-miss Source_Type must not slip through."""
    for near_miss in ("Regulatory Article", "Regulatory-ish", "Semi-Regulatory", "PubMed/Regulatory"):
        row = _ema_inventory_listed_row(Source_Type=near_miss)
        assert build_regulatory_record(row) is None, f"{near_miss!r} should be rejected"


def test_source_type_regulatory_case_insensitive_is_accepted():
    for casing in ("Regulatory", "regulatory", "REGULATORY", "ReGuLaToRy"):
        row = _ema_inventory_listed_row(Source_Type=casing)
        assert build_regulatory_record(row) is not None, f"{casing!r} should be accepted"


# ---------------------------------------------------------------------
# 9) WHO, ESCOP, and Novel Food placeholders never create a record on
#    their own, and are never read by this function.
# ---------------------------------------------------------------------

def test_who_escop_novel_food_alone_on_a_non_regulatory_row_create_nothing():
    row = {
        "Source_Type": "PubMed",
        "WHO_Status": "Yes",
        "ESCOP_Status": "Yes",
        "Novel_Food_Status": "To verify",
        "Evidence_Record_ID": "ev-301",
    }
    assert build_regulatory_record(row) is None


def test_who_escop_placeholder_text_on_an_eligible_row_is_never_read():
    """Even on an ELIGIBLE (Source_Type=="Regulatory") row, WHO_Status/
    ESCOP_Status must never influence the result — confirmed by giving
    them the real connector's own non-answer placeholder text and
    checking the record construction succeeds/fails purely based on
    Evidence_Level, unaffected by these fields' content."""
    row = _ema_inventory_listed_row(
        WHO_Status="See source PDF (column not reliably text-extractable)",
        ESCOP_Status="See source PDF (column not reliably text-extractable)",
        Novel_Food_Status="To verify",
    )
    result = build_regulatory_record(row)
    assert result.status == MarketVerificationStatus.REGULATORY_ASSESSMENT_INVENTORY_LISTED


# ---------------------------------------------------------------------
# 10) None, NaN, and pd.NA values are handled safely.
# ---------------------------------------------------------------------

def test_none_nan_pdna_values_handled_safely():
    for missing in (None, float("nan"), pd.NA):
        row = _ema_inventory_listed_row(
            Target_Market=missing, Source_Organization=missing, Evidence_Level=missing,
        )
        result = build_regulatory_record(row)
        assert result is not None  # id still valid
        assert result.jurisdiction_or_market is None
        assert result.monograph_source is None
        assert result.status == MarketVerificationStatus.UNKNOWN


def test_nan_evidence_record_id_returns_none():
    row = _ema_inventory_listed_row(Evidence_Record_ID=float("nan"))
    assert build_regulatory_record(row) is None


# ---------------------------------------------------------------------
# 11) Malformed input does not crash.
# ---------------------------------------------------------------------

def test_malformed_input_does_not_crash():
    for bad_input in (
        "not a mapping", 42, ["a", "list"], None, object(),
        {"Source_Type": object(), "Evidence_Record_ID": "x"},
        {"Source_Type": "Regulatory", "Evidence_Record_ID": object()},
    ):
        result = build_regulatory_record(bad_input)
        assert result is None or isinstance(result, RegulatoryRecord)


# ---------------------------------------------------------------------
# 12) Scope fields and last_verified_date remain None.
# ---------------------------------------------------------------------

def test_scope_fields_and_last_verified_date_always_none():
    row = _ema_inventory_listed_row(
        Dosage_Form="Infusion", Target_Indication="Sleep support", Source_Year="2021",
    )
    result = build_regulatory_record(row)
    assert result.scope_whole_herb_or_extract is None
    assert result.scope_traditional_indication is None
    assert result.scope_dosage_form is None
    assert result.last_verified_date is None


# ---------------------------------------------------------------------
# 13) The result contains one evidence-record ID and no duplicated URL
#     field.
# ---------------------------------------------------------------------

def test_result_contains_exactly_one_id_and_no_url_field():
    result = build_regulatory_record(_ema_inventory_listed_row())
    assert len(result.source_record_ids) == 1
    assert result.source_record_ids == ["ev-101"]
    assert not hasattr(result, "source_url")
    assert not hasattr(result, "url")
    assert not hasattr(result, "doi_pmid_url")


# ---------------------------------------------------------------------
# 14) The input mapping is not mutated.
# ---------------------------------------------------------------------

def test_input_mapping_is_not_mutated():
    row = _ema_inventory_listed_row()
    snapshot = dict(row)
    build_regulatory_record(row)
    assert row == snapshot


def test_input_dataframe_row_not_mutated():
    df = pd.DataFrame([_ema_inventory_listed_row()])
    snapshot = df.copy(deep=True)
    for _, row in df.iterrows():
        build_regulatory_record(row.to_dict())
    assert df.equals(snapshot)


# ---------------------------------------------------------------------
# 15) Existing enum values remain unchanged.
# ---------------------------------------------------------------------

def test_existing_enum_values_unchanged():
    assert MarketVerificationStatus.VERIFIED_MARKETED_PRODUCT.value == "Verified marketed product"
    assert MarketVerificationStatus.COMMERCIAL_EVIDENCE_UNVERIFIED.value == (
        "Commercial evidence reported, not independently verified"
    )
    assert MarketVerificationStatus.REGULATORY_MONOGRAPH_EXISTS.value == "Regulatory monograph exists"
    assert MarketVerificationStatus.TRADITIONAL_USE_STATUS.value == "Traditional-use status"
    assert MarketVerificationStatus.NO_VERIFIED_PRODUCT_FOUND.value == "No verified product found"
    assert MarketVerificationStatus.SEARCH_NOT_PERFORMED.value == "Search not performed"
    assert MarketVerificationStatus.SOURCE_UNAVAILABLE.value == "Source unavailable"
    assert MarketVerificationStatus.UNKNOWN.value == "Unknown"


def test_new_enum_value_added_correctly():
    assert (
        MarketVerificationStatus.REGULATORY_ASSESSMENT_INVENTORY_LISTED.value
        == "Listed in official regulatory assessment inventory"
    )
    assert len(list(MarketVerificationStatus)) == 9


# ---------------------------------------------------------------------
# 16) Existing flat regulatory fields remain unchanged (this function
#     never writes to its input, so this is really a call-site-level
#     confirmation that nothing about evidence_extractor.py/
#     evidence_standardizer.py's own flat-field output changed).
# ---------------------------------------------------------------------

def test_existing_flat_regulatory_fields_pass_through_unread_and_unwritten():
    row = _ema_inventory_listed_row(
        EMA_Status="Listed in HMPC inventory as 'Valerianae radix' — see source PDF for monograph status",
        WHO_Status="See source PDF (column not reliably text-extractable)",
        ESCOP_Status="See source PDF (column not reliably text-extractable)",
        Novel_Food_Status="To verify",
    )
    before = dict(row)
    build_regulatory_record(row)
    assert row["EMA_Status"] == before["EMA_Status"]
    assert row["WHO_Status"] == before["WHO_Status"]
    assert row["ESCOP_Status"] == before["ESCOP_Status"]
    assert row["Novel_Food_Status"] == before["Novel_Food_Status"]


# ---------------------------------------------------------------------
# 17) Scoring, gates, ranking, decision outputs remain byte-identical.
# ---------------------------------------------------------------------

def test_standard_evidence_builder_has_no_engine_or_streamlit_import():
    """Real, non-tautological check: standard_evidence_builder.py's own
    import statements (parsed via ast, not a sys.modules check that
    would trivially pass regardless of what this function does) must
    not include the engine, Streamlit, or the database layer."""
    import ast
    with open("standard_evidence_builder.py", encoding="utf-8") as f:
        tree = ast.parse(f.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = {"botanical_rd_candidate_engine", "streamlit", "database"}
    assert not (imported & forbidden), f"forbidden import(s) found: {imported & forbidden}"


def test_constructing_regulatory_records_does_not_alter_engine_output():
    """Task 14.1 correction — a REAL regression test, not an import
    check. Proves that constructing RegulatoryRecord objects (via
    build_regulatory_record(), called directly against the same
    evidence rows the engine also sees) has zero effect on the
    engine's own R&D_Opportunity_Score/Decision_Class/Gate_Results/
    candidate ranking — the builder is a pure, disconnected reader,
    never wired into scoring.

    Uses a deterministic mixed evidence fixture: two alternative
    plants competing for the same reference compound (so ranking is
    real and non-trivial, not a single-row edge case), plus one
    genuine Source_Type=="Regulatory" EMA row (the exact shape
    build_regulatory_record() is meant to activate) mixed in among
    ordinary PubMed rows.

    Same reusable engine-construction pattern as Task 11.1's own
    test_scores_ranking_gates_and_decision_class_unchanged() — no new
    harness invented.
    """
    evidence_df = pd.DataFrame([
        {
            "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
            "Notes": "randomized controlled trial RefCompoundA outcome improved",
            "Primary_Outcome": "randomized controlled trial RefCompoundA outcome improved",
            "Source_Type": "PubMed",
            "Target_Indication": "TestIndication",
            "Evidence_Record_ID": "ev-sci-1",
            "Evidence_Level": "High",
        },
        {
            "Scientific_Name": "PlantAlt", "Plant": "PlantAlt",
            "Notes": "European Medicines Agency HMPC assessment context for PlantAlt",
            "Source_Type": "Regulatory",
            "Target_Indication": "TestIndication",
            "Source_Organization": "EMA HMPC — Inventory of herbal substances for assessment",
            "Evidence_Level": "Listed in official EMA HMPC inventory",
            "Target_Market": "European Union",
            "Evidence_Record_ID": "ev-reg-1",
        },
        {
            "Scientific_Name": "PlantAlt2", "Plant": "PlantAlt2",
            "Notes": "weak observational report RefCompoundA no clear effect",
            "Source_Type": "PubMed",
            "Target_Indication": "TestIndication",
            "Evidence_Record_ID": "ev-sci-2",
            "Evidence_Level": "Low",
        },
    ])

    def _make_ranking_engine(edf):
        rows = [
            dict(scientific_name="PlantRef", compound_name="RefCompoundA",
                 indication="TestIndication", target="Laxative",
                 common_name="", plant_part="", extraction_method=""),
            dict(scientific_name="PlantAlt", compound_name="RefCompoundA",
                 indication="TestIndication", target="Laxative",
                 common_name="", plant_part="", extraction_method=""),
            dict(scientific_name="PlantAlt2", compound_name="RefCompoundA",
                 indication="TestIndication", target="Laxative",
                 common_name="", plant_part="", extraction_method=""),
        ] + [
            dict(scientific_name=f"Bg{i}", compound_name=f"BgCompound{i}",
                 indication="background", target="Antioxidant",
                 common_name="", plant_part="", extraction_method="")
            for i in range(25)
        ]
        return eng.BotanicalRDCandidateEngine(
            plant_compounds_df=pd.DataFrame(rows),
            compound_profiles_df=pd.DataFrame(),
            scientific_evidence_df=pd.DataFrame(),
            evidence_df=edf,
            use_live_search=False,
        )

    # Step 1 — run the engine normally, capture the fields of interest.
    engine_a = _make_ranking_engine(evidence_df)
    result_a = engine_a.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    captured_a = result_a[result_a["Alternative_Plant"].isin(["PlantAlt", "PlantAlt2"])][
        ["Alternative_Plant", "R&D_Opportunity_Score", "Decision_Class",
         "Decision_Class_AH", "Gate_Results"]
    ].reset_index(drop=True)

    # Step 2 — construct RegulatoryRecord objects from the SAME evidence
    # rows, entirely outside the engine. This is the additive
    # construction under test; nothing about its result is fed back
    # into the engine or into evidence_df.
    regulatory_records = []
    for _, row in evidence_df.iterrows():
        record = build_regulatory_record(row.to_dict())
        if record is not None:
            regulatory_records.append(record)
    assert len(regulatory_records) == 1  # only the genuine Regulatory row
    assert regulatory_records[0].source_record_ids == ["ev-reg-1"]
    assert regulatory_records[0].status == MarketVerificationStatus.REGULATORY_ASSESSMENT_INVENTORY_LISTED

    # evidence_df itself must be untouched by step 2.
    assert list(evidence_df["Evidence_Record_ID"]) == ["ev-sci-1", "ev-reg-1", "ev-sci-2"]

    # Step 3 — run the (unchanged) engine again, fresh instance, same
    # inputs, same evidence_df object.
    engine_b = _make_ranking_engine(evidence_df)
    result_b = engine_b.run(indication="TestIndication", dosage_form="Infusion", market="EU")
    captured_b = result_b[result_b["Alternative_Plant"].isin(["PlantAlt", "PlantAlt2"])][
        ["Alternative_Plant", "R&D_Opportunity_Score", "Decision_Class",
         "Decision_Class_AH", "Gate_Results"]
    ].reset_index(drop=True)

    # Step 4 — exact equality of captured fields AND row order/ranking.
    assert list(captured_a["Alternative_Plant"]) == list(captured_b["Alternative_Plant"])
    assert captured_a["R&D_Opportunity_Score"].tolist() == captured_b["R&D_Opportunity_Score"].tolist()
    assert captured_a["Decision_Class"].tolist() == captured_b["Decision_Class"].tolist()
    assert captured_a["Decision_Class_AH"].tolist() == captured_b["Decision_Class_AH"].tolist()
    assert captured_a["Gate_Results"].tolist() == captured_b["Gate_Results"].tolist()

    # PlantAlt (real evidence + regulatory row) must rank ahead of
    # PlantAlt2 (weak evidence only) in BOTH runs, identically — a real
    # ranking assertion, not just "the numbers match."
    assert list(captured_a["Alternative_Plant"])[0] == "PlantAlt"
    assert list(captured_b["Alternative_Plant"])[0] == "PlantAlt"
