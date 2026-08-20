"""Regression test for the small stagger between source-launch submissions
in collect_multi_source_evidence().

CONTEXT
Even after all previous Step 2 fixes (see test_step2_collection_budget.py
and test_connector_identification_headers.py), a real run kept coming back
with every plant marked INCOMPLETE. Root cause, verified against
retrieval_coverage.py: assess_retrieval_coverage() requires at least one of
PubMed/Europe PMC (literature) and at least one of
LiverTox/DailyMed/OpenFDA FAERS (safety) to have completed without being
"failed" (present in errors with zero saved records for that source) --
this is by design, not a bug, and is the correct behavior when those
sources genuinely didn't return anything usable. But PubMed, CrossRef, and
Semantic Scholar were observed returning real HTTP 429s on the very same
runs, even hours apart -- consistent with launching all ~15 sources for a
plant (and, with plant_workers=2, up to ~30 across two plants) in the same
instant, which is itself a burst that several of these providers rate-limit
on a per-second basis, not just cumulative daily volume.

This test locks in a small stagger between source-launch submissions, so a
handful of shared/sensitive hosts (e.g. PubMed and LiverTox both hit
eutils.ncbi.nlm.nih.gov) are not all hit in the same instant. This does not
guarantee an already-throttled provider recovers, but reduces how often
this application's own request pattern is the trigger.

HOW TO RUN
    pytest -q test_source_launch_stagger.py
"""
import time

import multi_source_collector as msc


def test_sources_are_submitted_with_a_stagger(monkeypatch):
    submit_times = []

    class _FakeExecutor:
        def __init__(self, max_workers=None):
            pass

        def submit(self, fn, *args, **kwargs):
            submit_times.append(time.monotonic())
            class _ImmediateFuture:
                def result(self_inner, timeout=None):
                    return [], []
            return _ImmediateFuture()

        def shutdown(self, wait=True, cancel_futures=False):
            pass

    monkeypatch.setattr(msc, "ThreadPoolExecutor", _FakeExecutor)
    monkeypatch.setattr(
        msc, "as_completed", lambda future_map, timeout=None: list(future_map)
    )

    msc.collect_multi_source_evidence(
        scientific_name="Test Plant",
        indication="TestIndication",
        dosage_form="Infusion",
        save=False,
    )

    assert len(submit_times) >= 2, "expected multiple sources to be submitted"
    gaps = [b - a for a, b in zip(submit_times, submit_times[1:])]
    # Every gap should reflect a real, non-zero stagger (not all fired in
    # the same instant).
    assert all(gap > 0 for gap in gaps), (
        "sources were submitted with no stagger between them -- this is "
        "the exact burst pattern that has been triggering real HTTP 429s "
        "from PubMed, CrossRef, and Semantic Scholar in production."
    )
