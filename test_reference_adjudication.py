from final_decision_policy import FinalDecisionStatus
from reference_adjudication import adjudicated_final_decision, adjudication_record


def test_case_005_is_adjudicated_to_expert_review():
    cid = "refgrounded_005_cimicifuga_racemosa_menopausal"
    assert adjudicated_final_decision(cid) == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
    r = adjudication_record(cid)
    assert "PMID:22972105" in r["sources"]
    assert "PMID:37192826" in r["sources"]
    assert "PMID:41401209" in r["sources"]


def test_case_023_is_adjudicated_to_expert_review():
    cid = "refgrounded_023_momordica_charantia_null_fbg"
    assert adjudicated_final_decision(cid) == FinalDecisionStatus.EXPERT_REVIEW_REQUIRED
    r = adjudication_record(cid)
    assert "PMID:38274207" in r["sources"]
    assert "PMID:41280283" in r["sources"]


def test_unadjudicated_case_has_no_overlay():
    assert adjudicated_final_decision("refgrounded_001_melissa_officinalis_sleep") is None
