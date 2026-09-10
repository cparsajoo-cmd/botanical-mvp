"""Regression tests for Problem 1's final remaining defect: PubMed
candidate-intervention attribution false positives.

ROOT CAUSE: verify_pubmed_intervention_attribution() previously kept a
whole sentence whenever it contained ANY administration cue, then checked
whether the candidate's name appeared anywhere in that sentence --
"administration word somewhere + botanical name somewhere" is not
sufficient (discontinuation, baseline/concomitant use, pre-enrollment
history all still put both in one sentence without the botanical being
the study's own administered intervention).

FIX: a bounded, general, deterministic LOCAL RELATION check (see
candidate_attribution._has_local_intervention_relation) -- the candidate's
name must sit immediately adjacent (only closed-class connector/dosage
tokens allowed in between) to one of a small set of administration
constructions, and is disqualified by a pluperfect auxiliary ("had"), an
aggregate/review-level subject ("trials", "studies", ...), or a trailing
exclusion verb ("were excluded"). None of these disqualifiers are
botanical- or indication-specific, so this generalizes to novel negation/
history/concomitant-use phrasing without an ever-growing blacklist.

Fictional botanicals/indications are used throughout.
"""
import candidate_attribution as ca


# =======================================================================
# Required regression tests A-H
# =======================================================================

def test_a_genuine_intervention_verifies():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants received Ficticus alpinum extract 300 mg daily.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True


def test_b_genuine_passive_intervention_verifies():
    result = ca.verify_pubmed_intervention_attribution(
        "Ficticus alpinum extract was administered twice daily.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True


def test_c_discontinuation_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants received placebo after discontinuing Ficticus alpinum extract.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_d_baseline_concomitant_use_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants using Ficticus alpinum at baseline received CBT during the trial.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_e_allowed_concomitant_use_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants receiving concomitant Ficticus alpinum were allowed; "
        "all subjects received CBT.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_f_pre_enrollment_historical_exposure_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "The control group had received Ficticus alpinum before enrollment "
        "but received placebo during the study.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_g_unrelated_administration_in_same_sentence_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Ficticus alpinum was recorded in medication history and "
        "participants received placebo.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_h_direct_randomized_arm_verifies():
    result = ca.verify_pubmed_intervention_attribution(
        "Participants were randomized to Ficticus alpinum extract or placebo.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True


# =======================================================================
# Additional true positives named in the cahier
# =======================================================================

def test_direct_passive_treated_with_verifies():
    result = ca.verify_pubmed_intervention_attribution(
        "The intervention group was treated with Ficticus alpinum.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is True


def test_additional_false_positive_named_examples_do_not_verify():
    for text in (
        "Participants received placebo after discontinuing Ficticus alpinum.",
        "Participants using Ficticus alpinum at baseline received CBT.",
        "Participants were asked about previous Ficticus alpinum use and received placebo.",
        "Ficticus alpinum was discussed with participants who received CBT.",
    ):
        result = ca.verify_pubmed_intervention_attribution(text, scientific_name="Ficticus alpinum")
        assert result["verified"] is False, text


# =======================================================================
# Review/meta-analysis overclaiming guard
# =======================================================================

def test_review_aggregate_subject_does_not_verify():
    result = ca.verify_pubmed_intervention_attribution(
        "Several trials administered Ficticus alpinum.",
        scientific_name="Ficticus alpinum",
    )
    assert result["verified"] is False


def test_review_aggregate_subject_variants_do_not_verify():
    for text in (
        "Many studies administered Ficticus alpinum in animal models.",
        "Prior reports administered Ficticus alpinum to assess safety.",
    ):
        result = ca.verify_pubmed_intervention_attribution(text, scientific_name="Ficticus alpinum")
        assert result["verified"] is False, text


# =======================================================================
# Adversarial sentence set (22 fictional sentences, one call each,
# covering every category the cahier lists: prior use, concomitant use,
# washout, discontinuation, exclusion, comparator, background literature,
# medication history, eligibility, botanical actually administered,
# botanical randomized arm).
# =======================================================================

ADVERSARIAL_CASES = [
    # -- prior use --
    ("Patients with a documented history of Ficticus alpinum use were "
     "included; all participants received placebo.", False),
    ("Participants who had previously used Ficticus alpinum were "
     "eligible; the study intervention was CBT.", False),
    # -- concomitant use --
    ("Concomitant use of Ficticus alpinum was permitted during the "
     "study; participants received CBT.", False),
    ("Ficticus alpinum was allowed as a concomitant supplement while "
     "participants received placebo.", False),
    # -- washout --
    ("Following a two week washout of Ficticus alpinum, participants "
     "received placebo capsules.", False),
    ("A washout period preceded randomization; Ficticus alpinum users "
     "then received the study drug.", False),
    # -- discontinuation --
    ("Participants discontinued Ficticus alpinum two weeks before "
     "receiving the study intervention.", False),
    ("Ficticus alpinum was stopped at screening and participants "
     "subsequently received CBT.", False),
    # -- exclusion --
    ("Individuals currently taking Ficticus alpinum were excluded from "
     "randomization.", False),
    ("Exclusion criteria included current use of Ficticus alpinum; "
     "eligible participants received placebo.", False),
    # -- comparator --
    ("Participants received CBT, while a separate historical cohort had "
     "used Ficticus alpinum for comparison.", False),
    ("The comparator arm received placebo; Ficticus alpinum was not "
     "part of the study protocol.", False),
    # -- background literature --
    ("Ficticus alpinum has been studied extensively in animal models; "
     "this trial evaluated CBT in humans.", False),
    ("Traditional medicine has long used Ficticus alpinum for sleep; "
     "the present RCT tested melatonin instead.", False),
    # -- medication history --
    ("Baseline medication history included Ficticus alpinum in 12% of "
     "participants who received CBT.", False),
    ("A structured questionnaire recorded prior Ficticus alpinum use "
     "before participants received placebo.", False),
    # -- eligibility --
    ("Eligible participants had no known allergy to Ficticus alpinum "
     "and received the study capsules.", False),
    # -- botanical actually administered (true positives) --
    ("Each participant received 500 mg of Ficticus alpinum extract "
     "before bedtime.", True),
    ("The treatment arm was given Ficticus alpinum capsules for eight "
     "weeks.", True),
    ("Ficticus alpinum was administered orally once daily throughout "
     "the trial.", True),
    # -- botanical randomized arm (true positives) --
    ("Subjects were randomly assigned to Ficticus alpinum or matching "
     "placebo.", True),
    ("Participants were randomised to receive Ficticus alpinum extract "
     "for six weeks.", True),
]


def test_adversarial_sentence_set():
    """Runs all 22 adversarial sentences and reports every mismatch, if
    any, rather than stopping at the first one -- so a single assertion
    failure below shows the complete set of cases that didn't match the
    independently-decided expected value (decided before running, per the
    cahier's instruction not to adjust expectations to make code pass).
    """
    mismatches = []
    for text, expected in ADVERSARIAL_CASES:
        result = ca.verify_pubmed_intervention_attribution(text, scientific_name="Ficticus alpinum")
        if result["verified"] != expected:
            mismatches.append((text, expected, result))
    assert not mismatches, "\n".join(
        f"expected={exp} actual={res} | {text}" for text, exp, res in mismatches
    )
