from pathlib import Path

from decision_benchmark_v1 import BenchmarkCohort, discover_reference_grounded_cases, split_cases
from independent_holdout_e2e import assess_executability, question_for_case

ROOT = Path(__file__).resolve().parent


def _holdout_cases():
    return split_cases(discover_reference_grounded_cases(ROOT))[BenchmarkCohort.PROSPECTIVE_HOLDOUT]


def test_all_frozen_holdout_members_are_structurally_executable_after_generalization():
    statuses = [assess_executability(case) for case in _holdout_cases()]
    assert len(statuses) == 15
    blocked = [s for s in statuses if s.status != "EXECUTABLE"]
    assert blocked == []


def test_named_botanical_nontherapeutic_case_builds_real_question_without_fake_indication():
    case = next(c for c in _holdout_cases() if not c.validation_unit.indication)
    q = question_for_case(case)
    assert case.validation_unit.taxon in q.question
    assert q.indication in {o.domain.value for o in case.resolved_outcomes}
