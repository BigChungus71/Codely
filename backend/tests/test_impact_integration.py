"""Actual native Semgrep -> AST -> graph -> ASIM. Static fixtures never run."""
import json
import os

import jsonschema
import pytest

from backend.app.analyzers.semgrep_adapter import ROOT, scan_repository
from backend.app.analyzers.structure_analyzer import analyze_repository
from backend.app.analyzers.architecture_graph import build_architecture_graph
from backend.app.analyzers.impact_analyzer import analyze_security_impact


pytestmark=[pytest.mark.integration,pytest.mark.skipif(
    os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION')!='1',
    reason='Requires real native Semgrep outside restricted sandbox')]


@pytest.fixture(scope='module')
def actual_pipeline():
    target=ROOT/'fixtures/impact_demo'
    scan=scan_repository(str(target))
    assert scan.status=='complete' and scan.summary['total']==1,scan.diagnostics
    assert scan.findings[0]['rule_id']=='codely.python.sql-injection'
    source=analyze_repository(str(target))
    graph=build_architecture_graph(source)
    assert source.status==graph.status=='complete'
    impact=analyze_security_impact(scan,source,graph)
    return scan,source,graph,impact


def test_real_end_to_end_mapping(actual_pipeline):
    scan,source,graph,impact=actual_pipeline
    assert impact.status=='complete'
    assert impact.summary['mapped_findings']==1 and impact.summary['unmapped_findings']==0
    row=impact.finding_impacts[0]
    assert row['finding_id']==scan.findings[0]['id']
    assert row['finding']['severity']=='HIGH' and row['finding']['cwe']==['CWE-89']
    assert row['finding']['file']=='database.py' and row['finding']['start_line']==11
    assert row['enclosing_function']['qualified_name']=='Repository.lookup'
    assert row['enclosing_class']['name']=='Repository'


def test_real_dependent_components_exclude_unrelated_modules(actual_pipeline):
    _scan,_source,graph,impact=actual_pipeline
    row=impact.finding_impacts[0]
    by_id={node['id']:node['file'] for node in graph.nodes}
    assert {by_id[node] for node in row['direct_dependent_node_ids']}=={'services.py'}
    assert {by_id[node] for node in row['transitive_dependent_node_ids']}=={'api.py','app.py','cycle.py'}
    assert {node['file'] for node in impact.node_contexts}=={'database.py','services.py','api.py','app.py','cycle.py'}
    assert graph.statistics['cyclic_component_count']==1
    assert len(impact.module_impacts[0]['paths'])==4 and len(impact.evidence_edges)==4


def test_real_payload_schema_and_representative_json(actual_pipeline):
    scan,_source,_graph,impact=actual_pipeline
    payload=impact.to_dict()
    schema=json.loads((ROOT/'contracts/security-impact-v1.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(payload)
    expected=json.loads((ROOT/'contracts/examples/security-impact-v1.json').read_text())
    assert payload==expected
    package=impact.evidence_for_finding(scan.findings[0]['id'])
    assert package['dependency_analysis']['summary']['transitive_dependents']==3
    assert 'statement' not in json.dumps(package)
