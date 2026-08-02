from general_indication_relevance import build_indication_profile


def test_unseen_indication_learns_related_vocabulary_from_corpus():
    corpus = [
        "Cough treatment with an antitussive herbal preparation.",
        "Patients with cough received an expectorant botanical syrup.",
        "Antitussive activity of Thymus vulgaris in a respiratory model.",
        "Expectorant and secretolytic effects of Glycyrrhiza glabra.",
        "Improved fasting glucose and insulin sensitivity in diabetes.",
    ]
    profile = build_indication_profile("cough", corpus)
    assert profile.match(corpus[2]).score >= 0.20
    assert profile.match(corpus[3]).score >= 0.20
    assert profile.match(corpus[4]).score == 0.0


def test_another_unseen_indication_requires_no_code_change():
    corpus = [
        "Migraine prophylaxis and reduction in headache frequency.",
        "People with migraine had fewer attacks after treatment.",
        "Reduction in headache frequency and aura duration.",
        "Improved sleep latency in insomnia.",
    ]
    profile = build_indication_profile("migraine", corpus)
    assert profile.match(corpus[2]).score >= 0.20
    assert profile.match(corpus[3]).score == 0.0
