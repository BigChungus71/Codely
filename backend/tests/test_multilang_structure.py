"""Multi-language structural, graph, checklist, ASIM and architecture rules tests."""
import json

import jsonschema
import pytest

from backend.app.analyzers.architecture_graph import build_architecture_graph
from backend.app.analyzers.architecture_policy import ArchitecturePolicy, ArchitectureThresholds, LayerPolicy
from backend.app.analyzers.architecture_rules import evaluate_architecture
from backend.app.analyzers.impact_analyzer import analyze_security_impact
from backend.app.analyzers.semgrep_adapter import ROOT, ScanResult
from backend.app.analyzers.structure_analyzer import analyze_repository
from backend.app.checklists import evaluate_repository


def write_repo(root, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')


def test_java_spring_boot_extraction_inheritance_and_resolution(tmp_path):
    write_repo(
        tmp_path,
        {
            'pom.xml': '<project><dependencies><dependency><artifactId>spring-boot-starter-web</artifactId><version>3.2.5</version></dependency></dependencies></project>\n',
            'src/main/resources/application.yml': 'server:\n  port: 8080\n',
            'src/main/java/com/acme/BaseEntity.java': 'package com.acme;\npublic class BaseEntity {}\n',
            'src/main/java/com/acme/Auditable.java': 'package com.acme;\npublic interface Auditable {}\n',
            'src/main/java/com/acme/OrderRepo.java': (
                'package com.acme;\n'
                'import org.springframework.stereotype.Repository;\n'
                '@Repository\n'
                'public class OrderRepo extends BaseEntity implements Auditable {\n'
                '    public OrderRepo() {}\n'
                '    public String find(String id) { return id; }\n'
                '}\n'
            ),
            'src/main/java/com/acme/OrderController.java': (
                'package com.acme;\n'
                'import org.springframework.web.bind.annotation.RestController;\n'
                'import org.springframework.web.bind.annotation.GetMapping;\n'
                'import com.acme.OrderRepo;\n'
                '@RestController\n'
                'public class OrderController {\n'
                '    private final OrderRepo repo = new OrderRepo();\n'
                '    @GetMapping("/api/orders")\n'
                '    public String list() { return repo.find("1"); }\n'
                '}\n'
            ),
        },
    )
    structure = analyze_repository(str(tmp_path))
    assert structure.status == 'complete'
    assert structure.coverage['supported_language'] == 'multi'
    assert 'java' in structure.coverage['languages']
    assert 'spring_boot' in structure.coverage['frameworks']
    assert 'spring_mvc' in structure.coverage['frameworks']
    assert 'maven' in structure.coverage['package_managers']
    assert {'yaml', 'manifest'} <= set(structure.coverage['config_file_kinds'])

    schema = json.loads((ROOT / 'contracts/repository-structure-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(schema).validate(structure.to_dict())

    repo_cls = next(c for c in structure.classes if c['name'] == 'OrderRepo')
    assert repo_cls['bases'][0]['relation'] == 'extends'
    assert repo_cls['bases'][1]['relation'] == 'implements'
    assert repo_cls['bases'][0]['target_symbol_id'] is not None
    assert repo_cls['bases'][1]['target_symbol_id'] is not None

    graph = build_architecture_graph(structure)
    assert graph.status == 'complete'
    rels = {e['relationship'] for e in graph.edges}
    assert {'imports', 'inherits', 'implements'} <= rels
    arch_schema = json.loads((ROOT / 'contracts/architecture-graph-v1.schema.json').read_text(encoding='utf-8'))
    jsonschema.Draft202012Validator(arch_schema).validate(graph.to_dict())


def test_ts_tsx_path_aliases_index_nestjs_react_and_config_profiling(tmp_path):
    write_repo(
        tmp_path,
        {
            'package.json': json.dumps({'dependencies': {'react': '18.3.1', '@nestjs/core': '10.0.0', 'next': '14.2.0'}}),
            'tsconfig.json': '// comment\n{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}\n',
            'src/styles/app.css': 'body { color: #111; }\n',
            'src/public/index.html': '<html><body></body></html>\n',
            'src/db/schema.sql': 'CREATE TABLE items (id INT);\n',
            'src/components/ui/index.tsx': 'import React from "react";\nexport function Card() { return <div />; }\n',
            'src/app/page.tsx': (
                'import React from "react";\n'
                'import "next/link";\n'
                'import { Card } from "@/components/ui";\n'
                'export default function HomePage() {\n'
                '    fetch("/api/items");\n'
                '    return <Card />;\n'
                '}\n'
            ),
            'src/api/items.controller.ts': (
                'import { Controller, Get } from "@nestjs/common";\n'
                '@Controller("/api")\n'
                'export class ItemsController {\n'
                '    @Get("/items")\n'
                '    findAll(a: string, b: string, c: string, d: string) { return [a, b, c, d]; }\n'
                '}\n'
            ),
        },
    )
    structure = analyze_repository(str(tmp_path))
    assert structure.status == 'complete'
    assert {'tsx', 'typescript'} <= set(structure.coverage['languages'])
    assert {'react', 'nextjs', 'nestjs'} <= set(structure.coverage['frameworks'])
    assert {'css', 'html', 'sql', 'manifest'} <= set(structure.coverage['config_file_kinds'])

    graph = build_architecture_graph(structure)
    rels = {(e['relationship'], e.get('confidence')) for e in graph.edges}
    assert ('imports', None) in rels
    assert ('references_component', 'confirmed') in rels
    assert ('potential_api_call', 'inferred') in rels

    # Phase 7 architecture rules work on TypeScript parameters without assuming layered architecture
    policy = ArchitecturePolicy(thresholds=ArchitectureThresholds(max_function_parameters=3))
    eval_res = evaluate_architecture(structure, graph, policy=policy)
    assert any(o['rule_id'] == 'CODELY-ARCH-009' for o in eval_res.observations)


def test_multilang_syntax_error_partial_and_unresolved_imports(tmp_path):
    write_repo(
        tmp_path,
        {
            'broken.ts': 'export function bad( { return ;;;\n',
            'missing.js': 'const helper = require("./does_not_exist");\n',
        },
    )
    structure = analyze_repository(str(tmp_path))
    assert structure.status == 'partial'
    assert any(d['code'] == 'syntax_error' and d['file'] == 'broken.ts' for d in structure.diagnostics)
    graph = build_architecture_graph(structure)
    eval_res = evaluate_architecture(structure, graph)
    assert eval_res.status == 'partial'
    assert any(o['rule_id'] == 'CODELY-ARCH-012' for o in eval_res.observations)


def test_multilang_asim_and_checklist_with_supplied_java_web_findings(tmp_path):
    write_repo(
        tmp_path,
        {
            'package.json': json.dumps({'dependencies': {'express': '4.19.2'}}),
            'package-lock.json': '{"lockfileVersion": 3}\n',
            'Dockerfile': 'FROM node:20-alpine\nUSER node\n',
            '.gitignore': '.env\n*.key\n',
            'src/repo.js': 'function queryUsers(id) {\n  return db.query("SELECT * FROM users WHERE id = " + id);\n}\nmodule.exports = { queryUsers };\n',
            'src/service.js': 'const repo = require("./repo");\nfunction getUser(id) { return repo.queryUsers(id); }\nmodule.exports = { getUser };\n',
            'src/unrelated.js': 'function ping() { return "ok"; }\n',
            'src/service.test.js': 'test("ok", () => {});\n',
        },
    )
    scan = ScanResult('complete')
    scan.findings = [
        {
            'id': 'finding_js_sql',
            'rule_id': 'codely.web.sql-concatenation',
            'source': 'semgrep',
            'severity': 'MEDIUM',
            'title': 'Concatenated SQL query in JS/TS',
            'file': 'src/repo.js',
            'start_line': 2,
            'end_line': 2,
            'message': 'Review concatenated SQL query construction.',
            'cwe': ['CWE-89'],
        }
    ]
    scan.summary['total'] = scan.summary['medium'] = 1
    scan.diagnostics = [{'code': 'coverage', 'rule_set': 'web-security-v1'}, {'code': 'scanner_exit', 'exit_code': 0}]
    scan.coverage = {'status': 'complete', 'rule_sets': ['web-security-v1']}

    structure = analyze_repository(str(tmp_path))
    graph = build_architecture_graph(structure)
    impact = analyze_security_impact(scan, structure, graph)
    assert impact.status == 'complete'
    assert impact.summary['mapped_findings'] == 1
    row = impact.finding_impacts[0]
    assert row['enclosing_function']['qualified_name'] == 'queryUsers'
    by_id = {n['id']: n['file'] for n in graph.nodes}
    assert {by_id[nid] for nid in row['direct_dependent_node_ids']} == {'src/service.js'}
    assert 'src/unrelated.js' not in {n['file'] for n in impact.node_contexts}

    checklist = evaluate_repository(str(tmp_path), scan)
    assert checklist.coverage['status'] == 'complete'
    by_key = {c['key']: c['status'] for c in checklist.checks}
    assert by_key['unsafe-sql'] == 'FAIL'
    assert by_key['dependency-manifest'] == 'PASS'
    assert by_key['dependency-constraints'] == 'PASS'
    assert by_key['test-presence'] == 'PASS'
    assert by_key['docker-user'] == 'PASS'
