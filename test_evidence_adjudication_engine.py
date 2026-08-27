import pandas as pd

import evidence_adjudication_engine as ea


def _evidence_df(rows):
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# Part 4 -- indication-relevant filtering, not the whole plant history
# ---------------------------------------------------------------------
def test_evidence_items_filtered_to_indication_relevant_rows_only():
    df = _evidence_df([
        {
            "Evidence_Record_ID": "E1", "Scientific_Name": "Citrus limon",
            "Indication_Match_Type": "EXPLICIT_FIELD", "Primary_Outcome": "reduced sleep latency",
            "Result_Direction": "positive", "Population": "human",
        },
        {
            "Evidence_Record_ID": "E2", "Scientific_Name": "Citrus limon",
            "Indication_Match_Type": "NO_MATCH", "Primary_Outcome": "antioxidant activity in vitro",
            "Result_Direction": "positive", "Population": "in vitro",
        },
    ])
    items = ea.build_adjudication_evidence_items(df, "Citrus limon", "sleep")
    ids = [item["evidence_id"] for item in items]
    assert ids == ["E1"]


def test_evidence_items_fallback_token_filter_when_no_match_column():
    df = _evidence_df([
        {"Evidence_Record_ID": "E1", "Scientific_Name": "Valeriana officinalis",
         "Primary_Outcome": "improved sleep quality scores"},
        {"Evidence_Record_ID": "E2", "Scientific_Name": "Valeriana officinalis",
         "Primary_Outcome": "reduced blood pressure"},
    ])
    items = ea.build_adjudication_evidence_items(df, "Valeriana officinalis", "sleep")
    ids = [item["evidence_id"] for item in items]
    assert ids == ["E1"]


def test_missing_metadata_is_none_not_invented():
    df = _evidence_df([
        {"Evidence_Record_ID": "E1", "Scientific_Name": "Lavandula angustifolia",
         "Indication_Match_Type": "EXPLICIT_FIELD"},
    ])
    items = ea.build_adjudication_evidence_items(df, "Lavandula angustifolia", "sleep")
    assert len(items) == 1
    assert items[0]["dose"] is None
    assert items[0]["plant_part"] is None
    assert items[0]["preparation"] is None


# ---------------------------------------------------------------------
# Part 5 -- AI cannot smuggle in a score/rank field
# ---------------------------------------------------------------------
def test_ai_cannot_directly_supply_score_or_rank(monkeypatch):
    def _fake(**kwargs):
        return {
            "indication_evidence_direction": "MOSTLY_POSITIVE",
            "human_evidence_strength": "MODERATE",
            "evidence_conflict_level": "LOW",
            "negative_evidence_severity": "NONE",
            "scientific_evidence_confidence": "MODERATE",
            "positive_evidence_ids": ["E1"],
            "negative_evidence_ids": [],
            "key_human_evidence_ids": ["E1"],
            "preparation_mismatch_evidence_ids": [],
            "summary_note": "ok",
            # An attempted score/rank override -- must simply be ignored,
            # never read into the result.
            "R&D_Opportunity_Score": 99,
            "rank": 1,
        }

    monkeypatch.setattr(ea.llm_client, "call_structured_json", _fake)
    df = _evidence_df([
        {"Evidence_Record_ID": "E1", "Scientific_Name": "Passiflora incarnata",
         "Indication_Match_Type": "EXPLICIT_FIELD", "Result_Direction": "positive",
         "Population": "human"},
    ])
    result = ea.adjudicate_candidate("Passiflora incarnata", "sleep", df)
    assert "R&D_Opportunity_Score" not in result
    assert "rank" not in result
    assert result["Evidence_Adjudication_Status"] == ea.ADJUDICATION_STATUS_OK


# ---------------------------------------------------------------------
# Part 16 -- AI failure never breaks the platform
# ---------------------------------------------------------------------
def test_ai_unavailable_falls_back_deterministically(monkeypatch):
    def _raise(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(ea.llm_client, "call_structured_json", _raise)
    df = _evidence_df([
        {"Evidence_Record_ID": "E1", "Scientific_Name": "Melissa officinalis",
         "Indication_Match_Type": "EXPLICIT_FIELD", "Result_Direction": "positive",
         "Population": "human"},
    ])
    result = ea.adjudicate_candidate("Melissa officinalis", "sleep", df)
    assert result["Evidence_Adjudication_Status"] == ea.ADJUDICATION_STATUS_FALLBACK
    assert result["Indication_Evidence_Direction"] in ea.INDICATION_EVIDENCE_DIRECTION_VALUES


def test_malformed_ai_json_falls_back_deterministically(monkeypatch):
    def _fake(**kwargs):
        return {"indication_evidence_direction": "NOT_A_REAL_VALUE"}  # missing required keys, bad enum

    monkeypatch.setattr(ea.llm_client, "call_structured_json", _fake)
    df = _evidence_df([
        {"Evidence_Record_ID": "E1", "Scientific_Name": "Humulus lupulus",
         "Indication_Match_Type": "EXPLICIT_FIELD", "Result_Direction": "negative",
         "Population": "human"},
    ])
    result = ea.adjudicate_candidate("Humulus lupulus", "sleep", df)
    assert result["Evidence_Adjudication_Status"] == ea.ADJUDICATION_STATUS_FALLBACK


def test_no_evidence_never_calls_ai(monkeypatch):
    calls = []
    monkeypatch.setattr(ea.llm_client, "call_structured_json", lambda **kw: calls.append(1))
    result = ea.adjudicate_candidate("Nonexistent plantus", "sleep", _evidence_df([]))
    assert result["Evidence_Adjudication_Status"] == ea.ADJUDICATION_STATUS_NO_EVIDENCE
    assert calls == []


def test_ai_disabled_flag_skips_ai_and_uses_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(ea.llm_client, "call_structured_json", lambda **kw: calls.append(1))
    df = _evidence_df([
        {"Evidence_Record_ID": "E1", "Scientific_Name": "Piper methysticum",
         "Indication_Match_Type": "EXPLICIT_FIELD", "Result_Direction": "positive",
         "Population": "human"},
    ])
    result = ea.adjudicate_candidate("Piper methysticum", "sleep", df, use_ai=False)
    assert calls == []
    assert result["Evidence_Adjudication_Status"] == ea.ADJUDICATION_STATUS_DISABLED


# ---------------------------------------------------------------------
# Preparation / plant-part / route compatibility -- reused from
# Dimension_Status, not re-derived by the AI (part 7/8).
# ---------------------------------------------------------------------
def test_preparation_mismatch_reused_from_dimension_status():
    fields = ea.compatibility_fields_from_dimension_status({"preparation": "MISMATCH"})
    assert fields["Preparation_Compatibility"] == "MISMATCH"


def test_preparation_direct_match_reused_from_dimension_status():
    fields = ea.compatibility_fields_from_dimension_status({"preparation": "MATCH"})
    assert fields["Preparation_Compatibility"] == "DIRECT"


def test_plant_part_mismatch_reused_from_dimension_status():
    fields = ea.compatibility_fields_from_dimension_status({"plant_part": "MISMATCH"})
    assert fields["Plant_Part_Compatibility"] == "MISMATCH"


def test_missing_dimension_status_is_unknown_not_direct():
    fields = ea.compatibility_fields_from_dimension_status(None)
    assert fields["Preparation_Compatibility"] == "UNKNOWN"
    assert fields["Plant_Part_Compatibility"] == "UNKNOWN"
    assert fields["Route_Compatibility"] == "UNKNOWN"


def test_preparation_adjustment_never_double_counts_score():
    # Preparation/plant-part are already applied multiplicatively via
    # Plant_Applicability_Factor upstream -- the exposed adjustment
    # columns must always be 0.0, regardless of compatibility value.
    adjudication = {
        "Negative_Evidence_Severity": "NONE", "Human_Evidence_Strength": "STRONG",
        "Indication_Evidence_Direction": "CONSISTENT_POSITIVE",
    }
    adjustments = ea.compute_deterministic_adjustments(adjudication, base_score=80.0)
    assert adjustments["Preparation_Adjustment"] == 0.0
    assert adjustments["Plant_Part_Adjustment"] == 0.0


# ---------------------------------------------------------------------
# Part 6/15 Case A -- negative human evidence matters and caps the
# decision, generically (no plant/indication hardcoding).
# ---------------------------------------------------------------------
def test_consistent_negative_human_evidence_caps_to_no_go():
    adjudication = {
        "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE",
        "Human_Evidence_Strength": "STRONG",
        "Negative_Evidence_Severity": "HIGH",
    }
    new_class, new_go, reason = ea.apply_negative_evidence_cap(
        "B — Established scientific candidate", "Go", adjudication,
    )
    assert new_go == "No-Go"
    assert new_class == "H — No-go / safety concern"
    assert reason == "consistent_negative_human_evidence"


def test_cap_never_upgrades_an_existing_hold():
    adjudication = {
        "Indication_Evidence_Direction": "MOSTLY_NEGATIVE",
        "Human_Evidence_Strength": "MODERATE",
        "Negative_Evidence_Severity": "MODERATE",
    }
    # Already worse than what the cap would impose -- must stay as-is.
    new_class, new_go, reason = ea.apply_negative_evidence_cap(
        "H — No-go / safety concern", "No-Go", adjudication,
    )
    assert new_class == "H — No-go / safety concern"
    assert new_go == "No-Go"


def test_no_cap_when_negative_evidence_is_mechanistic_only():
    # Negative severity present, but no human evidence strength -- must
    # NOT cap (part 6: mechanistic-only negative signal is not enough).
    adjudication = {
        "Indication_Evidence_Direction": "MOSTLY_NEGATIVE",
        "Human_Evidence_Strength": "NONE",
        "Negative_Evidence_Severity": "HIGH",
    }
    new_class, new_go, reason = ea.apply_negative_evidence_cap(
        "B — Established scientific candidate", "Go", adjudication,
    )
    assert reason is None
    assert new_class == "B — Established scientific candidate"
    assert new_go == "Go"


def test_negative_human_evidence_adjustment_only_when_human_evidence_present():
    with_human = ea.compute_deterministic_adjustments(
        {"Negative_Evidence_Severity": "HIGH", "Human_Evidence_Strength": "STRONG",
         "Indication_Evidence_Direction": "CONSISTENT_NEGATIVE"},
        base_score=70.0,
    )
    without_human = ea.compute_deterministic_adjustments(
        {"Negative_Evidence_Severity": "HIGH", "Human_Evidence_Strength": "NONE",
         "Indication_Evidence_Direction": "MOSTLY_NEGATIVE"},
        base_score=70.0,
    )
    assert with_human["Evidence_Adjudication_Adjustment"] < without_human["Evidence_Adjudication_Adjustment"]
    assert with_human["Final_R&D_Opportunity_Score"] < with_human["Base_R&D_Opportunity_Score"]


# ---------------------------------------------------------------------
# Part 15 Case D/E -- two otherwise-similar candidates can legitimately
# receive different final recommendations from adjudication.
# ---------------------------------------------------------------------
def test_final_recommendation_can_differ_for_scientifically_valid_reasons(monkeypatch):
    def _fake_positive(**kwargs):
        return {
            "indication_evidence_direction": "CONSISTENT_POSITIVE", "human_evidence_strength": "STRONG",
            "evidence_conflict_level": "NONE", "negative_evidence_severity": "NONE",
            "scientific_evidence_confidence": "HIGH", "positive_evidence_ids": ["E1"],
            "negative_evidence_ids": [], "key_human_evidence_ids": ["E1"],
            "preparation_mismatch_evidence_ids": [], "summary_note": "ok",
        }

    def _fake_negative(**kwargs):
        return {
            "indication_evidence_direction": "CONSISTENT_NEGATIVE", "human_evidence_strength": "STRONG",
            "evidence_conflict_level": "NONE", "negative_evidence_severity": "HIGH",
            "scientific_evidence_confidence": "MODERATE", "positive_evidence_ids": [],
            "negative_evidence_ids": ["E1"], "key_human_evidence_ids": ["E1"],
            "preparation_mismatch_evidence_ids": [], "summary_note": "ok",
        }

    df = _evidence_df([
        {"Evidence_Record_ID": "E1", "Scientific_Name": "Plant A",
         "Indication_Match_Type": "EXPLICIT_FIELD", "Population": "human"},
    ])
    monkeypatch.setattr(ea.llm_client, "call_structured_json", _fake_positive)
    adjudication_a = ea.adjudicate_candidate("Plant A", "sleep", df)
    monkeypatch.setattr(ea.llm_client, "call_structured_json", _fake_negative)
    adjudication_b = ea.adjudicate_candidate("Plant A", "sleep", df)

    class_a, go_a, _ = ea.apply_negative_evidence_cap("B — Established scientific candidate", "Go", adjudication_a)
    class_b, go_b, _ = ea.apply_negative_evidence_cap("B — Established scientific candidate", "Go", adjudication_b)
    assert (class_a, go_a) != (class_b, go_b)
    assert go_a == "Go"
    assert go_b == "No-Go"


# ---------------------------------------------------------------------
# Part 17 -- no cross-indication leakage: the exact text sent to the
# LLM (and therefore llm_client's cache key, which hashes it) differs
# whenever the indication differs.
# ---------------------------------------------------------------------
def test_user_content_differs_across_indications():
    items = [{"evidence_id": "E1", "result_direction": "positive"}]
    content_sleep = ea._build_user_content("Plant A", "sleep", {}, items)
    content_anxiety = ea._build_user_content("Plant A", "anxiety", {}, items)
    assert content_sleep != content_anxiety


# ---------------------------------------------------------------------
# Part 14 -- structured fields are the exact set merged into the
# report-ready export (candidate_shortlisting.merge_authoritative_scores).
# ---------------------------------------------------------------------
def test_authoritative_fields_include_adjudication_columns():
    import candidate_shortlisting as cs
    # Reach into the closure-free constant by re-deriving from the
    # function's own source is unnecessary -- merge a tiny frame instead.
    raw_df = pd.DataFrame([{"Alternative_Plant": "Plant A", "R&D_Opportunity_Score": 10}])
    plant_summary = pd.DataFrame([{
        "Alternative_Plant": "Plant A", "Overall_Score": 55.0,
        "Indication_Evidence_Direction": "MOSTLY_POSITIVE",
        "Preparation_Compatibility": "DIRECT",
        "Evidence_Adjudication_Status": "AI_ADJUDICATION_OK",
        "Final_R&D_Opportunity_Score": 51.0,
    }])
    merged = cs.merge_authoritative_scores(raw_df, plant_summary)
    assert merged.loc[0, "Indication_Evidence_Direction"] == "MOSTLY_POSITIVE"
    assert merged.loc[0, "Preparation_Compatibility"] == "DIRECT"
    assert merged.loc[0, "Evidence_Adjudication_Status"] == "AI_ADJUDICATION_OK"
    assert merged.loc[0, "Final_R&D_Opportunity_Score"] == 51.0


# ---------------------------------------------------------------------
# Rationale generation (part 13) -- deterministic, from structured
# fields only.
# ---------------------------------------------------------------------
def test_rationale_reflects_preparation_mismatch():
    structured = {
        "Human_Evidence_Strength": "MODERATE", "Indication_Evidence_Direction": "MOSTLY_POSITIVE",
        "Negative_Evidence_Severity": "NONE",
    }
    compatibility = {"Preparation_Compatibility": "MISMATCH", "Plant_Part_Compatibility": "DIRECT"}
    rationale = ea._build_rationale("Plant A", "sleep", structured, compatibility)
    assert "preparation" in rationale.lower()
