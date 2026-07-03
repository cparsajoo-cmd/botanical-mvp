import streamlit as st
from evidence_database import load_evidence_database
from decision_engine import analyze_evidence
from report_generator import generate_report

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

df = load_evidence_database()

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Evidence-based decision support for botanical product development")

st.sidebar.title("New Product Project")

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

min_score = st.sidebar.slider(
    "Minimum evidence score",
    0, 100, 0
)

st.markdown("## Product development question")

st.info(
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
        market=market,
        min_score=min_score
    )

    st.markdown("## Decision output")

    if result.empty:
        st.warning("No matching evidence records were found in the current Excel database.")
        st.write("Next step: add more structured evidence records to the Excel file.")
    else:
        st.success(f"{len(result)} relevant plant records found.")

        for _, row in result.iterrows():
            score = row.get("Evidence_Score", "")
            decision = row.get("Decision_Class", "")
            plant = row.get("Scientific_Name", "")
            common = row.get("Common_Name", "")
            reason = row.get("Decision_Reason", "")

            st.markdown("---")

            with st.expander(
                f"🌱 {plant} — {decision} — Score: {score}/100",
                expanded=True
            ):
                st.markdown(f"**Scientific name:** {plant}")
                st.markdown(f"**Common name:** {common}")
                st.markdown(f"**Decision:** {decision}")
                st.markdown(f"**Evidence score:** {score}/100")
                st.markdown(f"**Commercial potential:** {row.get('Commercial_Potential', '')}")

                st.markdown("### Regulatory evidence")
                st.markdown(f"**EMA:** {row.get('EMA_Status', '')}")
                st.markdown(f"**WHO:** {row.get('WHO_Status', '')}")
                st.markdown(f"**ESCOP:** {row.get('ESCOP_Status', '')}")
                st.markdown(f"**Regulatory status:** {row.get('Regulatory_Status', '')}")

                st.markdown("### Scientific evidence")
                st.markdown(f"**Clinical evidence:** {row.get('Clinical_Evidence', '')}")
                st.markdown(f"**Infusion-specific evidence:** {row.get('Infusion_Specific_Evidence', '')}")

                st.markdown("### Safety")
                st.markdown(f"**Safety:** {row.get('Safety', '')}")
                st.markdown(f"**Drug interactions:** {row.get('Drug_Interactions', '')}")

                st.markdown("### Product development decision")
                st.markdown(f"**Decision reason:** {reason}")
                st.markdown(f"**Reference:** {row.get('Reference', '')}")

        st.markdown("## Full decision table")
        st.dataframe(result, use_container_width=True)

        csv = result.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download decision output as CSV",
            data=csv,
            file_name="botanical_decision_output.csv",
            mime="text/csv"
        )

        report_text = generate_report(
            result=result,
            product_type=product_type,
            dosage_form=dosage_form,
            indication=indication,
            market=market
        )

        st.download_button(
            label="Download decision report as TXT",
            data=report_text.encode("utf-8"),
            file_name="botanical_decision_report.txt",
            mime="text/plain"
        )

st.divider()

st.caption(
    "This MVP reads structured evidence from Excel. "
    "Next versions will add source-level evidence, regulatory scoring, plant profile pages, and PDF reports."
)
