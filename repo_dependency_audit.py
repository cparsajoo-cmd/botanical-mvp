"""
repo_dependency_audit.py — repository dependency-integrity tool.

WHY THIS EXISTS (critical bug this tool is a direct response to)
.github/legacy-files.txt was a STATIC snapshot, generated once (Phase
1/7) by a one-off script and hand-copied into a text file. When
question_understanding_engine.py was later wired into step_inputs.py
(a subsequent session), nobody re-ran that snapshot — the text file
just went stale. The result: legacy-files.txt claimed
question_understanding_engine.py was safe to archive while step_inputs.py
was actively importing standardize_project_definition from it. Had
archive-legacy.yml been run in that state, it would have moved a live
production dependency into archive/ and broken the app.

The fix is not "regenerate the snapshot once more" (that just
recreates the same staleness risk the next time a file gets wired in)
— it's making the computation a real, reusable, re-runnable TOOL that
both a human and archive-legacy.yml itself can call fresh every time,
so the check is never trusting a stale file again.

WHAT THIS IS NOT
Not a new engine, not part of the R&D decision pipeline, not imported
by app.py or any Step file. This is a repository/dev-tooling utility,
the same category as scoring_sensitivity_report.py — run manually or
from CI, never from the running app.

HOW THE GRAPH IS COMPUTED
Entry points: app.py, plus every file under pages/ (each pages/*.py is
independently loaded by Streamlit, not imported by app.py, so each is
its own root). From those roots, local imports are followed
recursively via regex over `from X import ...` / `import X` lines.
The regex matches ANY indentation level (`^[ \\t]*from...`), so an
import inside a try/except block, inside a function, or inside an
if-statement is caught exactly the same as a top-level import — the
bug this tool exists to catch was never about try/except imports being
missed by this kind of check; it was about the check never being
RE-RUN after the codebase changed.

Dynamic imports (importlib.import_module(...), __import__(...)) canNOT
be resolved by this kind of static analysis, since the module name may
only exist as a runtime string/variable — find_dynamic_import_usage()
flags every occurrence for manual review rather than silently missing
them.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

_IMPORT_FROM_RE = re.compile(r'^[ \t]*from\s+([\w\.]+)\s+import', re.M)
_IMPORT_RE = re.compile(r'^[ \t]*import\s+([\w\.]+)', re.M)
_DYNAMIC_IMPORT_PATTERNS = [r'importlib\.import_module\(', r'__import__\(']


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def local_imports_of(path: str, known_modules: set) -> set:
    """Every locally-defined module (i.e. a name in known_modules)
    imported by the file at `path`, at any indentation level —
    catches imports inside try/except, functions, and conditionals,
    not just top-level statements."""
    text = _read(path)
    found = set()
    for m in _IMPORT_FROM_RE.finditer(text):
        found.add(m.group(1).split(".")[0])
    for m in _IMPORT_RE.finditer(text):
        found.add(m.group(1).split(".")[0])
    return found & known_modules


def find_dynamic_import_usage(root: str = ".") -> list:
    """Returns [(path, line_no, line_text), ...] for every
    importlib.import_module(...)/__import__(...) call found under
    `root` (top-level .py files and pages/*.py) — these need manual
    review since this tool's static analysis cannot resolve what
    module they actually load at runtime.

    Excludes this file itself (repo_dependency_audit.py) — its own
    docstrings and comments necessarily mention these exact function
    names to explain what the check does, which the naive pattern
    match below would otherwise flag as a false positive against
    itself."""
    hits = []
    self_name = os.path.basename(__file__)
    candidates = [f for f in os.listdir(root) if f.endswith(".py") and f != self_name]
    pages_dir = os.path.join(root, "pages")
    if os.path.isdir(pages_dir):
        candidates += [os.path.join("pages", f) for f in os.listdir(pages_dir) if f.endswith(".py")]

    for rel in candidates:
        path = os.path.join(root, rel) if not rel.startswith("pages") else os.path.join(root, rel)
        text = _read(path)
        if not text:
            continue
        for pattern in _DYNAMIC_IMPORT_PATTERNS:
            for m in re.finditer(pattern, text):
                line_no = text[: m.start()].count("\n") + 1
                line_text = text.splitlines()[line_no - 1].strip()
                hits.append((rel, line_no, line_text))
    return hits


@dataclass
class DependencySets:
    production_active: set = field(default_factory=set)  # reachable from app.py or pages/*
    test_only: set = field(default_factory=set)           # test_*.py, not reachable from production
    legacy_candidates: set = field(default_factory=set)    # neither production-active nor test-only
    entry_points: list = field(default_factory=list)       # what seeded the reachability walk


def compute_dependency_sets(root: str = ".") -> DependencySets:
    """The core computation: what's actually reachable from app.py and
    every pages/*.py file, walked recursively through local imports."""
    py_files = sorted(f for f in os.listdir(root) if f.endswith(".py"))
    modules = {f[:-3] for f in py_files}
    pages_dir = os.path.join(root, "pages")
    page_files = sorted(f for f in os.listdir(pages_dir) if f.endswith(".py")) if os.path.isdir(pages_dir) else []

    graph = {f[:-3]: local_imports_of(os.path.join(root, f), modules) for f in py_files}

    entry_points = ["app"] if "app" in modules else []
    for pf in page_files:
        entry_points.extend(sorted(local_imports_of(os.path.join(pages_dir, pf), modules)))
    entry_points = list(dict.fromkeys(entry_points))  # de-dupe, keep order

    visited = set()
    queue = list(entry_points)
    while queue:
        m = queue.pop()
        if m in visited:
            continue
        visited.add(m)
        for dep in graph.get(m, ()):
            if dep not in visited:
                queue.append(dep)

    test_files = {f for f in modules if f.startswith("test_")}
    production_active = visited
    test_only = test_files - production_active
    legacy_candidates = modules - production_active - test_only

    return DependencySets(
        production_active=production_active,
        test_only=test_only,
        legacy_candidates=legacy_candidates,
        entry_points=entry_points,
    )


def validate_legacy_list(legacy_file_path: str = ".github/legacy-files.txt", root: str = ".") -> list:
    """THE core safety check. Returns a list of human-readable error
    strings — empty means the legacy list is safe to act on. Never
    raises; a missing legacy file or unreadable entry is itself
    reported as an error string, not an exception."""
    errors = []
    full_path = os.path.join(root, legacy_file_path)
    if not os.path.isfile(full_path):
        return [f"Legacy file list not found at {legacy_file_path}"]

    entries = [line.strip() for line in _read(full_path).splitlines() if line.strip()]
    entry_modnames = {(e[:-3] if e.endswith(".py") else e): e for e in entries}

    sets = compute_dependency_sets(root)

    unsafe = sorted(set(entry_modnames) & sets.production_active)
    for modname in unsafe:
        errors.append(
            f"{entry_modnames[modname]} is listed as legacy/safe-to-archive but is "
            f"REACHABLE FROM PRODUCTION (app.py / pages/* import chain) — archiving "
            f"it would break the running app. Remove it from the legacy list."
        )

    return errors


if __name__ == "__main__":
    root = sys.argv[2] if len(sys.argv) > 2 else "."
    command = sys.argv[1] if len(sys.argv) > 1 else "validate"

    if command == "validate":
        legacy_path = sys.argv[3] if len(sys.argv) > 3 else ".github/legacy-files.txt"
        errors = validate_legacy_list(legacy_path, root)
        dynamic_hits = find_dynamic_import_usage(root)
        if dynamic_hits:
            print(f"NOTE: {len(dynamic_hits)} dynamic import call(s) found — not resolvable by "
                  f"static analysis, review manually:")
            for path, line_no, line_text in dynamic_hits:
                print(f"  {path}:{line_no}: {line_text}")
        if errors:
            print(f"\nUNSAFE: {len(errors)} legacy-list entr{'y is' if len(errors) == 1 else 'ies are'} "
                  f"actually production-active:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print("OK: legacy list contains no production-active files.")
        sys.exit(0)

    elif command == "summary":
        sets = compute_dependency_sets(root)
        print(f"Production-active: {len(sets.production_active)}")
        print(f"Test-only: {len(sets.test_only)}")
        print(f"Legacy candidates (neither): {len(sets.legacy_candidates)}")
        sys.exit(0)

    else:
        print(f"Unknown command: {command!r}. Use 'validate' or 'summary'.")
        sys.exit(2)
