"""conftest.py — gold_cases/

Purpose: this folder was separated from the repository root on 2026-08-03
so that Gold Case files, their dedicated tests, and their case-specific
reports/records live together, apart from the production platform body
(app.py, pages/, step_*.py, botanical_rd_candidate_engine.py) and apart
from the shared validation FRAMEWORK modules (gold_case.py,
applicability_check.py, assertion_vocabulary.py, reference_claim.py,
reference_descriptor.py, validation_unit.py, field_provenance.py,
agreement_eligibility.py, evaluation_run.py, reference_precedence.py,
user_roles.py, etc.), which remain at the repository root because future
Gold Cases will keep importing them too.

Every gold_case_reference_grounded_*.py and test_case_*.py file imports
those shared root-level framework modules with bare imports like
`from applicability_check import ReferenceDomain` (no explicit sys.path
manipulation of their own, relying instead on pytest's default "prepend"
import mode, which historically worked because these files all lived in
the repository root alongside the modules they import).

This conftest.py is pytest's standard mechanism for exactly this
situation: pytest auto-loads every conftest.py in a collected test's
directory (and parent directories) BEFORE importing the test module
itself. Inserting the repository root here — once — means every file in
this folder keeps resolving its existing bare imports exactly as before,
with no changes needed to any individual case or test file's own import
statements.

Do not remove this file. Removing it will break every test in this
folder with `ModuleNotFoundError` for whichever root-level module it
imports first (typically applicability_check or assertion_vocabulary).
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
