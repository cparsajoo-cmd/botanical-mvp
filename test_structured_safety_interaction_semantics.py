from safety_interaction_attribution import extract_structured_safety_interactions


def test_structured_interaction_terms_are_preserved_without_prose_relation():
    out = extract_structured_safety_interactions(
        {"bleeding": "reported concern"},
        ["anticoagulants", "antiplatelets"],
        "Ginkgo biloba",
    )
    assert "bleeding" in " ".join(out["adverse_events"]).lower()
    assert "anticoagulants" in " ".join(out["interactions"]).lower()


def test_structured_hypoglycemic_activity_is_not_adverse_event():
    out = extract_structured_safety_interactions(
        "significant hypoglycemic activity",
        None,
        "Syzygium cumini",
    )
    assert out["adverse_events"] == []


def test_structured_coordinated_hypoglycemic_properties_are_not_adverse():
    out = extract_structured_safety_interactions(
        "Psidium guajava and Syzygium cumini have shown significant "
        "hypoglycemic, antioxidant and anti-inflammatory properties.",
        None,
        "Syzygium cumini",
    )
    assert out["adverse_events"] == []
    assert out["safety_data_status"] == "not_assessed"
