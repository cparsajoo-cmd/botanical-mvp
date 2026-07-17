import time

import pandas as pd
import streamlit as st

from supabase_client import get_supabase_client
from supabase_data import load_plant_compounds_df
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

from multi_source_collector import collect_multi_source_evidence, _run_one_source

# Most errors during the first bulk pass came from only 2-3 sources
# (OpenAlex, Semantic Scholar, occasionally CrossRef) hitting rate
# limits — not from the other ~11 sources, which mostly succeeded. A
# "fast retry" that only re-queries the known-problematic sources is
# meant to be several times faster than re-running the full collector.
#
# IMPORTANT: these must run IN PARALLEL, not sequentially — the original
# collect_multi_source_evidence runs all ~14 sources concurrently via a
# thread pool, so it finishes as fast as its SLOWEST single source. A
# naive sequential loop over even just 3 sources adds each source's full
# time (including retry/backoff delays on repeated 429s, which are still
# expected for Semantic Scholar until its API key is configured) on top
# of the others — which can end up SLOWER per plant than the original
# 14-parallel-source approach, not faster.
FAST_RETRY_SOURCES = [
    {"name": "OpenAlex", "max_results": 5},
    {"name": "Semantic Scholar", "max_results": 5},
    {"name": "CrossRef", "max_results": 5},
]


def _fast_retry_sources(plant, indication):
    all_saved, all_errors = [], []

    executor = ThreadPoolExecutor(max_workers=len(FAST_RETRY_SOURCES))
    try:
        futures = {
            executor.submit(
                _run_one_source, source_config, plant, indication,
                "", "European Union", 3, True,
            ): source_config["name"]
            for source_config in FAST_RETRY_SOURCES
        }

        try:
            for future in as_completed(futures, timeout=20):
                try:
                    sr, er = future.result(timeout=1)
                    all_saved.extend(sr)
                    all_errors.extend(er)
                except Exception as exc:
                    all_errors.append({
                        "source": futures[future],
                        "plant": plant,
                        "error": str(exc),
                    })
        except TimeoutError:
            # At least one source didn't finish within the time budget.
            # Record it as an error for THIS run and move on immediately
            # -- do not wait for it. It'll simply be retried on a future
            # click, same as any other still-failing plant.
            all_errors.append({
                "source": "fast_retry_batch",
                "plant": plant,
                "error": "One or more sources exceeded the 20s time budget.",
            })
    finally:
        # wait=False is the key fix: don't let a slow/stuck source hold up
        # the entire batch loop. Any still-running thread keeps running in
        # the background and is simply discarded from this function's
        # point of view.
        executor.shutdown(wait=False, cancel_futures=True)

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

MAX_SECONDS_PER_CLICK = 600  # ~10 minutes of continuous work per click
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

st.markdown("---")
st.markdown("## 🔄 Backfill: EMA/WHO/ESCOP Regulatory (all plants)")
st.caption(
    "The 'EMA/WHO/ESCOP Regulatory' source used to be a stub that only "
    "ever found data for 4 hardcoded plants — every other plant silently "
    "got nothing from it, even in runs marked '✅ done' above. It's now "
    "wired to a real EMA HMPC lookup. This section re-runs ONLY that one "
    "source, for every plant, without re-touching the other 13 sources "
    "or resetting their progress above."
)

_EMA_BACKFILL_PREFIX = "EMA_BACKFILL::"


def _get_ema_backfilled_plants():
    client = get_supabase_client()
    done = set()
    start = 0
    page_size = 1000
    while True:
        resp = (
            client.table("bulk_evidence_progress")
            .select("scientific_name")
            .like("scientific_name", f"{_EMA_BACKFILL_PREFIX}%")
            .range(start, start + page_size - 1)
            .execute()
        )
        rows = resp.data or []
        done.update(
            r["scientific_name"][len(_EMA_BACKFILL_PREFIX):] for r in rows
        )
        if len(rows) < page_size:
            break
        start += page_size
    return done


def _mark_ema_backfilled(plant, n_saved, n_errors, sample_errors=""):
    client = get_supabase_client()
    client.table("bulk_evidence_progress").upsert({
        "scientific_name": f"{_EMA_BACKFILL_PREFIX}{plant}",
        "status": "ema_backfill_done",
        "records_saved": n_saved,
        "error_count": n_errors,
        "sample_errors": sample_errors[:2000],
    }).execute()


try:
    ema_done_plants = _get_ema_backfilled_plants()
except Exception as exc:
    ema_done_plants = set()
    st.warning(f"Could not read EMA backfill progress yet: {exc}")

ema_remaining = [p for p in sorted(all_plants) if p not in ema_done_plants]

ecol1, ecol2, ecol3 = st.columns(3)
ecol1.metric("Total plants", total)
ecol2.metric("EMA-checked", len(ema_done_plants))
ecol3.metric("Remaining", len(ema_remaining))
st.progress(len(ema_done_plants) / total if total else 0)

if not ema_remaining:
    st.success("✅ Every plant has been checked against the real EMA HMPC inventory!")
elif st.button("🔄 Backfill EMA/WHO/ESCOP for the next few minutes", type="secondary"):
    progress_bar = st.progress(0)
    status_area = st.empty()
    results_log = []

    batch_start_time = time.time()
    processed_count = 0

    for plant in ema_remaining:
        if time.time() - batch_start_time > MAX_SECONDS_PER_CLICK:
            break

        indication = all_plants.get(plant, "")
        processed_count += 1
        status_area.write(
            f"Checking **{plant}** against EMA HMPC "
            f"({processed_count} so far this click, "
            f"{len(ema_remaining) - processed_count} left overall)..."
        )

        try:
            saved, errors = _run_one_source(
                {"name": "EMA/WHO/ESCOP Regulatory", "max_results": 5},
                plant, indication, "", "European Union", 3, True,
            )
            n_saved, n_errors = len(saved), len(errors)
            sample_errors = "; ".join(
                f"{e.get('source', '?')}: {e.get('error', '')}"
                for e in errors[:5]
            )
        except Exception as exc:
            n_saved, n_errors = 0, 1
            sample_errors = str(exc)
            results_log.append(f"❌ {plant}: failed entirely — {exc}")
        else:
            results_log.append(f"✅ {plant}: {n_saved} record(s), {n_errors} error(s)")

        try:
            _mark_ema_backfilled(plant, n_saved, n_errors, sample_errors)
        except Exception as exc:
            results_log.append(f"⚠️ {plant}: checked but failed to save progress — {exc}")

        progress_bar.progress(
            min(1.0, (time.time() - batch_start_time) / MAX_SECONDS_PER_CLICK)
        )

    status_area.empty()
    st.success(f"This click checked {processed_count} plant(s) against EMA HMPC.")
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
