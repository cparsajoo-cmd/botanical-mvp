from safety_interaction_attribution import extract_attributed_safety_interactions


def test_general_synthetic_drug_side_effect_statement_is_not_attributed_to_plant():
    text = (
        "Syzygium cumini was reviewed for glycemic control. "
        "Synthetic drugs have many side effects and remain expensive."
    )
    out = extract_attributed_safety_interactions(text, "Syzygium cumini", structurally_linked=True)
    assert out["adverse_events"] == []
    assert out["safety_data_status"] == "not_assessed"


def test_protective_liver_injury_language_is_not_an_adverse_flag():
    text = (
        "Curcuma longa extract was studied in rats. "
        "The extract protected against liver injury and attenuated toxicity."
    )
    out = extract_attributed_safety_interactions(text, "Curcuma longa", structurally_linked=True)
    assert out["adverse_events"] == []


def test_explicit_plant_adverse_event_is_retained():
    text = (
        "Ginkgo biloba extract was administered for 12 weeks. "
        "Ginkgo biloba extract was associated with nausea and increased bleeding events."
    )
    out = extract_attributed_safety_interactions(text, "Ginkgo biloba", structurally_linked=True)
    assert len(out["adverse_events"]) == 1
    assert "bleeding" in out["adverse_events"][0].lower()
    assert out["safety_data_status"] == "adverse_signal_present"


def test_reassurance_is_separate_from_adverse_events():
    text = (
        "Valeriana officinalis extract was tested in adults. "
        "The extract was well tolerated and no serious adverse events were reported."
    )
    out = extract_attributed_safety_interactions(text, "Valeriana officinalis", structurally_linked=True)
    assert out["adverse_events"] == []
    assert out["safety_reassurance"]
    assert out["safety_data_status"] == "reassurance_reported"


def test_warfarin_name_alone_is_not_an_interaction():
    text = "Ginkgo biloba was reviewed. Warfarin is an anticoagulant commonly used in older adults."
    out = extract_attributed_safety_interactions(text, "Ginkgo biloba", structurally_linked=True)
    assert out["interactions"] == []


def test_explicit_plant_warfarin_interaction_is_retained():
    text = (
        "Ginkgo biloba extract was evaluated. "
        "Ginkgo biloba may interact with warfarin and increase bleeding risk."
    )
    out = extract_attributed_safety_interactions(text, "Ginkgo biloba", structurally_linked=True)
    assert len(out["interactions"]) == 1
    assert "warfarin" in out["interactions"][0].lower()


def test_unrelated_other_botanical_is_not_attributed():
    text = (
        "Abies spectabilis was included in the survey. "
        "Cannabis sativa was associated with adverse events and nausea."
    )
    out = extract_attributed_safety_interactions(text, "Abies spectabilis", structurally_linked=True)
    assert out["adverse_events"] == []


def test_retracted_source_is_excluded():
    text = (
        "This article has been retracted. Camellia sinensis extract caused nausea in the study."
    )
    out = extract_attributed_safety_interactions(text, "Camellia sinensis", structurally_linked=True)
    assert out["adverse_events"] == []
    assert out["safety_data_status"] == "source_excluded"


def test_hypoglycemic_activity_is_efficacy_not_adverse_event():
    text = (
        "Syzygium cumini was evaluated for diabetes. "
        "Syzygium cumini has shown significant hypoglycemic activity and antioxidant properties."
    )
    out = extract_attributed_safety_interactions(text, "Syzygium cumini", structurally_linked=True)
    assert out["adverse_events"] == []
    assert out["safety_data_status"] == "not_assessed"


def test_current_therapeutic_regimen_side_effects_are_not_attributed_to_plant():
    text = (
        "Scutellaria baicalensis was discussed as a possible natural product. "
        "The current therapeutic regimen has low success rates and numerous side effects."
    )
    out = extract_attributed_safety_interactions(text, "Scutellaria baicalensis", structurally_linked=True)
    assert out["adverse_events"] == []


def test_immediate_following_reported_adverse_event_can_use_local_anchor():
    text = (
        "Trigonella foenum-graecum extract was administered for 8 weeks. "
        "Mild gastrointestinal adverse events were reported."
    )
    out = extract_attributed_safety_interactions(text, "Trigonella foenum-graecum", structurally_linked=True)
    assert out["adverse_events"]


def test_coordinated_hypoglycemic_properties_phrase_is_efficacy_not_safety():
    text = (
        "Psidium guajava and Syzygium cumini have shown significant "
        "hypoglycemic, antioxidant and anti-inflammatory properties because "
        "of the presence of quercetin, rutin and gallic acid."
    )
    out = extract_attributed_safety_interactions(
        text, "Syzygium cumini", structurally_linked=True
    )
    assert out["adverse_events"] == []
    assert out["safety_data_status"] == "not_assessed"
