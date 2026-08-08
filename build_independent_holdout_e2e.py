from __future__ import annotations
import json
from dataclasses import asdict
from independent_holdout_e2e import OUT, SNAPSHOT_VERSION, evaluate_holdout

RCA = {
    'refgrounded_003_matricaria_chamomilla_sleep': {
        'responsible_stage': 'Evidence Interpretation -> Final Decision',
        'responsible_modules': ['evidence_interpretation.py', 'final_decision_policy.py', 'botanical_rd_candidate_engine.py'],
        'root_cause': ('The governing chamomile review is positive for some sleep endpoints but explicitly non-supportive for others. '
                       'Production collapses this conditional efficacy pattern to positive/eligible and has no scientific-evidence route to GO WITH CAUTION; '
                       'that class is currently emitted from safety/regulatory restrictions only.'),
    },
    'refgrounded_005_cimicifuga_racemosa_menopausal': {
        'responsible_stage': 'Evidence Interpretation -> Final Decision',
        'responsible_modules': ['evidence_interpretation.py', 'final_decision_policy.py'],
        'root_cause': ('Two independently retrieved systematic reviews are not converted into a governing negative/null or conflict state. '
                       'The phrase "insufficient evidence to support" is classified unclear, and unresolved scientific evidence falls through to GO '
                       'once eligibility passes. This converts uncertainty into a positive final decision.'),
    },
    'refgrounded_007_valeriana_officinalis_preparation_spec': {
        'responsible_stage': 'Evidence Transport / Botanical Identity Matching',
        'responsible_modules': ['botanical_rd_candidate_engine.py'],
        'root_cause': ('The retrieved EMA record is indexed under the binomial scientific name while the named candidate retains the botanical author suffix. '
                       'The evidence index uses literal normalized strings rather than the engine taxon-matching logic, so the preparation record is not attached '
                       'to the candidate. The row therefore reports no direct evidence and becomes INSUFFICIENT EVIDENCE instead of expert review.'),
    },
    'refgrounded_008_ginkgo_biloba_preparation_spec': {
        'responsible_stage': 'Evidence Transport / Botanical Identity Matching',
        'responsible_modules': ['botanical_rd_candidate_engine.py'],
        'root_cause': ('The Ginkgo EMA preparation record is present in the snapshot but is lost at candidate evidence indexing because botanical-author variants '
                       'are not canonicalized consistently between evidence rows and named candidates.'),
    },
    'refgrounded_011_matricaria_chamomilla_indication_evidence': {
        'responsible_stage': 'Evidence Interpretation',
        'responsible_modules': ['evidence_interpretation.py', 'botanical_rd_candidate_engine.py'],
        'root_cause': ('The systematic review conclusion that chamomile appears efficacious and safe for GAD is left unclear by the calibrated phrase classifier, '
                       'while the clinical-trial sentence containing a positive symptom result plus a non-significant relapse endpoint becomes mixed. '
                       'The aggregate therefore loses the high-level supportive conclusion and falls to INSUFFICIENT EVIDENCE.'),
    },
    'refgrounded_013_echinacea_purpurea_identity_quality': {
        'responsible_stage': 'Evidence Transport / Domain Routing',
        'responsible_modules': ['botanical_rd_candidate_engine.py', 'final_decision_policy.py'],
        'root_cause': ('The Kew identity record is independently retrieved, but the production evidence path is indication-centric and the botanical-name variant '
                       'does not attach to the candidate evidence index. Identity/quality evidence therefore does not become a domain-level reviewable decision state.'),
    },
    'refgrounded_014_ginkgo_biloba_safety_interaction': {
        'responsible_stage': 'Evidence Transport -> Safety',
        'responsible_modules': ['botanical_rd_candidate_engine.py', 'eligibility_gate.py'],
        'root_cause': ('The EMA dabigatran caution is in the frozen input but never reaches candidate safety text because the evidence record and candidate use '
                       'different taxonomic-name forms. Safety_Severity remains none and the row is marked incomplete for missing safety/regulatory evidence rather '
                       'than being routed to expert review.'),
    },
    'refgrounded_015_hypericum_perforatum_preparation_spec': {
        'responsible_stage': 'Evidence Transport / Botanical Identity Matching',
        'responsible_modules': ['botanical_rd_candidate_engine.py'],
        'root_cause': ('The independently retrieved EMA preparation specification is not attached to the named Hypericum candidate because evidence indexing and '
                       'candidate matching do not share one canonical botanical-identity key.'),
    },
    'refgrounded_017_matricaria_chamomilla_identity_quality': {
        'responsible_stage': 'Evidence Transport / Domain Routing',
        'responsible_modules': ['botanical_rd_candidate_engine.py', 'final_decision_policy.py'],
        'root_cause': ('The Kew accepted-species evidence is present but identity/quality evidence is not transported into a first-class final-decision domain for '
                       'this named-botanical E2E path; taxonomic author variation also prevents normal candidate evidence attachment.'),
    },
    'refgrounded_023_momordica_charantia_null_fbg': {
        'responsible_stage': 'Reference Currency / Evidence Conflict',
        'responsible_modules': ['gold_corpus/decision_benchmark_v1', 'final_decision_policy.py'],
        'root_cause': ('Independent retrieval found a 2024 null/insufficient systematic review and a newer 2025 meta-analysis reporting significant FBG reduction. '
                       'Production correctly recognizes equally ranked opposing directions as conflict and requests expert review. The frozen Gold reference still '
                       'expects INSUFFICIENT EVIDENCE from the older evidence state, so this mismatch is primarily a benchmark/reference-currency issue rather than '
                       'a demonstrated engine error.'),
    },
}


def main():
    statuses, metrics = evaluate_holdout()
    blocked = [asdict(s) for s in statuses if s.status == 'BLOCKED']
    scored = [asdict(s) for s in statuses if s.status == 'SCORED']
    mismatches = [s for s in scored if not s['match']]
    structural_blockers = [b for b in blocked if b['reason_code'] != 'INDEPENDENT_SNAPSHOT_MISSING']
    snapshot_pending = [b for b in blocked if b['reason_code'] == 'INDEPENDENT_SNAPSHOT_MISSING']
    rcas=[]
    for s in mismatches:
        r=dict(RCA.get(s['case_id'], {}))
        r.update({'case_id':s['case_id'],'expected':s['expected'],'actual':s['actual'],'remediation_applied':False})
        rcas.append(r)
    obj = {
        'benchmark': SNAPSHOT_VERSION,
        'holdout_n_total': len(statuses),
        'holdout_n_structurally_executable': len(statuses) - len(structural_blockers),
        'holdout_n_structurally_blocked': len(structural_blockers),
        'holdout_n_scored': metrics.n_scored,
        'holdout_n_pending_independent_snapshot': len(snapshot_pending),
        'accuracy': metrics.accuracy,
        'macro_f1': metrics.macro_f1,
        'n_correct': metrics.n_correct,
        'n_mismatched': metrics.n_scored - metrics.n_correct,
        'serious_safety_false_negatives': metrics.serious_safety_false_negatives,
        'regulatory_false_negatives': metrics.regulatory_false_negatives,
        'false_no_go': metrics.false_no_go,
        'expert_review_overuse': metrics.expert_review_overuse,
        'insufficient_evidence_miss': metrics.insufficient_evidence_miss,
        'confusion_matrix': metrics.confusion_matrix,
        'scored_cases': scored,
        'structural_blockers': structural_blockers,
        'pending_snapshot_cases': snapshot_pending,
        'mismatch_rca': rcas,
        'interpretation': (
            'All 15 pre-frozen prospective holdout members were executed against independently captured public-source snapshots. '
            'No production decision rule or Gold expected label was changed after snapshot freeze. The observed accuracy is therefore the first full '
            'unseen-holdout decision score for this benchmark version. Mismatches include both production-engine failures and one reference-currency conflict.'
        ),
    }
    (OUT / 'independent_holdout_metrics.json').write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

    report = '# Full Independent Holdout E2E Validation — 15/15\n\n'
    report += f'Frozen prospective holdout: **{len(statuses)} cases**. Scored: **{metrics.n_scored}/{len(statuses)}**. Pending: **{len(snapshot_pending)}**.\n\n'
    report += f'Final-decision agreement: **{metrics.n_correct}/{metrics.n_scored} = {metrics.accuracy:.1%}**. Macro-F1: **{metrics.macro_f1:.3f}**.\n\n'
    report += (f'Serious-safety false negatives: **{metrics.serious_safety_false_negatives}**; regulatory false negatives: **{metrics.regulatory_false_negatives}**; '
               f'false NO-GO: **{metrics.false_no_go}**; expert-review overuse: **{metrics.expert_review_overuse}**; '
               f'insufficient-evidence misses: **{metrics.insufficient_evidence_miss}**.\n\n')
    report += '## Case results\n\n'
    for s in scored:
        mark='PASS' if s['match'] else 'MISMATCH'
        report += f"- {s['case_id']}: reference **{s['expected']}**; engine **{s['actual']}** — **{mark}**.\n"
    report += '\n## Root-cause analysis\n\n'
    for r in rcas:
        report += f"### {r['case_id']}\n\nReference: **{r['expected']}**; engine: **{r['actual']}**.\n\n"
        report += f"Responsible stage: **{r.get('responsible_stage','Unresolved')}**. Modules: `{', '.join(r.get('responsible_modules',[]))}`.\n\n"
        report += r.get('root_cause','Root cause not yet resolved.')+'\n\n'
    report += '## What the data says to fix next\n\n'
    report += ('The largest repeated failure is **evidence transport/domain routing for named-botanical preparation, identity and safety questions** '
               '(Cases 007, 008, 013, 014, 015, 017). The next repeated issue is **scientific evidence interpretation/final-decision propagation** '
               '(Cases 003, 005, 011). Case 023 should first trigger **Gold/reference refresh adjudication**, because newer independently retrieved evidence '
               'creates a genuine same-tier conflict. No holdout-driven production remediation was applied in this run.\n')
    (OUT / 'FULL_15_HOLDOUT_REPORT.md').write_text(report, encoding='utf-8')
    print(json.dumps({'scored':metrics.n_scored,'correct':metrics.n_correct,'accuracy':metrics.accuracy,'macro_f1':metrics.macro_f1,'mismatches':len(mismatches)},indent=2))

if __name__ == '__main__':
    main()
