"""Repository intelligence v1: static AST and Tree-sitter evidence, not a runtime call graph."""
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath, PureWindowsPath
import re
import sys

from .structure_discovery import StructureOptions, discover
from .structure_extractor import Extractor, stable_id
from .structure_resolver import resolve_imports
from .structure_ts_adapters import JavaStructureAdapter, JsTsStructureAdapter


LIMITATIONS = [
    'Static source evidence only; never a complete runtime import or call graph.',
    'No target code, dependency installation, LLM, import hooks, or external API is executed.',
    'Host Python grammar/stdlib and configured file, byte, entry and AST limits bound coverage.',
    'Source-root candidates are conservative; runtime sys.path and packaging hooks are not evaluated.',
    'Unknown external modules, dynamic imports/attributes, re-exports and wildcard symbols can remain unresolved.',
    'Filename classifications are inferred; framework declarations do not prove runtime use or authentication coverage.',
    'Literal defaults, annotation strings, route paths, arguments, assignment values and docstrings are omitted.',
    'The caller must own a stable repository and prevent concurrent filesystem replacement.',
]


def _normalize_route_for_matching(raw_path: str) -> str:
    path_only = raw_path.split('?', 1)[0].rstrip('/') or '/'
    return re.sub(r'(\$\{[^}]+\}|\[[^]]+\]|\{[^}]+\}|<[^>]+>|:[A-Za-z_][A-Za-z0-9_]*)', '{param}', path_only)


@dataclass
class RepositoryStructure:
    schema_version: str
    status: str
    summary: dict
    files: list[dict]
    modules: list[dict]
    classes: list[dict]
    functions: list[dict]
    module_symbols: list[dict]
    imports: list[dict]
    calls: list[dict]
    internal_dependencies: list[dict]
    external_dependencies: list[dict]
    framework_indicators: list[dict]
    classifications: list[dict]
    unresolved_references: list[dict]
    diagnostics: list[dict]
    coverage: dict

    def to_dict(self):
        return asdict(self)


def analyze_repository(project_path: str, *, options: StructureOptions | None = None) -> RepositoryStructure:
    options = options or StructureOptions()
    discovered = discover(project_path, options)
    modules, classes, functions, symbols, imports, calls, frameworks, classifications = [], [], [], [], [], [], [], []
    exports = {}
    all_routes: list[dict] = []
    all_api_calls: list[dict] = []
    all_component_refs: list[dict] = []
    package_names: dict[str, str] = {}

    for file in sorted(discovered.files, key=lambda item: item['file']):
        if file['status'] == 'linked_file_skipped':
            continue
        path = file['file']
        lang = file.get('language') or discovered.languages.get(path, 'python')
        identifier = stable_id('module', path)
        file['module_id'] = identifier
        module = {
            'id': identifier,
            'file': path,
            'is_package': PurePosixPath(path).stem == '__init__' if lang == 'python' else PurePosixPath(path).stem == 'index',
            'parsed': path in discovered.trees or path in discovered.ts_trees,
            'names': [],
            'start_line': 1 if file.get('line_count') else None,
            'end_line': file.get('line_count') or None,
        }
        if lang != 'python':
            module['language'] = lang
        modules.append(module)

        if path in discovered.trees:
            extractor = Extractor(path, identifier)
            try:
                extractor.visit(discovered.trees[path])
                extractor.apply_heuristics()
            except RecursionError:
                module['parsed'] = False
                file['status'] = 'extraction_recursion_limit'
                discovered.diagnostics.append({'code': 'extraction_recursion_limit', 'file': path})
                continue
            classes.extend(extractor.classes)
            functions.extend(extractor.functions)
            symbols.extend(extractor.symbols)
            imports.extend(extractor.imports)
            calls.extend(extractor.calls)
            frameworks.extend(extractor.frameworks)
            classifications.extend(extractor.classifications)
            for rec in extractor.route_records:
                all_routes.append({**rec, 'normalized_path': _normalize_route_for_matching(rec['raw_pattern'])})
            exports[identifier] = (
                {item['name'] for item in extractor.classes + extractor.functions if item['parent_id'] == identifier}
                | {item['name'] for item in extractor.symbols}
                | {item['binding'] for item in extractor.imports if item['scope_id'] == identifier}
            )
        elif path in discovered.ts_trees:
            source_bytes = discovered.sources[path]
            adapter = (
                JavaStructureAdapter(path, identifier, lang, source_bytes)
                if lang == 'java'
                else JsTsStructureAdapter(path, identifier, lang, source_bytes)
            )
            adapter.extract(discovered.ts_trees[path])
            if adapter.package_name:
                module['package_name'] = adapter.package_name
                package_names[identifier] = adapter.package_name
            classes.extend(adapter.classes)
            functions.extend(adapter.functions)
            symbols.extend(adapter.symbols)
            imports.extend(adapter.imports)
            calls.extend(adapter.calls)
            frameworks.extend(adapter.frameworks)
            classifications.extend(adapter.classifications)
            all_routes.extend(adapter.route_records)
            all_api_calls.extend(adapter.api_client_calls)
            all_component_refs.extend(adapter.component_references)
            exports[identifier] = adapter.exports

    roots, dependencies, external, unresolved = resolve_imports(
        modules, imports, exports, options, config_files=discovered.config_files
    )

    for call in calls:
        if (
            call['resolution'] == 'dynamic_callable'
            or call['callee'] in {'__import__', 'importlib.import_module'}
            or call['import_qualified_name'] in {'importlib.import_module', 'builtins.__import__'}
        ):
            unresolved.append(
                {
                    'kind': 'call',
                    'reference_id': call['id'],
                    'reason': 'dynamic_callable_or_import',
                    **{key: call[key] for key in ('file', 'start_line', 'end_line')},
                }
            )

    # Index classes and internal imports for intra-file and cross-file base resolution
    mod_lang = {m['id']: m.get('language', 'python') for m in modules}
    classes_by_mod_name: dict[tuple[str, str], list[dict]] = {}
    for cls in classes:
        if cls['parent_id'] == cls['module_id']:
            classes_by_mod_name.setdefault((cls['module_id'], cls['name']), []).append(cls)
    import_target_by_mod_binding: dict[tuple[str, str], tuple[str, str | None]] = {}
    for imp in imports:
        if imp.get('resolution') == 'internal' and len(imp.get('candidate_module_ids') or []) == 1:
            tmod = imp['candidate_module_ids'][0]
            iname = imp.get('name') if imp.get('name') not in (None, '*', 'default') else None
            import_target_by_mod_binding[(imp['module_id'], imp['binding'])] = (tmod, iname)

    semantic_relationships: list[dict] = []
    seen_sem: set[tuple] = set()

    def add_semantic(src_mod: str, tgt_mod: str, rel: str, conf: str, file: str, start: int, end: int, ref_id: str) -> None:
        if src_mod == tgt_mod:
            return
        key = (src_mod, tgt_mod, rel, file, start, end)
        if key in seen_sem:
            return
        seen_sem.add(key)
        semantic_relationships.append(
            {
                'id': stable_id('sem_rel', src_mod, tgt_mod, rel, file, start, end),
                'source_module_id': src_mod,
                'target_module_id': tgt_mod,
                'relationship': rel,
                'confidence': conf,
                'file': file,
                'start_line': start,
                'end_line': end,
                'reference_id': ref_id,
            }
        )

    for cls in classes:
        is_python = mod_lang.get(cls['module_id'], 'python') == 'python'
        for base in cls['bases']:
            candidates = [
                item['id']
                for item in classes
                if item['file'] == cls['file']
                and item['parent_id'] == cls['parent_id']
                and item['name'] == base['name']
                and (not is_python or item['start_line'] < cls['start_line'])
            ]
            target_cls = None
            if len(candidates) == 1:
                base['target_symbol_id'] = candidates[0]
            else:
                # Try imported symbol across modules
                bname = (base.get('name') or '').split('.')[-1]
                hit = import_target_by_mod_binding.get((cls['module_id'], bname))
                if hit:
                    tmod, iname = hit
                    sym_name = iname or bname
                    cross = classes_by_mod_name.get((tmod, sym_name), [])
                    if len(cross) == 1:
                        target_cls = cross[0]
                elif cls['module_id'] in package_names:
                    src_pkg = package_names[cls['module_id']]
                    pkg_matches = [
                        cand
                        for (m_id, cname), cands in classes_by_mod_name.items()
                        if m_id != cls['module_id'] and package_names.get(m_id) == src_pkg and cname == bname
                        for cand in cands
                    ]
                    if len(pkg_matches) == 1:
                        target_cls = pkg_matches[0]
                base['target_symbol_id'] = target_cls['id'] if target_cls is not None else None
                if target_cls is not None:
                    rel = 'implements' if base.get('relation') == 'implements' else 'inherits'
                    add_semantic(
                        cls['module_id'],
                        target_cls['module_id'],
                        rel,
                        'confirmed',
                        cls['file'],
                        cls['start_line'],
                        cls['end_line'],
                        cls['id'],
                    )
            if base['is_dynamic']:
                unresolved.append(
                    {
                        'kind': 'inheritance',
                        'reference_id': cls['id'],
                        'reason': 'dynamic_base_expression',
                        **{key: cls[key] for key in ('file', 'start_line', 'end_line')},
                    }
                )
            elif (
                base['target_symbol_id'] is None
                and base['import_qualified_name'] is None
                and base['name']
                not in {
                    'object',
                    'Exception',
                    'BaseException',
                    'str',
                    'dict',
                    'list',
                    'tuple',
                    'int',
                    'float',
                    'bool',
                }
                and is_python
            ):
                unresolved.append(
                    {
                        'kind': 'inheritance',
                        'reference_id': cls['id'],
                        'reason': 'base_symbol_not_statically_resolved',
                        **{key: cls[key] for key in ('file', 'start_line', 'end_line')},
                    }
                )

    # React component references (<MyComponent /> matching imported local component module)
    for ref in all_component_refs:
        hit = import_target_by_mod_binding.get((ref['source_module_id'], ref['component']))
        if hit:
            tmod, _iname = hit
            add_semantic(
                ref['source_module_id'],
                tmod,
                'references_component',
                'confirmed',
                ref['file'],
                ref['start_line'],
                ref['end_line'],
                stable_id('jsx', ref['file'], ref['component'], ref['start_line'], ref['end_line']),
            )

    # Potential frontend HTTP call -> backend route links (inferred, never exposing raw paths)
    routes_by_norm: dict[str, list[dict]] = {}
    for route in all_routes:
        routes_by_norm.setdefault(route['normalized_path'], []).append(route)
    for call in all_api_calls:
        for route in routes_by_norm.get(call['normalized_path'], []):
            if route['methods'] and call['method'] not in route['methods']:
                continue
            add_semantic(
                call['module_id'],
                route['module_id'],
                'potential_api_call',
                'inferred',
                call['file'],
                call['start_line'],
                call['end_line'],
                stable_id('api_call', call['file'], call['start_line'], route['symbol_id']),
            )

    if not discovered.files and discovered.valid:
        discovered.diagnostics.append({'code': 'no_supported_files'})
    status = 'error' if not discovered.valid or not discovered.files else ('partial' if discovered.diagnostics else 'complete')
    parsed = sum(module['parsed'] for module in modules)

    detected_code_langs = sorted({m.get('language', 'python') for m in modules})
    has_non_python = any(lang != 'python' for lang in detected_code_langs) or bool(discovered.config_files) or bool(semantic_relationships)

    coverage = {
        'supported_language': 'python' if not any(l != 'python' for l in detected_code_langs) else 'multi',
        'parser_python_version': f'{sys.version_info.major}.{sys.version_info.minor}',
        'column_units': 'zero_based_utf8_bytes',
        'discovered_files': len(discovered.files),
        'unresolved_imports': sum(item['resolution'] == 'unresolved' for item in imports),
        'ambiguous_imports': sum(item['resolution'] == 'ambiguous' for item in imports),
        'dynamic_call_sites': sum(item['resolution'] == 'dynamic_callable' for item in calls),
        'parsed_files': parsed,
        'skipped_files': len(discovered.files) - parsed,
        'unsupported_files': discovered.unsupported_files,
        'bytes_read': discovered.bytes_read,
        'source_roots': roots,
        'excluded_paths': sorted(discovered.excluded, key=lambda item: item['file']),
        'limits': {
            key: getattr(options, key)
            for key in (
                'max_files',
                'max_file_bytes',
                'max_repository_bytes',
                'max_entries',
                'max_ast_nodes',
                'max_repository_ast_nodes',
            )
        },
        'limitations': LIMITATIONS,
    }

    if has_non_python:
        detected_frameworks = sorted({f['framework'] for f in frameworks} | {fw for cfg in discovered.config_files for fw in cfg.get('frameworks', [])})
        detected_pms = sorted({pm for cfg in discovered.config_files for pm in cfg.get('package_managers', [])})
        config_kinds = sorted(
            {k for cfg in discovered.config_files for k in (cfg.get('kind'), cfg.get('ext_kind')) if k}
        )
        coverage['languages'] = detected_code_langs
        coverage['frameworks'] = detected_frameworks
        coverage['package_managers'] = detected_pms
        coverage['config_file_kinds'] = config_kinds
        coverage['recognized_config_files'] = sorted(cfg['file'] for cfg in discovered.config_files)
        coverage['semantic_relationships'] = sorted(
            semantic_relationships, key=lambda r: (r['file'], r['start_line'], r['relationship'], r['id'])
        )

    key = lambda item: (
        item.get('file', item.get('evidence', {}).get('file', '')),
        item.get('start_line', item.get('evidence', {}).get('start_line', 0)),
        item.get('id', item.get('reference_id', '')),
        item.get('component', ''),
    )
    lists = [
        modules,
        classes,
        functions,
        symbols,
        imports,
        calls,
        dependencies,
        external,
        frameworks,
        classifications,
        unresolved,
        discovered.diagnostics,
    ]
    for items in lists:
        items.sort(key=key)
    summary = {
        'files': len(discovered.files),
        'parsed_files': parsed,
        'modules': len(modules),
        'classes': len(classes),
        'functions': len(functions),
        'imports': len(imports),
        'external_dependencies': sum(item['kind'] == 'external' for item in external),
        'stdlib_dependencies': sum(item['kind'] == 'stdlib' for item in external),
        'internal_dependencies': len(dependencies),
        'unresolved_references': len(unresolved),
    }
    return RepositoryStructure(
        '1.0.0',
        status,
        summary,
        sorted(discovered.files, key=lambda item: item['file']),
        modules,
        classes,
        functions,
        symbols,
        imports,
        calls,
        dependencies,
        external,
        frameworks,
        classifications,
        unresolved,
        discovered.diagnostics,
        coverage,
    )


def enclosing_symbols(structure: RepositoryStructure, file: str, line: int) -> dict:
    """Locate nested containing declarations; include decorator extents, not source text."""
    path = PureWindowsPath(file)
    if path.is_absolute() or path.drive or '..' in path.parts or type(line) is not int or line < 1:
        raise ValueError('Expected a repository-relative file and positive line')
    normalized = PurePosixPath(file.replace('\\', '/')).as_posix()
    if not normalized or normalized == '.' or normalized.startswith('/'):
        raise ValueError('Invalid file')

    def matching(items):
        return sorted(
            [item for item in items if item['file'] == normalized and item['extent_start_line'] <= line <= item['end_line']],
            key=lambda item: (item['end_line'] - item['extent_start_line'], -item['start_line'], item['id']),
        )

    return {
        'module': next((module for module in structure.modules if module['file'] == normalized), None),
        'functions': matching(structure.functions),
        'classes': matching(structure.classes),
    }


def enclosing_function(structure, file, line):
    return next(iter(enclosing_symbols(structure, file, line)['functions']), None)


def enclosing_class(structure, file, line):
    return next(iter(enclosing_symbols(structure, file, line)['classes']), None)
