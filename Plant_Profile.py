import streamlit as st
from evidence_database import load_evidence_database
from plant_profile_regulatory import get_regulatory_source_rows
from standard_evidence_builder import normalize_missing_value

st.set_page_config(
    page_title="Plant Profile",
    page_icon="🌿",
    layout="wide"
)

st.title("🌿 Plant Profile")
st.caption("Detailed botanical evidence profile")

try:
    df = load_evidence_database()
except Exception as exc:
    df = None
    st.error(f"Could not load the evidence database: {exc}")

if df is None or df.empty or "Scientific_Name" not in df.columns:
    st.info(
        "No evidence records are available yet. This page will populate "
        "once evidence has been collected (Step 2 on the main page) or "
        "imported."
    )
else:
    plant_list = sorted(df["Scientific_Name"].dropna().unique())

    if not plant_list:
        st.info("No plants with a name are available in the evidence database yet.")
    else:
        selected_plant = st.selectbox("Select a plant", plant_list)

        plant_data = df[df["Scientific_Name"] == selected_plant]

        if plant_data.empty:
            st.warning("No profile found for this plant.")
        else:
            row = plant_data.iloc[0]

            st.markdown(f"## {row.get('Scientific_Name', '')}")
            st.markdown(f"**Common name:** {row.get('Common_Name', '')}")

            st.divider()

            st.markdown("## Product development summary")
            st.markdown(f"**Decision class:** {row.get('Decision_Class', '')}")
            st.markdown(f"**Evidence score:** {row.get('Evidence_Score', '')}/100")
            st.markdown(f"**Commercial potential:** {row.get('Commercial_Potential', '')}")
            st.markdown(f"**Decision reason:** {row.get('Decision_Reason', '')}")

            # Task 16 — replaces the previous arbitrary-first-row display
            # of EMA_Status/WHO_Status/ESCOP_Status/Regulatory_Status
            # (which came from `row`, the same plant_data.iloc[0] used
            # for the non-regulatory sections above — a genuinely
            # different, non-regulatory-shaped concern this task does
            # not touch). The regulatory section below deliberately
            # does NOT read from `row` at all: it looks at every
            # evidence record for this plant and shows only the ones
            # genuinely sourced from a regulatory connector
            # (Source_Type == "Regulatory"), each with its own real
            # provenance — never one row's flags standing in for "the"
            # regulatory status of the whole plant.
            st.markdown("## Regulatory evidence")

            regulatory_rows = get_regulatory_source_rows(df, selected_plant)

            if regulatory_rows.empty:
                st.info(
                    "No source-linked regulatory record was found for this "
                    "plant in the current evidence database."
                )
            else:
                record_count = len(regulatory_rows)
                st.markdown(
                    f"**Regulatory-source evidence** "
                    f"({record_count} record{'s' if record_count != 1 else ''} found)"
                )
                # Task 16 §7 — every matching record is shown; multiple
                # records are never silently collapsed into one, and no
                # new deduplication is introduced (the page has none
                # today). Deliberately does NOT display raw EMA_Status/
                # WHO_Status/ESCOP_Status/Regulatory_Status/
                # Novel_Food_Status anywhere below — only genuinely
                # source-linked provenance fields, per the Task 16
                # correction's explicit field list.
                for position, (_, reg_row) in enumerate(regulatory_rows.iterrows(), start=1):
                    organization = normalize_missing_value(reg_row.get("Source_Organization"))
                    title = normalize_missing_value(reg_row.get("Source_Title"))
                    evidence_level = normalize_missing_value(reg_row.get("Evidence_Level"))
                    record_id = normalize_missing_value(reg_row.get("Evidence_Record_ID"))
                    url = normalize_missing_value(reg_row.get("Source_URL"))
                    notes = normalize_missing_value(reg_row.get("Notes"))

                    expander_label = f"Record {position}"
                    if organization:
                        expander_label += f" — {organization}"

                    with st.expander(expander_label, expanded=(record_count == 1)):
                        if title:
                            st.markdown(f"**Source title:** {title}")
                        if organization:
                            st.markdown(f"**Source organization:** {organization}")
                        if evidence_level:
                            # Prefer this over any status-label wording —
                            # for a genuine EMA/HMPC inventory record this
                            # reads e.g. "Listed in official EMA HMPC
                            # inventory", a factual statement about
                            # presence in the source, never "approved" or
                            # "authorised" (Task 16 §5).
                            st.markdown(f"**Evidence level:** {evidence_level}")
                        if record_id:
                            st.markdown(f"**Evidence record ID:** {record_id}")
                        if url:
                            st.markdown(f"**Source:** [{url}]({url})")
                        if notes:
                            st.markdown(f"**Notes:** {notes}")

                st.caption(
                    "Shown here only where the underlying evidence record's "
                    "own Source_Type identifies it as coming from a "
                    "regulatory-source connector. This reflects presence in "
                    "a regulatory source, not a confirmed approval, "
                    "authorisation, or monograph status."
                )

            st.markdown("## Scientific evidence")
            st.markdown(f"**Clinical evidence:** {row.get('Clinical_Evidence', '')}")
            st.markdown(f"**Infusion-specific evidence:** {row.get('Infusion_Specific_Evidence', '')}")

            st.markdown("## Safety")
            st.markdown(f"**Safety:** {row.get('Safety', '')}")
            st.markdown(f"**Drug interactions:** {row.get('Drug_Interactions', '')}")

            st.markdown("## Source")
            st.markdown(f"**Evidence source:** {row.get('Evidence_Source', '')}")
            st.markdown(f"**Source document:** {row.get('Source_Document', '')}")
            st.markdown(f"**Reference:** {row.get('Reference', '')}")
