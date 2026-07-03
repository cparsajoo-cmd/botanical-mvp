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

parsed = None
if free_question.strip():
    parsed = parse_user_question(free_question)

product_type_options = sorted(df["Product_Type"].dropna().astype(str).unique())
dosage_form_options = sorted(df["Dosage_Form"].dropna().astype(str).unique())
indication_options = sorted(df["Target_Indication"].dropna().astype(str).unique())
market_options = sorted(df["Target_Market"].dropna().astype(str).unique())

def get_index(options, value):
    if value in options:
        return options.index(value)
    return 0

product_type = st.sidebar.selectbox(
    "Product type",
    product_type_options,
    index=get_index(product_type_options, parsed["product_type"] if parsed else None)
)

dosage_form = st.sidebar.selectbox(
    "Dosage form",
    dosage_form_options,
    index=get_index(dosage_form_options, parsed["dosage_form"] if parsed else None)
)

indication = st.sidebar.selectbox(
    "Target indication",
    indication_options,
    index=get_index(indication_options, parsed["indication"] if parsed else None)
)

market = st.sidebar.selectbox(
    "Target market",
    market_options,
    index=get_index(market_options, parsed["market"] if parsed else None)
)

min_score = st.sidebar.slider("Minimum evidence score", 0, 100, 0)

if parsed:
    st.sidebar.markdown("### Parsed question")
    st.sidebar.write(parsed)

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
        st.success(f"{len(result)} relevant
