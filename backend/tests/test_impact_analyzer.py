from copy import deepcopy
import json

import pytest

from backend.app.analyzers.architecture_graph import GraphOptions, build_architecture_graph
from backend.app.analyzers.architecture_traversal import TraversalLimits
from backend.app.analyzers.impact_analyzer import ImpactOptions, analyze_finding_impact, analyze_security_impact
from backend.app.analyzers.semgrep_adapter import ScanResult
from backend.app.analyzers.structure_analyzer import analyze_repository


def write(root, files):
    for file, text in files.items():
        target=root/file; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(text,encoding='utf-8')


@pytest.fixture
def pipeline(tmp_path):
    write(tmp_path, {'database.py':'class Repository:\n    def lookup(self):\n        return unsafe_value\n',
        'services.py':'from database import Repository\ndef service():\n    return Repository()\n',
        'api.py':'from services import service\n', 'app.py':'import api\n',
        'unrelated.py':'value=1\n'})
    source=analyze_repository(str(tmp_path))
    return source,build_architecture_graph(source)


def finding(identifier='finding_one', file='database.py', start=3, end=None):
    return {'id':identifier,'rule_id':'codely.python.sql-injection','source':'semgrep','severity':'HIGH',
        'title':'Potential SQL injection','message':'Static local rule message','file':file,
        'start_line':start,'end_line':end or start,'cwe':['CWE-89']}


def scan(*findings, status='complete'):
    result=ScanResult(status)
    result.findings=list(findings)
    result.summary['total']=result.summary['high']=len(findings)
    result.diagnostics=[{'code':'coverage','rule_set':'python-security-v2'},
                        {'code':'scanner_exit','exit_code':0}]
    return result


def analyze(pipeline, *findings, **kwargs):
    source,architecture=pipeline
    return analyze_security_impact(scan(*(findings or [finding()])),source,architecture,**kwargs)


def filenames(result, ids):
    return {node['file'] for node in result.node_contexts if node['id'] in ids}


def test_mapping_function_method_class_and_metadata(pipeline):
    result=analyze(pipeline)
    row=result.finding_impacts[0]
    assert result.status=='complete' and result.summary['mapped_findings']==1
    assert row['enclosing_function']['qualified_name']=='Repository.lookup'
    assert row['enclosing_symbol']['kind']=='method'
    assert row['enclosing_class']['name']=='Repository' and row['enclosing_class']['kind']=='class'
    assert row['finding']['rule_id']=='codely.python.sql-injection'
    assert row['finding']['severity']=='HIGH' and row['finding']['cwe']==['CWE-89']
    assert len(row['source_references'])==3


def test_direct_transitive_and_dependency_distances(pipeline):
    result=analyze(pipeline)
    row=result.finding_impacts[0]
    assert filenames(result,row['direct_dependent_node_ids'])=={'services.py'}
    assert filenames(result,row['transitive_dependent_node_ids'])=={'api.py','app.py'}
    analysis=result.module_impacts[0]
    distances={node['file']:next(d['distance'] for d in analysis['dependency_distances'] if d['node_id']==node['id'])
               for node in result.node_contexts if node['file']!='database.py'}
    assert distances=={'services.py':1,'api.py':2,'app.py':3}
    assert all('severity' not in node and 'cwe' not in node for node in result.node_contexts)
    assert all('severity' not in row for row in analysis['dependency_distances'])


def test_paths_have_existing_graph_edge_ids_and_proofs(pipeline):
    result=analyze(pipeline)
    edges={edge['id']:edge for edge in result.evidence_edges}
    for path in result.module_impacts[0]['paths']:
        assert [(edges[e]['source'],edges[e]['target']) for e in path['edge_ids']]==list(zip(path['node_ids'],path['node_ids'][1:]))
        assert path['node_ids'][-1]==result.finding_impacts[0]['vulnerable_node_id']
    assert all(edge['evidence'] and edge['evidence'][0]['start_line']>0 for edge in edges.values())


def test_multiple_shortest_paths_are_bounded(tmp_path):
    write(tmp_path,{'database.py':'value=1\n','left.py':'import database\n','right.py':'import database\n',
                    'app.py':'import left\nimport right\n'})
    source=analyze_repository(str(tmp_path)); architecture=build_architecture_graph(source)
    result=analyze_security_impact(scan(finding(file='database.py',start=1)),source,architecture)
    app=architecture.module_for_file('app.py')['id']
    paths=[path for path in result.module_impacts[0]['paths'] if path['target_id']==app]
    assert len(paths)==2 and all(path['distance']==2 for path in paths)
    assert len({tuple(path['node_ids']) for path in paths})==2


def test_multiple_findings_share_one_module_traversal(pipeline,monkeypatch):
    from backend.app.analyzers import impact_analyzer
    calls=[]; original=impact_analyzer.dependency_analysis
    def counted(*args,**kwargs):
        calls.append(args[1]); return original(*args,**kwargs)
    monkeypatch.setattr(impact_analyzer,'dependency_analysis',counted)
    result=analyze(pipeline,finding('first'),finding('second'))
    assert result.summary['mapped_findings']==2 and len(calls)==1
    assert len(result.module_impacts)==1
    assert len({row['module_impact_id'] for row in result.finding_impacts})==1


def test_findings_across_modules_remain_relative_to_each_source(pipeline):
    result=analyze(pipeline,finding(),finding('service-finding',file='services.py',start=3))
    assert result.summary['mapped_findings']==result.summary['vulnerable_modules']==2
    assert len(result.module_impacts)==2
    assert {row['finding']['file'] for row in result.finding_impacts}=={'database.py','services.py'}


def test_circular_imports_are_safe_and_seed_not_its_own_dependent(tmp_path):
    write(tmp_path,{'a.py':'import b\nvalue=1\n','b.py':'import a\n'})
    source=analyze_repository(str(tmp_path)); architecture=build_architecture_graph(source)
    result=analyze_security_impact(scan(finding(file='a.py',start=2)),source,architecture)
    analysis=result.module_impacts[0]
    assert len(analysis['direct_dependent_node_ids'])==1
    assert analysis['transitive_dependent_node_ids']==[]
    assert analysis['vulnerable_node_id'] not in analysis['direct_dependent_node_ids']
    assert all(len(set(p['node_ids']))==len(p['node_ids']) for p in analysis['paths'])


@pytest.mark.parametrize('file,reason',[('missing.py','source_file_not_in_structure'),
    ('../database.py','invalid_finding_path'),(r'C:\database.py','invalid_finding_path'),
    (r'\\host\share\database.py','invalid_finding_path')])
def test_unmapped_findings_are_preserved(pipeline,file,reason):
    result=analyze(pipeline,finding(file=file))
    assert result.summary['unmapped_findings']==1 and result.summary['mapped_findings']==0
    assert result.finding_impacts[0]['finding_id']=='finding_one'
    assert result.finding_impacts[0]['mapping_reason']==reason
    assert result.status=='partial'


def test_missing_graph_node_is_unmapped(pipeline):
    source,_=pipeline
    architecture=build_architecture_graph(source,options=GraphOptions(max_nodes=1))
    missing=next(m['file'] for m in source.modules if architecture.module_for_file(m['file']) is None)
    result=analyze_security_impact(scan(finding(file=missing,start=1)),source,architecture)
    assert result.finding_impacts[0]['mapping_reason']=='architecture_node_not_found'


def test_unparsed_finding_source_is_explicitly_unmapped(tmp_path):
    write(tmp_path,{'broken.py':'def broken(:\n'})
    source=analyze_repository(str(tmp_path)); architecture=build_architecture_graph(source)
    result=analyze_security_impact(scan(finding(file='broken.py',start=1)),source,architecture)
    assert result.status=='partial' and result.finding_impacts[0]['mapping_reason']=='source_not_parsed'


def test_unrelated_syntax_gap_keeps_positive_mapping(tmp_path):
    write(tmp_path,{'valid.py':'value=1\n','broken.py':'def broken(:\n'})
    source=analyze_repository(str(tmp_path)); architecture=build_architecture_graph(source)
    result=analyze_security_impact(scan(finding(file='valid.py',start=1)),source,architecture)
    assert result.status=='partial' and result.summary['mapped_findings']==1
    assert any(d['code']=='syntax_error' for d in result.diagnostics)


@pytest.mark.parametrize('status',['partial','error'])
def test_incomplete_scanner_coverage_preserves_positive_findings(pipeline,status):
    source,architecture=pipeline
    result=analyze_security_impact(scan(finding(),status=status),source,architecture)
    assert result.status=='partial' and result.summary['mapped_findings']==1
    assert not result.coverage['scanner_complete']


def test_failed_empty_scan_is_error_not_clean(pipeline):
    source,architecture=pipeline
    assert analyze_security_impact(scan(status='error'),source,architecture).status=='error'


def test_complete_zero_findings_is_valid_but_not_a_security_verdict(pipeline):
    source,architecture=pipeline
    result=analyze_security_impact(scan(),source,architecture)
    assert result.status=='complete' and result.summary['mapped_findings']==0
    assert 'not confirmed exploit propagation' in result.coverage['limitations'][0]


def test_windows_relative_path_normalization(pipeline):
    result=analyze(pipeline,finding(file=r'.\database.py'))
    assert result.summary['mapped_findings']==1 and result.finding_impacts[0]['finding']['file']=='database.py'


@pytest.mark.parametrize('line,end',[(100,100),(3,100)])
def test_out_of_range_findings_are_unmapped(pipeline,line,end):
    assert analyze(pipeline,finding(start=line,end=end)).finding_impacts[0]['mapping_reason']=='source_location_out_of_range'


def test_module_scope_finding_has_no_fabricated_function(pipeline):
    result=analyze(pipeline,finding(file='api.py',start=1))
    row=result.finding_impacts[0]
    assert row['enclosing_symbol']['kind']=='module' and row['enclosing_function'] is None


def test_class_scope_and_cross_function_range(pipeline):
    row=analyze(pipeline,finding(start=1,end=3)).finding_impacts[0]
    assert row['enclosing_symbol']['kind']=='class' and row['enclosing_function'] is None


@pytest.mark.parametrize('depth,expected',[(0,0),(1,1),(2,2),(3,3)])
def test_depth_limits(pipeline,depth,expected):
    result=analyze(pipeline,options=ImpactOptions(traversal=TraversalLimits(max_depth=depth)))
    module=result.module_impacts[0]
    assert len(module['dependency_distances'])==expected
    assert result.coverage['truncated']==(depth<3)


def test_node_edge_path_and_expansion_limits(pipeline):
    options=[ImpactOptions(traversal=TraversalLimits(max_nodes=1)),
        ImpactOptions(traversal=TraversalLimits(max_edges=1)),
        ImpactOptions(traversal=TraversalLimits(max_paths=1)),
        ImpactOptions(max_path_search_edges=1),ImpactOptions(max_path_expansions=1)]
    for option in options:
        result=analyze(pipeline,options=option)
        assert result.status=='partial' and result.coverage['truncated']


def test_finding_limit_does_not_silently_drop_rows(pipeline):
    result=analyze(pipeline,finding('a'),finding('b'),options=ImpactOptions(max_findings=1))
    assert len(result.finding_impacts)==2 and result.summary['unmapped_findings']==1
    assert any(row['mapping_reason']=='max_findings' for row in result.finding_impacts)


def test_module_budget_preserves_source_mapping(pipeline):
    result=analyze(pipeline,finding(),finding('second',file='services.py',start=2),options=ImpactOptions(max_modules=1))
    assert result.summary['mapped_findings']==2 and result.summary['analyzed_modules']==1
    assert result.status=='partial' and result.coverage['truncated']


def test_evidence_limits_are_explicit(pipeline):
    result=analyze(pipeline,options=ImpactOptions(max_evidence_records=1))
    assert result.coverage['truncated'] and sum(len(e['evidence']) for e in result.evidence_edges)==1
    assert any(edge['evidence_truncated'] for edge in result.evidence_edges)


def test_duplicate_finding_ids_remain_explicit_and_ambiguous(pipeline):
    result=analyze(pipeline,finding(),finding())
    assert result.summary['unmapped_findings']==2 and len({r['id'] for r in result.finding_impacts})==2
    assert all(row['mapping_reason']=='duplicate_finding_id' for row in result.finding_impacts)
    with pytest.raises(ValueError):
        result.evidence_for_finding('finding_one')


@pytest.mark.parametrize('mutation',[{'severity':[]},{'cwe':None},{'id':None},{'start_line':True},{'end_line':-1}])
def test_invalid_finding_metadata_is_reported(pipeline,mutation):
    raw=finding(); raw.update(mutation)
    result=analyze(pipeline,raw)
    assert len(result.finding_impacts)==1 and result.summary['unmapped_findings']==1


def test_invalid_finding_object_is_not_dropped(pipeline):
    result=analyze(pipeline,42)
    assert result.summary['unmapped_findings']==1 and result.finding_impacts[0]['finding_id'] is None


def test_graph_structure_mismatch_fails_closed(tmp_path,pipeline):
    source,architecture=pipeline
    write(tmp_path,{'other.py':'value=1\n'})
    other=analyze_repository(str(tmp_path))
    result=analyze_security_impact(scan(finding()),other,architecture)
    assert result.status=='error' and result.finding_impacts[0]['mapping_reason']=='graph_structure_mismatch'


def test_single_finding_selection_and_missing_id(pipeline):
    source,architecture=pipeline
    raw=scan(finding('a'),finding('b'))
    selected=analyze_finding_impact('b',raw,source,architecture)
    assert selected.summary['findings_received']==2 and selected.summary['findings_selected']==1
    assert selected.finding_impacts[0]['finding_id']=='b'
    assert analyze_finding_impact('missing',raw,source,architecture).status=='error'


def test_secret_redaction_determinism_and_input_preservation(pipeline):
    source,architecture=pipeline
    secret='SYNTHETIC-SECRET-NO-EXPORT'
    raw=finding(); raw['title']=raw['message']=secret
    raw['evidence']={'lines':secret}
    supplied=scan(raw,finding('second'))
    before=(supplied.to_dict(),source.to_dict(),architecture.to_dict())
    first=analyze_security_impact(supplied,source,architecture)
    assert secret not in json.dumps(first.to_dict())
    assert secret not in json.dumps(first.evidence_for_finding('finding_one'))
    supplied.findings.reverse()
    assert first.to_dict()==analyze_security_impact(supplied,source,architecture).to_dict()
    supplied.findings.reverse()
    assert before==(supplied.to_dict(),source.to_dict(),architecture.to_dict())


def test_evidence_package_has_only_selected_finding(pipeline):
    result=analyze(pipeline,finding('a'),finding('b'))
    package=result.evidence_for_finding('a')
    assert package['finding_impact']['finding_id']=='a'
    assert package['dependency_analysis']['vulnerable_node_id']==package['finding_impact']['vulnerable_node_id']
    with pytest.raises(KeyError):
        result.evidence_for_finding('absent')


def test_no_repeated_scan_parse_or_graph_build(pipeline,monkeypatch):
    from backend.app.analyzers import semgrep_adapter,structure_analyzer,architecture_graph
    for module,name in [(semgrep_adapter,'scan_repository'),(structure_analyzer,'analyze_repository'),
                        (architecture_graph,'build_architecture_graph')]:
        monkeypatch.setattr(module,name,lambda *a,**kw:pytest.fail('Unexpected pipeline rerun'))
    assert analyze(pipeline).summary['mapped_findings']==1


@pytest.mark.parametrize('options',[ImpactOptions(max_findings=0),ImpactOptions(max_modules=0),
    ImpactOptions(max_evidence_records=0),ImpactOptions(max_path_search_edges=0),
    ImpactOptions(traversal=TraversalLimits(max_depth=-1))])
def test_invalid_options(pipeline,options):
    with pytest.raises(ValueError):
        analyze(pipeline,options=options)


@pytest.mark.parametrize('payload',[
    {'status':'complete','findings':[],'diagnostics':None},
    {'status':[],'findings':[],'diagnostics':[]},
    {'status':'complete','findings':{},'diagnostics':[]},
])
def test_invalid_scan_envelopes_cannot_look_complete(pipeline,payload):
    source,architecture=pipeline
    result=analyze_security_impact(payload,source,architecture)
    assert result.status=='error' and result.coverage['scanner_status']=='invalid'


def test_missing_process_success_remains_incomplete(pipeline):
    source,architecture=pipeline
    supplied=scan(finding()); supplied.diagnostics=[{'code':'scanner_exit','exit_code':2}]
    result=analyze_security_impact(supplied,source,architecture)
    assert result.status=='partial' and not result.coverage['scanner_complete']


def test_stale_dependency_edges_fail_consistency_check(pipeline):
    source,architecture=pipeline
    changed=deepcopy(source)
    changed.internal_dependencies[0]['target_module_id']='not-the-original-target'
    result=analyze_security_impact(scan(finding()),changed,architecture)
    assert result.status=='error' and not result.coverage['graph_structure_consistent']


def test_diagnostic_budget_and_secret_redaction(pipeline):
    source,architecture=pipeline
    supplied=scan(finding(),status='partial')
    supplied.diagnostics=[{'code':'scanner_error','message':'SYNTHETIC-SECRET'}]*4
    result=analyze_security_impact(supplied,source,architecture,options=ImpactOptions(max_diagnostics=1))
    assert result.coverage['diagnostics_truncated'] and result.coverage['truncated']
    assert 'SYNTHETIC-SECRET' not in json.dumps(result.to_dict())


def test_per_edge_evidence_budget_marks_finding_and_module(tmp_path):
    write(tmp_path,{'database.py':'value=1\n','service.py':'import database\nimport database as db\n'})
    source=analyze_repository(str(tmp_path)); architecture=build_architecture_graph(source)
    result=analyze_security_impact(scan(finding(file='database.py',start=1)),source,architecture,
        options=ImpactOptions(max_evidence_per_edge=1))
    assert result.status=='partial' and result.evidence_edges[0]['evidence_count']==2
    assert result.evidence_edges[0]['provided_evidence_count']==1
    assert result.finding_impacts[0]['coverage']['truncated']
    assert result.module_impacts[0]['coverage']['truncated']


def test_cli_runs_each_stage_once(pipeline,monkeypatch,capsys):
    from backend.app.analyzers import impact_cli
    source,architecture=pipeline
    calls=[]
    monkeypatch.setattr(impact_cli,'scan_repository',lambda path:calls.append('scan') or scan(finding()))
    monkeypatch.setattr(impact_cli,'analyze_repository',lambda path:calls.append('ast') or source)
    monkeypatch.setattr(impact_cli,'build_architecture_graph',lambda parsed:calls.append('graph') or architecture)
    assert impact_cli.main(['fixture'])==0 and calls==['scan','ast','graph']
    assert json.loads(capsys.readouterr().out)['summary']['mapped_findings']==1


def test_empty_invalid_repository_pipeline_is_error(tmp_path):
    source=analyze_repository(str(tmp_path)); architecture=build_architecture_graph(source)
    result=analyze_security_impact(scan(status='error'),source,architecture)
    assert result.status=='error' and result.summary['findings_selected']==0


def test_unresolved_imports_make_impact_coverage_partial(tmp_path):
    write(tmp_path,{'database.py':'value=1\n','api.py':'import database\nimport unknown_package\n'})
    source=analyze_repository(str(tmp_path)); architecture=build_architecture_graph(source)
    assert source.status==architecture.status=='complete'
    result=analyze_security_impact(scan(finding(file='database.py',start=1)),source,architecture)
    assert result.status=='partial' and result.summary['mapped_findings']==1
    assert result.coverage['dependency_gaps']['unresolved_imports']==1
    assert {'code':'dependency_resolution_incomplete'} in result.diagnostics
