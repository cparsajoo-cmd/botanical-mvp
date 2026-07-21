import streamlit as st

from regulatory_frameworks import get_market_framework


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
    st.session_state["rd_demo_scenario_active"] = scenario["label"]


def render_inputs():
    st.markdown("## Step 0 — Define R&D Question")

    active = st.session_state.get("rd_demo_scenario_active")
    if active:
        banner_col, clear_col = st.columns([5, 1])
        with banner_col:
            st.success(
                f"{active} loaded — scroll down to **Step 5** and click "
                "**\"Run Candidate Discovery\"** to see the result."
            )
        with clear_col:
            if st.button("✖️ Clear", key="demo_clear_btn"):
                st.session_state["rd_demo_scenario_active"] = None
                st.rerun()

    with st.expander("🎬 Demo mode — one-click, pre-validated scenarios", expanded=not active):
        st.caption(
            "These fill in every field below with a scenario that's already "
            "been checked against known science — safe to run live without "
            "typing anything or guessing which plant/indication to use."
        )
        demo_cols = st.columns(len(DEMO_SCENARIOS))
        for col, (key, scenario) in zip(demo_cols, DEMO_SCENARIOS.items()):
            with col:
                if st.button(scenario["label"], key=f"demo_btn_{key}", use_container_width=True):
                    _apply_demo_scenario(key)
                    st.rerun()

    col1, col2 = st.columns(2)

    with col1:
        product_type = st.selectbox(
            "Product type",
            [
                "Herbal medicinal product (THMP)",
                "Food supplement",
                "Cosmetic",
                "Novel food ingredient",
                "Functional food / beverage",
                "Botanical extract / raw ingredient (B2B)",
                "Veterinary botanical product",
            ],
            key="rd_product_type",
        )

        indication = st.selectbox(
            "Target indication",
            [
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
            ],
            key="rd_indication",
        )

    with col2:
        dosage_form = st.selectbox(
            "Dosage form",
            [
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
            ],
            key="rd_dosage_form",
        )

        market = st.selectbox(
            "Target market",
            [
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
            ],
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

    return {
        "product_type": product_type,
        "indication": indication,
        "dosage_form": dosage_form,
        "market": market,
        "target_count": target_count,
        "max_pubmed_results": max_pubmed_results,
    }
