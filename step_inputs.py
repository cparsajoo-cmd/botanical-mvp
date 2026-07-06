import streamlit as st


def render_inputs():
    st.markdown("## Step 0 — Define R&D question")

    col1, col2 = st.columns(2)

    with col1:
        product_type = st.selectbox(
            "Product type",
            [
                "Herbal product",
                "Food supplement",
                "Cosmetic",
                "Medical device",
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
                "France",
                "United States",
                "Canada",
                "Iran",
                "Global R&D",
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
