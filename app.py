import streamlit as st
import pandas as pd
from io import StringIO

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("MVP demo — evidence-based botanical product decision support")

# -----------------------------
# Demo evidence database
# Later, this section can be replaced by Excel/CSV/JSON files from your 22 evidence documents.
# -----------------------------
DATA = [
    {
        "Plant": "Melissa officinalis",
        "Common name": "Lemon balm",
        "Indication fit": "Sleep / relaxation",
        "Allowed form fit": "Dried herb infusion",
        "EMA/HMPC support": "Traditional use for mild symptoms of mental stress and to aid sleep",
        "Infusion-specific evidence": "Direct infusion-specific evidence limited; traditional infusion use supported",
        "Commercial attractiveness": "High",
        "Safety": "Generally acceptable for short-term traditional use",
        "Decision": "Priority candidate",
        "Main reason": "Best fit for a bedtime infusion MVP because regulatory, traditional-use and product-form fit are aligned."
    },
    {
        "Plant": "Valeriana officinalis",
        "Common name": "Valerian",
        "Indication fit": "Sleep",
        "Allowed form fit": "Dried root infusion possible",
        "EMA/HMPC support": "Traditional use for mild nervous tension and sleep disorders",
        "Infusion-specific evidence": "Direct infusion-specific evidence limited; much evidence is from extracts",
        "Commercial attractiveness": "High",
        "Safety": "Sedation warning; caution with CNS depressants",
        "Decision": "Conditional candidate",
        "Main reason": "Strong sleep reputation, but many clinical data are not infusion-specific."
    },
    {
        "Plant": "Passiflora incarnata",
        "Common name": "Passionflower",
        "Indication fit": "Stress / sleep support",
        "Allowed form fit": "Dried aerial parts infusion",
        "EMA/HMPC support": "Traditional use for mild symptoms of mental stress and to aid sleep",
        "Infusion-specific evidence": "Some infusion-related traditional use; direct clinical infusion evidence remains limited",
        "Commercial attractiveness": "Medium-high",
        "Safety": "Generally acceptable; caution with sedatives",
        "Decision": "Conditional candidate",
        "Main reason": "Good regulatory fit, but should be positioned carefully as relaxation/sleep support."
    },
    {
        "Plant": "Matricaria chamomilla / Chamomilla recutita",
        "Common name": "Chamomile",
        "Indication fit": "Relaxation / digestive comfort",
        "Allowed form fit": "Flower infusion",
        "EMA/HMPC support": "Traditional use mainly for gastrointestinal and minor inflammatory conditions",
        "Infusion-specific evidence": "Infusion use is commercially and traditionally strong, but sleep-specific evidence is weaker",
        "Commercial attractiveness": "Very high",
        "Safety": "Generally acceptable; allergy risk in Asteraceae-sensitive users",
        "Decision": "Supportive blend candidate",
        "Main reason": "Excellent consumer acceptance and infusion fit, but not the strongest direct sleep claim candidate."
    },
    {
        "Plant": "Lavandula angustifolia",
        "Common name": "Lavender",
        "Indication fit": "Relaxation",
        "Allowed form fit": "Flower infusion possible",
        "EMA/HMPC support": "Traditional use exists, but much sleep/anxiety evidence involves essential oil or extracts",
        "Infusion-specific evidence": "Direct infusion-specific evidence not found in this demo database",
        "Commercial attractiveness": "High",
        "Safety": "Generally acceptable as herbal tea ingredient; essential-oil evidence should not be transferred automatically",
        "Decision": "Supportive blend candidate",
        "Main reason": "Commercially attractive, but evidence must not be borrowed from essential oil studies."
    },
    {
        "Plant": "Humulus lupulus",
        "Common name": "Hops",
        "Indication fit": "Sleep / nervous tension",
        "Allowed form fit": "Dried strobiles infusion possible",
        "EMA/HMPC support": "Traditional use for mild symptoms of mental stress and to aid sleep",
        "Infusion-specific evidence": "Direct infusion-specific evidence limited; often used with valerian",
        "Commercial attractiveness": "Medium",
        "Safety": "Sedative caution; taste may limit consumer acceptance",
        "Decision": "Conditional blend candidate",
        "Main reason": "Regulatory fit is useful, but taste and combination-dependence need product-development work."
    },
    {
        "Plant": "Tilia cordata / Tilia platyphyllos",
        "Common name": "Linden flower",
        "Indication fit": "Relaxation / mild stress",
        "Allowed form fit": "Flower infusion",
        "EMA/HMPC support": "Traditional herbal medicinal use may support mild stress-related positioning depending on source set",
        "Infusion-specific evidence": "Traditional infusion use strong; direct clinical sleep evidence limited",
        "Commercial attractiveness": "Medium-high",
        "Safety": "Generally acceptable for traditional infusion use",
        "Decision": "Supportive blend candidate",
        "Main reason": "Good tea identity and relaxation image, but weaker direct sleep-efficacy basis."
    },
    {
        "Plant": "Aloysia citriodora",
        "Common name": "Lemon verbena",
        "Indication fit": "Relaxation / sensory bedtime blend",
        "Allowed form fit": "Leaf infusion",
        "EMA/HMPC support": "Sleep-specific EMA support not established in this demo database",
        "Infusion-specific evidence": "Direct infusion-specific evidence not found in this demo database",
        "Commercial attractiveness": "Medium-high",
        "Safety": "Generally used in herbal teas; evidence basis should be checked carefully",
        "Decision": "Sensory/supportive candidate",
        "Main reason": "Useful for taste and consumer appeal, but not a core evidence-based sleep claim plant."
    },
    {
        "Plant": "Eschscholzia californica",
        "Common name": "California poppy",
        "Indication fit": "Sleep / mild anxiety",
        "Allowed form fit": "Dried aerial parts infusion possible",
        "EMA/HMPC support": "Regulatory position must be checked carefully for target market",
        "Infusion-specific evidence": "Direct infusion-specific evidence not found in this demo database",
        "Commercial attractiveness": "Medium",
        "Safety": "Needs careful safety and regulatory review before use",
        "Decision": "Evidence-gap candidate",
        "Main reason": "Potentially relevant, but not suitable as a first MVP priority without stronger regulatory and safety confirmation."
    }
]

df = pd.DataFrame(DATA)

# -----------------------------
# Sidebar inputs
# -----------------------------
st.sidebar.header("Product question")
product = st.sidebar.selectbox("Product type", ["Herbal tea", "Capsule", "Topical cream", "Syrup"], index=0)
dosage_form = st.sidebar.selectbox("Dosage form", ["Infusion", "Capsule/tablet", "Hydroalcoholic extract", "Essential oil"], index=0)
indication = st.sidebar.selectbox("Health indication", ["Sleep and relaxation", "Constipation", "Cough", "Digestive comfort", "Skin"], index=0)
market = st.sidebar.selectbox("Target market", ["European Union", "France", "Iran", "USA", "Canada"], index=0)

st.sidebar.markdown("---")
st.sidebar.write("**Core rule**")
st.sidebar.info("Evidence must match the dosage form. Essential oil, capsule, extract or tablet evidence is not automatically valid for an infusion product.")

# -----------------------------
# Main content
# -----------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Candidate plants", len(df))
col2.metric("Product form", dosage_form)
col3.metric("Market", market)

st.markdown("### Decision question")
st.write(
    f"Which medicinal plants are scientifically and commercially worth investing in for a **{product}** "
    f"prepared as **{dosage_form}** for **{indication}** in **{market}**?"
)

if product != "Herbal tea" or dosage_form != "Infusion" or indication != "Sleep and relaxation":
    st.warning("This MVP demo is currently configured for: Herbal tea → Infusion → Sleep and relaxation. Other options are placeholders for future versions.")

if st.button("Analyze evidence", type="primary"):
    st.success("Evidence analysis completed — MVP demo output")

    st.markdown("## 1. Executive decision")
    priority = df[df["Decision"].isin(["Priority candidate", "Conditional candidate"])]
    st.dataframe(priority[["Plant", "Common name", "Decision", "Main reason"]], use_container_width=True)

    st.markdown("## 2. Full evidence matrix")
    st.dataframe(df, use_container_width=True)

    st.markdown("## 3. Investment interpretation")
    st.write(
        "For a first bedtime infusion MVP, **Melissa officinalis** is the strongest starting candidate. "
        "**Valeriana officinalis** and **Passiflora incarnata** are relevant but should be treated as conditional candidates because the dosage-form specificity of the evidence must be checked carefully. "
        "Chamomile, lavender, linden and lemon verbena may be useful as supportive or sensory blend ingredients, but should not carry the strongest sleep claim unless direct evidence supports it."
    )

    st.markdown("## 4. Evidence gaps")
    gaps = df[df["Infusion-specific evidence"].str.contains("not found|limited", case=False, regex=True)]
    st.dataframe(gaps[["Plant", "Infusion-specific evidence", "Decision"]], use_container_width=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download evidence matrix as CSV",
        data=csv,
        file_name="botanical_sleep_tea_evidence_matrix.csv",
        mime="text/csv"
    )

else:
    st.info("Set the product question in the sidebar, then click **Analyze evidence**.")

st.markdown("---")
st.caption("MVP note: This is a demonstration structure. In the final platform, the evidence database should be populated only from your verified EMA, WHO, ESCOP, pharmacopoeia and clinical evidence documents.")
