
from eligibility_gate import classify_regulatory_finding, evaluate_eligibility, EligibilityStatus

def _finding(status):
    return classify_regulatory_finding(
        barrier_types=frozenset(),
        has_evidence_text=True,
        same_plant=True,
        finding_text="Authoritative regulatory record.",
        candidate_dosage_form="oral",
        candidate_context_text="EU food supplement",
        authorization_statuses=(status,),
    )

def test_not_authorized_is_hard_regulatory_no_go():
    f=_finding("not authorized")
    d=evaluate_eligibility(
        __import__("eligibility_gate").classify_safety_finding(
            hit_terms=frozenset(),flagged_terms=frozenset(),
            has_evidence_text=True,same_plant=True
        ),
        f,
    )
    assert d.status == EligibilityStatus.NO_GO_REGULATORY

def test_terminated_authorization_is_hard_regulatory_no_go():
    assert _finding("terminated").status.value == "prohibited"

def test_denied_authorization_is_hard_regulatory_no_go():
    assert _finding("denied").status.value == "prohibited"

def test_pending_authorization_is_not_silently_clear():
    f=_finding("pending")
    assert f.status.value == "restricted"

def test_authorized_status_does_not_create_barrier():
    f=_finding("authorized")
    assert f.status.value == "clear"

def test_unknown_status_does_not_invent_prohibition():
    f=_finding("unknown")
    assert f.status.value == "clear"
