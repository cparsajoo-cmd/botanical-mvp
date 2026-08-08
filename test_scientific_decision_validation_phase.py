from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from gold_corpus.e2e_snapshot_pilot import PILOT_CASE_NUMBERS, load_gold_case, load_snapshot, snapshot_question, snapshot_records, frozen_candidate_discovery
from end_to_end_validation import _build_plant_df
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine
from scientific_decision_validation import derive_reference_final_decision
import pandas as pd

EXPECTED = {
    6: FinalDecisionStatus.NO_GO_SAFETY,
    16: FinalDecisionStatus.NO_GO_REGULATORY,
    18: FinalDecisionStatus.GO_WITH_CAUTION,
    19: FinalDecisionStatus.GO,
    20: FinalDecisionStatus.GO,
    21: FinalDecisionStatus.EXPERT_REVIEW_REQUIRED,
    22: FinalDecisionStatus.INSUFFICIENT_EVIDENCE,
}


def _engine_status(n):
    s = load_snapshot(n); q = snapshot_question(s); recs = snapshot_records(s)
    candidates = frozen_candidate_discovery(s)(q)
    evidence_df = pd.DataFrame([r.to_engine_row(q.indication, q.dosage_form, q.market) for r in recs])
    engine = BotanicalRDCandidateEngine(
        plant_compounds_df=_build_plant_df(candidates, q.indication),
        compound_profiles_df=pd.DataFrame(), scientific_evidence_df=pd.DataFrame(),
        evidence_df=evidence_df, use_live_search=False,
    )
    output = engine.run(indication=q.indication, dosage_form=q.dosage_form, market=q.market)
    target = load_gold_case(n).validation_unit.taxon.lower().split()[0]
    row = output[output["Alternative_Plant"].str.lower().str.startswith(target)].iloc[0]
    return final_status_from_engine_row(row), row


def test_reference_mapping_is_case_id_independent_and_matches_curated_outcomes():
    for n in PILOT_CASE_NUMBERS:
        assert derive_reference_final_decision(load_gold_case(n)) == EXPECTED[n]


def test_frozen_pilot_final_decision_agreement_after_root_cause_remediation():
    for n in PILOT_CASE_NUMBERS:
        actual, _ = _engine_status(n)
        assert actual == EXPECTED[n]


def test_hard_no_go_and_abstention_partitions_are_non_normal():
    for n in (6, 16, 21, 22):
        _, row = _engine_status(n)
        assert row["Ranking_Partition"] != "normal"
        assert bool(row["Eligible_For_Normal_Ranking"]) is False
