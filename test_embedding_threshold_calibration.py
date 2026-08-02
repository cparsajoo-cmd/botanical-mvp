from embedding_threshold_calibration import (
    CalibrationCase,
    evaluate_threshold,
    sweep_thresholds,
    best_threshold_by_f1,
)


def _cases():
    return [
        CalibrationCase("tp1", "q", "r1", True, 0.90),
        CalibrationCase("tp2", "q", "r2", True, 0.75),
        CalibrationCase("fn1", "q", "r3", True, 0.40),   # relevant but low similarity
        CalibrationCase("tn1", "q", "r4", False, 0.20),
        CalibrationCase("fp1", "q", "r5", False, 0.85),  # irrelevant but high similarity
    ]


def test_evaluate_threshold_counts_correctly():
    m = evaluate_threshold(_cases(), threshold=0.7)
    assert m.true_positives == 2   # tp1, tp2
    assert m.false_positives == 1  # fp1
    assert m.true_negatives == 1   # tn1
    assert m.false_negatives == 1  # fn1


def test_precision_recall_computed_correctly():
    m = evaluate_threshold(_cases(), threshold=0.7)
    assert round(m.precision, 3) == round(2 / 3, 3)
    assert round(m.recall, 3) == round(2 / 3, 3)


def test_higher_threshold_lowers_recall_never_raises_it():
    low = evaluate_threshold(_cases(), threshold=0.3)
    high = evaluate_threshold(_cases(), threshold=0.9)
    assert high.recall <= low.recall


def test_sweep_returns_one_result_per_threshold():
    results = sweep_thresholds(_cases(), thresholds=[0.1, 0.5, 0.9])
    assert [r.threshold for r in results] == [0.1, 0.5, 0.9]


def test_best_threshold_by_f1_is_not_the_lowest_threshold_naively():
    """The best-F1 threshold must not degenerate to 0.0 (which would
    trivially maximize recall at the cost of precision) -- proves the
    selection is not choosing a threshold just to pass one example."""
    best = best_threshold_by_f1(_cases())
    assert best.threshold > 0.0
    assert best.precision > 0.0
