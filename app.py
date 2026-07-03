import streamlit as st
from evidence_database import load_evidence_database
from decision_engine import analyze_evidence
from report_generator import generate_report
from question_parser import parse_user_question

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

df = load_evidence_database()

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("Evidence-based decision support for botanical product development")

st.sidebar.title("New Product Project")

free_question = st.sidebar.text_area(
    "Describe your product idea",
    placeholder="Example: I want to develop a bedtime herbal tea for sleep in the EU."
)

parsed = parse_user_question(free_question) if free_question.strip() else None

def options(column):
    return sorted(df[column].dropna().astype(str).unique())

def get_index(opts, value):
    return opts.index(value) if value in opts else 0

product_type_options = options("Product_Type")
dosage_form_options = options("Dosage_Form")
indication_options = options("Target_Indication")
market_options = options("Target_Market")

product_type = st.sidebar.selectbox(
    "Product type",
    product_type_options,
    index=get_index(product_type_options, parsed.get("product_type") if parsed else None)
)

dosage_form = st.sidebar.selectbox(
    "Dosage form",
    dosage_form_options,
    index=get_index(dosage_form_options, parsed.get("dosage_form") if parsed else None)
)

indication = st.sidebar.selectbox(
    "Target indication",
    indication_options,
    index=get_index(indication_options, parsed.get("indication") if parsed else None)
)

market = st.sidebar.selectbox(
    "Target market",
    market_options,
    index=get_index(market_options, parsed.get("market") if parsed else None)
)

min_score = st.sidebar.slider("Minimum evidence score", 0, 100, 0)

if parsed:
    st.sidebar.markdown("### Parsed question")
    st.sidebar.json(parsed)

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
        st.warning("No matching evidence records were found.")
    else:
        st.success(str(len(result)) + " relevant plant records found.")

        st.markdown("## Ranked recommendations")

        for _, row in result.iterrows():
            plant = row.get("Scientific_Name", "")
            common = row.get("Common_Name", "")
            decision = row.get("Decision_Class", "")
            score = row.get("Evidence_Score", "")
            reason = row.get("Notes", "")

            with st.expander(
                f"🌱 {plant} — {decision} — Score: {score}/100",
                expanded=True
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("### Identity")
                    st.markdown(f"**Scientific name:** {plant}")
                    st.markdown(f"**Common name:** {common}")
                    st.markdown(f"**Decision:** {decision}")
                    st.markdown(f"**Evidence score:** {score}/100")
                    st.markdown(f"**Commercial level:** {row.get('Commercial_Level', '')}")

                with col2:
                    st.markdown("### Product fit")
                    st.markdown(f"**Product type:** {row.get('Product_Type', '')}")
                    st.markdown(f"**Dosage form:** {row.get('Dosage_Form', '')}")
                    st.markdown(f"**Indication:** {row.get('Target_Indication', '')}")
                    st.markdown(f"**Market:** {row.get('Target_Market', '')}")

                st.markdown("### Regulatory evidence")
                st.markdown(f"**EMA:** {row.get('EMA_Status', '')}")
                st.markdown(f"**WHO:** {row.get('WHO_Status', '')}")
                st.markdown(f"**ESCOP:** {row.get('ESCOP_Status', '')}")
                st.markdown(f"**Regulatory status:** {row.get('Regulatory_Status', '')}")

                st.markdown("### Scientific evidence")
                st.markdown(f"**Clinical level:** {row.get('Clinical_Level', '')}")
                st.markdown(f"**RCT count:** {row.get('Clinical_RCT_Count', '')}")
                st.markdown(f"**Meta-analysis level:** {row.get('Meta_Level', '')}")
                st.markdown(f"**Meta-analysis count:** {row.get('Meta_Count', '')}")
                st.markdown(f"**Dosage-form evidence:** {row.get('Infusion_Evidence', '')}")

                st.markdown("### Safety and market")
                st.markdown(f"**Safety level:** {row.get('Safety_Level', '')}")
                st.markdown(f"**Drug interaction level:** {row.get('Drug_Interaction_Level', '')}")
                st.markdown(f"**Commercial level:** {row.get('Commercial_Level', '')}")
                st.markdown(f"**Novel food status:** {row.get('Novel_Food_Status', '')}")

                st.markdown("### Notes")
                st.write(reason)

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
