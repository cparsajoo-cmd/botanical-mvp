import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Botanical Product Intelligence Platform",
    layout="wide"
)

# -----------------------------
# Evidence database — MVP version
# -----------------------------

plants = [
    {
        "Plant": "Melissa officinalis",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use for mild symptoms of mental stress and to aid sleep",
        "Infusion-specific evidence": "Supported as herbal tea/infusion in traditional-use context",
        "Safety": "Generally acceptable for short-term traditional use",
        "Commercial value": "High",
        "Decision": "Priority candidate",
        "Reason": "Strong regulatory fit for EU sleep/relaxation tea and good infusion suitability."
    },
    {
        "Plant": "Valeriana officinalis",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use for relief of mild nervous tension and sleep disorders",
        "Infusion-specific evidence": "Infusion is possible, but much clinical evidence relates to extracts",
        "Safety": "Possible drowsiness; caution with sedatives and driving",
        "Commercial value": "High",
        "Decision": "Conditional candidate",
        "Reason": "Strong sleep association, but infusion-specific clinical evidence is weaker than extract evidence."
    },
    {
        "Plant": "Passiflora incarnata",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use for mild symptoms of mental stress and to aid sleep",
        "Infusion-specific evidence": "Traditional infusion use is relevant",
        "Safety": "Generally acceptable; caution with sedative medicines",
        "Commercial value": "Medium",
        "Decision": "Conditional candidate",
        "Reason": "Good traditional-use fit, but clinical evidence is limited."
    },
    {
        "Plant": "Matricaria chamomilla",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use mainly for gastrointestinal and mild skin/mucosal indications",
        "Infusion-specific evidence": "Infusion is commercially and traditionally suitable",
        "Safety": "Possible allergy in Asteraceae-sensitive individuals",
        "Commercial value": "High",
        "Decision": "Supportive ingredient",
        "Reason": "Excellent tea suitability and market familiarity, but sleep-specific regulatory support is weaker."
    },
    {
        "Plant": "Lavandula angustifolia",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use for mild symptoms of mental stress and exhaustion",
        "Infusion-specific evidence": "Direct infusion-specific evidence is limited; much evidence relates to essential oil or oral oil preparations",
        "Safety": "Generally acceptable as herbal tea ingredient, but evidence transfer from essential oil is not direct",
        "Commercial value": "High",
        "Decision": "Supportive ingredient",
        "Reason": "Commercially attractive, but direct infusion-specific sleep evidence is limited."
    },
    {
        "Plant": "Humulus lupulus",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use for mild symptoms of mental stress and to aid sleep",
        "Infusion-specific evidence": "Often used in herbal tea combinations; direct standalone infusion evidence limited",
        "Safety": "Caution in pregnancy and hormone-sensitive contexts",
        "Commercial value": "Medium",
        "Decision": "Combination candidate",
        "Reason": "Useful in sleep formulas, especially combined with valerian or lemon balm."
    },
    {
        "Plant": "Tilia cordata / Tilia platyphyllos",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use mainly for common cold and mild symptoms of mental stress",
        "Infusion-specific evidence": "Very suitable for infusion",
        "Safety": "Generally acceptable in traditional tea use",
        "Commercial value": "Medium",
        "Decision": "Supportive ingredient",
        "Reason": "Good infusion and relaxation fit, but sleep-specific evidence is modest."
    },
    {
        "Plant": "Aloysia citriodora",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "No strong EMA sleep indication identified in this MVP dataset",
        "Infusion-specific evidence": "Commercially suitable as infusion",
        "Safety": "Generally used as tea; regulatory evidence should be verified",
        "Commercial value": "Medium",
        "Decision": "Evidence gap",
        "Reason": "Interesting sensory ingredient, but direct regulatory and clinical sleep evidence is limited."
    },
    {
        "Plant": "Eschscholzia californica",
        "Product form": "Infusion",
        "Indication": "Sleep and relaxation",
        "Market": "European Union",
        "EMA/HMPC": "Traditional use for mild symptoms of mental stress and to aid sleep",
        "Infusion-specific evidence": "Traditional herbal preparation may be relevant, but direct infusion evidence needs verification",
        "Safety": "Caution because of sedative positioning and regulatory differences",
        "Commercial value": "Medium",
        "Decision": "Conditional candidate",
        "Reason": "Potentially relevant, but requires careful regulatory and safety verification."
    },
]

df = pd.DataFrame(plants)

# -----------------------------
# Sidebar inputs
# -----------------------------

st.sidebar.title("Product question")

product_form = st.sidebar.selectbox(
    "Product form",
    ["Infusion", "Capsule", "Tablet", "Essential oil", "Hydroalcoholic extract"]
)

indication = st.sidebar.selectbox(
    "Target indication",
    ["Sleep and relaxation", "Constipation", "Anxiety", "Digestive comfort"]
)

market = st.sidebar.selectbox(
    "Target market",
    ["European Union", "United States", "Canada", "Iran"]
)

commercial_filter = st.sidebar.selectbox(
    "Commercial priority",
    ["All", "High", "Medium"]
)

st.title("🌿 Botanical Product Intelligence Platform")
st.caption("MVP demo — evidence-based botanical product decision support")

st.markdown("## Input question")

st.write(
    f"Which medicinal plants are scientifically and commercially worth investing in "
    f"for a product prepared as **{product_form}** for **{indication}** in **{market}**?"
)

# -----------------------------
# Decision logic
# -----------------------------

if st.button("Analyze evidence"):
    result = df[
        (df["Product form"] == product_form)
        & (df["Indication"] == indication)
        & (df["Market"] == market)
    ]

    if commercial_filter != "All":
        result = result[result["Commercial value"] == commercial_filter]

    st.markdown("## Output decision")

    if result.empty:
        st.warning("No direct evidence record found for this product question in the MVP database.")
        st.info(
            "This means the current MVP database does not yet contain enough structured evidence "
            "for this combination of product form, indication, and market."
        )
    else:
        priority = result[result["Decision"] == "Priority candidate"]
        conditional = result[result["Decision"] == "Conditional candidate"]
        supportive = result[result["Decision"] == "Supportive ingredient"]
        gap = result[result["Decision"] == "Evidence gap"]
        combination = result[result["Decision"] == "Combination candidate"]

        st.success(f"{len(result)} relevant plant records found.")

        st.markdown("### Summary table")
        st.dataframe(
            result[
                [
                    "Plant",
                    "Decision",
                    "Commercial value",
                    "EMA/HMPC",
                    "Infusion-specific evidence",
                    "Safety",
                    "Reason",
                ]
            ],
            use_container_width=True
        )

        st.markdown("### Recommended interpretation")

        if not priority.empty:
            st.markdown("#### Priority candidates")
            for _, row in priority.iterrows():
                st.write(f"**{row['Plant']}** — {row['Reason']}")

        if not conditional.empty:
            st.markdown("#### Conditional candidates")
            for _, row in conditional.iterrows():
                st.write(f"**{row['Plant']}** — {row['Reason']}")

        if not combination.empty:
            st.markdown("#### Combination candidates")
            for _, row in combination.iterrows():
                st.write(f"**{row['Plant']}** — {row['Reason']}")

        if not supportive.empty:
            st.markdown("#### Supportive ingredients")
            for _, row in supportive.iterrows():
                st.write(f"**{row['Plant']}** — {row['Reason']}")

        if not gap.empty:
            st.markdown("#### Evidence gaps")
            for _, row in gap.iterrows():
                st.write(f"**{row['Plant']}** — {row['Reason']}")

        csv = result.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="Download result as CSV",
            data=csv,
            file_name="botanical_product_decision.csv",
            mime="text/csv"
        )

st.divider()

st.caption(
    "MVP note: This demo uses a small structured evidence database. "
    "The next version should connect to the full botanical evidence database and official source documents."
)
