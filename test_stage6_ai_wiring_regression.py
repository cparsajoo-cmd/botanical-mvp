import ast
from pathlib import Path
import pandas as pd


def _load_helpers():
    source = Path(__file__).with_name('step_rd_candidates.py').read_text()
    tree = ast.parse(source)
    wanted = {'_resolve_report_plant_column', '_attach_ai_insights_to_report_df'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    module = ast.Module(body=nodes, type_ignores=[])
    ns = {'pd': pd}
    exec(compile(module, '<stage6_helpers>', 'exec'), ns)
    return ns


def test_ai_insights_are_attached_to_authoritative_report_frame():
    ns = _load_helpers()
    df = pd.DataFrame([
        {'Alternative_Plant': 'Melissa officinalis', 'R&D_Opportunity_Score': 70.0},
        {'Alternative_Plant': 'Rhodiola rosea', 'R&D_Opportunity_Score': 50.0},
    ])
    insights = {
        'Melissa officinalis': {
            'evidence_items_count': 4,
            'mechanistic_edges': [{'compound': 'rosmarinic acid'}],
            'evidence_synthesis': {'overall_consistency': 'mostly_consistent', 'summary': 'Human evidence is supportive.'},
            'hypotheses': [{'hypothesis': 'Evaluate standardized infusion.', 'research_next_step': 'Pilot dose-ranging study.'}],
        }
    }
    out = ns['_attach_ai_insights_to_report_df'](df, insights)
    melissa = out.iloc[0]
    rhodiola = out.iloc[1]
    assert melissa['AI_Insight_Status'] == 'AI_REVIEW_AVAILABLE'
    assert melissa['AI_Evidence_Items_Reviewed'] == 4
    assert melissa['AI_Evidence_Consistency'] == 'mostly_consistent'
    assert melissa['AI_Top_Hypothesis'] == 'Evaluate standardized infusion.'
    assert rhodiola['AI_Insight_Status'] == 'AI_REVIEW_UNAVAILABLE'
