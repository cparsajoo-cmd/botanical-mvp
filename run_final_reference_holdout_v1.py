"""Runs one Reference-Grounded Validation case set (v1, v2, or v3) against
the current engine code. v1/v2 are REGRESSION checks (see below); v3 is
the genuine BLIND holdout, added 2026-08-11 -- see the freeze note further
down before running it.

BUG FOUND (2026-08-10): the original version of this script always read
gold_corpus/scientific_validity/final_holdout_v1/frozen_reference_labels.json
and always wrote blind_results.json / release_gate_result.json under the
SAME unversioned filenames, for both the v1 and v2 case sets. When v2 was
run, it silently overwrote v1's frozen expected-labels file and v1's
result artifacts -- v1's raw evidence snapshots (gold_corpus/.../snapshots/
rgv1_*.json) survived, but v1's frozen "correct answer" for each case did
not, and was only recovered because Hamid found an older commit of that
file on GitHub. v1's original blind_results.json/release_gate_result.json
were NOT recoverable and are gone for good.

Fix: --tag is now required and selects both the input labels file
(frozen_reference_labels_<tag>.json) and the output filenames
(blind_results_<tag>.json, release_gate_result_<tag>.json), so running one
case set can never again silently destroy the other's frozen labels or
results. There is no default tag -- an explicit choice is required every
time this script runs.

Per the holdout integrity rule (see FINAL_REFERENCE_GROUNDED_VALIDATION_
V2_REPORT.md): v1 and v2 are EXPOSED. Their output is a regression check
on already-seen cases, never an independent/blind validity estimate.

v3 (2026-08-11): a genuinely independent 20-case holdout -- zero overlap
with v1/v2, gold_cases/, or decision_holdout_v2 through v5 (80 species
checked programmatically; see FREEZE_MANIFEST_v3.json). Frozen before
this script was ever run against it. --tag v3 is the one case where this
script's output is a real blind validation, not a regression check --
but ONLY if the freeze integrity check (verify_rgv3_freeze.py) passes
first; the GitHub Actions workflow runs that check as a required prior
step and refuses to proceed on any mismatch. Per the project's holdout
integrity rule: if v3's result is weak, report it as weak -- do not add
vocabulary, change a label, drop a case, tune a threshold, or add a
special-case rule in response to seeing this output. Any such change
would require freezing an entirely new holdout first.

SEMANTIC GATE WIRING (2026-08-11): the semantic-gate layer (LLM-based
safety/regulatory assertions, semantic_gate_assertions.py) is additive
and reads ONLY the ``llm_gate_assertions`` field already present on a
contributing evidence record (see the "New semantic gate layer" comment
in botanical_rd_candidate_engine.py) -- it never calls the LLM itself
from inside scoring/eligibility. In production that field is populated by
backfill_semantic_gate_assertions.py against the live evidence_records
table. This script's injected snapshot evidence never went through that
backfill (it isn't in evidence_records at all), so every RGV run before
this fix silently exercised the deterministic-only path -- the semantic
gate never fired for a single validation case, regression or blind. Fixed
here by calling extract_gate_assertions_with_llm() once per evidence
record (mirroring backfill_semantic_gate_assertions.py's own call and
payload shape exactly) before building the row, so v1/v2/v3 all now
exercise the real production decision path, not a silently-narrower one.
A failed/empty extraction leaves the field unset for that record (same
"stay retryable, don't fabricate" rule as the backfill script) rather
than blocking the whole run.

EVIDENCE-DIRECTION WIRING (2026-08-11): identical root-cause pattern found
a second time. resolve_record_direction() (canonical_scientific_assertion.py)
prefers source_result_direction, then llm_result_direction, and only falls
back to the OLD, narrow regex-based evidence_interpretation.classify_
evidence_direction() (reported_direction) when neither is set. In
production, backfill_canonical_assertions.py already populates
llm_result_direction for every real evidence_records row. This script's
injected evidence never had it, so every v1/v2/v3 case was silently
scored against the OLD regex classifier this project explicitly moved
away from -- confirmed directly: classify_evidence_direction() returns
"unclear" for real GO-WITH-CAUTION case text like the bilberry/EMA
monograph wording ("grants traditional-use status... based on
long-standing use"), which reads as a monograph-style regulatory
description, not the trial-result phrasing the regex was written to
catch. That single "unclear" is what drove Decision_Class to "Insufficient
evidence" for cases that should have reached GO/GO WITH CAUTION -- a
plausible major contributor to the GO/GO WITH CAUTION under-performance
seen across v1/v2/v3. Fixed by also calling extract_evidence_with_llm()
(the same function backfill_canonical_assertions.py already uses) per
evidence record and populating LLM_Result_Direction/LLM_Safety_Signal,
so injected validation evidence gets the same modern extraction real
Supabase rows get.
"""
import argparse
import sys
import time
from pathlib import Path
import json, pandas as pd
from dataclasses import asdict
from botanical_rd_candidate_engine import BotanicalRDCandidateEngine, DECISION_ENGINE_VERSION
from end_to_end_validation import _build_plant_df, _norm_taxon
from final_decision_policy import FinalDecisionStatus, final_status_from_engine_row
from scientific_decision_validation import DecisionComparison
from decision_benchmark_v1 import compute_metrics
from scientific_validity_release_gate import ReferenceValidationProtocol, evaluate_reference_grounded_release
from llm_extractor import extract_gate_assertions_with_llm, extract_evidence_with_llm
from semantic_gate_assertions import SEMANTIC_GATE_ASSERTION_VERSION

ROOT=Path(__file__).resolve().parent
BASE=ROOT/"gold_corpus/scientific_validity/final_holdout_v1"

GATE_EXTRACTION_MAX_RETRIES = 2
DIRECTION_EXTRACTION_MAX_RETRIES = 2


def _direction_signal_for(notes, *, source_title, dosage_form, indication):
    """Mirrors backfill_canonical_assertions.py's own call to
    extract_evidence_with_llm(), so injected validation evidence gets the
    same modern LLM-derived result_direction/safety_signal real Supabase
    rows get instead of silently falling back to the old regex classifier.
    Returns (llm_result_direction, llm_safety_signal) or (None, None) if
    extraction failed after retries -- left unset rather than fabricated,
    same policy as the gate-assertion extractor above."""
    if not str(notes or "").strip():
        return None, None

    record = {"Source_Title": source_title or "", "Notes": notes}
    last_error = None
    for attempt in range(DIRECTION_EXTRACTION_MAX_RETRIES + 1):
        try:
            out = extract_evidence_with_llm(
                record, selected_dosage_form=dosage_form or "", selected_indication=indication or "",
            )
            direction = str(out.get("result_direction") or "Unknown").strip() or "Unknown"
            safety = str(out.get("safety_signal") or "").strip() or None
            return direction, safety
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < DIRECTION_EXTRACTION_MAX_RETRIES:
                time.sleep(0.75 * (attempt + 1))
    print(
        f"WARNING: direction extraction failed after "
        f"{DIRECTION_EXTRACTION_MAX_RETRIES + 1} attempts, leaving "
        f"llm_result_direction unset for this record: {last_error}",
        file=sys.stderr,
    )
    return None, None


def _utc_now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _persisted_gate_payload(raw):
    """Same shape backfill_semantic_gate_assertions.py writes to the
    llm_gate_assertions column, so injected validation evidence looks
    identical to real backfilled Supabase rows from the engine's point
    of view."""
    return {
        "schema_version": SEMANTIC_GATE_ASSERTION_VERSION,
        "processed_at": _utc_now(),
        "safety_assertions": list(raw.get("safety_assertions") or []),
        "regulatory_assertions": list(raw.get("regulatory_assertions") or []),
    }


def _gate_assertions_for(notes, *, target_indication, dosage_form, target_market):
    """Calls the same LLM extraction the production backfill uses, with
    the same bounded-retry pattern (MAX_RETRIES=2, 0.75s*(attempt+1)
    backoff). Returns the persisted-payload dict, or None if extraction
    failed after retries (the caller leaves llm_gate_assertions unset for
    that record rather than fabricating a payload)."""
    if not str(notes or "").strip():
        return _persisted_gate_payload({"safety_assertions": [], "regulatory_assertions": []})

    record = {
        "Notes": notes,
        "Target_Indication": target_indication or "",
        "Dosage_Form": dosage_form or "",
        "Target_Market": target_market or "",
    }
    candidate_context = " | ".join(
        v for v in (target_indication, dosage_form, target_market) if str(v or "").strip()
    )

    last_error = None
    for attempt in range(GATE_EXTRACTION_MAX_RETRIES + 1):
        try:
            raw = extract_gate_assertions_with_llm(record, candidate_context=candidate_context)
            return _persisted_gate_payload(raw)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < GATE_EXTRACTION_MAX_RETRIES:
                time.sleep(0.75 * (attempt + 1))
    print(
        f"WARNING: semantic gate extraction failed after "
        f"{GATE_EXTRACTION_MAX_RETRIES + 1} attempts, leaving "
        f"llm_gate_assertions unset for this record: {last_error}",
        file=sys.stderr,
    )
    return None


def to_row(r, indication, target_market="EU"):
    dosage_form = "oral"
    row = {
        "Evidence_Record_ID":r["reference_id"],"Scientific_Name":r["scientific_name"],
        "Target_Indication":r.get("target_indication") or indication,"Dosage_Form":dosage_form,"Target_Market":target_market,
        "Notes":r["notes"],"Source_Type":r.get("source_type",""),"Source_Title":r.get("source_title",""),
        "Source_URL":r.get("source_url",""),"PMID":r.get("pmid",""),"Study_Type":r.get("study_design",""),
        "Evidence_Level":r.get("evidence_quality",""),"Source_Authority":r.get("source_authority",""),
        "Source_Year":r.get("publication_year",""),"Primary_Outcome":r.get("primary_outcome",""),
        "Comparator":r.get("comparator",""),"Risk_of_Bias":r.get("risk_of_bias",""),
    }
    gate_payload = _gate_assertions_for(
        r["notes"],
        target_indication=row["Target_Indication"],
        dosage_form=dosage_form,
        target_market=target_market,
    )
    if gate_payload is not None:
        row["LLM_Gate_Assertions"] = gate_payload

    llm_direction, llm_safety = _direction_signal_for(
        r["notes"],
        source_title=row["Source_Title"],
        dosage_form=dosage_form,
        indication=row["Target_Indication"],
    )
    if llm_direction is not None:
        row["LLM_Result_Direction"] = llm_direction
    if llm_safety is not None:
        row["LLM_Safety_Signal"] = llm_safety
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--tag",
        required=True,
        choices=["v1", "v2", "v3"],
        help="Which exposed case set to run as a regression check. Required "
        "(no default) so v1 and v2 can never again silently overwrite each "
        "other's frozen labels or results -- see the 2026-08-10 note above.",
    )
    args = ap.parse_args()
    tag = args.tag

    labels_path = BASE / f"frozen_reference_labels_{tag}.json"
    if not labels_path.exists():
        raise SystemExit(
            f"Missing {labels_path}. This is the frozen expected-answer file "
            f"for case set '{tag}' -- it must exist and must not be "
            "reconstructed from memory or from aggregate report numbers."
        )

    refs=json.loads(labels_path.read_text())["cases"]
    rows=[]; comps=[]
    for c in refs:
        snap=json.loads((BASE/"snapshots"/f"{c['case_id']}.json").read_text())
        ev=pd.DataFrame([to_row(r,c["indication"]) for r in snap["records"]])
        # Isolation fix (2026-08-11): evidence_records_df was never passed
        # here, so BotanicalRDCandidateEngine.__init__'s _load_supabase_df()
        # treated it as "not explicitly provided" and fetched the REAL,
        # live production `evidence_records` table (~22,570 rows) over the
        # network instead of using an empty frame. That silently broke the
        # sealed/self-contained nature of this holdout: _get_reference_plants()
        # -> _reference_plants_from_supabase() searched that live table for
        # the case's indication text, and for common indications (e.g.
        # "constipation", "angina", "weight loss") frequently found real
        # unrelated plants there, returned them immediately as the
        # reference set, and never reached the synthetic single-candidate
        # self-match path. The synthetic candidate's placeholder compound
        # ("validation_shared_compound") never matches any real reference
        # plant's compounds, so it silently received zero output rows,
        # surfacing as actual=None for that case (not a scoring miss -- the
        # candidate never appeared in the engine's output at all). All four
        # Supabase-backed frames must be pinned to explicit (here, empty)
        # DataFrames for this holdout to be genuinely sealed; only
        # evidence_records_df was missing.
        engine=BotanicalRDCandidateEngine(
            plant_compounds_df=_build_plant_df(snap["candidate_pool"],c["indication"]),
            compound_profiles_df=pd.DataFrame(),scientific_evidence_df=pd.DataFrame(),
            evidence_records_df=pd.DataFrame(),
            evidence_df=ev,use_live_search=False)
        out=engine.run(indication=c["indication"],dosage_form="oral",market="EU")
        target=_norm_taxon(c["botanical"])
        tr=out[out["Alternative_Plant"].map(_norm_taxon)==target]
        actual=None if tr.empty else final_status_from_engine_row(tr.iloc[0])
        expected=FinalDecisionStatus(c["expected"])
        match=actual==expected
        rows.append({"case_id":c["case_id"],"botanical":c["botanical"],"expected":expected.value,
                     "actual":None if actual is None else actual.value,"match":match})
        comps.append(DecisionComparison(c["case_id"],expected,actual,match))

    metrics=compute_metrics(comps)
    payload={"version":f"reference-grounded-final-holdout-{tag}/1.0.0","engine_version":DECISION_ENGINE_VERSION,
             "rows":rows,"metrics":asdict(metrics)}
    (BASE/f"blind_results_{tag}.json").write_text(json.dumps(payload,indent=2,default=str))

    class_support={}
    source_support={}
    for c in refs:
        class_support[c["expected"]]=class_support.get(c["expected"],0)+1
        source_support[c["case_id"]]=1
    protocol=ReferenceValidationProtocol(
        benchmark_id=f"reference-grounded-final-holdout-{tag}",
        reference_frozen_before_engine_run=True,engine_blinded_to_reference_labels=True,
        remediation_cases_excluded=True,reference_evidence_excluded_from_engine_input=True,
        provenance_complete=True,n_cases=len(refs),class_support=class_support,
        reference_source_support=source_support)
    gate=evaluate_reference_grounded_release(protocol,metrics)
    gate_payload={"releasable":gate.releasable,"claim":gate.claim,"blockers":list(gate.blockers),"warnings":list(gate.warnings)}
    (BASE/f"release_gate_result_{tag}.json").write_text(json.dumps(gate_payload,indent=2))
    print(json.dumps({"tag":tag,"engine_version":DECISION_ENGINE_VERSION,"rows":rows,"metrics":asdict(metrics),"gate":gate_payload},indent=2,default=str))


if __name__ == "__main__":
    main()
