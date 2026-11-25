"""End-to-end unified pipeline unit and native Semgrep integration tests."""
import json
import os

import jsonschema
import pytest

from backend.app.analyzers.architecture_policy import load_policy
from backend.app.analyzers.pipeline import PipelineOptions, main as pipeline_cli_main, run_analysis_pipeline
from backend.app.analyzers.semgrep_adapter import ROOT, scan_repository


def test_unified_pipeline_skip_scan_and_empty_repo(tmp_path):
    empty = tmp_path / 'empty'
    empty.mkdir()
    res_empty = run_analysis_pipeline(str(empty), options=PipelineOptions(include_scan=False))
    assert res_empty.status == 'error'

    res_rules = run_analysis_pipeline(
        str(ROOT / 'fixtures/architecture_rules_demo'),
        policy=load_policy(ROOT / 'contracts/examples/architecture-policy-v1.json'),
        options=PipelineOptions(include_scan=False),
    )
    assert res_rules.status == 'partial'
    assert res_rules.timings_ms['total_ms'] >= 0.0
    assert res_rules.architecture_evaluation.summary['total_observations'] == 5
    gemini = res_rules.gemini_context()
    assert 'untrusted' in gemini['safety_notice'].lower()
    assert gemini['architecture_evidence']['observations']

    schema = json.loads((ROOT / 'contracts/unified-pipeline-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(res_rules.to_dict())


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION') != '1',
    reason='Requires native Semgrep outside restricted sandbox',
)
def test_native_spring_boot_end_to_end():
    res = run_analysis_pipeline(str(ROOT / 'fixtures/spring_boot_demo'))
    assert res.status == 'complete'
    assert res.profile['languages'] == ['java']
    assert {'spring_boot', 'spring_mvc'} <= set(res.profile['frameworks'])
    assert 'maven' in res.profile['package_managers']

    # Native Semgrep SQL concatenation finding in OrderRepository.java
    assert res.scan.summary['total'] == 1
    assert res.scan.findings[0]['rule_id'] == 'codely.java.sql-concatenation'
    assert res.impact.summary['mapped_findings'] == 1
    row = res.impact.finding_impacts[0]
    assert row['enclosing_function']['qualified_name'] == 'OrderRepository.findByStatus'
    by_id = {n['id']: n['file'] for n in res.architecture.nodes}
    assert {by_id[n] for n in row['direct_dependent_node_ids']} == {'src/main/java/com/example/orders/OrderService.java'}
    assert {by_id[n] for n in row['transitive_dependent_node_ids']} == {'src/main/java/com/example/orders/OrderController.java'}
    assert all('UnrelatedHealthController' not in n['file'] for n in res.impact.node_contexts)

    chk = {c['key']: c['status'] for c in res.checklist.checks}
    assert chk['unsafe-sql'] == 'FAIL'
    assert chk['dependency-manifest'] == 'PASS'
    assert chk['test-presence'] == 'PASS'


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION') != '1',
    reason='Requires native Semgrep outside restricted sandbox',
)
def test_native_express_end_to_end():
    res = run_analysis_pipeline(str(ROOT / 'fixtures/express_demo'))
    assert res.status == 'complete'
    assert res.profile['languages'] == ['javascript']
    assert 'express' in res.profile['frameworks']
    rule_ids = {f['rule_id'] for f in res.scan.findings}
    assert {'codely.web.sql-concatenation', 'codely.web.insecure-cookie', 'codely.web.open-redirect'} <= rule_ids
    sql_impact = next(i for i in res.impact.finding_impacts if i['finding']['rule_id'] == 'codely.web.sql-concatenation')
    by_id = {n['id']: n['file'] for n in res.architecture.nodes}
    assert {by_id[n] for n in sql_impact['direct_dependent_node_ids']} == {'src/services/userService.js'}
    assert {by_id[n] for n in sql_impact['transitive_dependent_node_ids']} == {'src/routes/users.js'}
    assert all('formatters.js' not in n['file'] for n in res.impact.node_contexts)


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION') != '1',
    reason='Requires native Semgrep outside restricted sandbox',
)
def test_native_fullstack_mixed_language_end_to_end(capsys):
    res = run_analysis_pipeline(
        str(ROOT / 'fixtures/fullstack_demo'),
        policy=load_policy(ROOT / 'contracts/examples/architecture-policy-v1.json'),
    )
    assert res.status == 'complete'
    assert {'python', 'tsx'} <= set(res.profile['languages'])
    assert {'fastapi', 'react'} <= set(res.profile['frameworks'])

    rule_ids = {f['rule_id'] for f in res.scan.findings}
    assert {'codely.python.sql-injection', 'codely.web.dangerously-set-inner-html'} <= rule_ids

    # Cross-language potential_api_call + React component reference edges present
    edge_rels = {e['relationship'] for e in res.architecture.edges}
    assert {'imports', 'references_component', 'potential_api_call'} <= edge_rels

    # ASIM maps Python SQLi across backend chain AND surfaces inferred React API caller
    py_impact = next(i for i in res.impact.finding_impacts if i['finding']['rule_id'] == 'codely.python.sql-injection')
    mod_impact = next(m for m in res.impact.module_impacts if m['id'] == py_impact['module_impact_id'])
    inferred_files = {
        next(n['file'] for n in res.architecture.nodes if n['id'] == rel['node_id'])
        for rel in mod_impact.get('inferred_relationships', [])
    }
    assert 'frontend/src/components/OrderList.tsx' in inferred_files
    assert all('unrelated.py' not in n['file'] for n in res.impact.node_contexts)

    # Frontend & Gemini payloads validate and expose no secret literals
    frontend = res.frontend_payload(project_id='demo-fullstack')
    assert frontend['architecture']['graph_type'] == 'dependencies'
    assert frontend['architecture']['project_id'] == 'demo-fullstack'
    gemini = res.gemini_context()
    assert len(gemini['security_findings']) == 2
    assert 'SELECT id FROM orders' not in json.dumps(gemini)

    schema = json.loads((ROOT / 'contracts/unified-pipeline-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(res.to_dict())
    example_payload = json.loads((ROOT / 'contracts/examples/unified-pipeline-v1.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(example_payload)
    actual_no_timing = {k: v for k, v in res.to_dict().items() if k != 'timings_ms'}
    expected_no_timing = {k: v for k, v in example_payload.items() if k != 'timings_ms'}
    assert actual_no_timing == expected_no_timing

    assert pipeline_cli_main([str(ROOT / 'fixtures/fullstack_demo'), '--gemini-context']) == 0
    cli_out = json.loads(capsys.readouterr().out)
    assert cli_out['repository_profile']['languages'] == res.profile['languages']


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION') != '1',
    reason='Requires native Semgrep outside restricted sandbox',
)
def test_native_new_java_and_web_rules_positive_and_negative(tmp_path):
    (tmp_path / 'SafeController.java').write_text(
        'class SafeController {\n'
        '  void handle(javax.servlet.http.Cookie c) {\n'
        '    c.setHttpOnly(true);\n'
        '    c.setSecure(true);\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )
    (tmp_path / 'UnsafeController.java').write_text(
        'class UnsafeController {\n'
        '  Object handle(javax.servlet.http.Cookie c, String next, javax.servlet.http.HttpServletResponse resp) throws Exception {\n'
        '    c.setHttpOnly(false);\n'
        '    resp.sendRedirect("/app/" + next);\n'
        '    return new ModelAndView("redirect:" + next);\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )
    (tmp_path / 'safe.tsx').write_text('export function Safe({ text }: { text: string }) { return <div>{text}</div>; }\n', encoding='utf-8')
    (tmp_path / 'unsafe.tsx').write_text('export function Unsafe({ html }: { html: string }) { return <div dangerouslySetInnerHTML={{ __html: html }} />; }\n', encoding='utf-8')

    scan = scan_repository(str(tmp_path))
    assert scan.status == 'complete'
    by_file = {}
    for f in scan.findings:
        by_file.setdefault(f['file'], set()).add(f['rule_id'])
    assert 'SafeController.java' not in by_file
    assert 'safe.tsx' not in by_file
    assert {'codely.java.insecure-cookie', 'codely.java.open-redirect'} <= by_file['UnsafeController.java']
    assert 'codely.web.dangerously-set-inner-html' in by_file['unsafe.tsx']
