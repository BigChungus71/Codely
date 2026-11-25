"""Conservative static import resolution across Python, Java, JavaScript, TypeScript, JSX and TSX."""
from pathlib import PurePosixPath
import posixpath
import sys


KNOWN_EXTERNAL = {'fastapi', 'flask', 'flask_login', 'flask_cors', 'flask_sqlalchemy',
                  'django', 'requests', 'httpx', 'sqlalchemy', 'sqlmodel', 'pydantic',
                  'networkx', 'pytest', 'yaml', 'uvicorn', 'numpy', 'pandas'}

NODE_STDLIB = {
    'assert', 'buffer', 'child_process', 'cluster', 'crypto', 'dgram', 'dns',
    'events', 'fs', 'http', 'http2', 'https', 'module', 'net', 'os', 'path',
    'perf_hooks', 'process', 'querystring', 'readline', 'stream', 'string_decoder',
    'timers', 'tls', 'tty', 'url', 'util', 'v8', 'vm', 'worker_threads', 'zlib',
}

KNOWN_JS_EXTERNAL = {
    'react', 'react-dom', 'next', 'express', 'axios', 'lodash', 'zod', 'prisma',
    '@prisma/client', 'mongoose', 'typeorm', 'sequelize', 'pg', 'mysql2', 'sqlite3',
    'better-sqlite3', 'passport', 'jsonwebtoken', 'bcrypt', 'bcryptjs', 'dotenv',
    'cors', 'helmet', 'jest', 'vitest', 'lucide-react', 'clsx', 'tailwind-merge',
}

KNOWN_JAVA_EXTERNAL_PREFIXES = (
    'org.springframework.',
    'com.fasterxml.',
    'org.slf4j.',
    'org.apache.',
    'org.junit.',
    'org.mockito.',
    'lombok.',
    'io.swagger.',
    'io.jsonwebtoken.',
    'org.hibernate.',
)

JS_EXTENSION_CANDIDATES = ('', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs')
JS_INDEX_CANDIDATES = ('/index.ts', '/index.tsx', '/index.js', '/index.jsx', '/index.mjs', '/index.cjs')


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


def _resolve_js_candidate(candidate_path: str, by_file: dict[str, dict]) -> list[str]:
    norm = posixpath.normpath(candidate_path).lstrip('./')
    if norm == '.' or norm.startswith('..'):
        return []
    hits = []
    for ext in JS_EXTENSION_CANDIDATES:
        probe = norm + ext
        if probe in by_file:
            hits.append(by_file[probe]['id'])
    if not hits:
        for idx in JS_INDEX_CANDIDATES:
            probe = norm + idx
            if probe in by_file:
                hits.append(by_file[probe]['id'])
    return sorted(set(hits))


def _resolve_ts_alias(spec: str, tsconfigs: list[dict], by_file: dict[str, dict]) -> tuple[list[str], bool]:
    matched_alias = False
    for cfg_entry in tsconfigs:
        cfg_file = cfg_entry.get('file', 'tsconfig.json')
        cfg_dir = posixpath.dirname(cfg_file)
        cfg = cfg_entry.get('tsconfig') or {}
        base_url = cfg.get('base_url') or '.'
        base_dir = posixpath.normpath(posixpath.join(cfg_dir, base_url)) if cfg_dir else posixpath.normpath(base_url)
        paths = cfg.get('paths') or {}
        for pattern, targets in paths.items():
            if '*' in pattern:
                prefix, suffix = pattern.split('*', 1)
                if spec.startswith(prefix) and spec.endswith(suffix):
                    matched_alias = True
                    inner = spec[len(prefix): len(spec) - len(suffix) if suffix else None]
                    for target_pat in targets:
                        rel_target = target_pat.replace('*', inner)
                        joined = posixpath.join(base_dir, rel_target) if base_dir != '.' else rel_target
                        hits = _resolve_js_candidate(joined, by_file)
                        if hits:
                            return hits, True
            elif spec == pattern:
                matched_alias = True
                for target_pat in targets:
                    joined = posixpath.join(base_dir, target_pat) if base_dir != '.' else target_pat
                    hits = _resolve_js_candidate(joined, by_file)
                    if hits:
                        return hits, True
        if cfg.get('base_url') and not spec.startswith('.'):
            joined = posixpath.join(base_dir, spec) if base_dir != '.' else spec
            hits = _resolve_js_candidate(joined, by_file)
            if hits:
                return hits, True
    return [], matched_alias


def resolve_imports(modules, imports, exports, options, *, config_files=None):
    config_files = config_files or []
    roots = {'.', *[root.replace('\\', '/').rstrip('/') or '.' for root in options.source_roots]}
    for module in modules:
        parts = PurePosixPath(module['file']).parts[:-1]
        for index, part in enumerate(parts):
            if part == 'src':
                roots.add('/'.join(parts[:index + 1]))
            if part == 'java' and index >= 2 and parts[index - 1] in {'main', 'test'} and parts[index - 2] == 'src':
                roots.add('/'.join(parts[:index + 1]))
    roots = sorted(roots)
    by_file = {module['file']: module for module in modules}
    by_id = {module['id']: module for module in modules}

    python_modules = [m for m in modules if m.get('language', 'python') == 'python']
    java_modules = [m for m in modules if m.get('language') == 'java']
    js_modules = [m for m in modules if m.get('language') in {'javascript', 'jsx', 'typescript', 'tsx'}]

    index, namespaces = {}, {}
    for module in python_modules:
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

    java_fqn_index: dict[str, set[str]] = {}
    java_pkg_index: dict[str, set[str]] = {}
    java_pkg_roots: set[str] = set()
    for module in java_modules:
        pkg = module.get('package_name')
        stem = PurePosixPath(module['file']).stem
        names = set()
        if pkg:
            java_pkg_index.setdefault(pkg, set()).add(module['id'])
            java_pkg_roots.add(pkg.split('.')[0])
            for exp in exports.get(module['id'], {stem}):
                fqn = f'{pkg}.{exp}'
                names.add(fqn)
                java_fqn_index.setdefault(fqn, set()).add(module['id'])
        else:
            for root in roots:
                if (derived := module_name(module['file'], root)):
                    names.add(derived)
                    java_fqn_index.setdefault(derived, set()).add(module['id'])
        module['names'] = sorted(names) if names else [stem]

    for module in js_modules:
        names = set()
        for root in roots:
            try:
                rel = PurePosixPath(module['file']).relative_to(PurePosixPath(root)).with_suffix('')
                parts = list(rel.parts)
                if parts[-1:] == ['index'] and len(parts) > 1:
                    parts.pop()
                if parts:
                    names.add('/'.join(parts))
            except ValueError:
                pass
        module['names'] = sorted(names) if names else [PurePosixPath(module['file']).stem]

    tsconfigs = [cfg for cfg in config_files if cfg.get('tsconfig') is not None]
    declared_npm_pkgs: set[str] = set()
    for cfg in config_files:
        for dep in cfg.get('dependencies') or []:
            declared_npm_pkgs.add(dep)

    dependencies, external, unresolved = [], [], []
    for item in imports:
        source = by_file[item['file']]
        lang = source.get('language', 'python')
        kind = item.get('kind', '')
        name = item['module']
        base = name
        reason = None
        candidates = set()
        symbol_status = None
        namespaces_found = []

        if lang == 'java' or kind in {'java_import', 'java_static'}:
            full_ref = f'{name}.{item["name"]}' if item.get('name') else name
            base = full_ref
            if item.get('name') == '*':
                pkg_hits = set(java_pkg_index.get(name, set()))
                if len(pkg_hits) == 1:
                    candidates = pkg_hits
                    resolution, reason = 'internal', 'java_package_wildcard'
                elif len(pkg_hits) > 1:
                    candidates = pkg_hits
                    resolution, reason = 'ambiguous', 'multiple_local_candidates'
                elif name.startswith(('java.', 'javax.', 'jakarta.')):
                    resolution, reason = 'stdlib', 'java_platform_package'
                elif name.startswith(KNOWN_JAVA_EXTERNAL_PREFIXES) or name.split('.')[0] in set(options.external_modules):
                    resolution, reason = 'external', 'known_or_caller_declared_external_module'
                elif name.split('.')[0] in java_pkg_roots:
                    resolution, reason = 'unresolved', 'local_module_not_found'
                else:
                    resolution, reason = 'unresolved', 'not_local_stdlib_or_known_external'
            else:
                direct_hits = set(java_fqn_index.get(full_ref, set()))
                if not direct_hits and kind == 'java_static' and '.' in name:
                    # import static pkg.Class.METHOD -> pkg.Class
                    direct_hits = set(java_fqn_index.get(name, set()))
                if len(direct_hits) == 1:
                    candidates = direct_hits
                    resolution, reason = 'internal', 'java_fqn_match'
                elif len(direct_hits) > 1:
                    candidates = direct_hits
                    resolution, reason = 'ambiguous', 'multiple_local_candidates'
                elif full_ref.startswith(('java.', 'javax.', 'jakarta.')):
                    resolution, reason = 'stdlib', 'java_platform_package'
                elif full_ref.startswith(KNOWN_JAVA_EXTERNAL_PREFIXES) or full_ref.split('.')[0] in set(options.external_modules):
                    resolution, reason = 'external', 'known_or_caller_declared_external_module'
                elif full_ref.split('.')[0] in java_pkg_roots:
                    resolution, reason = 'unresolved', 'local_module_not_found'
                else:
                    resolution, reason = 'unresolved', 'not_local_stdlib_or_known_external'

        elif lang in {'javascript', 'jsx', 'typescript', 'tsx'}:
            spec = name
            base = spec
            if spec.startswith(('./', '../')) or spec in {'.', '..'}:
                src_dir = posixpath.dirname(source['file'])
                joined = posixpath.join(src_dir, spec) if src_dir else spec
                norm_check = posixpath.normpath(joined)
                if norm_check.startswith('..'):
                    resolution, reason = 'unresolved', 'relative_import_beyond_source_root'
                else:
                    hits = _resolve_js_candidate(joined, by_file)
                    if len(hits) == 1:
                        candidates = set(hits)
                        resolution, reason = 'internal', 'js_relative_match'
                    elif len(hits) > 1:
                        candidates = set(hits)
                        resolution, reason = 'ambiguous', 'multiple_local_candidates'
                    else:
                        resolution, reason = 'unresolved', 'local_module_not_found'
            else:
                alias_hits, matched_alias = _resolve_ts_alias(spec, tsconfigs, by_file)
                if len(alias_hits) == 1:
                    candidates = set(alias_hits)
                    resolution, reason = 'internal', 'tsconfig_path_alias_match'
                elif len(alias_hits) > 1:
                    candidates = set(alias_hits)
                    resolution, reason = 'ambiguous', 'multiple_local_candidates'
                elif matched_alias:
                    resolution, reason = 'unresolved', 'local_module_not_found'
                elif spec.startswith('node:') or spec.split('/')[0] in NODE_STDLIB:
                    resolution, reason = 'stdlib', 'nodejs_builtin_module'
                else:
                    pkg_root = spec if not spec.startswith('@') else '/'.join(spec.split('/')[:2])
                    sub_root = spec.split('/')[0]
                    if (
                        pkg_root in KNOWN_JS_EXTERNAL
                        or sub_root in KNOWN_JS_EXTERNAL
                        or pkg_root.startswith('@nestjs/')
                        or pkg_root.startswith('@testing-library/')
                        or pkg_root in declared_npm_pkgs
                        or pkg_root in set(options.external_modules)
                        or sub_root in set(options.external_modules)
                    ):
                        resolution, reason = 'external', 'known_or_caller_declared_external_module'
                    else:
                        resolution, reason = 'unresolved', 'not_local_stdlib_or_known_external'

        else:
            # Python static resolution (unchanged behavior)
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
