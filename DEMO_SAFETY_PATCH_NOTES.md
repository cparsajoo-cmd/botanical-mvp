# Final demo-safety patch

This package contains the production files that should overlay the original project before the live demo.

## Reliability hardening added in this pass

1. Per-candidate Step-5 isolation is preserved from the prior repair: an exception while scoring one plant produces an `INCOMPLETE` / `Hold` row for that plant and the remaining candidates continue.
2. Supabase loaders now support `strict=True` without changing their default interactive behavior.
3. Step 5 uses strict core-table loads so a genuine Supabase failure is observable and cannot be mislabeled as a successful empty fetch.
4. Failed core-table loads set `data_source_reliable=False`; the existing engine safety logic therefore prevents a `Go` decision from being issued from unreliable/fallback data.
5. The UI now displays an early warning when the primary evidence database is unavailable or only partially verified.
6. Step 5 displays an explicit degraded-mode warning if core scientific sources are unreliable.
7. `ENGINE_CACHE_VERSION` was bumped so Streamlit does not silently reuse a pre-patch cached engine after deployment.

## Offline checks performed

- Python compilation passed for all replacement production files.
- Simulated Supabase outage test passed:
  - default/non-strict loaders return an empty DataFrame without crashing the UI;
  - strict Step-5 loaders re-raise the outage so the wrapper marks that source unreliable.
- The full repository test suite could not be rerun in this container because Streamlit is not installed and internet access is disabled. The immediately preceding Claude repair reported 3840 passed / 0 failed / 3 expected failures before this small reliability patch.

## Before the investor demo

Restart the Streamlit process after copying these files, then run the exact Sleep/Relaxation scenario once from Step 0 through Step 6. Do not rely only on browser refresh; restarting ensures all process-level caches are clean.
