"""Validates the SECTION-PARSING LOGIC in ema_monograph_connector.py
against real monograph text.

IMPORTANT LIMITATION, STATED UP FRONT: this test does NOT exercise the
live HTTP fetch (_fetch_pdf_text against a real ema.europa.eu URL).
The sandbox this connector was developed in does not have network
access to ema.europa.eu, so the live-fetch path is untested end-to-end
by this engineer. What IS tested below is the parsing logic itself,
against the real, verbatim text of the actual final Melissa officinalis
monograph (EMA/HMPC/196745/2012) — the same text independently fetched
and read during this project's research phase, pasted here as a fixture
rather than re-fetched. Before this connector runs in production, a
real end-to-end fetch against a live URL should be run once and its
output checked by a human — this test is not a substitute for that.
"""

from ema_monograph_connector import (
    _split_clinical_sections,
    _detect_weu_status,
)

# Verbatim text of the real Melissa officinalis monograph's clinical
# sections (4.1-4.9), as fetched from
# https://www.ema.europa.eu/en/documents/herbal-monograph/
# final-community-herbal-monograph-melissa-officinalis-l-folium_en.pdf
# during this project's research phase. Reproduced here under the
# source document's own stated terms ("Reproduction is authorised
# provided the source is acknowledged").
MELISSA_MONOGRAPH_FIXTURE = """
4. Clinical particulars 
4.1. Therapeutic indications
Well-established use Traditional use 
Indication 1)
Traditional herbal medicinal product for relief of 
mild symptoms of mental stress and to aid sleep.
Indication 2)
Traditional herbal medicinal product for
symptomatic treatment of mild gastrointestinal
complaints including bloating and flatulence.
The product is a traditional herbal medicinal
product for use in specified indications exclusively 
based upon long-standing use.
4.2. Posology and method of administration3
Well-established use Traditional use 
Posology
Indications 1) and 2)
Adolescents over 12 years of age, adults and
elderly
Single dose
a) Herbal tea: 1.5-4.5 g of the comminuted herbal 
substance in 150 ml of boiling water as a herbal 
infusion, 1-3 times daily.
4.3. Contraindications
Well-established use Traditional use 
Hypersensitivity to the active substance.
4.4. Special warnings and precautions for use
Well-established use Traditional use 
Indication 1) and 2)
The use in children under 12 years of age has not 
been established due to lack of adequate data.
4.5. Interactions with other medicinal products and other forms of
interaction
Well-established use Traditional use 
No data available.
4.6. Fertility, pregnancy and lactation
Well-established use Traditional use 
Safety during pregnancy and lactation has not
been established.
4.7. Effects on ability to drive and use machines
Well-established use Traditional use 
May impair ability to drive and use machines.
4.8. Undesirable effects
Well-established use Traditional use 
None known.
4.9. Overdose
Well-established use Traditional use 
No case of overdose has been reported.
5. Pharmacological properties
5.1. Pharmacodynamic properties
Well-established use Traditional use 
Not required as per Article 16c(1)(a)(iii) of 
Directive 2001/83/EC as amended.
"""


def test_all_nine_clinical_sections_found():
    sections = _split_clinical_sections(MELISSA_MONOGRAPH_FIXTURE)
    expected_numbers = {f"4.{i}" for i in range(1, 10)}
    found_numbers = set(sections.keys())
    missing = expected_numbers - found_numbers
    assert not missing, f"Failed to locate sections: {missing}"
    print(f"PASS: all 9 clinical sections located: {sorted(found_numbers)}")


def test_section_5_boundary_excludes_pharmacological_properties():
    sections = _split_clinical_sections(MELISSA_MONOGRAPH_FIXTURE)
    overdose_text = sections["4.9"]
    assert "Pharmacodynamic" not in overdose_text, (
        "Section 4.9 text leaked into section 5 content — the "
        "section-5 boundary regex did not stop the split correctly."
    )
    print("PASS: section 4.9 does not bleed into section 5 content")


def test_populated_section_reports_present_see_raw_text():
    # Section 4.3 (Contraindications) in the real Melissa monograph has
    # NO well-established-use content — extraction leaves only the
    # "Well-established use Traditional use" header line followed by
    # the single (traditional-use-only) sentence. Confirm this doesn't
    # get misclassified as "confirmed_absent" just because it's short.
    sections = _split_clinical_sections(MELISSA_MONOGRAPH_FIXTURE)
    contraindications_text = sections["4.3"]
    print(f"4.3 raw text: {contraindications_text!r}")
    status = _detect_weu_status(contraindications_text)
    assert status == "present_see_raw_text", (
        f"Expected 'present_see_raw_text' for a section with real "
        f"content after the header, got: {status!r}"
    )
    print(
        "PASS: a section with real content after the WEU/TU header "
        "correctly reports 'present_see_raw_text' — no split is "
        "attempted, matching the confirmed design decision"
    )


def test_empty_section_after_header_reports_confirmed_absent():
    header_only = "Well-established use Traditional use"
    status = _detect_weu_status(header_only)
    assert status == "confirmed_absent", (
        f"Expected 'confirmed_absent' for a header with no content "
        f"after it, got: {status!r}"
    )
    print("PASS: a truly empty WEU column (header only, no content) is correctly reported as 'confirmed_absent'")


if __name__ == "__main__":
    test_all_nine_clinical_sections_found()
    test_section_5_boundary_excludes_pharmacological_properties()
    test_populated_section_reports_present_see_raw_text()
    test_empty_section_after_header_reports_confirmed_absent()
    print("\nAll parsing tests passed against the real Melissa officinalis fixture.")
