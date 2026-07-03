import streamlit as st

from evidence_database import load_evidence_database
from decision_engine import analyze_evidence

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("MVP demo — connected to Excel evidence database")

df = load_evidence_database()

st.sidebar.title("New Project")

product_type = st.sidebar.selectbox(
    "Product type",
    sorted(df["Product_Type"].dropna().unique())
)

dosage_form = st.sidebar.selectbox(
    "Dosage form",
    sorted(df["Dosage_Form"].dropna().unique())
)

indication = st.sidebar.selectbox(
    "Target indication",
    sorted(df["Target_Indication"].dropna().unique())
)

market = st.sidebar.selectbox(
    "Target market",
    sorted(df["Target_Market"].dropna().unique())
)

st.markdown("## Input question")

st.write(
    f"Which medicinal plants are scientifically and commercially worth investing in "
    f"for **{product_type}** prepared as **{dosage_form}** for **{indication}** "
    f"in **{market}**?"
)

if st.button("Analyze evidence"):
    result = analyze_evidence(
        df=df,
        product_type=product_type,
        dosage_form=dosage_form,
        indication=indication,
        market=market
    )

    st.markdown("## Output decision")

    if result.empty:
        st.warning("No evidence record found for this product question in the current Excel database.")
    else:
        st.success(f"{len(result)} relevant plant records found.")

        columns_to_show = [
            "Scientific_Name",
            "Common_Name",
            "Decision_Class",
            "Evidence_Score",
            "EMA_Status",
            "WHO_Status",
            "ESCOP_Status",
            "Clinical_Evidence",
            "Infusion_Specific_Evidence",
            "Safety",
            "Commercial_Potential",
            "Decision_Reason",
        ]

        available_columns = [c for c in columns_to_show if c in result.columns]

        st.dataframe(
            result[available_columns],
            use_container_width=True
        )

        st.markdown("### Recommended interpretation")

        for _, row in result.iterrows():
            st.write(
                f"**{row['Scientific_Name']}** "
                f"({row.get('Common_Name', '')}) — "
                f"**{row.get('Decision_Class', '')}**. "
                f"{row.get('Decision_Reason', '')}"
            )

        csv = result.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download decision table as CSV",
            data=csv,
            file_name="botanical_decision_output.csv",
            mime="text/csv"
        )

st.divider()

st.caption(
    "MVP note: The app now reads evidence records from the Excel database. "
    "To add plants or evidence, update the Excel file and commit it to GitHub."
)
