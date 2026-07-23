"""
Production import/dependency integrity smoke test.

WHY THIS EXISTS
Direct response to a confirmed critical bug: .github/legacy-files.txt
listed question_understanding_engine.py as safe to archive while
step_inputs.py was actively importing standardize_project_definition
from it. The static legacy list had gone stale after a later session
wired that file into production and nobody re-validated the list. This
test suite makes that class of bug fail loudly in CI, every run,
instead of silently waiting to be discovered by a broken archive.

WHAT THIS CHECKS (maps directly to the required smoke-test scope)
1. app.py and every direct production module remain import-resolvable
   (attempted for real via importlib; environments missing a
   third-party dependency like streamlit SKIP that specific check
   rather than failing the whole suite for an unrelated reason — see
   _try_import's handling of ModuleNotFoundError).
2. Every module imported by step_inputs.py, step_question.py,
   step_evidence.py, step_rd_candidates.py, and step_import_data.py
   has a corresponding .py file that actually exists (pure static
   check, always runs, no dependencies needed).
3. .github/legacy-files.txt contains zero production-active files —
   the core safety property this whole test file exists to guard.
4. A simulated archive operation (moving every currently-listed legacy
   file out of the root) would not remove anything step_inputs.py,
   step_question.py, step_evidence.py, step_rd_candidates.py, or
   step_import_data.py — or anything THEY transitively depend on —
   actually needs.
"""

import importlib
import os

import repo_dependency_audit as audit

STEP_FILES = [
    "step_inputs.py",
    "step_question.py",
    "step_evidence.py",
    "step_rd_candidates.py",
    "step_import_data.py",
]


def _known_modules():
    return {f[:-3] for f in os.listdir(".") if f.endswith(".py")}


def test_every_module_imported_by_the_five_step_files_exists_on_disk():
    modules = _known_modules()
    missing = []
    for step_file in STEP_FILES:
        assert os.path.isfile(step_file), f"{step_file} itself does not exist"
        imported = audit.local_imports_of(step_file, modules)
        for mod in imported:
            if not os.path.isfile(f"{mod}.py"):
                missing.append(f"{step_file} imports {mod!r} but {mod}.py does not exist")
    assert not missing, "\n".join(missing)


def test_legacy_list_contains_no_production_active_files():
    """The core check this whole file exists for — directly catches
    the question_understanding_engine.py class of bug."""
    errors = audit.validate_legacy_list(".github/legacy-files.txt", ".")
    assert errors == [], (
        "legacy-files.txt is UNSAFE — it lists file(s) that are actually "
        "reachable from production:\n" + "\n".join(errors)
    )


def test_archiving_the_current_legacy_list_would_not_remove_a_step_dependency():
    """Simulates what archive-legacy.yml's move step would do, and
    confirms none of the five Step files (or anything they transitively
    import) would lose a real file out from under them."""
    modules = _known_modules()
    legacy_entries = [
        line.strip()[:-3] for line in open(".github/legacy-files.txt") if line.strip()
    ]
    legacy_set = set(legacy_entries)

    # Build the FULL transitive closure of what the 5 Step files need,
    # not just their direct imports — a Step file could import module A,
    # which imports module B, and B being (wrongly) listed as legacy
    # would be just as much a production-breaking move as A being
    # listed would be.
    needed = set()
    queue = []
    for step_file in STEP_FILES:
        queue.extend(audit.local_imports_of(step_file, modules))
    while queue:
        m = queue.pop()
        if m in needed:
            continue
        needed.add(m)
        if os.path.isfile(f"{m}.py"):
            queue.extend(audit.local_imports_of(f"{m}.py", modules))

    conflict = sorted(needed & legacy_set)
    assert not conflict, (
        f"Archiving the current legacy-files.txt would remove a module the "
        f"Step files transitively depend on: {conflict}"
    )


def _try_import(module_name):
    """Attempts a real import. Returns (ok, reason). A ModuleNotFoundError
    for a THIRD-PARTY package (not one of our own local .py files) means
    this environment simply doesn't have dependencies installed
    (e.g. no streamlit in a minimal sandbox) — that's an environment
    limitation, not a repository integrity bug, so it's reported as
    "skipped" rather than failed. A ModuleNotFoundError naming one of
    OUR OWN local modules is a real integrity failure."""
    local_modules = _known_modules()
    try:
        importlib.import_module(module_name)
        return True, None
    except ModuleNotFoundError as exc:
        missing_name = (exc.name or "").split(".")[0]
        if missing_name in local_modules:
            return False, f"missing LOCAL module {missing_name!r} — real integrity failure"
        return None, f"third-party dependency {missing_name!r} not installed in this environment"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def test_app_py_and_direct_production_modules_are_import_resolvable():
    """Best-effort REAL import attempt (not just static file-existence)
    for app.py and its direct imports. Distinguishes "this sandbox
    doesn't have streamlit installed" (skipped, not a bug) from "one of
    our own modules can't be imported" (a real failure)."""
    modules = _known_modules()
    direct_targets = ["app"] + sorted(audit.local_imports_of("app.py", modules))

    real_failures = []
    skipped = []
    for mod in direct_targets:
        ok, reason = _try_import(mod)
        if ok is False:
            real_failures.append(f"{mod}: {reason}")
        elif ok is None:
            skipped.append(f"{mod}: {reason}")

    if skipped:
        print(f"\n[skipped, third-party deps not installed here]: {skipped}")

    assert not real_failures, "\n".join(real_failures)


if __name__ == "__main__":
    import sys

    try:
        import pytest
        sys.exit(pytest.main([__file__, "-v"]))
    except ImportError:
        this_module = sys.modules[__name__]
        test_fns = [
            getattr(this_module, name)
            for name in dir(this_module)
            if name.startswith("test_") and callable(getattr(this_module, name))
        ]
        passed, failed = [], []
        for fn in test_fns:
            try:
                fn()
            except AssertionError as exc:
                failed.append((fn.__name__, str(exc) or "assertion failed"))
            except Exception as exc:  # noqa: BLE001
                failed.append((fn.__name__, f"{type(exc).__name__}: {exc}"))
            else:
                passed.append(fn.__name__)
        print(f"\n{len(passed) + len(failed)} test(s) run.\n")
        for name in passed:
            print(f"  \u2705 {name}")
        if failed:
            print()
            for name, reason in failed:
                print(f"  \u274c {name}\n     -> {reason}")
            print(f"\n{len(failed)} FAILED, {len(passed)} passed.\n")
            sys.exit(1)
        print(f"\nALL TESTS PASSED ({len(passed)}/{len(passed)}).\n")
        sys.exit(0)
