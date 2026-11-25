"""Conservative file-backed import resolution, without importlib or sys.path mutation."""
from pathlib import PurePosixPath
import sys


KNOWN_EXTERNAL = {'fastapi', 'flask', 'flask_login', 'flask_cors', 'flask_sqlalchemy',
                  'django', 'requests', 'httpx', 'sqlalchemy', 'sqlmodel', 'pydantic',
                  'networkx', 'pytest', 'yaml', 'uvicorn', 'numpy', 'pandas'}


def module_name(file, source_root):
    path = PurePosixPath(file)
    try:
        relative = path.relative_to(PurePosixPath(source_root))
    except ValueError:
        return None
    parts = list(relative.with_suffix('').parts)
    if parts[-1:] == ['__init__']:
        parts.pop()
    return '.'.join(parts) if parts and all(part.isidentifier() for part in parts) else None


def resolve_imports(modules, imports, exports, options):
    roots = {'.', *[root.replace('\\', '/').rstrip('/') or '.' for root in options.source_roots]}
    for module in modules:
        parts = PurePosixPath(module['file']).parts[:-1]
        for index, part in enumerate(parts):
            if part == 'src':
                roots.add('/'.join(parts[:index + 1]))
    roots = sorted(roots)
    by_file = {module['file']: module for module in modules}
    index, namespaces = {}, {}
    for module in modules:
        module['names'] = sorted({name for root in roots if (name := module_name(module['file'], root))})
        for root in roots:
            name = module_name(module['file'], root)
            if not name:
                continue
            index.setdefault(name, set()).add(module['id'])
            parts = name.split('.')
            for size in range(1, len(parts)):
                namespace = '.'.join(parts[:size])
                path = str(PurePosixPath(root).joinpath(*parts[:size]))
                namespaces.setdefault(namespace, set()).add(path)
    by_id = {module['id']: module for module in modules}
    dependencies, external, unresolved = [], [], []
    for item in imports:
        source = by_file[item['file']]
        name = item['module']
        base = name
        reason = None
        if item['level']:
            applicable = [root for root in roots if module_name(source['file'], root)]
            selected_root = max(applicable, key=lambda root: len(PurePosixPath(root).parts), default='.')
            current = module_name(source['file'], selected_root) or ''
            package = current.split('.') if source['is_package'] else current.split('.')[:-1]
            if item['level'] > len(package):
                reason = 'relative_import_beyond_source_root'
                base = None
            else:
                anchor = package[:len(package) - item['level'] + 1]
                base = '.'.join(anchor + ([name] if name else []))
        candidates = set()
        symbol_status = None
        namespaces_found = []
        if base:
            if item['kind'] == 'from' and item['name'] != '*':
                child = base + '.' + item['name']
                child_candidates = set(index.get(child, set()))
                base_candidates = set(index.get(base, set()))
                declared = {identifier for identifier in base_candidates
                            if item['name'] in exports.get(identifier, set())}
                if any(not by_id[identifier]['is_package'] for identifier in base_candidates):
                    child_candidates = set()
                    if not declared:
                        reason = 'parent_module_is_not_uniquely_a_package'
                # A package attribute and same-named submodule are not statically interchangeable.
                candidates = child_candidates | declared
                if len(base_candidates) > 1 and candidates:
                    candidates |= base_candidates
                if child_candidates and declared:
                    symbol_status = 'attribute_or_submodule_ambiguous'
                elif declared:
                    symbol_status = 'observed_declaration'
                elif child_candidates:
                    symbol_status = 'submodule'
                elif base_candidates:
                    reason = 'imported_attribute_not_statically_identified'
            else:
                candidates = set(index.get(base, set()))
                symbol_status = 'wildcard_not_expanded' if item['name'] == '*' else 'module'
                if not candidates and base in namespaces:
                    namespaces_found = sorted(namespaces[base])
            # A plain module cannot be a regular package parent. Do not turn a
            # same-named directory into an asserted child dependency in that case.
            prefixes = ['.'.join(base.split('.')[:size]) for size in range(1, len(base.split('.')))]
            if any(any(not by_id[identifier]['is_package'] for identifier in index.get(prefix, set()))
                   for prefix in prefixes):
                candidates.clear()
                namespaces_found = []
                reason = 'parent_module_is_not_uniquely_a_package'
        if len(candidates) > 1:
            resolution, reason = 'ambiguous', symbol_status or 'multiple_local_candidates'
        elif len(candidates) == 1:
            resolution = 'internal'
        elif namespaces_found:
            resolution, reason = 'internal', 'namespace_package_without_source_file'
        elif item['level'] or reason or (base and any(base == local or base.startswith(local + '.') for local in index)):
            resolution, reason = 'unresolved', reason or 'local_module_not_found'
        elif base and base.split('.')[0] in sys.stdlib_module_names:
            resolution, reason = 'stdlib', 'host_stdlib_module_name'
        elif base and base.split('.')[0] in KNOWN_EXTERNAL | set(options.external_modules):
            resolution, reason = 'external', 'known_or_caller_declared_external_module'
        else:
            resolution, reason = 'unresolved', 'not_local_stdlib_or_known_external'
        item.update(resolution=resolution, resolved_name=base,
                    candidate_module_ids=sorted(candidates), namespace_paths=namespaces_found,
                    symbol_status=symbol_status, reason=reason)
        if resolution == 'internal' and len(candidates) == 1:
            target = next(iter(candidates))
            dependencies.append({'id': 'dependency_' + item['id'].removeprefix('import_'),
                'source_module_id': source['id'], 'target_module_id': target,
                'relationship': 'imports', 'import_id': item['id'],
                'target_parsed': by_id[target]['parsed'],
                **{key: item[key] for key in ('file', 'start_line', 'end_line')}})
        if resolution in {'external', 'stdlib'}:
            external.append({'import_id': item['id'], 'module': base, 'kind': resolution,
                             **{key: item[key] for key in ('file', 'start_line', 'end_line')}})
        if resolution in {'unresolved', 'ambiguous'}:
            unresolved.append({'kind': 'import', 'reference_id': item['id'], 'name': base,
                'reason': reason, 'candidate_module_ids': sorted(candidates),
                **{key: item[key] for key in ('file', 'start_line', 'end_line')}})
    return roots, dependencies, external, unresolved
