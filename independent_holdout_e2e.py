"""Independent prospective-holdout E2E validation.

Validation-only infrastructure. It never mutates production rules and never
uses GoldCase claims to construct engine evidence. Frozen snapshots are inputs
captured independently from public retrieval, and Gold truth is consulted only
*after* snapshot freeze for scoring.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional
import json
import pandas as pd

from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from decision_benchmark_v1 import BenchmarkCohort, compute_metrics, discover_reference_grounded_cases, split_cases
from end_to_end_validation import RetrievedEvidence, ValidationQuestion, _build_plant_df, _norm_taxon
from final_decision_policy import final_status_from_engine_row
from knowledge_retrieval_engine import get_candidate_plants
from scientific_decision_validation import DecisionComparison, derive_reference_final_decision

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'gold_corpus' / 'decision_benchmark_v1'
SNAPSHOT_DIR = OUT / 'independent_holdout_snapshots'
SNAPSHOT_VERSION = 'independent-holdout-e2e/1.2.0'

@dataclass(frozen=True)
class HoldoutExecutionStatus:
    case_id: str
    status: str
    reason_code: str
    reason: str
    candidate_count: int = 0
    snapshot_file: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    match: Optional[bool] = None


def case_number(case_id: str) -> int:
    return int(case_id.split('_', 2)[1])


def _validation_domain(case) -> str:
    outcomes = getattr(case, "resolved_outcomes", None) or []
    if outcomes:
        domain = getattr(outcomes[0], "domain", None)
        value = getattr(domain, "value", None)
        if value:
            return str(value)
    return "Botanical scientific assessment"


def question_for_case(case) -> ValidationQuestion:
    """Build an executable scientific question without inventing Gold truth.

    Therapeutic cases use their indication. Preparation/identity/safety cases
    are *named-botanical* questions by definition, so the botanical identity
    is legitimate question input rather than a discovered expected answer.
    Missing dosage form is represented as an empty string, which the production
    engine already supports.
    """
    u = case.validation_unit
    dosage = u.preparation.dosage_form if u.preparation else ""
    indication = u.indication or _validation_domain(case)
    return ValidationQuestion(
        question=f'What is the scientific decision for {u.taxon} for {indication}' +
                 (f' as {dosage}' if dosage else '') +
                 f' in {u.jurisdiction or "unspecified market"}?',
        indication=indication,
        dosage_form=dosage,
        market=u.jurisdiction or '',
    )


def _candidate_pool_for_case(case, q: ValidationQuestion) -> list[str]:
    # For therapeutic discovery, candidate identity must come from production
    # discovery. For a non-therapeutic named-botanical validation question
    # (identity, preparation, safety), the botanical is explicitly the subject
    # of the question and therefore is not hidden Gold output.
    if case.validation_unit.indication:
        return list(dict.fromkeys(get_candidate_plants(q.indication) or []))
    return [case.validation_unit.taxon]


def assess_executability(case) -> HoldoutExecutionStatus:
    q = question_for_case(case)
    candidates = _candidate_pool_for_case(case, q)
    if not candidates:
        return HoldoutExecutionStatus(
            case.case_id, 'BLOCKED', 'CANDIDATE_DISCOVERY_ZERO_CANDIDATES',
            f'Production default candidate discovery returned no candidates for indication {q.indication!r}.', 0
        )
    gold_norm = _norm_taxon(case.validation_unit.taxon)
    if gold_norm not in {_norm_taxon(c) for c in candidates}:
        return HoldoutExecutionStatus(
            case.case_id, 'BLOCKED', 'GOLD_CANDIDATE_NOT_DISCOVERED',
            'Production default candidate discovery returned candidates, but not the reference botanical.', len(candidates)
        )
    reason = ('Named-botanical non-therapeutic validation can execute without candidate discovery.'
              if not case.validation_unit.indication else
              'Candidate discovery can execute without GoldCase injection.')
    return HoldoutExecutionStatus(case.case_id, 'EXECUTABLE', 'READY', reason, len(candidates))


def load_snapshot(case_number_: int) -> dict:
    return json.loads((SNAPSHOT_DIR / f'case_{case_number_:03d}_independent.json').read_text(encoding='utf-8'))


def run_snapshot(case, snapshot: dict):
    q = ValidationQuestion(**snapshot['question'])
    candidates = list(snapshot['candidate_pool'])
    records = [RetrievedEvidence(**r) for r in snapshot['records']]
    evidence_df = pd.DataFrame([r.to_engine_row(q.indication, q.dosage_form, q.market) for r in records])
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=_build_plant_df(candidates, q.indication),
        compound_profiles_df=pd.DataFrame(), scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df, use_live_search=False,
        # These exposed frozen snapshots were captured before canonical
        # structured directions were populated.  Preserve them as regression
        # fixtures via an explicit legacy-mode opt-in; production remains
        # fail-safe by default (False).
        allow_legacy_text_fallback=True,
    )
    output = engine.run(indication=q.indication, dosage_form=q.dosage_form, market=q.market)
    target = _norm_taxon(case.validation_unit.taxon)
    rows = output[output['Alternative_Plant'].map(_norm_taxon) == target]
    if rows.empty:
        raise RuntimeError(f'{case.case_id}: expected candidate disappeared during engine execution')
    row = rows.iloc[0]
    return final_status_from_engine_row(row), row


def evaluate_holdout():
    cases = split_cases(discover_reference_grounded_cases(ROOT))[BenchmarkCohort.PROSPECTIVE_HOLDOUT]
    statuses = []
    comparisons = []
    for case in cases:
        base = assess_executability(case)
        if base.status != 'EXECUTABLE':
            statuses.append(base)
            continue
        snap_path = SNAPSHOT_DIR / f'case_{case_number(case.case_id):03d}_independent.json'
        if not snap_path.exists():
            statuses.append(HoldoutExecutionStatus(
                case.case_id, 'BLOCKED', 'INDEPENDENT_SNAPSHOT_MISSING',
                'Case is structurally executable, but no independently captured frozen retrieval snapshot is present.',
                base.candidate_count,
            ))
            continue
        actual, _ = run_snapshot(case, json.loads(snap_path.read_text(encoding='utf-8')))
        expected = derive_reference_final_decision(case)
        match = actual == expected
        comparisons.append(DecisionComparison(case.case_id, expected, actual, match))
        statuses.append(HoldoutExecutionStatus(
            case.case_id, 'SCORED', 'OK' if match else 'FINAL_DECISION_MISMATCH',
            'Frozen independent snapshot executed successfully.', base.candidate_count,
            str(snap_path.relative_to(ROOT)), expected.value, actual.value, match,
        ))
    return statuses, compute_metrics(comparisons)
