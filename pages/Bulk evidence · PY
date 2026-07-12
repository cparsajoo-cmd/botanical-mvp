import time

import pandas as pd
import streamlit as st

from supabase_client import get_supabase_client
from supabase_data import load_plant_compounds_df
from multi_source_collector import collect_multi_source_evidence

st.set_page_config(page_title="Bulk Evidence Collection", page_icon="📚", layout="wide")

st.title("📚 Bulk Evidence Collection")
st.caption(
    "Runs the same evidence search used in Step 2, across every plant in "
    "the database instead of just the ones for one indication. Click the "
    "button below repeatedly (each click processes a small batch) until "
    "it's done — progress is saved in Supabase, so it's safe to close this "
    "page and come back later; it will pick up where it left off."
)

BATCH_SIZE = 10
MAX_INDICATIONS_PER_PLANT = 5


@st.cache_data(ttl=300, show_spinner=False)
def _all_plants_with_indications():
    df = load_plant_compounds_df()
    if df.empty or "scientific_name" not in df.columns:
        return {}

    plant_indications = {}
    for name, group in df.groupby("scientific_name"):
        name = str(name).strip()
        if not name:
            continue
        indications = sorted(set(
            d.strip()
            for text in group.get("indication", pd.Series(dtype=str)).dropna().astype(str)
            for d in text.split(";")
            if d.strip()
        ))
        plant_indications[name] = "; ".join(indications[:MAX_INDICATIONS_PER_PLANT])

    return plant_indications


def _get_done_plants():
    client = get_supabase_client()
    done = set()
    start = 0
    page_size = 1000
    while True:
        resp = (
            client.table("bulk_evidence_progress")
            .select("scientific_name")
            .range(start, start + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        done.update(r["scientific_name"] for r in rows)
        if len(rows) < page_size:
            break
        start += page_size
    return done


def _mark_done(plant, n_saved, n_errors):
    client = get_supabase_client()
    client.table("bulk_evidence_progress").upsert({
        "scientific_name": plant,
        "status": "done",
        "records_saved": n_saved,
        "error_count": n_errors,
    }).execute()


all_plants = _all_plants_with_indications()
total = len(all_plants)

if total == 0:
    st.error(
        "Could not load the plant list from Supabase. Check your "
        "connection/credentials before running this."
    )
    st.stop()

try:
    done_plants = _get_done_plants()
except Exception as exc:
    st.error(
        f"Could not read the bulk_evidence_progress table: {exc}\n\n"
        "Make sure you've run the create_progress_table.sql script in "
        "Supabase's SQL Editor first."
    )
    st.stop()

remaining = [p for p in sorted(all_plants) if p not in done_plants]

col1, col2, col3 = st.columns(3)
col1.metric("Total plants", total)
col2.metric("Done", len(done_plants))
col3.metric("Remaining", len(remaining))

st.progress(len(done_plants) / total if total else 0)

if not remaining:
    st.success("✅ All plants have been processed!")
else:
    st.info(
        f"Next click will process up to {min(BATCH_SIZE, len(remaining))} "
        f"more plant(s). At roughly 10-30 seconds per plant, that's a "
        f"couple of minutes per click."
    )

    if st.button("▶️ Process next batch", type="primary"):
        batch = remaining[:BATCH_SIZE]
        progress_bar = st.progress(0)
        status_area = st.empty()
        results_log = []

        for i, plant in enumerate(batch, 1):
            indication = all_plants.get(plant, "")
            status_area.write(f"Processing **{plant}** ({i}/{len(batch)})...")

            try:
                result = collect_multi_source_evidence(
                    scientific_name=plant,
                    indication=indication,
                    dosage_form="",
                    market="European Union",
                    max_pubmed_results=3,
                    max_clinicaltrials_results=3,
                    save=True,
                )
                n_saved = len(result.get("saved_records", []))
                n_errors = len(result.get("errors", []))
            except Exception as exc:
                n_saved, n_errors = 0, 1
                results_log.append(f"❌ {plant}: failed entirely — {exc}")
            else:
                results_log.append(f"✅ {plant}: {n_saved} record(s), {n_errors} error(s)")

            try:
                _mark_done(plant, n_saved, n_errors)
            except Exception as exc:
                results_log.append(f"⚠️ {plant}: processed but failed to save progress — {exc}")

            progress_bar.progress(i / len(batch))
            time.sleep(1)

        status_area.empty()
        st.success(f"Batch complete — {len(batch)} plant(s) processed.")
        for line in results_log:
            st.write(line)

        st.cache_data.clear()
        st.rerun()

with st.expander("How this works / notes"):
    st.markdown(
        """
- Each plant is searched using its **own** already-known indications
  (from `plant_compounds`), capped at 5 per plant, instead of one fixed
  indication for every plant.
- Progress is tracked in the `bulk_evidence_progress` Supabase table —
  not in this browser session — so multiple people, devices, or visits
  over time all contribute to the same progress.
- A batch size of 10 keeps each click safely within the time a single
  page interaction is allowed to take. Larger batches risk the click
  timing out before finishing.
- If a plant fails, it's still marked "done" with `error_count` set so
  the batch keeps moving — check the `bulk_evidence_progress` table in
  Supabase SQL Editor to see which ones had errors, and manually
  `DELETE FROM bulk_evidence_progress WHERE scientific_name = '...'` for
  any you want retried.
        """
    )
