from __future__ import annotations
import json
from dataclasses import asdict
from independent_holdout_e2e import OUT, SNAPSHOT_VERSION, evaluate_holdout


def main():
    statuses, metrics = evaluate_holdout()
    blocked = [asdict(s) for s in statuses if s.status == 'BLOCKED']
    scored = [asdict(s) for s in statuses if s.status == 'SCORED']
    mismatches = [s for s in scored if not s['match']]
    structural_blockers = [b for b in blocked if b['reason_code'] != 'INDEPENDENT_SNAPSHOT_MISSING']
    snapshot_pending = [b for b in blocked if b['reason_code'] == 'INDEPENDENT_SNAPSHOT_MISSING']
    obj = {
        'benchmark': SNAPSHOT_VERSION,
        'holdout_n_total': len(statuses),
        'holdout_n_structurally_executable': len(statuses) - len(structural_blockers),
        'holdout_n_structurally_blocked': len(structural_blockers),
        'holdout_n_scored': metrics.n_scored,
        'holdout_n_pending_independent_snapshot': len(snapshot_pending),
        'accuracy_on_scored_subset': metrics.accuracy,
        'macro_f1_on_scored_subset': metrics.macro_f1,
        'serious_safety_false_negatives': metrics.serious_safety_false_negatives,
        'regulatory_false_negatives': metrics.regulatory_false_negatives,
        'false_no_go': metrics.false_no_go,
        'expert_review_overuse': metrics.expert_review_overuse,
        'insufficient_evidence_miss': metrics.insufficient_evidence_miss,
        'confusion_matrix': metrics.confusion_matrix,
        'scored_cases': scored,
        'structural_blockers': structural_blockers,
        'pending_snapshot_cases': snapshot_pending,
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
            'All 15 frozen holdout members are now structurally executable without Gold evidence injection. '
            'Only two have independently captured frozen retrieval snapshots, so accuracy remains conditional on those two scored cases. '
            'The remaining 13 are pending independent snapshot capture, not blocked by question schema or candidate discovery.'
        ),
    }
    (OUT / 'independent_holdout_metrics.json').write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    report = "# Independent Holdout E2E Validation v1.1 — Structural Blocker Remediation\n\n"
    report += f"Total prospective holdout cases: **{len(statuses)}**. Structurally executable without Gold evidence injection: **{len(statuses)-len(structural_blockers)}/{len(statuses)}**. Structurally blocked: **{len(structural_blockers)}**.\n\n"
    report += f"Cases with frozen independent retrieval snapshots and therefore currently scorable: **{metrics.n_scored}**. Pending independent snapshot capture: **{len(snapshot_pending)}**.\n\n"
    if metrics.accuracy is not None:
        report += f"Frozen scored-subset agreement remains **{metrics.n_correct}/{metrics.n_scored} = {metrics.accuracy:.1%}**; Macro-F1: **{metrics.macro_f1:.3f}**. This score was not changed or re-labelled during blocker remediation.\n\n"

    report += "## What changed\n\n"
    report += "- Candidate discovery no longer requires an exact key in the six-entry legacy map. It uses the existing therapeutic-area registry, global candidate database, and bounded related-concept hypotheses; these are search hypotheses only, never evidence.\n"
    report += "- Free-text clinical wording with non-contiguous terms (for example fasting/blood/glucose wording) can resolve to an existing therapeutic family through conservative >=2-token overlap.\n"
    report += "- Non-therapeutic identity, preparation, and safety validation cases now use a named-botanical question path. The botanical is explicit question input for those domains, not hidden Gold output. Missing dosage form is no longer fabricated.\n\n"

    report += "## Scored cases (frozen; unchanged)\n\n"
    for s in scored:
        report += f"- {s['case_id']}: reference **{s['expected']}**, engine **{s['actual']}**, match={s['match']}.\n"

    report += "\n## Remaining validation gap\n\n"
    if structural_blockers:
        report += "Structural blockers remain:\n"
        for b in structural_blockers:
            report += f"- {b['case_id']}: `{b['reason_code']}` — {b['reason']}\n"
    else:
        report += "**No question-schema or candidate-discovery structural blockers remain across the 15 frozen holdout members.**\n"
    report += f"\nThe remaining **{len(snapshot_pending)}** unscored cases are waiting only for independently captured retrieval snapshots. They must not be populated from GoldCase reference claims.\n\n"

    report += "## Preserved mismatch\n\n"
    if mismatches:
        report += "Case 003 remains reference `GO WITH CAUTION` vs engine `GO`. No decision-policy remediation was applied in this phase, so the unseen mismatch remains a valid future development target rather than being tuned away on holdout.\n\n"

    report += "## Next action based on data\n\nCapture independent retrieval snapshots for the remaining 13 frozen holdout members using only their question/context inputs, freeze those snapshots, and only then score them. Do not change the holdout membership or expected labels. In parallel, reproduce the Case 003 scientific-caution failure on development fixtures before any production decision-policy change.\n"
    (OUT / 'INDEPENDENT_HOLDOUT_REPORT.md').write_text(report, encoding='utf-8')
    print(json.dumps({
        'structurally_executable': len(statuses)-len(structural_blockers),
        'structurally_blocked': len(structural_blockers),
        'scored': metrics.n_scored,
        'pending_snapshot': len(snapshot_pending),
        'accuracy': metrics.accuracy,
        'macro_f1': metrics.macro_f1,
    }, indent=2))

if __name__ == '__main__':
    main()
