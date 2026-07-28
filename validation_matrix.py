"""
Task 7 — Validation Coverage Matrix.

WHAT THIS IS
validation_case_protocol.py (Task 6) defines what it means to LOCK one
validation case. This module answers a different question: across the
platform's ENTIRE real coverage — every product_type x indication x
dosage_form x market combination step_inputs.py actually offers (7 x
28 x 12 x 25 = 58,800 combinations) — which cases exist, what is their
current readiness, and what is the single next step to move each one
forward? It is the tool that generates the "which case should I work
on next" view Appendix A's four hand-picked examples never gave a way
to produce for anything outside those four.

WHY THIS DOESN'T ALSO GENERATE CANDIDATE SETS, CORPORA, OR PANELS
Doing so automatically would be dishonest for the exact reason
validation_case_protocol.py's own docstring explains: a candidate set
needs documented eligibility rules from real scientific/regulatory
judgment, a reference corpus must be built INDEPENDENTLY of this
platform, and an expert panel must be real, credentialed people who
form an independent judgment. None of those can be fabricated by a
script without making every "locked" case in the matrix meaningless.
This module only ever fills in DecisionContext (population, route,
dosage form, jurisdiction, product_type, indication) — every
combination it generates is therefore CONDITIONALLY_READY at best,
never LOCKED, until a person completes the remaining three elements
by hand for the specific case(s) that matter.

SCOPE-NARROWING IS THE POINT, NOT A LIMITATION
58,800 combinations is not a worklist — it's a coverage map. The real
value of this module is letting someone filter it down (by
product_type, indication, dosage_form, or market) to the handful of
combinations that actually matter for their current commercial or
scientific priorities, and get a properly-shaped DecisionContext
starting point for each one instead of typing it by hand.

DERIVED FIELDS, AND WHERE THEY'RE HONEST APPROXIMATIONS
step_inputs.py captures product_type/indication/dosage_form/market
directly, but not population or route_of_administration as their own
fields — Appendix A requires both. This module derives them with
documented, disclosed rules (see ROUTE_OF_ADMINISTRATION_BY_DOSAGE_FORM
and _population_for_product_type() below) rather than leaving them
blank, but every generated DecisionContext should still be reviewed
and corrected by a person before its case is treated as more than a
starting draft — a script's best guess at "route" or "population" is
not itself a locked decision context.
"""

from __future__ import annotations

import csv
import sys
from itertools import product as _cartesian_product
from typing import Optional

from step_inputs import PRODUCT_TYPES, INDICATIONS, DOSAGE_FORMS, MARKETS
from validation_case_protocol import (
    DecisionContext,
    ValidationCaseProtocol,
    ProtocolReadiness,
    assess_readiness,
    to_appendix_row,
)

# Documented, disclosed dosage-form -> route mapping. Where a dosage
# form genuinely has more than one common route (e.g. essential oil
# can be applied topically, diffused, or occasionally taken orally
# under professional guidance), the value says so explicitly rather
# than silently picking one — a reviewer must resolve it for the
# specific case, this module never guesses silently.
ROUTE_OF_ADMINISTRATION_BY_DOSAGE_FORM = {
    "Infusion": "Oral",
    "Capsule": "Oral",
    "Tablet": "Oral",
    "Syrup": "Oral",
    "Powder": "Oral (unless otherwise specified for the case)",
    "Extract": "Oral (unless otherwise specified for the case)",
    "Cream": "Topical",
    "Gel": "Topical",
    "Mouthwash": "Oromucosal",
    "Chewing gum": "Oromucosal",
    "Nasal spray": "Nasal",
    "Essential oil": "Topical / inhalation (route-ambiguous — must be resolved per case)",
}


def _route_of_administration(dosage_form: str) -> Optional[str]:
    return ROUTE_OF_ADMINISTRATION_BY_DOSAGE_FORM.get(dosage_form)


def _population_for_product_type(product_type: str) -> Optional[str]:
    """Only "Veterinary botanical product" carries an unambiguous
    population signal from product_type alone. Every other product
    type defaults to a disclosed, reviewable assumption — never a
    silent one — since the platform does not currently capture
    pediatric/pregnancy/elderly sub-population as its own field."""
    if product_type == "Veterinary botanical product":
        return "Veterinary (species not further specified by the platform — must be resolved per case)"
    return "Human adults (default assumption — platform does not currently capture pediatric/pregnancy/elderly sub-population as a separate field; must be reviewed per case)"


def generate_decision_context(
    product_type: str, indication: str, dosage_form: str, market: str
) -> DecisionContext:
    """Builds one DecisionContext from the platform's four real Step-0
    fields, plus the two derived fields above. Every value here is a
    STARTING DRAFT for a human reviewer, not a locked decision — see
    module docstring."""
    return DecisionContext(
        population=_population_for_product_type(product_type),
        route_of_administration=_route_of_administration(dosage_form),
        dosage_form=dosage_form,
        jurisdiction=market,
        product_type=product_type,
        indication=indication,
    )


def case_name_for(product_type: str, indication: str, dosage_form: str, market: str) -> str:
    return f"{indication} — {dosage_form} ({product_type}, {market})"


def generate_matrix(
    product_types: Optional[list] = None,
    indications: Optional[list] = None,
    dosage_forms: Optional[list] = None,
    markets: Optional[list] = None,
) -> list:
    """Returns a list[ValidationCaseProtocol], one per combination of
    the (optionally filtered) input lists. Defaults to the platform's
    FULL real option lists (step_inputs.py's PRODUCT_TYPES/
    INDICATIONS/DOSAGE_FORMS/MARKETS) when a given axis is not
    filtered — callers wanting a manageable subset should pass an
    explicit, narrower list for one or more axes rather than
    generating and then discarding the full 58,800-row matrix.

    Every returned protocol has ONLY decision_context populated
    (candidate_set/reference_corpus/expert_panel are left at their
    empty defaults) — see module docstring for why this module never
    fills those in automatically.
    """
    product_types = product_types if product_types is not None else PRODUCT_TYPES
    indications = indications if indications is not None else INDICATIONS
    dosage_forms = dosage_forms if dosage_forms is not None else DOSAGE_FORMS
    markets = markets if markets is not None else MARKETS

    protocols = []
    for product_type, indication, dosage_form, market in _cartesian_product(
        product_types, indications, dosage_forms, markets
    ):
        protocols.append(
            ValidationCaseProtocol(
                case_name=case_name_for(product_type, indication, dosage_form, market),
                decision_context=generate_decision_context(
                    product_type, indication, dosage_form, market
                ),
            )
        )
    return protocols


def matrix_readiness_summary(protocols: list) -> dict:
    """Counts protocols by ProtocolReadiness across the given list —
    the coverage-map-level view: "how many of these N combinations are
    at least conditionally ready vs. not started." Every protocol
    generate_matrix() produces is decision-context-complete by
    construction, so in practice this will show 100% CONDITIONALLY_READY
    and 0% elsewhere for a matrix built entirely by generate_matrix()
    — this function's real value is for a MIXED list (e.g. after a
    person has manually completed candidate_set/reference_corpus/
    expert_panel for a handful of cases pulled out of the matrix and
    put them back in), where the counts become genuinely informative.
    """
    counts = {r: 0 for r in ProtocolReadiness}
    for protocol in protocols:
        counts[assess_readiness(protocol)] += 1
    total = len(protocols)
    return {
        "total": total,
        "counts": {r.value: counts[r] for r in ProtocolReadiness},
        "percentages": {
            r.value: (round(100 * counts[r] / total, 1) if total else 0.0)
            for r in ProtocolReadiness
        },
    }


def matrix_rows(protocols: list) -> list:
    """One dict per protocol, combining to_appendix_row()'s
    {Case, Readiness, Principal gap} with the four raw decision-context
    fields — the shape a CSV export or a filtering UI needs. Column
    order matches write_matrix_csv()'s header."""
    rows = []
    for protocol in protocols:
        appendix_row = to_appendix_row(protocol)
        dc = protocol.decision_context
        rows.append({
            "Case": appendix_row["Case"],
            "Product_Type": dc.product_type or "",
            "Indication": dc.indication or "",
            "Dosage_Form": dc.dosage_form or "",
            "Jurisdiction": dc.jurisdiction or "",
            "Population": dc.population or "",
            "Route_Of_Administration": dc.route_of_administration or "",
            "Readiness": appendix_row["Readiness"],
            "Principal_Gap": appendix_row["Principal gap"],
        })
    return rows


_CSV_FIELDNAMES = [
    "Case", "Product_Type", "Indication", "Dosage_Form", "Jurisdiction",
    "Population", "Route_Of_Administration", "Readiness", "Principal_Gap",
]


def write_matrix_csv(protocols: list, path: str) -> int:
    """Writes matrix_rows(protocols) to `path` as CSV. Returns the
    number of rows written. This is the practical deliverable for
    reviewing a large matrix outside Python — e.g. in a spreadsheet,
    to pick which handful of cases to actually complete by hand."""
    rows = matrix_rows(protocols)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def filter_matrix(
    protocols: list,
    product_type: Optional[str] = None,
    indication: Optional[str] = None,
    dosage_form: Optional[str] = None,
    market: Optional[str] = None,
) -> list:
    """Narrows an already-generated matrix by any combination of the
    four axes (each optional; None means "don't filter on this axis").
    Convenience for working with a matrix already in memory, as an
    alternative to re-calling generate_matrix() with narrower input
    lists."""
    result = protocols
    if product_type is not None:
        result = [p for p in result if p.decision_context.product_type == product_type]
    if indication is not None:
        result = [p for p in result if p.decision_context.indication == indication]
    if dosage_form is not None:
        result = [p for p in result if p.decision_context.dosage_form == dosage_form]
    if market is not None:
        result = [p for p in result if p.decision_context.jurisdiction == market]
    return result


def main(argv=None) -> int:
    """CLI: python3 validation_matrix.py export <output.csv>
    [--product-type "X"] [--indication "Y"] [--dosage-form "Z"] [--market "W"]

    Generates the (optionally filtered) full coverage matrix and writes
    it to a CSV file, then prints the readiness summary — same
    "run + print report" shape as benchmark_harness.py's own CLI.
    """
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2 or argv[0] != "export":
        print(
            "Usage: python3 validation_matrix.py export <output.csv> "
            '[--product-type "X"] [--indication "Y"] [--dosage-form "Z"] [--market "W"]'
        )
        return 2

    output_path = argv[1]
    filters = {"product_types": None, "indications": None, "dosage_forms": None, "markets": None}
    flag_to_key = {
        "--product-type": "product_types",
        "--indication": "indications",
        "--dosage-form": "dosage_forms",
        "--market": "markets",
    }
    i = 2
    while i < len(argv) - 1:
        flag = argv[i]
        if flag in flag_to_key:
            filters[flag_to_key[flag]] = [argv[i + 1]]
            i += 2
        else:
            i += 1

    protocols = generate_matrix(**filters)
    count = write_matrix_csv(protocols, output_path)
    summary = matrix_readiness_summary(protocols)

    print(f"Wrote {count} rows to {output_path}")
    print(f"Total combinations: {summary['total']}")
    for readiness_label, pct in summary["percentages"].items():
        print(f"  {readiness_label}: {summary['counts'][readiness_label]} ({pct}%)")
    print()
    print(
        "Reminder: every row here has ONLY a draft decision context. "
        "None are locked — see validation_case_protocol.py's lock_protocol() "
        "for what a case still needs before it can be treated as validation-ready."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
