from pathlib import Path
import json

import jsonschema
import pytest

from ai_intelligence.system_graph import analyze_system


BASE = Path(__file__).parent
FIXTURE = BASE / 'fixtures/system_graph'


def test_system_graph_is_grounded_and_stable():
    pytest.importorskip('tree_sitter_java')
    pytest.importorskip('tree_sitter_typescript')
    graph = analyze_system(FIXTURE)
    schema = json.loads((BASE.parent / 'contracts/system-architecture-v1.schema.json').read_text())
    jsonschema.validate(graph, schema)
    assert graph == analyze_system(FIXTURE)
    assert graph['status'] == 'partial'
    assert {'code': 'unresolved_api_route'} in graph['diagnostics']
    nodes = {item['id']: item for item in graph['nodes']}
    assert {'backend', 'frontend', 'controller', 'service', 'repository', 'database', 'external_api'} <= {
        item['type'] for item in nodes.values()
    }
    assert any(item['type'] == 'routing' for node in nodes.values() for item in node.get('capabilities', []))
    for edge in graph['edges']:
        assert edge['source'] in nodes and edge['target'] in nodes
        for source in edge['evidence']:
            file = FIXTURE / source['file']
            assert 1 <= source['start_line'] <= source['end_line'] <= len(file.read_text().splitlines())
    api, = [edge for edge in graph['edges'] if edge['relationship'] == 'api_route_reference']
    assert api['confidence'] == 'inferred'
    assert len(api['evidence']) == 2
    assert nodes[api['target']]['type'] == 'controller'
    assert any(edge['relationship'] == 'constructor_dependency' for edge in graph['edges'])
    assert any(edge['relationship'] == 'imports' for edge in graph['edges'])


def test_unsupported_returns_no_invented_components(tmp_path):
    (tmp_path / 'sample.py').write_text('pass\n')
    graph = analyze_system(tmp_path)
    assert graph['status'] == 'unsupported'
    assert graph['nodes'] == [] and graph['edges'] == []
