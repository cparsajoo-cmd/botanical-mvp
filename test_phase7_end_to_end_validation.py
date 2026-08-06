from datetime import datetime, timezone

import pytest

from assertion_vocabulary import ValidationScope
from end_to_end_validation import (
    BenchmarkMode, BenchmarkVersions, FailureSeverity, FailureStage,
    FrozenSnapshotRetriever, GoldSourceExpectation, GoldSourceSet,
    RetrievedEvidence, SourceRole, ValidationQuestion,
    build_end_to_end_evaluation_run, compare_benchmark_runs,
    configuration_hash, run_end_to_end_case,
)
from gold_case import DecisionDirection, ExpectedOutput, GoldCase
from validation_unit import PreparationSpec, ValidationUnit


def _case(case_id="phase7_case", taxon="Melissa officinalis L.", expected=DecisionDirection.POSITIVE):
    return GoldCase(
        case_id=case_id,
        validation_unit=ValidationUnit(
            taxon=taxon,
            indication="Sleep and relaxation",
            preparation=PreparationSpec(dosage_form="capsule"),
            jurisdiction="EU",
        ),
        expected_output=ExpectedOutput(expected_decision_direction=expected),
    )


def _question():
    return ValidationQuestion("Which botanical for sleep?", "Sleep and relaxation", "capsule", "EU")


def _versions():
    return BenchmarkVersions("phase7-test/1", "gold-test/1", "engine-test", "rules-test", "evidence-test", {"frozen":"1"})


def _positive(ref="rct1", taxon="Melissa officinalis L."):
    return RetrievedEvidence(
        reference_id=ref, scientific_name=taxon,
        notes="Randomized controlled trial demonstrated significant improvement in sleep symptoms.",
        source_type="PubMed", source_title="A randomized controlled trial",
        pmid="12345" if ref == "rct1" else "", target_indication="Sleep and relaxation",
    )


def _discover(_q):
    return ["Melissa officinalis L.", "Valeriana officinalis L.", "Passiflora incarnata L.", "Lavandula angustifolia Mill.", "Matricaria chamomilla L."]


def _metric(run, name):
    return next(m for m in run.metrics if m.metric_name == name)


def test_provided_evidence_scope_remains_separate():
    from evaluation_run import EvaluationRun, InvalidValidationScopeError
    with pytest.raises(InvalidValidationScopeError):
        EvaluationRun("x","e","g",datetime.now(timezone.utc),"h","Locked holdout",ValidationScope.END_TO_END)


def test_end_to_end_starts_from_question_and_retriever_never_receives_case_id():
    seen = {}
    def retriever(question, candidates):
        seen["question"] = question.question; seen["candidates"] = candidates
        return [_positive()]
    run_end_to_end_case(_case(), _question(), GoldSourceSet(), retriever, _discover)
    assert seen["question"] == "Which botanical for sleep?"
    assert "Melissa officinalis L." in seen["candidates"]


def test_critical_source_retrieved_counted_correctly():
    gs=GoldSourceSet((GoldSourceExpectation("rct1",SourceRole.CRITICAL),))
    r=run_end_to_end_case(_case(),_question(),gs,FrozenSnapshotRetriever([_positive()]),_discover)
    assert r.source_counts["critical_retrieved"] == 1


def test_missing_critical_source_is_retrieval_failure():
    gs=GoldSourceSet((GoldSourceExpectation("missing",SourceRole.CRITICAL),))
    r=run_end_to_end_case(_case(),_question(),gs,FrozenSnapshotRetriever([]),_discover)
    assert any(f.stage==FailureStage.RETRIEVAL_FAILURE and f.code=="CRITICAL_SOURCE_MISSED" for f in r.failures)


def test_irrelevant_source_penalizes_labelled_precision():
    ir=RetrievedEvidence("noise","Melissa officinalis L.","Unrelated observational background.",source_title="Noise")
    gs=GoldSourceSet((GoldSourceExpectation("rct1",SourceRole.SUPPORTING),GoldSourceExpectation("noise",SourceRole.IRRELEVANT)))
    run=build_end_to_end_evaluation_run([(_case(),_question(),gs)],FrozenSnapshotRetriever([_positive(),ir]),_versions(),BenchmarkMode.FROZEN_SNAPSHOT,_discover)
    assert _metric(run,"evidence_retrieval_precision_labelled_subset").proportion.point_estimate == 0.5


def test_duplicate_retrieved_article_counted_once():
    a=_positive(); b=RetrievedEvidence("duplicate_connector_copy",a.scientific_name,a.notes,source_title=a.source_title,pmid="12345",target_indication=a.target_indication)
    r=run_end_to_end_case(_case(),_question(),GoldSourceSet(),FrozenSnapshotRetriever([a,b]),_discover)
    assert r.source_counts["retrieved"]==2 and r.source_counts["unique"]==1 and r.source_counts["duplicates"]==1


@pytest.mark.parametrize("text,expected",[
    ("Randomized controlled trial demonstrated significant improvement in symptoms.","positive"),
    ("Randomized controlled trial failed to demonstrate efficacy and did not meet the primary endpoint.","negative"),
    ("Randomized controlled trial found no significant difference from placebo.","null"),
])
def test_rct_direction_validation(text,expected):
    rec=RetrievedEvidence("r1","Melissa officinalis L.",text,source_title="RCT",target_indication="Sleep and relaxation")
    gs=GoldSourceSet((GoldSourceExpectation("r1",SourceRole.SUPPORTING,expected_direction=expected),))
    r=run_end_to_end_case(_case(),_question(),gs,FrozenSnapshotRetriever([rec]),_discover)
    chk=r.classification_checks[0]
    assert chk["actual"]["evidence_direction"] == expected


def test_applicability_mismatch_detected():
    rec=RetrievedEvidence("r1","Melissa officinalis L.","Clinical trial protocol registered for a future randomized trial.",source_title="Protocol",target_indication="Sleep and relaxation")
    gs=GoldSourceSet((GoldSourceExpectation("r1",SourceRole.SUPPORTING,expected_applicability="direct_reported"),))
    r=run_end_to_end_case(_case(),_question(),gs,FrozenSnapshotRetriever([rec]),_discover)
    assert any(f.stage==FailureStage.APPLICABILITY_FAILURE for f in r.failures)


def test_safety_source_missed_is_critical_retrieval_failure():
    gs=GoldSourceSet((GoldSourceExpectation("ema-warning",SourceRole.CRITICAL,safety_critical=True),))
    r=run_end_to_end_case(_case(expected=DecisionDirection.NEGATIVE),_question(),gs,FrozenSnapshotRetriever([]),_discover)
    assert any(f.stage==FailureStage.RETRIEVAL_FAILURE and f.severity==FailureSeverity.CRITICAL for f in r.failures)


def test_source_unavailable_not_clearance():
    rec=RetrievedEvidence("ema","Melissa officinalis L.","",source_available=False,target_indication="Sleep and relaxation")
    r=run_end_to_end_case(_case(),_question(),GoldSourceSet(),FrozenSnapshotRetriever([rec]),_discover)
    assert any(f.stage==FailureStage.SOURCE_UNAVAILABLE for f in r.failures)


def test_regulatory_prohibition_miss_is_critical():
    gs=GoldSourceSet((GoldSourceExpectation("reg-ban",SourceRole.CRITICAL,regulatory_critical=True),))
    r=run_end_to_end_case(_case(expected=DecisionDirection.NEGATIVE),_question(),gs,FrozenSnapshotRetriever([]),_discover)
    assert any(f.code=="CRITICAL_SOURCE_MISSED" and f.severity==FailureSeverity.CRITICAL for f in r.failures)


def test_no_go_in_top5_is_flagged(monkeypatch):
    import end_to_end_validation as m
    class FakeEngine:
        def __init__(self,**kwargs): pass
        def run(self,**kwargs):
            import pandas as pd
            from data_contracts import GateStatus
            return pd.DataFrame([{"Alternative_Plant":"Melissa officinalis L.","Decision_Class":"Regulatory prohibition — not suitable without regulatory review","Gate_Results":{"regulatory":{"status":GateStatus.FAILED}}}])
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",FakeEngine)
    r=run_end_to_end_case(_case(expected=DecisionDirection.NEGATIVE),_question(),GoldSourceSet(),FrozenSnapshotRetriever([_positive()]),lambda q:["Melissa officinalis L."])
    assert any(f.code=="NO_GO_IN_TOP5" for f in r.failures)


def test_incomplete_result_does_not_count_as_validated_recommendation(monkeypatch):
    import end_to_end_validation as m
    class FakeEngine:
        def __init__(self,**kwargs): pass
        def run(self,**kwargs):
            import pandas as pd
            return pd.DataFrame([{"Alternative_Plant":"Melissa officinalis L.","Decision_Class":"Low priority / insufficient data","Gate_Results":{}}])
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",FakeEngine)
    r=run_end_to_end_case(_case(expected=DecisionDirection.POSITIVE),_question(),GoldSourceSet(),FrozenSnapshotRetriever([]),lambda q:["Melissa officinalis L."])
    assert r.decision_direction == DecisionDirection.HOLD
    assert any(f.code=="DECISION_DIRECTION_MISMATCH" for f in r.failures)


def test_decision_direction_agreement_metric(monkeypatch):
    import end_to_end_validation as m
    class FakeEngine:
        def __init__(self,**kwargs): pass
        def run(self,**kwargs):
            import pandas as pd
            return pd.DataFrame([{"Alternative_Plant":"Melissa officinalis L.","Decision_Class":"Strong R&D candidate","Gate_Results":{}}])
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",FakeEngine)
    run=build_end_to_end_evaluation_run([(_case(),_question(),GoldSourceSet())],FrozenSnapshotRetriever([_positive()]),_versions(),BenchmarkMode.FROZEN_SNAPSHOT,lambda q:["Melissa officinalis L."])
    assert _metric(run,"decision_direction_agreement").proportion.point_estimate == 1.0


def test_top3_and_top5_inclusion_calculated(monkeypatch):
    import end_to_end_validation as m
    class FakeEngine:
        def __init__(self,**kwargs): pass
        def run(self,**kwargs):
            import pandas as pd
            names=["Valeriana officinalis L.","Melissa officinalis L.","Passiflora incarnata L.","Lavandula angustifolia Mill.","Matricaria chamomilla L."]
            return pd.DataFrame([{"Alternative_Plant":n,"Decision_Class":"Strong R&D candidate","Gate_Results":{}} for n in names])
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",FakeEngine)
    run=build_end_to_end_evaluation_run([(_case(),_question(),GoldSourceSet())],FrozenSnapshotRetriever([]),_versions(),BenchmarkMode.FROZEN_SNAPSHOT,_discover)
    assert _metric(run,"top_3_inclusion").proportion.point_estimate == 1.0
    assert _metric(run,"top_5_inclusion").proportion.point_estimate == 1.0


def test_failure_attribution_is_retrieval_not_scoring_for_missing_rct():
    gs=GoldSourceSet((GoldSourceExpectation("negative-rct",SourceRole.CRITICAL),))
    r=run_end_to_end_case(_case(),_question(),gs,FrozenSnapshotRetriever([]),_discover)
    assert any(f.stage==FailureStage.RETRIEVAL_FAILURE for f in r.failures)
    assert not any(f.stage==FailureStage.SCORING_FAILURE for f in r.failures)


def test_benchmark_run_has_versions_scope_hash_and_snapshot():
    run=build_end_to_end_evaluation_run([],FrozenSnapshotRetriever([]),_versions(),BenchmarkMode.FROZEN_SNAPSHOT,_discover,data_snapshot="snapshot-2026-08-06",config={"x":1})
    assert run.validation_scope==ValidationScope.END_TO_END
    assert run.versions.gold_corpus_version=="gold-test/1"
    assert run.data_snapshot=="snapshot-2026-08-06"
    assert run.configuration_hash==configuration_hash({"x":1})


def test_benchmark_comparison_identifies_regression(monkeypatch):
    import end_to_end_validation as m
    class Good:
        def __init__(self,**kwargs): pass
        def run(self,**kwargs):
            import pandas as pd
            return pd.DataFrame([{"Alternative_Plant":"Melissa officinalis L.","Decision_Class":"Strong R&D candidate","Gate_Results":{}}])
    class Bad:
        def __init__(self,**kwargs): pass
        def run(self,**kwargs):
            import pandas as pd
            return pd.DataFrame([{"Alternative_Plant":"Melissa officinalis L.","Decision_Class":"Low priority / insufficient data","Gate_Results":{}}])
    kwargs=dict(cases=[(_case(),_question(),GoldSourceSet())],retriever=FrozenSnapshotRetriever([]),versions=_versions(),mode=BenchmarkMode.FROZEN_SNAPSHOT,candidate_discovery=lambda q:["Melissa officinalis L."],execution_timestamp=datetime(2026,8,6,tzinfo=timezone.utc),evaluation_run_id="stable")
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",Good); a=build_end_to_end_evaluation_run(**kwargs)
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",Bad); b=build_end_to_end_evaluation_run(**kwargs)
    cmp=compare_benchmark_runs(a,b)
    assert cmp["metric_worsened"] or cmp["decision_changes"]


def test_frozen_snapshot_run_is_deterministic(monkeypatch):
    import end_to_end_validation as m
    class Fake:
        def __init__(self,**kwargs): pass
        def run(self,**kwargs):
            import pandas as pd
            return pd.DataFrame([{"Alternative_Plant":"Melissa officinalis L.","Decision_Class":"Strong R&D candidate","Gate_Results":{}}])
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",Fake)
    kwargs=dict(cases=[(_case(),_question(),GoldSourceSet((GoldSourceExpectation("rct1",SourceRole.CRITICAL),)))],retriever=FrozenSnapshotRetriever([_positive()]),versions=_versions(),mode=BenchmarkMode.FROZEN_SNAPSHOT,candidate_discovery=lambda q:["Melissa officinalis L."],execution_timestamp=datetime(2026,8,6,tzinfo=timezone.utc),evaluation_run_id="fixed",data_snapshot="fixed",config={"a":1})
    a=build_end_to_end_evaluation_run(**kwargs); b=build_end_to_end_evaluation_run(**kwargs)
    assert [(m.metric_name, getattr(m.proportion,"point_estimate",None)) for m in a.metrics] == [(m.metric_name, getattr(m.proportion,"point_estimate",None)) for m in b.metrics]
    assert a.configuration_hash==b.configuration_hash


def test_gold_case_identifier_does_not_change_production_behavior(monkeypatch):
    import end_to_end_validation as m
    captured=[]
    class Fake:
        def __init__(self,**kwargs): captured.append(kwargs)
        def run(self,**kwargs):
            import pandas as pd
            return pd.DataFrame([{"Alternative_Plant":"Melissa officinalis L.","Decision_Class":"Strong R&D candidate","Gate_Results":{}}])
    monkeypatch.setattr(m,"BotanicalRDCandidateEngine",Fake)
    retr=FrozenSnapshotRetriever([_positive()])
    a=run_end_to_end_case(_case("gold_A"),_question(),GoldSourceSet(),retr,lambda q:["Melissa officinalis L."])
    b=run_end_to_end_case(_case("totally_different_id"),_question(),GoldSourceSet(),retr,lambda q:["Melissa officinalis L."])
    assert a.decision_class==b.decision_class
    assert captured[0]["evidence_df"].to_dict("records") == captured[1]["evidence_df"].to_dict("records")


def test_live_retriever_adapter_degrades_source_unavailable_when_dependencies_missing(monkeypatch):
    import builtins
    from end_to_end_validation import LiveMultiSourceRetriever
    real_import = builtins.__import__
    def fake_import(name,*args,**kwargs):
        if name == "multi_source_collector":
            raise ModuleNotFoundError("supabase")
        return real_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,"__import__",fake_import)
    rows=LiveMultiSourceRetriever()(_question(),["Melissa officinalis L."])
    assert rows and rows[0].source_available is False


def test_benchmark_persistence_is_append_only(tmp_path):
    from end_to_end_validation import persist_end_to_end_run
    run=build_end_to_end_evaluation_run([],FrozenSnapshotRetriever([]),_versions(),BenchmarkMode.FROZEN_SNAPSHOT,_discover,evaluation_run_id="immutable-run")
    path=persist_end_to_end_run(run,str(tmp_path))
    assert path.endswith("immutable-run.json")
    with pytest.raises(FileExistsError):
        persist_end_to_end_run(run,str(tmp_path))
