import streamlit as st

from question_understanding_engine import standardize_project_definition


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)


# =========================================================
# Sidebar
# =========================================================

st.sidebar.title("Project Settings")

show_standardized_json = st.sidebar.checkbox(
    "Show Standardized Project JSON",
    value=True
)

show_debug_info = st.sidebar.checkbox(
    "Show Debug Information",
    value=False
)


# =========================================================
# Main Interface
# =========================================================

st.title("🌿 Botanical Product Intelligence Platform")

st.markdown(
    """
    Evidence-based decision-support platform for botanical product development.
    """
)

st.divider()


# =========================================================
# Module Status
# =========================================================

st.caption("Current Module: Module 2 — Project Definition / Understanding Layer")


# =========================================================
# Project Definition Form
# =========================================================

st.header("Project Definition")

with st.form("project_definition_form"):

    st.subheader("Product Strategy")

    col1, col2 = st.columns(2)

    with col1:
        product = st.text_input(
            "Product",
            value="Herbal bedtime infusion",
            help="Example: Herbal bedtime infusion, botanical capsule, nasal spray"
        )

        product_category = st.selectbox(
            "Product Category",
            [
                "Botanical Food Product",
                "Food Supplement",
                "Herbal Medicinal Product",
                "Cosmetic Product",
                "Medical Device",
                "Not Sure"
            ]
        )

        dosage_form = st.selectbox(
            "Dosage Form",
            [
                "Herbal Infusion",
                "Capsule",
                "Tablet",
                "Drops",
                "Syrup",
                "Nasal Spray",
                "Cream",
                "Gel",
                "Ointment",
                "Other"
            ]
        )

        route = st.selectbox(
            "Route of Administration",
            [
                "Oral",
                "Topical",
                "Intranasal",
                "Inhalation",
                "Not Sure"
            ]
        )

    with col2:
        indication = st.text_input(
            "Target Indication / Health Area",
            value="Sleep",
            help="Example: Sleep, Stress, Allergic Rhinitis, Constipation"
        )

        intended_claim = st.selectbox(
            "Intended Claim Type",
            [
                "General Well-being Claim",
                "Structure / Function Claim",
                "Traditional Use Claim",
                "Therapeutic Claim",
                "Disease Risk Reduction Claim",
                "Not Sure"
            ]
        )

        population = st.selectbox(
            "Target Population",
            [
                "Adults",
                "Children",
                "Elderly",
                "Pregnant Women",
                "General Population",
                "Not Sure"
            ]
        )

        market = st.selectbox(
            "Target Market",
            [
                "European Union",
                "France",
                "United States",
                "United Kingdom",
                "Canada",
                "Global"
            ]
        )

    st.divider()

    st.subheader("Scientific Evidence Requirements")

    col3, col4 = st.columns(2)

    with col3:
        minimum_clinical_evidence = st.selectbox(
            "Minimum Clinical Evidence",
            [
                "Any Evidence",
                "Traditional Use Only",
                "Human Clinical Evidence Preferred",
                "RCT Required",
                "Meta-analysis Required"
            ]
        )

        ema_required = st.checkbox("EMA-HMPC evidence required", value=True)
        who_required = st.checkbox("WHO monograph evidence required", value=False)
        escop_required = st.checkbox("ESCOP evidence required", value=False)

    with col4:
        pharmacopoeia_required = st.checkbox(
            "Pharmacopoeia / Quality Standard required",
            value=False
        )

        safety_priority = st.selectbox(
            "Safety Priority",
            [
                "Standard",
                "Low Risk Required",
                "Suitable for Sensitive Population",
                "Avoid Known Interaction Risks"
            ]
        )

        evidence_strictness = st.selectbox(
            "Evidence Strictness",
            [
                "Flexible",
                "Balanced",
                "Strict",
                "Very Strict"
            ]
        )

    st.divider()

    st.subheader("Regulatory Strategy")

    col5, col6 = st.columns(2)

    with col5:
        regulatory_pathway = st.selectbox(
            "Preferred Regulatory Pathway",
            [
                "Food Supplement",
                "Traditional Herbal Medicinal Product",
                "Well-established Use Herbal Medicinal Product",
                "Cosmetic Product",
                "Medical Device",
                "Not Sure"
            ]
        )

    with col6:
        regulatory_risk_tolerance = st.selectbox(
            "Regulatory Risk Tolerance",
            [
                "Low",
                "Medium",
                "High"
            ]
        )

    st.divider()

    st.subheader("Commercial Strategy")

    col7, col8 = st.columns(2)

    with col7:
        commercial_goal = st.selectbox(
            "Commercial Goal",
            [
                "New Product Development",
                "Portfolio Screening",
                "Investment Decision",
                "Regulatory Assessment",
                "Evidence Gap Analysis"
            ]
        )

        innovation_level = st.selectbox(
            "Innovation Level",
            [
                "Low - Established Ingredient",
                "Medium - Differentiated Positioning",
                "High - Novel Botanical Opportunity"
            ]
        )

    with col8:
        time_to_market = st.selectbox(
            "Time to Market",
            [
                "Fast",
                "Medium",
                "Long-term"
            ]
        )

        budget_level = st.selectbox(
            "Budget Level",
            [
                "Low",
                "Medium",
                "High",
                "Not Sure"
            ]
        )

    st.divider()

    st.subheader("Product Constraints")

    constraints = st.multiselect(
        "Constraints",
        [
            "Dried herbal material only",
            "No capsules",
            "No tablets",
            "No hydroalcoholic extracts",
            "No standardized extracts",
            "No essential oils",
            "Infusion-specific evidence required",
            "EU regulatory compatibility required",
            "Low safety risk required",
            "Vegan",
            "Organic",
            "Sugar free",
            "Alcohol free"
        ]
    )

    submitted = st.form_submit_button("Analyze Project")


# =========================================================
# Run Module 2
# =========================================================

if submitted:

    form_input = {
        "product": product,
        "product_category": product_category,
        "dosage_form": dosage_form,
        "route": route,
        "indication": indication,
        "intended_claim": intended_claim,
        "population": population,
        "market": market,
        "minimum_clinical_evidence": minimum_clinical_evidence,
        "ema_required": ema_required,
        "who_required": who_required,
        "escop_required": escop_required,
        "pharmacopoeia_required": pharmacopoeia_required,
        "safety_priority": safety_priority,
        "evidence_strictness": evidence_strictness,
        "regulatory_pathway": regulatory_pathway,
        "regulatory_risk_tolerance": regulatory_risk_tolerance,
        "commercial_goal": commercial_goal,
        "innovation_level": innovation_level,
        "time_to_market": time_to_market,
        "budget_level": budget_level,
        "constraints": constraints
    }

    standardized_project = standardize_project_definition(form_input)

    st.success("Project definition standardized successfully.")

    if show_standardized_json:
        st.subheader("Standardized Project Definition")
        st.json(standardized_project)

    if show_debug_info:
        st.subheader("Raw Form Input")
        st.json(form_input)

else:
    st.info("Complete the project definition form and click Analyze Project.")
