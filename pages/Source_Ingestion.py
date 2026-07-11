import streamlit as st

st.title("Source Ingestion")
st.caption(
    "Manually-curated evidence source records. This page is for reference "
    "only — use the 'Optional: import / ingest data' panel on the main "
    "app page to actually load new sources into Supabase."
)

# ------------------------------------------------------------------ #
# Each entry below is a manually-reviewed evidence source. Add new
# sources as additional dicts in EVIDENCE_SOURCES rather than pasting
# raw text directly into this file — unquoted text at module level is
# not valid Python and will crash the entire app (this is exactly what
# happened before this fix: a pasted reference document with no
# surrounding quotes/triple-quotes was treated as executable code).
# ------------------------------------------------------------------ #

EVIDENCE_SOURCES = [
    {
        "source_type": "EMA-HMPC",
        "title": (
            "European Medicines Agency Assessment Report — "
            "Melissa officinalis L., folium"
        ),
        "organization": "European Medicines Agency (EMA)",
        "year": "2013",
        "url": "https://www.ema.europa.eu",
        "text": """Melissa officinalis L. leaf has a long tradition of medicinal use in Europe.

The herbal substance consists of the dried leaves of Melissa officinalis L.

Traditional herbal medicinal product for the relief of mild symptoms of mental stress and to aid sleep.

Traditional herbal medicinal product for mild gastrointestinal complaints including bloating and flatulence.

Dosage form assessed:
- Herbal tea (infusion)
- Comminuted herbal substance
- Cut herbal substance

The recommended preparation is an herbal infusion prepared with boiling water.

Safety:
Generally well tolerated. No major safety concerns have been identified when used according to the monograph.

Regulatory status:
Traditional Use — EMA HMPC positive monograph.

Clinical evidence:
Traditional use supported. Human data available but limited.""",
        "reference": "EMA/HMPC/196745/2012",
    },
]

for source in EVIDENCE_SOURCES:
    with st.expander(f"{source['title']} ({source['year']})"):
        st.markdown(f"**Source type:** {source['source_type']}")
        st.markdown(f"**Organization:** {source['organization']}")
        st.markdown(f"**Year:** {source['year']}")
        st.markdown(f"**URL:** {source['url']}")
        st.markdown("**Text:**")
        st.text(source["text"])
        st.markdown(f"**Reference:** {source['reference']}")

if not EVIDENCE_SOURCES:
    st.info("No manually-curated sources added yet.")
