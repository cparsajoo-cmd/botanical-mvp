import streamlit as st
import pandas as pd

from question_understanding_engine import standardize_project_definition


st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)


# =========================================================
# Load Database
# =========================================================

@st.cache_data
def load_database():
    file_path = "botanical_database.xlsx"
    df = pd.read_excel(file_path)
    return df


# =========================================================
# Simple Decision Engine
# =========================================================

def calculate_score(row, standardized_project):
    score = 0

    indication = str(standardized_project.get("target_indication", "")).lower()
    dosage_form = str(standardized_project.get("dosage_form", "")).lower()
    market = str(standardized_project.get("target_market", "")).lower()

    row_indication = str(row.get("Indication", "")).lower()
    row_dosage = str(row.get("Dosage Form", "")).lower()
    row_market = str(row.get("Market", "")).lower()

    ema = str(row.get("EMA", "")).lower()
    who = str(row.get("WHO", "")).lower()
    escop = str(row.get("ESCOP", "")).lower()
    clinical = str(row.get("Clinical Evidence", "")).lower()
    safety = str(row.get("Safety", "")).lower()

    if indication and indication in row_indication:
        score += 25

    if dosage_form and dosage_form in row_dosage:
        score += 20

    if market and market in row_market:
        score += 10

    if "yes" in ema or "available" in ema:
        score += 15

    if "yes" in who or "available" in who:
        score += 10

    if "yes" in escop or "available" in escop:
        score += 10

    if "strong" in clinical:
        score += 15
    elif "moderate" in clinical:
        score += 10
    elif "limited" in clinical:
        score += 5

    if "safe" in safety or "low risk" in safety:
        score += 10

    return score


def rank_plants(df, standardized_project):
    df = df.copy()
    df["Decision Score"] = df.apply(
        lambda row: calculate_score(row, standardized_project),
        axis=1
    )

    df = df.sort_values(by="Decision Score", ascending=False)
    return df


# =========================================================
# Sidebar
# =========================================================

st.sidebar.title("Project Settings")

show_database = st.sidebar.checkbox("Show Raw Database", value=False)
show_standardized_json = st.sidebar.checkbox("Show Standardized Project JSON", value=True)

min_score = st.sidebar.slider(
    "Minimum Decision Score",
    min_value=0,
    max_value=100,
    value=0,
    step=5
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
# Project Definition Form
# =========================================================

st.header("Project Definition")

with st.form("project_definition_form"):

    col1, col2 = st.columns(2)

    with col1:
        product = st.text_input(
            "Product",
            value="Herbal bedtime infusion",
            help="Example: Herbal bedtime infusion, nasal spray, botanical capsule"
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

        indication = st.text_input(
            "Target Indication",
            value="Sleep",
            help="Example: Sleep, Stress, Allergic Rhinitis, Constipation"
        )

    with col2:
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

        population = st.selectbox(
            "Target Population",
            [
                "Adults",
                "Children",
                "Elderly",
                "Pregnant Women",
                "General Population"
            ]
        )

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

    constraints = st.multiselect(
        "Product Constraints",
        [
            "Dried herbal material only",
            "No capsules",
            "No tablets",
            "No hydroalcoholic extracts",
            "No essential oils",
            "Infusion-specific evidence required",
            "EU regulatory compatibility required",
            "Low safety risk required"
        ]
    )

    submitted = st.form_submit_button("Analyze Project")


# =========================================================
# Run Analysis
# =========================================================

if submitted:

    form_input = {
        "product": product,
        "dosage_form": dosage_form,
        "indication": indication,
        "market": market,
        "population": population,
        "constraints": constraints,
        "commercial_goal": commercial_goal
    }

    standardized_project = standardize_project_definition(form_input)

    st.success("Project definition standardized successfully.")

    if show_standardized_json:
        st.subheader("Standardized Project Definition")
        st.json(standardized_project)

    st.divider()

    # Load database
    try:
        df = load_database()
    except FileNotFoundError:
        st.error(
            "Database file not found. Please make sure `botanical_database.xlsx` exists in the project folder."
        )
        st.stop()

    if show_database:
        st.subheader("Raw Botanical Database")
        st.dataframe(df, use_container_width=True)

    # Ranking
    ranked_df = rank_plants(df, standardized_project)
    ranked_df = ranked_df[ranked_df["Decision Score"] >= min_score]

    st.header("Ranked Botanical Recommendations")

    if ranked_df.empty:
        st.warning("No botanical ingredients matched the current project settings.")
    else:
        for _, row in ranked_df.iterrows():

            plant_name = row.get("Plant Name", "Unknown Plant")
            score = row.get("Decision Score", 0)

            with st.expander(f"{plant_name} — Decision Score: {score}"):

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Decision Score", score)
                    st.write("**Indication:**", row.get("Indication", "Not specified"))
                    st.write("**Dosage Form:**", row.get("Dosage Form", "Not specified"))
                    st.write("**Market:**", row.get("Market", "Not specified"))

                with col2:
                    st.write("**EMA:**", row.get("EMA", "Not specified"))
                    st.write("**WHO:**", row.get("WHO", "Not specified"))
                    st.write("**ESCOP:**", row.get("ESCOP", "Not specified"))
                    st.write("**Clinical Evidence:**", row.get("Clinical Evidence", "Not specified"))

                with col3:
                    st.write("**Safety:**", row.get("Safety", "Not specified"))
                    st.write("**Commercial Potential:**", row.get("Commercial Potential", "Not specified"))
                    st.write("**Recommendation:**", row.get("Recommendation", "Not specified"))

                st.markdown("### Evidence Gap")
                st.write(row.get("Evidence Gap", "Not specified"))

                st.markdown("### Development Decision")
                st.write(row.get("Development Decision", "Not specified"))

else:
    st.info("Complete the project definition form and click Analyze Project.")
