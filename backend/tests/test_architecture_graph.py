from copy import deepcopy
import json

import networkx as nx
import pytest

from backend.app.analyzers.architecture_graph import GraphOptions, build_architecture_graph
from backend.app.analyzers.architecture_traversal import TraversalLimits, traverse_dependencies
from backend.app.analyzers.structure_analyzer import RepositoryStructure, analyze_repository
from backend.app.analyzers.semgrep_adapter import ROOT
from backend.app.analyzers.architecture_cli import main


def structure(names=('a', 'b', 'c'), relationships=(('a', 'b'), ('b', 'c')), status='complete'):
    modules = [{'id': name, 'file': f'{name}.py', 'names': [name], 'parsed': True, 'is_package': False}
               for name in names]
    imports, dependencies = [], []
    for index, (source, target) in enumerate(relationships):
        identifier = f'import_{index}'
        imports.append({'id': identifier, 'module_id': source, 'scope_id': source,
            'file': f'{source}.py', 'start_line': index+1, 'end_line': index+1,
            'resolution': 'internal', 'candidate_module_ids': [target], 'conditional': False})
        dependencies.append({'id': f'dependency_{index}', 'source_module_id': source,
            'target_module_id': target, 'relationship': 'imports', 'import_id': identifier,
            'file': f'{source}.py', 'start_line': index+1, 'end_line': index+1})
    return RepositoryStructure('1.0.0', status, {}, [], modules, [], [], [], imports, [],
                               dependencies, [], [], [], [], [], {})


def graph(*args, **kwargs):
    return build_architecture_graph(structure(*args, **kwargs))


def test_simple_chain_and_edge_direction():
    architecture = graph()
    assert [(e['source'], e['target'], e['relationship']) for e in architecture.edges] == [
        ('a','b','imports'), ('b','c','imports')]
    assert architecture.direct_dependencies('a') == ['b']
    assert architecture.direct_dependents('c') == ['b']
    assert architecture.statistics['is_acyclic']
    assert architecture.statistics['weak_component_count'] == 1


def test_fan_metrics_are_unique_neighbor_counts():
    architecture = graph(relationships=(('a','b'), ('a','b'), ('c','b')))
    nodes = {n['id']: n for n in architecture.nodes}
    assert nodes['a']['fan_out'] == 1 and nodes['b']['fan_in'] == 2
    assert architecture.statistics['import_evidence_count'] == 3
    assert architecture.statistics['edge_count'] == 2


def test_duplicate_import_pairs_retain_all_evidence():
    architecture = graph(relationships=(('a','b'), ('a','b')))
    assert len(architecture.edges) == 1
    edge = architecture.edges[0]
    assert edge['evidence_count'] == 2
    assert {e['start_line'] for e in edge['evidence']} == {1,2}
    assert all(e['resolution'] == 'internal' for e in edge['evidence'])


def test_exact_duplicate_dependency_records_are_removed():
    source = structure()
    source.internal_dependencies += deepcopy(source.internal_dependencies)
    architecture = build_architecture_graph(source)
    assert len(architecture.edges) == 2
    assert architecture.coverage['duplicate_dependency_records_removed'] == 2


def test_cycle_scc_and_evidence_witness():
    architecture = graph(relationships=(('a','b'), ('b','c'), ('c','a')))
    stats = architecture.statistics
    assert not stats['is_acyclic']
    assert stats['cyclic_component_count'] == stats['strong_component_count'] == 1
    witness = stats['cyclic_components'][0]['witness']
    assert witness['node_ids'] == ['a','b','c','a']
    assert set(witness['edge_ids']) == {e['id'] for e in architecture.edges}
    traversed = architecture.transitive_dependencies('a')
    assert [n['id'] for n in traversed.nodes] == ['b','c']
    assert not traversed.truncated


def test_self_import_is_cyclic_not_isolated():
    architecture = graph(names=('a',), relationships=(('a','a'),))
    assert architecture.statistics['cyclic_component_count'] == 1
    assert architecture.statistics['self_import_count'] == 1
    assert architecture.statistics['isolated_modules'] == []
    assert architecture.statistics['cyclic_components'][0]['witness']['node_ids'] == ['a','a']
    assert architecture.transitive_dependencies('a').nodes == []


def test_disconnected_components_and_isolation():
    architecture = graph(names=('a','b','c','d','alone'), relationships=(('a','b'), ('c','d')))
    assert architecture.statistics['weak_component_count'] == 3
    assert architecture.statistics['isolated_modules'] == ['alone']
    assert sorted(c['size'] for c in architecture.statistics['weak_components']) == [1,2,2]


def test_reverse_traversal_paths_use_actual_import_direction():
    architecture = graph()
    traversal = architecture.reverse_dependencies('c')
    assert traversal.direction == 'incoming'
    assert traversal.nodes == [{'id':'b','depth':1},{'id':'a','depth':2}]
    path = next(p for p in traversal.paths if p['target_id'] == 'a')
    assert path['node_ids'] == ['a','b','c']
    evidence = {e['id']: e for e in traversal.evidence_edges}
    assert [(evidence[e]['source'],evidence[e]['target']) for e in path['edge_ids']] == [('a','b'),('b','c')]


def test_outgoing_transitive_shortest_paths():
    architecture = graph(names=('a','b','c','d'), relationships=(('a','b'),('a','c'),('b','d'),('c','d')))
    traversal = architecture.transitive_dependencies('a')
    assert next(p for p in traversal.paths if p['target_id']=='d')['node_ids'] == ['a','b','d']
    assert len({edge['id'] for edge in traversal.evidence_edges}) == len(traversal.evidence_edges)


@pytest.mark.parametrize('depth,count,truncated', [(0,0,True), (1,1,True), (2,2,False), (3,2,False)])
def test_depth_limits(depth,count,truncated):
    result = graph().transitive_dependencies('a', limits=TraversalLimits(max_depth=depth))
    assert len(result.nodes) == count and result.truncated == truncated
    assert result.examined_edges <= 2


def test_node_edge_and_path_budgets():
    architecture = graph()
    assert architecture.transitive_dependencies('a', limits=TraversalLimits(max_nodes=1)).limit_reasons == ['max_nodes']
    assert architecture.transitive_dependencies('a', limits=TraversalLimits(max_edges=1)).limit_reasons == ['max_edges']
    limited = architecture.transitive_dependencies('a', limits=TraversalLimits(max_paths=1))
    assert len(limited.nodes) == 2 and len(limited.paths) == 1 and limited.limit_reasons == ['max_paths']


@pytest.mark.parametrize('limits', [TraversalLimits(max_depth=-1),TraversalLimits(max_depth=257),
    TraversalLimits(max_depth=True), TraversalLimits(max_nodes=0),TraversalLimits(max_edges=0),TraversalLimits(max_paths=0)])
def test_invalid_traversal_budgets(limits):
    with pytest.raises(ValueError):
        graph().transitive_dependencies('a',limits=limits)


def test_missing_node_and_invalid_direction():
    with pytest.raises(KeyError):
        graph().direct_dependencies('missing')
    with pytest.raises(KeyError):
        graph().reverse_dependencies('missing')
    with pytest.raises(ValueError):
        traverse_dependencies(graph(),'a',direction='sideways')


def test_windows_module_lookup_and_path_validation():
    source = structure()
    source.modules[0]['file'] = 'src/app/a.py'
    source.imports[0]['file'] = source.internal_dependencies[0]['file'] = 'src/app/a.py'
    architecture = build_architecture_graph(source)
    assert architecture.module_for_file(r'src\app\a.py')['id'] == 'a'
    assert architecture.module_for_file('missing.py') is None


@pytest.mark.parametrize('path', ['../a.py',r'..\a.py',r'C:\a.py',r'C:a.py',r'\\host\share\a.py','/a.py','',None])
def test_invalid_lookup_paths(path):
    with pytest.raises(ValueError):
        graph().module_for_file(path)


def test_unresolved_imports_never_create_edges():
    source = structure()
    source.imports[0]['resolution'] = 'unresolved'
    source.imports[0]['candidate_module_ids'] = []
    architecture = build_architecture_graph(source)
    assert [(e['source'],e['target']) for e in architecture.edges] == [('b','c')]
    assert architecture.status == 'partial' and architecture.coverage['unresolved_imports'] == 1


def test_dangling_and_forged_evidence_is_rejected():
    source = structure()
    source.internal_dependencies[0]['target_module_id'] = 'absent'
    source.internal_dependencies[1]['file'] = '../outside.py'
    architecture = build_architecture_graph(source)
    assert architecture.edges == [] and architecture.status == 'partial'
    assert all(d['code']=='invalid_or_dangling_dependency_skipped' for d in architecture.diagnostics)


def test_partial_structure_is_preserved():
    source = structure(status='partial')
    source.modules[2]['parsed'] = False
    source.diagnostics = [{'code':'syntax_error','file':'c.py','message':'must not export raw source'}]
    architecture = build_architecture_graph(source)
    assert architecture.status == 'partial'
    assert architecture.coverage['unparsed_modules'] == 1
    assert not architecture.edges[-1]['evidence'][0]['target_parsed']
    assert 'must not export' not in json.dumps(architecture.to_dict())


@pytest.mark.parametrize('status', ['complete','error','partial'])
def test_empty_graph_safe(status):
    architecture = graph(names=(),relationships=(),status=status)
    assert architecture.status == status
    assert architecture.nodes == architecture.edges == []
    assert architecture.statistics['node_count'] == architecture.statistics['weak_component_count'] == 0
    assert architecture.statistics['is_acyclic']


def test_stable_ids_and_ordering_and_no_input_mutation():
    source = structure(relationships=(('a','b'),('a','b'),('b','c')))
    original = source.to_dict()
    first = build_architecture_graph(source).to_dict()
    assert source.to_dict() == original
    source.modules.reverse(); source.imports.reverse(); source.internal_dependencies.reverse()
    assert build_architecture_graph(source).to_dict() == first


def test_classifications_confirmed_before_heuristics():
    source = structure()
    source.classifications = [
        {'module_id':'a','component':'service','confidence':'inferred','reason':'filename_heuristic','evidence':{'file':'a.py'}},
        {'module_id':'a','component':'controller','confidence':'confirmed','reason':'framework_route_decorator',
         'evidence':{'file':'a.py','start_line':1,'end_line':1}},
        {'module_id':'b','component':'data_access','confidence':'inferred','reason':'filename_heuristic','evidence':{'file':'b.py'}}]
    architecture = build_architecture_graph(source)
    nodes = {n['id']:n for n in architecture.nodes}
    assert nodes['a']['type']=='controller' and nodes['a']['classification_confidence']=='confirmed'
    assert nodes['b']['type']=='data_access' and nodes['b']['classification_confidence']=='inferred'
    assert nodes['c']['type']=='unclassified'


def test_entry_point_filename_is_only_inferred():
    source = structure(names=('main',),relationships=())
    node = build_architecture_graph(source).nodes[0]
    assert node['type']=='application_entry_point' and node['classification_confidence']=='inferred'


def test_networkx_copy_cannot_modify_internal_graph():
    architecture = graph()
    copied = architecture.networkx_graph
    assert isinstance(copied,nx.DiGraph)
    with pytest.raises(nx.NetworkXError):
        copied.add_node('not-allowed')
    copied.nodes['a']['file']='changed.py'
    assert architecture.module_for_file('a.py')['file']=='a.py'


@pytest.mark.parametrize('options', [GraphOptions(max_nodes=0),GraphOptions(max_edges=0),GraphOptions(max_evidence_records=0)])
def test_invalid_graph_limits(options):
    with pytest.raises(ValueError):
        build_architecture_graph(structure(),options=options)


@pytest.mark.parametrize('options,code', [(GraphOptions(max_nodes=1),'graph_node_limit'),
    (GraphOptions(max_edges=1),'graph_edge_limit'),(GraphOptions(max_evidence_records=1),'graph_evidence_limit')])
def test_graph_limits_report_partial(options,code):
    architecture=build_architecture_graph(structure(),options=options)
    assert architecture.status=='partial' and any(d['code']==code for d in architecture.diagnostics)
    ids={n['id'] for n in architecture.nodes}
    assert all(e['source'] in ids and e['target'] in ids for e in architecture.edges)


def test_duplicate_and_invalid_module_records_do_not_create_duplicate_nodes():
    source=structure()
    source.modules.extend([deepcopy(source.modules[0]),{'id':'bad','file':'../escape.py'}])
    architecture=build_architecture_graph(source)
    assert len(architecture.nodes)==len({n['id'] for n in architecture.nodes})==3
    assert architecture.status=='partial'


def test_conflicting_duplicate_modules_are_deterministic():
    source=structure()
    conflicting=deepcopy(source.modules[0]); conflicting['names']=['conflicting']
    source.modules.append(conflicting)
    first=build_architecture_graph(source).to_dict()
    source.modules.reverse()
    assert build_architecture_graph(source).to_dict()==first
    assert first['status']=='partial'


def test_conflicting_import_records_are_not_arbitrarily_chosen():
    source=structure()
    conflicting=deepcopy(source.imports[0]); conflicting['start_line']=100
    source.imports.append(conflicting)
    first=build_architecture_graph(source).to_dict()
    source.imports.reverse()
    assert build_architecture_graph(source).to_dict()==first
    assert first['status']=='partial' and len(first['edges'])==1


@pytest.mark.parametrize('component,type_name', [('api_application','application_entry_point'),
    ('router','router'),('controller','controller'),('service','service'),('data_access','data_access'),
    ('database_model','database_model'),('authentication','authentication'),('configuration','configuration'),
    ('utility','utility'),('test','test')])
def test_all_supported_component_roles(component,type_name):
    source=structure()
    source.classifications=[{'module_id':'a','component':component,'confidence':'inferred',
                            'reason':'filename_heuristic','evidence':{'file':'a.py'}}]
    node=build_architecture_graph(source).module_for_file('a.py')
    assert node['type']==type_name and node['classification_confidence']=='inferred'


def test_large_cycle_witness_is_bounded_and_nonrecursive():
    names=tuple(f'm{i}' for i in range(1100))
    architecture=graph(names=names,relationships=tuple(zip(names,names[1:]+names[:1])))
    assert architecture.statistics['cyclic_component_count']==1
    assert len(architecture.statistics['cyclic_components'][0]['witness']['node_ids'])==1101


def test_no_source_literals_or_unselected_metadata_are_forwarded():
    source=structure()
    source.modules[0]['secret']='SYNTHETIC-SECRET-NEVER-EXPORT'
    source.internal_dependencies[0]['message']='SYNTHETIC-SECRET-NEVER-EXPORT'
    assert 'SYNTHETIC-SECRET-NEVER-EXPORT' not in json.dumps(build_architecture_graph(source).to_dict())


def test_graph_never_reparses_or_executes_source(monkeypatch):
    from backend.app.analyzers import structure_analyzer
    monkeypatch.setattr(structure_analyzer,'analyze_repository',lambda path: pytest.fail('Unexpected parse'))
    assert build_architecture_graph(structure()).statistics['node_count']==3


@pytest.mark.parametrize('value', ['repo/path',{},None])
def test_requires_structure_object(value):
    with pytest.raises(TypeError):
        build_architecture_graph(value)


def test_representative_structure_fixture_statistics():
    architecture=build_architecture_graph(analyze_repository(str(ROOT/'fixtures/structure_demo')))
    stats=architecture.statistics
    assert architecture.status=='partial'
    assert (stats['node_count'],stats['edge_count'],stats['isolated_module_count'])==(13,7,6)
    assert stats['cyclic_component_count']==1 and stats['strong_component_count']==12
    assert stats['weak_component_count']==7
    assert stats['max_fan_in']==4 and stats['max_fan_out']==2
    assert all(e['evidence_count']>=1 for e in architecture.edges)


def test_multilayer_components_from_real_ast(tmp_path):
    files={'app.py':'from fastapi import FastAPI\nfrom api import router\napp=FastAPI()\n',
        'api.py':'from fastapi import APIRouter\nfrom services import work\nrouter=APIRouter()\n'
        '@router.get("/private")\ndef endpoint():\n    return work()\n',
        'services.py':'from repositories import fetch\ndef work():\n    return fetch()\n',
        'repositories.py':'import sqlite3\ndef fetch():\n    return sqlite3.connect(":memory:")\n'}
    for file,text in files.items():
        (tmp_path/file).write_text(text)
    architecture=build_architecture_graph(analyze_repository(str(tmp_path)))
    assert architecture.status=='complete'
    nodes={n['file']:n for n in architecture.nodes}
    assert [nodes[f]['type'] for f in files]==['application_entry_point','router','service','data_access']
    assert len(architecture.edges)==3


def test_thousand_module_chain_is_iterative_and_bounded():
    names=tuple(f'm{i}' for i in range(1000))
    architecture=graph(names=names,relationships=tuple(zip(names,names[1:])))
    assert architecture.statistics['node_count']==1000 and architecture.statistics['edge_count']==999
    reached=architecture.transitive_dependencies('m0')
    assert len(reached.nodes)==32 and reached.limit_reasons==['max_depth']


def test_cli_parses_once_and_prints_json(monkeypatch,capsys):
    from backend.app.analyzers import architecture_cli
    calls=[]
    monkeypatch.setattr(architecture_cli,'analyze_repository',lambda path: calls.append(path) or structure())
    assert main(['fixture'])==0
    assert calls==['fixture'] and json.loads(capsys.readouterr().out)['statistics']['node_count']==3


def test_graph_json_contract_including_legacy_minimum():
    import jsonschema
    schema=json.loads((ROOT/'contracts/architecture-graph-v1.schema.json').read_text())
    architecture=graph()
    jsonschema.Draft202012Validator(schema).validate(architecture.to_dict())
    minimum={'nodes':[{k:n[k] for k in ('id','label','type','file')} for n in architecture.nodes],
             'edges':[{k:e[k] for k in ('source','target','relationship')} for e in architecture.edges]}
    jsonschema.Draft202012Validator(schema).validate(minimum)
    assert json.loads(json.dumps(architecture.to_dict()))==architecture.to_dict()


def test_representative_json_matches_actual_graph():
    expected=json.loads((ROOT/'contracts/examples/architecture-graph-v1.json').read_text())
    architecture=build_architecture_graph(analyze_repository(str(ROOT/'fixtures/structure_demo')))
    assert architecture.to_dict()==expected
