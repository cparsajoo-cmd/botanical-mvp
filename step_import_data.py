import streamlit as st
import pandas as pd

from supabase_client import get_supabase_client


PLANT_COMPOUNDS_COLUMNS = [
    "scientific_name", "common_name", "compound_name", "compound_class",
    "plant_part", "concentration", "unit", "extraction_method", "solvent",
    "yield_percent", "target", "mechanism", "bioavailability", "toxicity",
    "safety_note", "indication", "dosage_form", "market", "evidence_level",
    "confidence_score", "reference_title", "reference_url", "source",
    "source_year",
]

COMPOUND_PROFILES_COLUMNS = [
    "compound_name", "compound_class", "major_target", "mechanism",
    "evidence_level", "activity_score", "bioavailability", "stability",
    "extraction_difficulty", "toxicity", "commercial_interest",
    "reference_url", "source",
]

REQUIRED_COLUMNS = {
    "plant_compounds": ["scientific_name", "compound_name"],
    "compound_profiles": ["compound_name"],
}

DEDUPE_KEYS = {
    "plant_compounds": ["scientific_name", "compound_name", "indication"],
    "compound_profiles": ["compound_name"],
}

TABLE_COLUMNS = {
    "plant_compounds": PLANT_COMPOUNDS_COLUMNS,
    "compound_profiles": COMPOUND_PROFILES_COLUMNS,
}


def _clean_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value if value else None
    return value


def _load_uploaded_file(uploaded_file):
    if uploaded_file.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    return pd.read_csv(uploaded_file)


def _rows_from_dataframe(df, table):
    columns = TABLE_COLUMNS[table]
    required = REQUIRED_COLUMNS[table]

    unknown_cols = [c for c in df.columns if c not in columns]

    rows = []
    skipped = 0

    for _, raw_row in df.iterrows():
        row = {}
        for col in columns:
            row[col] = _clean_value(raw_row[col]) if col in df.columns else None

        if any(row.get(field) is None for field in required):
            skipped += 1
            continue

        rows.append(row)

    return rows, skipped, unknown_cols


def _row_key(row, table):
    key_cols = DEDUPE_KEYS[table]
    return tuple((row.get(col) or "").strip().lower() for col in key_cols)


def _existing_keys(supabase, table):
    key_cols = DEDUPE_KEYS[table]
    seen = set()

    start = 0
    page_size = 1000

    while True:
        response = (
            supabase.table(table)
            .select(",".join(key_cols))
            .range(start, start + page_size - 1)
            .execute()
        )
        data = response.data or []

        for item in data:
            key = tuple((item.get(col) or "").strip().lower() for col in key_cols)
            seen.add(key)

        if len(data) < page_size:
            break

        start += page_size

    return seen


def render_import_step():
    st.markdown("---")

    with st.expander("🛠️ Admin: Import data into Supabase (plant_compounds / compound_profiles)"):
        st.caption(
            "Upload a CSV or Excel file matching the real table columns and "
            "insert it directly into Supabase — no terminal needed."
        )

        table = st.selectbox(
            "Target table",
            ["plant_compounds", "compound_profiles"],
        )

        st.caption("Expected columns: " + ", ".join(TABLE_COLUMNS[table]))

        uploaded_file = st.file_uploader(
            "CSV or Excel file",
            type=["csv", "xlsx", "xls"],
            key=f"import_uploader_{table}",
        )

        if uploaded_file is None:
            return

        try:
            df = _load_uploaded_file(uploaded_file)
        except Exception as e:
            st.error(f"Could not read file: {e}")
            return

        st.write(f"{len(df)} row(s) found in the file.")
        st.dataframe(df.head(10), use_container_width=True)

        rows, skipped, unknown_cols = _rows_from_dataframe(df, table)

        if unknown_cols:
            st.info(f"Ignoring unrecognized columns: {unknown_cols}")

        if skipped:
            st.warning(
                f"{skipped} row(s) are missing a required field "
                f"({REQUIRED_COLUMNS[table]}) and will be skipped."
            )

        st.write(f"{len(rows)} row(s) are ready to import.")

        if not rows:
            return

        force = st.checkbox(
            "Import even if rows look like duplicates of existing data",
            value=False,
        )

        if st.button("Import into Supabase", type="primary"):
            try:
                supabase = get_supabase_client()
            except Exception as e:
                st.error(f"Could not connect to Supabase: {e}")
                return

            final_rows = rows

            if not force:
                with st.spinner("Checking for duplicates already in Supabase..."):
                    existing = _existing_keys(supabase, table)
                final_rows = [
                    r for r in rows if _row_key(r, table) not in existing
                ]
                dupes_skipped = len(rows) - len(final_rows)
                if dupes_skipped:
                    st.info(
                        f"Skipped {dupes_skipped} row(s) that already exist "
                        "in Supabase (check 'Import even if duplicates' to "
                        "force them in anyway)."
                    )

            if not final_rows:
                st.warning("Nothing new to import.")
                return

            batch_size = 200
            inserted = 0
            errors = []

            with st.spinner(f"Inserting {len(final_rows)} row(s)..."):
                for start in range(0, len(final_rows), batch_size):
                    batch = final_rows[start:start + batch_size]
                    try:
                        supabase.table(table).insert(batch).execute()
                        inserted += len(batch)
                    except Exception as e:
                        errors.append(str(e))

            if inserted:
                st.success(f"Inserted {inserted} row(s) into '{table}'.")
            if errors:
                st.error(f"{len(errors)} batch(es) failed:")
                for err in errors:
                    st.code(err)
