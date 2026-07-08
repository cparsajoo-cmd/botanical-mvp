import streamlit as st

from regulatory_frameworks import get_market_framework


def render_inputs():
    st.markdown("## Step 0 — Define R&D question")

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
        )

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
                "plant-specific or product-specific legal opinion. Verify "
                "against the actual ingredient, formulation, and supplier "
                "before commercial use."
            )

    st.info(
        f"Find and rank global medicinal plants and active compounds for "
        f"**{product_type}** as **{dosage_form}** for **{indication}** "
        f"in **{market}**."
    )

    return {
        "product_type": product_type,
        "indication": indication,
        "dosage_form": dosage_form,
        "market": market,
        "target_count": target_count,
        "max_pubmed_results": max_pubmed_results,
    }
