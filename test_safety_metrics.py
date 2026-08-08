from safety_metrics import SafetyOutcome, compute_safety_metrics


def test_safety_metrics_all_requested_rates():
    rows = [
        SafetyOutcome(True, True, True, False),
        SafetyOutcome(True, True, False, False),
        SafetyOutcome(False, True, False, False),
        SafetyOutcome(False, False, False, True, False),
    ]
    m = compute_safety_metrics(rows)
    assert m['serious_safety_recall'] == 1.0
    assert round(m['serious_safety_precision'], 6) == round(2/3, 6)
    assert m['false_negative_rate'] == 0.0
    assert round(m['false_positive_rate'], 6) == round(1/2, 6)
    assert m['no_go_recall'] == 0.5
    assert m['no_go_precision'] == 1.0
    assert m['expert_review_rate'] == 0.25
    assert m['unknown_safety_rate'] == 0.25
