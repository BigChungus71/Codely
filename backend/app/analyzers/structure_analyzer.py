"""Repository intelligence v1: static AST evidence, not a runtime call graph."""
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath, PureWindowsPath
import sys

from .structure_discovery import StructureOptions, discover
from .structure_extractor import Extractor, stable_id
from .structure_resolver import resolve_imports


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
    for file in sorted(discovered.files, key=lambda item: item['file']):
        if file['status'] == 'linked_file_skipped':
            continue
        path = file['file']
        identifier = stable_id('module', path)
        file['module_id'] = identifier
        module = {'id': identifier, 'file': path, 'is_package': PurePosixPath(path).stem == '__init__',
                  'parsed': path in discovered.trees, 'names': [],
                  'start_line': 1 if file.get('line_count') else None, 'end_line': file.get('line_count') or None}
        modules.append(module)
        if path not in discovered.trees:
            continue
        extractor = Extractor(path, identifier)
        try:
            extractor.visit(discovered.trees[path])
            extractor.apply_heuristics()
        except RecursionError:
            module['parsed'] = False
            file['status'] = 'extraction_recursion_limit'
            discovered.diagnostics.append({'code': 'extraction_recursion_limit', 'file': path})
            continue
        classes.extend(extractor.classes); functions.extend(extractor.functions)
        symbols.extend(extractor.symbols); imports.extend(extractor.imports)
        calls.extend(extractor.calls); frameworks.extend(extractor.frameworks)
        classifications.extend(extractor.classifications)
        exports[identifier] = {item['name'] for item in extractor.classes + extractor.functions
                               if item['parent_id'] == identifier} | {
                               item['name'] for item in extractor.symbols} | {
                               item['binding'] for item in extractor.imports if item['scope_id'] == identifier}
    roots, dependencies, external, unresolved = resolve_imports(modules, imports, exports, options)
    for call in calls:
        if (call['resolution'] == 'dynamic_callable' or call['callee'] in {'__import__', 'importlib.import_module'}
                or call['import_qualified_name'] in {'importlib.import_module', 'builtins.__import__'}):
            unresolved.append({'kind': 'call', 'reference_id': call['id'],
                'reason': 'dynamic_callable_or_import',
                **{key: call[key] for key in ('file', 'start_line', 'end_line')}})
    for cls in classes:
        for base in cls['bases']:
            candidates = [item['id'] for item in classes if item['file'] == cls['file']
                          and item['parent_id'] == cls['parent_id'] and item['name'] == base['name']
                          and item['start_line'] < cls['start_line']]
            base['target_symbol_id'] = candidates[0] if len(candidates) == 1 else None
            if base['is_dynamic']:
                unresolved.append({'kind': 'inheritance', 'reference_id': cls['id'],
                    'reason': 'dynamic_base_expression', **{key: cls[key] for key in ('file', 'start_line', 'end_line')}})
            elif not candidates and base['import_qualified_name'] is None and base['name'] not in {
                    'object', 'Exception', 'BaseException', 'str', 'dict', 'list', 'tuple', 'int', 'float', 'bool'}:
                unresolved.append({'kind': 'inheritance', 'reference_id': cls['id'],
                    'reason': 'base_symbol_not_statically_resolved',
                    **{key: cls[key] for key in ('file', 'start_line', 'end_line')}})
    if not discovered.files and discovered.valid:
        discovered.diagnostics.append({'code': 'no_supported_files'})
    status = 'error' if not discovered.valid or not discovered.files else ('partial' if discovered.diagnostics else 'complete')
    parsed = sum(module['parsed'] for module in modules)
    coverage = {'supported_language': 'python', 'parser_python_version': f'{sys.version_info.major}.{sys.version_info.minor}',
        'column_units': 'zero_based_utf8_bytes', 'discovered_files': len(discovered.files),
        'unresolved_imports': sum(item['resolution'] == 'unresolved' for item in imports),
        'ambiguous_imports': sum(item['resolution'] == 'ambiguous' for item in imports),
        'dynamic_call_sites': sum(item['resolution'] == 'dynamic_callable' for item in calls),
        'parsed_files': parsed, 'skipped_files': len(discovered.files) - parsed,
        'unsupported_files': discovered.unsupported_files, 'bytes_read': discovered.bytes_read,
        'source_roots': roots, 'excluded_paths': sorted(discovered.excluded, key=lambda item: item['file']),
        'limits': {key: getattr(options, key) for key in ('max_files', 'max_file_bytes',
                  'max_repository_bytes', 'max_entries', 'max_ast_nodes', 'max_repository_ast_nodes')},
        'limitations': LIMITATIONS}
    key = lambda item: (item.get('file', item.get('evidence', {}).get('file', '')),
                        item.get('start_line', item.get('evidence', {}).get('start_line', 0)),
                        item.get('id', item.get('reference_id', '')), item.get('component', ''))
    lists = [modules, classes, functions, symbols, imports, calls, dependencies, external,
             frameworks, classifications, unresolved, discovered.diagnostics]
    for items in lists:
        items.sort(key=key)
    summary = {'files': len(discovered.files), 'parsed_files': parsed, 'modules': len(modules),
        'classes': len(classes), 'functions': len(functions), 'imports': len(imports),
        'external_dependencies': sum(item['kind'] == 'external' for item in external),
        'stdlib_dependencies': sum(item['kind'] == 'stdlib' for item in external),
        'internal_dependencies': len(dependencies), 'unresolved_references': len(unresolved)}
    return RepositoryStructure('1.0.0', status, summary,
        sorted(discovered.files, key=lambda item: item['file']), modules, classes, functions,
        symbols, imports, calls, dependencies, external, frameworks, classifications,
        unresolved, discovered.diagnostics, coverage)


def enclosing_symbols(structure: RepositoryStructure, file: str, line: int) -> dict:
    """Locate nested containing declarations; include decorator extents, not source text."""
    path = PureWindowsPath(file)
    if path.is_absolute() or path.drive or '..' in path.parts or type(line) is not int or line < 1:
        raise ValueError('Expected a repository-relative file and positive line')
    normalized = PurePosixPath(file.replace('\\', '/')).as_posix()
    if not normalized or normalized == '.' or normalized.startswith('/'):
        raise ValueError('Invalid file')
    def matching(items):
        return sorted([item for item in items if item['file'] == normalized
                       and item['extent_start_line'] <= line <= item['end_line']],
                      key=lambda item: (item['end_line'] - item['extent_start_line'], -item['start_line'], item['id']))
    return {'module': next((module for module in structure.modules if module['file'] == normalized), None),
            'functions': matching(structure.functions), 'classes': matching(structure.classes)}


def enclosing_function(structure, file, line):
    return next(iter(enclosing_symbols(structure, file, line)['functions']), None)


def enclosing_class(structure, file, line):
    return next(iter(enclosing_symbols(structure, file, line)['classes']), None)
