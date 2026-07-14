import time

import pandas as pd
import streamlit as st

from supabase_client import get_supabase_client
from supabase_data import load_plant_compounds_df
from multi_source_collector import collect_multi_source_evidence, _run_one_source

# Most errors during the first bulk pass came from only 2-3 sources
# (OpenAlex, Semantic Scholar, occasionally CrossRef) hitting rate
# limits — not from the other ~11 sources, which mostly succeeded. A
# "fast retry" that only re-queries the known-problematic sources is
# several times faster than re-running the full collector, and avoids
# creating duplicate saved records for sources that already succeeded.
FAST_RETRY_SOURCES = [
    {"name": "OpenAlex", "max_results": 5},
    {"name": "Semantic Scholar", "max_results": 5},
    {"name": "CrossRef", "max_results": 5},
]


def _fast_retry_sources(plant, indication):
    all_saved, all_errors = [], []
    for source_config in FAST_RETRY_SOURCES:
        sr, er = _run_one_source(
            source_config, plant, indication, "", "European Union", 3, True
        )
        all_saved.extend(sr)
        all_errors.extend(er)
    return {"saved_records": all_saved, "errors": all_errors}

st.set_page_config(page_title="Bulk Evidence Collection", page_icon="📚", layout="wide")

st.title("📚 Bulk Evidence Collection")
st.caption(
    "Runs the same evidence search used in Step 2, across every plant in "
    "the database instead of just the ones for one indication. Click the "
    "button below repeatedly (each click processes a small batch) until "
    "it's done — progress is saved in Supabase, so it's safe to close this "
    "page and come back later; it will pick up where it left off."
)

MAX_SECONDS_PER_CLICK = 240  # ~4 minutes of continuous work per click
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


def _mark_done(plant, n_saved, n_errors, sample_errors=""):
    client = get_supabase_client()
    client.table("bulk_evidence_progress").upsert({
        "scientific_name": plant,
        "status": "done",
        "records_saved": n_saved,
        "error_count": n_errors,
        "sample_errors": sample_errors[:2000],
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
    fast_mode = st.checkbox(
        "⚡ Fast retry mode: only re-query OpenAlex / Semantic Scholar / "
        "CrossRef (the sources that actually failed last time), skip the "
        "other ~11 sources that already succeeded",
        value=True,
        help="Turn this OFF if these are brand-new plants that have never "
             "been processed at all — new plants need the full 14-source "
             "search, not just these 3.",
    )

    st.info(
        f"Each click will keep processing plants for about "
        f"{MAX_SECONDS_PER_CLICK // 60} minutes straight (however many "
        f"that turns out to be — usually 15-30+ plants in full mode, "
        f"much more in fast mode), instead of a fixed small batch. You "
        f"can click again as soon as it finishes, or come back later."
    )

    button_label = (
        "⚡ Fast retry for the next few minutes"
        if fast_mode else
        "▶️ Full search for the next few minutes"
    )

    if st.button(button_label, type="primary"):
        progress_bar = st.progress(0)
        status_area = st.empty()
        results_log = []

        batch_start_time = time.time()
        processed_count = 0

        for plant in remaining:
            if time.time() - batch_start_time > MAX_SECONDS_PER_CLICK:
                break

            indication = all_plants.get(plant, "")
            processed_count += 1
            status_area.write(
                f"Processing **{plant}** "
                f"({processed_count} so far this click, "
                f"{len(remaining) - processed_count} left overall)..."
            )

            try:
                if fast_mode:
                    result = _fast_retry_sources(plant, indication)
                else:
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
                errors_list = result.get("errors", [])
                n_errors = len(errors_list)
                sample_errors = "; ".join(
                    f"{e.get('source', '?')}: {e.get('error', '')}"
                    for e in errors_list[:5]
                )
            except Exception as exc:
                n_saved, n_errors = 0, 1
                sample_errors = str(exc)
                results_log.append(f"❌ {plant}: failed entirely — {exc}")
            else:
                results_log.append(f"✅ {plant}: {n_saved} record(s), {n_errors} error(s)")

            try:
                _mark_done(plant, n_saved, n_errors, sample_errors)
            except Exception as exc:
                results_log.append(f"⚠️ {plant}: processed but failed to save progress — {exc}")

            progress_bar.progress(
                min(1.0, (time.time() - batch_start_time) / MAX_SECONDS_PER_CLICK)
            )

        status_area.empty()
        st.success(f"This click processed {processed_count} plant(s).")
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
- A time budget (not a fixed count) is used per click so it adapts to
  how fast each plant happens to respond, instead of guessing a fixed
  number that's either too small (lots of clicking) or too large (risks
  the click timing out before finishing).
- If a plant fails, it's still marked "done" with `error_count` set so
  the batch keeps moving — check the `bulk_evidence_progress` table in
  Supabase SQL Editor to see which ones had errors, and manually
  `DELETE FROM bulk_evidence_progress WHERE scientific_name = '...'` for
  any you want retried.
        """
    )
