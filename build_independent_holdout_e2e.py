from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from independent_holdout_e2e import OUT, SNAPSHOT_VERSION, evaluate_holdout


def main():
    statuses, metrics = evaluate_holdout()
    blockers = [asdict(s) for s in statuses if s.status == 'BLOCKED']
    scored = [asdict(s) for s in statuses if s.status == 'SCORED']
    mismatches = [s for s in scored if not s['match']]
    obj = {
        'benchmark': SNAPSHOT_VERSION,
        'holdout_n_total': len(statuses),
        'holdout_n_scored': metrics.n_scored,
        'holdout_n_blocked': len(blockers),
        'accuracy_on_executable_scored_subset': metrics.accuracy,
        'macro_f1_on_executable_scored_subset': metrics.macro_f1,
        'serious_safety_false_negatives': metrics.serious_safety_false_negatives,
        'regulatory_false_negatives': metrics.regulatory_false_negatives,
        'false_no_go': metrics.false_no_go,
        'expert_review_overuse': metrics.expert_review_overuse,
        'insufficient_evidence_miss': metrics.insufficient_evidence_miss,
        'confusion_matrix': metrics.confusion_matrix,
        'scored_cases': scored,
        'blocked_cases': blockers,
        'mismatch_rca': [{
            'case_id': 'refgrounded_003_matricaria_chamomilla_sleep',
            'expected': 'GO WITH CAUTION',
            'actual': 'GO',
            'responsible_stage': 'Evidence Interpretation -> Final Decision',
            'responsible_modules': ['evidence_interpretation.py', 'final_decision_policy.py', 'botanical_rd_candidate_engine.py'],
            'root_cause': (
                'The independently retrieved governing systematic review is mixed/conditional across sleep endpoints. '
                'The current six-class production policy has no scientific-evidence path from a single conditional/mixed supportive source to GO WITH CAUTION: '
                'GO WITH CAUTION is emitted only for ELIGIBLE_WITH_RESTRICTIONS (safety/regulatory restriction). '
                'Accordingly this scientific caveat is lost and the eligible candidate falls through to GO.'
            ),
            'remediation_applied': False,
        }] if mismatches else [],
        'interpretation': (
            'This is the first leakage-controlled prospective holdout result. Accuracy is conditional on the executable/scored subset only; '
            'it must not be reported as 15-case accuracy because 13 cases are structurally blocked by the current question/candidate-discovery path.'
        ),
    }
    (OUT / 'independent_holdout_metrics.json').write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    report = "# Independent Holdout E2E Validation v1.0\n\n"
    report += f"Total prospective holdout cases: **{len(statuses)}**. Scored without GoldCase evidence injection: **{metrics.n_scored}**. Structurally blocked: **{len(blockers)}**.\n\n"
    if metrics.accuracy is not None:
        report += f"Executable-subset agreement: **{metrics.n_correct}/{metrics.n_scored} = {metrics.accuracy:.1%}**; Macro-F1: **{metrics.macro_f1:.3f}**.\n\n"
    report += "## Scored cases\n\n"
    for s in scored:
        report += f"- {s['case_id']}: reference **{s['expected']}**, engine **{s['actual']}**, match={s['match']}.\n"
    report += "\n## Root-cause analysis\n\n"
    if mismatches:
        report += ("**Case 003 (Matricaria chamomilla, sleep):** reference GO WITH CAUTION, engine GO. The independent systematic review carries mixed/conditional efficacy across sleep endpoints, but the current final-decision policy only creates GO WITH CAUTION from safety/regulatory `ELIGIBLE_WITH_RESTRICTIONS`. A scientific conditional-support state therefore falls through to GO. Responsible path: `evidence_interpretation.py` -> `final_decision_policy.py` -> `botanical_rd_candidate_engine.py`. **No remediation was made in this holdout phase.**\n\n")
    report += "## Structural blockers\n\n"
    by_code = {}
    for b in blockers: by_code.setdefault(b['reason_code'], []).append(b['case_id'])
    for code, ids in sorted(by_code.items()):
        report += f"- `{code}` ({len(ids)}): " + ', '.join(ids) + "\n"
    report += ("\nThese blockers are validation findings, not silently imputed inputs. Cases with no indication/dosage-form compatible question are not forced through an indication-driven engine, and cases whose indication is absent from production candidate discovery are not seeded with the Gold botanical.\n\n")
    report += "## Next action based on data\n\nDo **not** tune against this holdout. Preserve this result. The next engineering phase should address the demonstrated architectural blockers on development fixtures: broaden candidate discovery beyond the exact hard-coded indication map and define a domain-appropriate E2E path for preparation/identity/safety cases. Separately, reproduce the Case 003 scientific-caution loss on development data before changing final-decision policy.\n"
    (OUT / 'INDEPENDENT_HOLDOUT_REPORT.md').write_text(report, encoding='utf-8')
    print(json.dumps({'scored': metrics.n_scored, 'blocked': len(blockers), 'accuracy': metrics.accuracy, 'macro_f1': metrics.macro_f1}, indent=2))

if __name__ == '__main__': main()
