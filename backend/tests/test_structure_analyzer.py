import json
from pathlib import Path
import shutil
import sys

import pytest

from backend.app.analyzers import structure_discovery as discovery
from backend.app.analyzers.semgrep_adapter import ROOT
from backend.app.analyzers.structure_analyzer import (
    StructureOptions, analyze_repository, enclosing_class, enclosing_function, enclosing_symbols)
from backend.app.analyzers.structure_cli import main


def write(root, files):
    for file, content in files.items():
        target = root / file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
    return root


@pytest.fixture
def demo(tmp_path):
    shutil.copytree(ROOT / 'fixtures/structure_demo', tmp_path, dirs_exist_ok=True)
    return tmp_path


def test_fixture_extraction_and_partial_coverage(demo):
    result = analyze_repository(str(demo))
    assert result.status == 'partial'
    assert result.coverage['parsed_files'] == 12
    assert result.coverage['discovered_files'] == 13
    assert {'code': 'syntax_error', 'file': 'src/demo/broken.py', 'start_line': 2} in result.diagnostics
    assert {'BaseService', 'Service', 'Repository', 'Record'} <= {c['name'] for c in result.classes}
    assert len(result.internal_dependencies) >= 7


def test_parameters_methods_async_decorators_and_positions(demo):
    result = analyze_repository(str(demo))
    function = next(f for f in result.functions if f['name'] == 'read_item')
    assert function['is_async']
    assert [p['kind'] for p in function['parameters']] == ['positional_only', 'positional', 'keyword_only', 'var_keyword']
    assert [p['has_default'] for p in function['parameters']] == [False, True, True, False]
    assert function['start_line'] == 11 and function['extent_start_line'] == 9
    assert function['end_line'] == 13
    method = next(f for f in result.functions if f['qualified_name'] == 'Service.create')
    assert method['kind'] == 'method' and method['decorators'][0]['name'] == 'classmethod'
    assert any(c['callee'] == 'worker.fetch' and c['resolution'] == 'syntactic_only' for c in result.calls)


def test_inheritance_target_and_module_symbols(demo):
    result = analyze_repository(str(demo))
    service = next(c for c in result.classes if c['name'] == 'Service')
    base = next(c for c in result.classes if c['name'] == 'BaseService')
    assert service['bases'][0]['target_symbol_id'] == base['id']
    assert any(s['name'] == 'DEFAULT_TOKEN' for s in result.module_symbols)


def test_src_layout_relative_and_alias_imports(demo):
    result = analyze_repository(str(demo))
    assert 'src' in result.coverage['source_roots']
    imported = next(i for i in result.imports if i['file'] == 'src/demo/api.py' and i['name'] == 'Service')
    assert imported['alias'] == 'Worker' and imported['resolution'] == 'internal'
    assert imported['resolved_name'] == 'demo.services'
    edge = next(e for e in result.internal_dependencies if e['import_id'] == imported['id'])
    target = next(m for m in result.modules if m['id'] == edge['target_module_id'])
    assert target['file'] == 'src/demo/services.py'
    assert edge['file'] == 'src/demo/api.py' and edge['start_line'] == 3


def test_circular_import_evidence_is_retained_without_graph_analysis(demo):
    result = analyze_repository(str(demo))
    files = {module['id']: module['file'] for module in result.modules}
    pairs = {(files[edge['source_module_id']], files[edge['target_module_id']]) for edge in result.internal_dependencies}
    assert ('src/demo/services.py', 'src/demo/nested/helpers.py') in pairs
    assert ('src/demo/nested/helpers.py', 'src/demo/services.py') in pairs


def test_framework_components_prefer_explicit_evidence(demo):
    result = analyze_repository(str(demo))
    routes = [r for r in result.framework_indicators if r['kind'] == 'route']
    assert {(r['framework'], tuple(r['methods'])) for r in routes} == {('fastapi', ('GET',)), ('flask', ('POST',))}
    assert all(route['path'] == '<redacted>' for route in routes)
    components = {(c['component'], c['confidence']) for c in result.classifications}
    assert {('router','confirmed'), ('controller','confirmed'), ('database_model','confirmed'),
            ('data_access','confirmed'), ('configuration','confirmed'), ('authentication','confirmed'),
            ('service','inferred'), ('utility','inferred'), ('test','inferred')} <= components


def test_unresolved_and_external_stdlib_are_distinct(demo):
    result = analyze_repository(str(demo))
    imports = {i['module']: i['resolution'] for i in result.imports if i['kind'] == 'import'}
    assert imports['missing_demo_dependency'] == 'unresolved'
    assert imports['sqlite3'] == 'stdlib'
    assert any(d['module'] == 'fastapi' and d['kind'] == 'external' for d in result.external_dependencies)
    assert any(u['kind'] == 'call' and u['reason'] == 'dynamic_callable_or_import' for u in result.unresolved_references)


def test_stable_ids_and_output_across_checkout_paths(demo, tmp_path_factory):
    first = analyze_repository(str(demo)).to_dict()
    other = tmp_path_factory.mktemp('structure-copy')
    shutil.copytree(demo, other, dirs_exist_ok=True)
    assert first == analyze_repository(str(other)).to_dict()
    assert first == analyze_repository(str(demo)).to_dict()


def test_enclosing_helpers_handle_windows_paths(demo):
    result = analyze_repository(str(demo))
    assert enclosing_function(result, r'src\demo\services.py', 18)['qualified_name'] == 'Service.fetch'
    assert enclosing_class(result, r'src\demo\services.py', 18)['name'] == 'Service'
    assert enclosing_function(result, 'src/demo/api.py', 9)['name'] == 'read_item'
    assert enclosing_function(result, 'src/demo/services.py', 1) is None
    assert enclosing_symbols(result, 'missing.py', 1)['module'] is None


@pytest.mark.parametrize('file,line', [('../outside.py',1), (r'..\outside.py',1), ('/outside.py',1),
    (r'C:\outside.py',1), (r'C:outside.py',1), (r'\\host\share\a.py',1), ('x.py',0), ('x.py',True)])
def test_enclosing_helpers_reject_unsafe_locations(file, line, demo):
    with pytest.raises(ValueError):
        enclosing_symbols(analyze_repository(str(demo)), file, line)


def test_literal_secrets_and_docstrings_are_not_exported(tmp_path):
    secret = 'SYNTHETIC-SECRET-DO-NOT-EXPORT'
    write(tmp_path, {'app.py': f'''from fastapi import FastAPI
app = FastAPI()
PASSWORD = "{secret}"
@app.get("/{secret}")
def route(value: "{secret}" = "{secret}"):
    """{secret}"""
    print("{secret}")
    return value
''', 'broken.py': f'password = "{secret}\n'})
    serialized = json.dumps(analyze_repository(str(tmp_path)).to_dict())
    assert secret not in serialized and str(tmp_path) not in serialized


def test_never_imports_or_executes_target_modules(tmp_path):
    write(tmp_path, {'__init__.py': 'raise RuntimeError("Never execute")\n',
        'setup.py': 'raise RuntimeError("Never execute setup")\n',
        'danger.py': 'import totally_missing_dependency\nraise RuntimeError("Never execute")\n'})
    result = analyze_repository(str(tmp_path))
    assert result.status == 'complete' and result.coverage['parsed_files'] == 3
    assert any(i['resolution'] == 'unresolved' for i in result.imports)


@pytest.mark.parametrize('folder', ['.venv','venv','.git','__pycache__','vendor','node_modules','site-packages','.pytest_cache'])
def test_excluded_directories(tmp_path, folder):
    write(tmp_path, {'app.py':'value = 1\n', folder+'/secret.py':'raise RuntimeError("never parse")\n'})
    result = analyze_repository(str(tmp_path))
    assert [f['file'] for f in result.files] == ['app.py']
    assert {'file': folder, 'reason': 'excluded_directory'} in result.coverage['excluded_paths']


def test_file_and_repository_size_limits(tmp_path):
    write(tmp_path, {'a.py':'x = 1\n', 'b.py':'x = 2\n'})
    result = analyze_repository(str(tmp_path), options=StructureOptions(max_file_bytes=1))
    assert result.status == 'partial' and result.coverage['parsed_files'] == 0
    result = analyze_repository(str(tmp_path), options=StructureOptions(max_repository_bytes=7))
    assert result.status == 'partial' and result.coverage['parsed_files'] == 1
    assert result.coverage['bytes_read'] <= 7


def test_file_count_and_ast_limits(tmp_path):
    write(tmp_path, {'a.py':'x = 1\n', 'b.py':'x = 2\n'})
    result = analyze_repository(str(tmp_path), options=StructureOptions(max_files=1))
    assert result.status == 'partial' and len(result.files) == 1
    assert {'code':'file_count_limit','file':'b.py'} in result.diagnostics
    result = analyze_repository(str(tmp_path), options=StructureOptions(max_ast_nodes=2))
    assert result.coverage['parsed_files'] == 0
    assert all(file['status'] == 'ast_node_limit' for file in result.files)


def test_valid_encoding_cookie_and_invalid_bytes(tmp_path):
    write(tmp_path, {'latin.py': b'# coding: latin-1\nname = "caf\xe9"\n', 'bad.py': b'x = "\xff"\n'})
    result = analyze_repository(str(tmp_path))
    assert result.coverage['parsed_files'] == 1 and result.status == 'partial'
    assert {'code':'encoding_error','file':'bad.py'} in result.diagnostics


def test_unreadable_file_keeps_other_evidence(tmp_path, monkeypatch):
    write(tmp_path, {'a.py':'x = 1\n', 'unreadable.py':'y = 1\n'})
    original = Path.open
    def guarded(path, *args, **kwargs):
        if path.name == 'unreadable.py':
            raise PermissionError('secret error detail')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    result = analyze_repository(str(tmp_path))
    assert result.status == 'partial' and result.coverage['parsed_files'] == 1
    assert 'secret error detail' not in json.dumps(result.to_dict())


def test_linked_file_is_not_read(tmp_path, monkeypatch):
    write(tmp_path, {'a.py':'x=1\n','link.py':'DO_NOT_READ = True\n'})
    original = discovery._linked
    monkeypatch.setattr(discovery, '_linked', lambda path: path.name == 'link.py' or original(path))
    result = analyze_repository(str(tmp_path))
    assert {'code':'linked_file_skipped','file':'link.py'} in result.diagnostics
    assert not any(m['file'] == 'link.py' for m in result.modules)


def test_resolved_escape_is_not_read(tmp_path, monkeypatch):
    write(tmp_path, {'escape.py':'x = 1\n'})
    original = Path.resolve
    monkeypatch.setattr(Path, 'resolve', lambda path, *a, **kw:
        tmp_path.parent / 'outside.py' if path.name == 'escape.py' else original(path, *a, **kw))
    result = analyze_repository(str(tmp_path))
    assert result.coverage['parsed_files'] == 0
    assert {'code':'linked_file_skipped','file':'escape.py'} in result.diagnostics


@pytest.mark.parametrize('value', ['',None,42,'not-a-repository'])
def test_invalid_repositories(value):
    result = analyze_repository(value)
    assert result.status == 'error' and result.summary['files'] == 0


def test_empty_and_unsupported_repositories(tmp_path):
    assert analyze_repository(str(tmp_path)).status == 'error'
    write(tmp_path, {'sample.go':'package sample\n'})
    result = analyze_repository(str(tmp_path))
    assert result.status == 'error' and result.coverage['unsupported_files'] == 1


@pytest.mark.parametrize('options', [StructureOptions(max_files=0), StructureOptions(max_file_bytes=-1),
    StructureOptions(source_roots=('../outside',)), StructureOptions(source_roots=(r'C:\outside',))])
def test_invalid_options(tmp_path, options):
    with pytest.raises(ValueError):
        analyze_repository(str(tmp_path), options=options)


def test_ambiguous_modules_do_not_create_edges(tmp_path):
    write(tmp_path, {'duplicate.py':'x=1\n','duplicate/__init__.py':'x=2\n','main.py':'import duplicate\n'})
    result = analyze_repository(str(tmp_path))
    item = result.imports[0]
    assert item['resolution'] == 'ambiguous' and len(item['candidate_module_ids']) == 2
    assert result.internal_dependencies == []


def test_namespace_packages_and_submodule_imports(tmp_path):
    write(tmp_path, {'namespace/sub.py':'x=1\n','main.py':'import namespace\nfrom namespace import sub\n'})
    result = analyze_repository(str(tmp_path))
    assert result.imports[0]['reason'] == 'namespace_package_without_source_file'
    assert result.imports[0]['namespace_paths'] == ['namespace']
    assert len(result.internal_dependencies) == 1


def test_missing_attribute_is_unresolved(tmp_path):
    write(tmp_path, {'pkg/__init__.py':'KNOWN = 1\n','main.py':'from pkg import absent\n'})
    result = analyze_repository(str(tmp_path))
    assert result.imports[0]['resolution'] == 'unresolved'
    assert result.internal_dependencies == []


def test_nonpackage_parent_does_not_fabricate_submodule_relationship(tmp_path):
    write(tmp_path, {'pkg.py':'x=1\n','pkg/sub.py':'x=2\n','main.py':'import pkg.sub\n'})
    result = analyze_repository(str(tmp_path))
    assert result.imports[0]['resolution'] == 'unresolved'
    assert result.internal_dependencies == []


def test_from_nonpackage_does_not_invent_child_module(tmp_path):
    write(tmp_path, {'pkg.py':'x=1\n','pkg/sub.py':'x=2\n','main.py':'from pkg import sub\n'})
    result = analyze_repository(str(tmp_path))
    assert result.imports[0]['resolution'] == 'unresolved'
    assert result.internal_dependencies == []


def test_symbol_ids_survive_unrelated_line_insertion(tmp_path):
    source = 'class Example:\n    def method(self):\n        return 1\n'
    write(tmp_path, {'app.py':source})
    first = analyze_repository(str(tmp_path))
    write(tmp_path, {'app.py':'# unrelated new line\n\n'+source})
    second = analyze_repository(str(tmp_path))
    assert first.classes[0]['id'] == second.classes[0]['id']
    assert first.functions[0]['id'] == second.functions[0]['id']
    assert first.functions[0]['start_line'] != second.functions[0]['start_line']


def test_subscripted_callable_remains_dynamic(tmp_path):
    write(tmp_path, {'app.py':'handlers[dynamic_index]()\n'})
    result = analyze_repository(str(tmp_path))
    assert result.calls[0]['resolution'] == 'dynamic_callable'


def test_custom_exclusions_extend_mandatory_exclusions(tmp_path):
    write(tmp_path, {'app.py':'x=1\n','.git/hook.py':'x=2\n','generated/code.py':'x=3\n'})
    result = analyze_repository(str(tmp_path), options=StructureOptions(excluded_directories=('generated',)))
    assert [f['file'] for f in result.files] == ['app.py']


def test_repository_ast_budget(tmp_path):
    write(tmp_path, {'a.py':'x=1\n','b.py':'y=2\n'})
    result = analyze_repository(str(tmp_path), options=StructureOptions(max_repository_ast_nodes=5))
    assert result.status == 'partial' and result.coverage['parsed_files'] == 1
    assert {'code':'repository_ast_node_limit','file':'b.py'} in result.diagnostics


def test_relative_beyond_package_is_unresolved(tmp_path):
    write(tmp_path, {'pkg/__init__.py':'','pkg/module.py':'from ...outside import X\n'})
    result = analyze_repository(str(tmp_path))
    assert result.imports[0]['reason'] == 'relative_import_beyond_source_root'
    assert result.internal_dependencies == []


def test_unknown_route_receiver_and_shadowed_factory_are_not_confirmed(tmp_path):
    write(tmp_path, {'app.py':'from fastapi import FastAPI\nFastAPI = other_factory\n'
        'app = FastAPI()\n@app.get("/private")\ndef route():\n    pass\n'})
    result = analyze_repository(str(tmp_path))
    assert not any(item['kind'] != 'import' for item in result.framework_indicators)


def test_nested_functions_and_unpacking_symbols(tmp_path):
    write(tmp_path, {'app.py':'left, right = ("private", "private")\n'
        'def outer(value, *args, **kwargs):\n    async def inner():\n        return value\n    return inner\n'})
    result = analyze_repository(str(tmp_path))
    assert {s['name'] for s in result.module_symbols} == {'left','right'}
    assert enclosing_function(result,'app.py',4)['qualified_name'] == 'outer.inner'
    assert [p['kind'] for p in result.functions[0]['parameters']] == ['positional','var_positional','var_keyword']


def test_known_local_file_shadows_stdlib_name(tmp_path):
    write(tmp_path, {'json.py':'value=1\n','main.py':'import json\n'})
    result = analyze_repository(str(tmp_path))
    assert result.imports[0]['resolution'] == 'internal'


def test_custom_source_roots_and_external_modules(tmp_path):
    write(tmp_path, {'python/pkg/__init__.py':'VALUE=1\n',
                     'main.py':'import pkg\nimport corporate_client\n'})
    result = analyze_repository(str(tmp_path), options=StructureOptions(
        source_roots=(r'python',), external_modules=('corporate_client',)))
    assert [i['resolution'] for i in result.imports] == ['internal','external']


def test_duplicate_definitions_have_unique_ids(tmp_path):
    write(tmp_path, {'app.py':'def duplicate():\n    pass\ndef duplicate():\n    pass\n'})
    result = analyze_repository(str(tmp_path))
    assert len({f['id'] for f in result.functions}) == 2


def test_cli_json(demo, capsys):
    assert main([str(demo)]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data['schema_version'] == '1.0.0' and data['status'] == 'partial'


def test_forward_class_base_is_not_a_confirmed_binding(tmp_path):
    write(tmp_path, {'app.py':'class Child(Base):\n    pass\nclass Base:\n    pass\n'})
    result = analyze_repository(str(tmp_path))
    assert result.classes[0]['bases'][0]['target_symbol_id'] is None
    assert any(item['reason'] == 'base_symbol_not_statically_resolved' for item in result.unresolved_references)


def test_structure_contract_and_entity_references(demo):
    import jsonschema
    result = analyze_repository(str(demo))
    schema = json.loads((ROOT / 'contracts/repository-structure-v1.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(result.to_dict())
    modules = {m['id'] for m in result.modules}
    scopes = modules | {item['id'] for item in result.classes + result.functions}
    assert all(item['parent_id'] in scopes for item in result.classes + result.functions)
    assert all(item['scope_id'] in scopes for item in result.imports + result.calls)
    assert all(item['target_module_id'] in modules and item['source_module_id'] in modules
               for item in result.internal_dependencies)


def test_representative_structure_json_matches_fixture():
    result = analyze_repository(str(ROOT / 'fixtures/structure_demo')).to_dict()
    expected = json.loads((ROOT / 'contracts/examples/repository-structure-v1.json').read_text())
    assert result["coverage"]["parser_python_version"] == f"{sys.version_info.major}.{sys.version_info.minor}"
    expected["coverage"]["parser_python_version"] = result["coverage"]["parser_python_version"]
    assert result == expected
