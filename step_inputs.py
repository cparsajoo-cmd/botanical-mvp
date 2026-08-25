import streamlit as st

from regulatory_frameworks import get_market_framework
from free_text_question_parser import parse_free_text_question
from question_understanding_engine import standardize_project_definition


# Task 7 — extracted from inline selectbox literals into named,
# importable constants (behavior-preserving: still passed as the exact
# same list to the exact same st.selectbox() calls below). This is
# what lets validation_case_protocol.py's coverage-matrix tooling
# (validation_matrix.py) generate a DecisionContext for every real
# product_type/indication/dosage_form/market combination the platform
# actually supports, instead of maintaining a second, separately-typed
# copy of these four lists that could silently drift out of sync with
# what Step 0 actually offers.
PRODUCT_TYPES = [
    "Herbal medicinal product (THMP)",
    "Food supplement",
    "Cosmetic",
    "Novel food ingredient",
    "Functional food / beverage",
    "Botanical extract / raw ingredient (B2B)",
    "Veterinary botanical product",
]

INDICATIONS = [
    "Sleep and relaxation",
    "Anxiety",
    "Stress",
    "Inflammation",
    "Constipation",
    "Cough",
    "Digestive comfort",
    "Skin inflammation",
    "Dry mouth",
    "Allergic rhinitis",
    "IBS",
    "Wound healing",
    "Cognitive decline / Alzheimer's support",
    "Immune support",
    "Cardiovascular / circulation",
    "Liver support / detox",
    "Joint & muscle comfort",
    "Energy / fatigue",
    "Metabolic & blood sugar support",
    "Weight management",
    "Menopause support",
    "Menstrual / PMS support",
    "Prostate / men's health",
    "Urinary tract health",
    "Cold & flu / respiratory",
    "Headache / mood support",
    "Hair, skin & nail beauty-from-within",
    "Eye health",
]

DOSAGE_FORMS = [
    "Infusion",
    "Capsule",
    "Tablet",
    "Syrup",
    "Cream",
    "Gel",
    "Mouthwash",
    "Nasal spray",
    "Chewing gum",
    "Powder",
    "Extract",
    "Essential oil",
]

MARKETS = [
    "European Union",
    "Germany",
    "France",
    "Italy",
    "Spain",
    "Netherlands",
    "Poland",
    "United Kingdom",
    "Switzerland",
    "Nordic countries (Sweden, Norway, Denmark, Finland)",
    "Iran",
    "Middle East / GCC",
    "Turkey",
    "United States",
    "Canada",
    "Brazil / Latin America",
    "China",
    "Japan",
    "South Korea",
    "India",
    "Southeast Asia (Vietnam / Thailand / Indonesia)",
    "Australia",
    "New Zealand",
    "South Africa",
    "Global / Multi-market",
]


# Each hero scenario was one of the plants actually run through the
# known-answer validation round (real regulatory backing, clean
# compound data, no safety exclusions) — these are meant to be safe,
# rehearsed, reliable choices for a live demo, not a random pick.
DEMO_SCENARIOS = {
    "chamomile": {
        "label": "🎬 Demo: Chamomile — Digestive comfort",
        "product_type": "Herbal medicinal product (THMP)",
        "indication": "Digestive comfort",
        "dosage_form": "Infusion",
        "market": "European Union",
        "reference_plant": "Matricaria chamomilla",
    },
    "milk_thistle": {
        "label": "🎬 Demo: Milk thistle — Liver support",
        "product_type": "Herbal medicinal product (THMP)",
        "indication": "Liver support / detox",
        "dosage_form": "Infusion",
        "market": "European Union",
        "reference_plant": "Silybum marianum",
    },
}


def _apply_demo_scenario(scenario_key):
    scenario = DEMO_SCENARIOS[scenario_key]
    st.session_state["rd_product_type"] = scenario["product_type"]
    st.session_state["rd_indication"] = scenario["indication"]
    st.session_state["rd_dosage_form"] = scenario["dosage_form"]
    st.session_state["rd_market"] = scenario["market"]
    st.session_state["rd_reference_plant"] = scenario["reference_plant"]
    # Demo scenarios predate explicit preparation/part/dose fields. Clear any
    # values left from a prior manual session so the demo cannot silently use
    # stale product-definition constraints.
    st.session_state["rd_target_preparation"] = ""
    st.session_state["rd_target_plant_part"] = ""
    st.session_state["rd_target_dose"] = ""
    st.session_state["rd_demo_scenario_active"] = scenario["label"]


def render_inputs():
    st.markdown("## Step 0 — Define R&D Question")

    active = st.session_state.get("rd_demo_scenario_active")
    if active:
        banner_col, clear_col = st.columns([5, 1])
        with banner_col:
            st.success(
                f"{active} loaded."
            )
        with clear_col:
            if st.button("✖️ Clear", key="demo_clear_btn"):
                st.session_state["rd_demo_scenario_active"] = None
                st.rerun()

    with st.expander("🎬 Demo scenarios", expanded=not active):
        st.caption(
            "Choose a prepared scenario to fill the project fields automatically."
        )
        demo_cols = st.columns(len(DEMO_SCENARIOS))
        for col, (key, scenario) in zip(demo_cols, DEMO_SCENARIOS.items()):
            with col:
                if st.button(scenario["label"], key=f"demo_btn_{key}", width="stretch"):
                    _apply_demo_scenario(key)
                    st.rerun()

    with st.expander("✍️ Describe the project in your own words"):
        st.caption(
            "Describe the indication, dosage form, target population or market. The recognized fields can be reviewed below."
        )
        free_text_question = st.text_area(
            "Your question", key="rd_free_text_question", label_visibility="collapsed",
        )
        if st.button("Parse this question", key="rd_parse_free_text_btn"):
            parsed = parse_free_text_question(free_text_question)
            st.session_state["rd_parsed_question"] = parsed
            if parsed.indication:
                st.session_state["rd_indication"] = parsed.indication
            if parsed.dosage_form:
                st.session_state["rd_dosage_form"] = parsed.dosage_form
            if parsed.market:
                st.session_state["rd_market"] = parsed.market
            st.session_state["rd_demo_scenario_active"] = None
            st.rerun()

        parsed_question = st.session_state.get("rd_parsed_question")
        if parsed_question is not None and free_text_question:
            found = []
            if parsed_question.indication:
                found.append(f"Indication: **{parsed_question.indication}** (matched \"{parsed_question.indication_matched_phrase}\")")
            if parsed_question.dosage_form:
                found.append(f"Dosage form: **{parsed_question.dosage_form}** (matched \"{parsed_question.dosage_form_matched_phrase}\")")
            if parsed_question.market:
                found.append(f"Market: **{parsed_question.market}** (matched \"{parsed_question.market_matched_phrase}\")")
            if parsed_question.target_population:
                found.append(f"Target population: **{', '.join(parsed_question.target_population)}**")
            if parsed_question.safety_constraints:
                found.append(f"Safety constraints: **{', '.join(parsed_question.safety_constraints)}**")

            if found:
                st.success("Recognized from your question:\n\n" + "\n\n".join(f"- {f}" for f in found))
            else:
                st.warning(
                    "The project fields could not be identified automatically. Please select them below."
                )
            unmatched_notice = []
            if not parsed_question.indication:
                unmatched_notice.append("indication")
            if not parsed_question.dosage_form:
                unmatched_notice.append("dosage form")
            if not parsed_question.market:
                unmatched_notice.append("market")
            if unmatched_notice and found:
                st.caption(
                    f"Not recognized: {', '.join(unmatched_notice)} — please select "
                    f"{'these' if len(unmatched_notice) > 1 else 'this'} manually below."
                )

    col1, col2 = st.columns(2)

    with col1:
        product_type = st.selectbox(
            "Product type",
            PRODUCT_TYPES,
            key="rd_product_type",
        )

        indication = st.selectbox(
            "Target indication",
            INDICATIONS,
            key="rd_indication",
        )

    with col2:
        dosage_form = st.selectbox(
            "Dosage form",
            DOSAGE_FORMS,
            key="rd_dosage_form",
        )

        market = st.selectbox(
            "Target market",
            MARKETS,
            key="rd_market",
        )

    # These two controls genuinely change engine behavior (target_count caps
    # how many reference plants Step 5 analyzes; max_pubmed_results controls
    # how deep the live PubMed search goes) — they're kept, just tucked away
    # by default so Step 0 isn't cluttered for the common case of using the
    # defaults.
    with st.expander("⚙️ Advanced settings", expanded=False):
        target_count = st.slider(
            "Number of global plant candidates to analyze",
            10,
            100,
            50,
        )

        max_pubmed_results = st.slider(
            "Online PubMed results per candidate plant",
            1,
            10,
            3,
        )

        st.caption(
            "Optional details can improve preparation, plant-part and dose matching. Leave them blank if they are not defined yet."
        )
        target_preparation = st.text_input(
            "Target botanical preparation (optional)",
            key="rd_target_preparation",
            placeholder="e.g. standardized dry extract, tincture, infusion",
        )
        target_plant_part = st.text_input(
            "Target plant part (optional)",
            key="rd_target_plant_part",
            placeholder="e.g. leaf, root, aerial part",
        )
        target_dose = st.text_input(
            "Target dose (optional)",
            key="rd_target_dose",
            placeholder="e.g. 240 mg/day",
        )

    framework = get_market_framework(market)

    if framework:
        with st.expander(f"📋 Regulatory framework — {market}"):
            st.write(f"**Primary authority:** {framework['primary_authority']}")
            st.write("**Key pathways:**")
            for pathway in framework["key_pathways"]:
                st.write(f"- {pathway}")
            st.caption(framework["notes"])
            st.caption(
                "This is general, market-level regulatory context — not a "
                "plant-specific or product-specific legal opinion."
            )

    parsed_question = st.session_state.get("rd_parsed_question")
    standardized_project = standardize_project_definition({
        "product": indication,  # no separate free-text "product name" field exists yet; indication is the closest proxy
        "dosage_form": dosage_form,
        "indication": indication,
        "market": market,
        "target_preparation": target_preparation,
        "target_plant_part": target_plant_part,
        "target_dose": target_dose,
        "population": ", ".join(parsed_question.target_population) if parsed_question and parsed_question.target_population else None,
        "constraints": parsed_question.safety_constraints if parsed_question else [],
    })

    with st.expander("📐 Project definition", expanded=False):
        st.caption(
            "Structured project information used by the analysis."
        )
        st.json(standardized_project)

    return {
        "product_type": product_type,
        "indication": indication,
        "dosage_form": dosage_form,
        "market": market,
        "target_count": target_count,
        "max_pubmed_results": max_pubmed_results,
        "standardized_project": standardized_project,
    }
