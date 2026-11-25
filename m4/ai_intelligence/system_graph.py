"""Bounded Java/Spring and React system graph. Reads source without executing it."""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from .context import _language

SKIP = {'.git', '.venv', 'venv', 'node_modules', 'target', 'dist', 'build', 'coverage', 'vendor', 'out'}
WEB = {'.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'}
LIMITS = {'files': 2500, 'file_bytes': 384_000, 'total_bytes': 20_000_000, 'nodes': 180, 'edges': 500}
SPRING_ROLES = {
    'RestController': 'controller', 'Controller': 'controller', 'Service': 'service',
    'Repository': 'repository', 'Configuration': 'configuration',
    'SpringBootApplication': 'configuration', 'Component': 'component',
}
ANNOTATION_PACKAGES = {
    'RestController': 'org.springframework.web.bind.annotation',
    'RequestMapping': 'org.springframework.web.bind.annotation',
    'Controller': 'org.springframework.stereotype',
    'Service': 'org.springframework.stereotype',
    'Repository': 'org.springframework.stereotype',
    'Component': 'org.springframework.stereotype',
    'Configuration': 'org.springframework.context.annotation',
    'SpringBootApplication': 'org.springframework.boot.autoconfigure',
}
WEB_CAPABILITIES = {
    'react-router': 'routing', 'react-router-dom': 'routing', '@tanstack/react-router': 'routing',
    '@reduxjs/toolkit': 'state_management', 'react-redux': 'state_management',
    'zustand': 'state_management', 'jotai': 'state_management',
}
MAVEN_INTEGRATIONS = {
    'spring-boot-starter-data-jpa': ('database', 'JPA database integration'),
    'spring-boot-starter-jdbc': ('database', 'JDBC integration'),
    'spring-boot-starter-data-redis': ('database', 'Redis integration'),
    'spring-boot-starter-mail': ('external_api', 'Spring Mail integration'),
    'spring-ai-openai-spring-boot-starter': ('ai_service', 'OpenAI integration'),
    'spring-ai-starter-model-openai': ('ai_service', 'OpenAI integration'),
    'spring-ai-starter-model-vertex-ai-gemini': ('ai_service', 'Gemini integration'),
}
ROUTE = re.compile(r'["\'](/api(?:/[A-Za-z0-9_./-]+)?)["\']')
TYPES = re.compile(r'(?<![\w.])(?:[a-z_]\w*\.)*[A-Z]\w*')
IDENTIFIER = re.compile(r'[A-Za-z_$][\w$]*\Z')


def stable_id(kind, *entry):
    return kind + '_' + hashlib.sha256('\0'.join(entry).encode()).hexdigest()[:20]


def ref(file, node=None, line=None):
    start = line or (node.start_point.row + 1 if node else 1)
    end = max(start, node.end_point.row + bool(node.end_point.column)) if node else start
    return {'file': file, 'start_line': start, 'end_line': end}


def walk(node):
    stack = [node]
    while stack:
        item = stack.pop()
        yield item
        stack.extend(reversed(item.named_children))


def content(node):
    return node.text.decode('utf-8') if node else ''


class SystemGraph:
    def __init__(self, root):
        self.root = root
        self.nodes = {}
        self.edges = {}
        self.diagnostics = []
        self.parsed = defaultdict(int)
        self.detected = set()
        self.apps = {'backend': {}, 'frontend': {}}
        self.handlers = defaultdict(list)
        self.skipped = 0

    def add_node(self, key, label, kind, evidence):
        identifier = stable_id('component', kind, key)
        if identifier not in self.nodes:
            if len(self.nodes) >= LIMITS['nodes']:
                self.limit('node_limit')
                return None
            self.nodes[identifier] = {
                'id': identifier, 'label': label[:150], 'type': kind,
                'file': evidence['file'], 'files': [evidence['file']], 'evidence': [evidence],
            }
        elif evidence['file'] not in self.nodes[identifier]['files'] and len(self.nodes[identifier]['files']) < 6:
            self.nodes[identifier]['files'].append(evidence['file'])
            self.nodes[identifier]['evidence'].append(evidence)
        return identifier

    def add_edge(self, source, target, relationship, confidence, evidence):
        if not source or not target or source == target:
            return
        identifier = stable_id('relationship', source, target, relationship)
        if identifier not in self.edges:
            if len(self.edges) >= LIMITS['edges']:
                self.limit('edge_limit')
                return
            self.edges[identifier] = {
                'id': identifier, 'source': source, 'target': target, 'relationship': relationship,
                'confidence': confidence, 'evidence': [], **evidence[0],
            }
        for item in evidence:
            row = self.edges[identifier]['evidence']
            if item not in row and len(row) < 12:
                row.append(item)

    def limit(self, reason):
        if {'code': reason} not in self.diagnostics:
            self.diagnostics.append({'code': reason})

    def sources(self):
        total = count = 0
        for folder, dirs, files in os.walk(self.root, followlinks=False,
                                         onerror=lambda _: self.limit('unreadable_directory')):
            dirs[:] = sorted(name for name in dirs if name not in SKIP and not name.startswith('.')
                             and not (Path(folder) / name).is_symlink())
            for name in sorted(files):
                if name.startswith('.') or name.endswith(('.d.ts', '.min.js')):
                    continue
                path = Path(folder) / name
                suffix = path.suffix.lower()
                if name not in {'pom.xml', 'package.json'} and suffix not in WEB | {'.java'}:
                    continue
                if count >= LIMITS['files'] or total >= LIMITS['total_bytes']:
                    self.limit('inventory_limit')
                    return
                rel = path.relative_to(self.root).as_posix()
                self.detected.add('java' if suffix == '.java' else 'typescript' if suffix in {'.ts', '.tsx'}
                                  else 'javascript' if suffix in WEB else 'manifests')
                count += 1
                try:
                    if path.is_symlink() or not path.resolve().is_relative_to(self.root):
                        raise OSError
                    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
                    with os.fdopen(os.open(path, flags), 'rb') as stream:
                        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                            raise OSError
                        data = stream.read(min(LIMITS['file_bytes'], LIMITS['total_bytes'] - total) + 1)
                    if len(data) > min(LIMITS['file_bytes'], LIMITS['total_bytes'] - total):
                        raise ValueError
                    text = data.decode('utf-8')
                except (ValueError, OSError):
                    self.skipped += 1
                    self.diagnostics.append({'code': 'unreadable_or_oversized_source', 'file': rel})
                    continue
                total += len(data)
                yield rel, suffix, text

    def collect_manifest(self, file, text):
        directory = Path(file).parent
        if Path(file).name == 'pom.xml':
            try:
                if '<!DOCTYPE' in text.upper():
                    raise ValueError
                project = ElementTree.fromstring(text)
            except (ElementTree.ParseError, DefusedXmlException, ValueError):
                self.diagnostics.append({'code': 'invalid_manifest', 'file': file})
                return
            dependencies = {entry.findtext('{*}artifactId') for entry in
                            project.findall('./{*}dependencies/{*}dependency')
                            if entry.findtext('{*}scope') != 'test'}
            parent = project.findtext('./{*}parent/{*}artifactId') or ''
            if parent != 'spring-boot-starter-parent' and not any(
                    name and name.startswith('spring-boot-starter') for name in dependencies):
                return
            backend = self.add_node(str(directory), 'Spring Boot backend', 'backend', ref(file))
            self.apps['backend'][directory] = backend
            for name in sorted(dependencies & MAVEN_INTEGRATIONS.keys()):
                kind, label = MAVEN_INTEGRATIONS[name]
                line = next((i for i, row in enumerate(text.splitlines(), 1) if name in row), 1)
                evidence = ref(file, line=line)
                target = self.add_node(f'{directory}:{name}', label, kind, evidence)
                self.add_edge(backend, target, 'declares_integration', 'confirmed', [evidence])
        else:
            try:
                package = json.loads(text)
                deps = set(package.get('dependencies', {})) | set(package.get('devDependencies', {}))
            except (ValueError, TypeError, AttributeError):
                self.diagnostics.append({'code': 'invalid_manifest', 'file': file})
                return
            if 'react' in deps:
                self.apps['frontend'][directory] = self.add_node(str(directory), 'React frontend', 'frontend', ref(file))

    def owner(self, file, app):
        return next(((parent, self.apps[app][parent]) for parent in Path(file).parents
                     if parent in self.apps[app]), (None, None))

    def parse(self, file, suffix, text):
        language = _language('.js' if suffix in {'.cjs', '.mjs'} else suffix)
        if language is None:
            self.limit(f'parser_unavailable:{suffix}')
            return None
        from tree_sitter import Parser
        root = Parser(language).parse(text.encode()).root_node
        if root.has_error:
            self.skipped += 1
            self.diagnostics.append({'code': 'source_parse_error', 'file': file})
            return None
        self.parsed['java' if suffix == '.java' else 'typescript' if suffix in {'.ts', '.tsx'}
                    else 'javascript'] += 1
        return root

    def java(self, sources):
        registry = defaultdict(list)
        records = []
        for file, root in sources:
            if 'src/test' in file or 'src/it' in file:
                continue
            package = next((content(node).removeprefix('package').strip(' ;\r\n')
                            for node in root.named_children if node.type == 'package_declaration'), '')
            imports = {}
            wildcards = set()
            for node in root.named_children:
                if node.type == 'import_declaration':
                    name = content(node).removeprefix('import').strip(' ;\r\n')
                    if name.startswith('static '):
                        continue
                    if name.endswith('.*'):
                        wildcards.add(name[:-2])
                    else:
                        imports[name.rsplit('.', 1)[-1]] = name
            for node in root.named_children:
                if node.type not in {'class_declaration', 'interface_declaration', 'record_declaration'}:
                    continue
                simple = content(node.child_by_field_name('name'))
                if not simple:
                    continue
                name = f'{package}.{simple}' if package else simple
                modifiers = next((part for part in node.named_children if part.type == 'modifiers'), None)
                annotations = []
                for part in modifiers.named_children if modifiers else []:
                    if part.type in {'annotation', 'marker_annotation'}:
                        raw = content(part.child_by_field_name('name'))
                        symbol = imports.get(raw, raw)
                        if symbol == raw and ANNOTATION_PACKAGES.get(raw) in wildcards:
                            symbol = f'{ANNOTATION_PACKAGES[raw]}.{raw}'
                        if symbol.startswith('org.springframework.'):
                            annotations.append((symbol.rsplit('.', 1)[-1], part))
                role = next((value for kind, value in SPRING_ROLES.items()
                             if any(annotation == kind for annotation, _ in annotations)), None)
                if not role and 'JpaRepository' in imports and imports['JpaRepository'].startswith('org.springframework.data.'):
                    signature = content(node).split('{', 1)[0]
                    if re.search(r'\bextends\s+JpaRepository\b', signature):
                        role = 'repository'
                if not role:
                    continue
                evidence = ref(file, node.child_by_field_name('name'))
                identifier = self.add_node(name + ':' + file, simple, role, evidence)
                if not identifier:
                    continue
                registry[name].append(identifier)
                _, app = self.owner(file, 'backend')
                self.add_edge(app, identifier, 'contains', 'confirmed', [evidence])
                if role == 'controller':
                    for annotation, part in annotations:
                        if annotation == 'RequestMapping':
                            for route in ROUTE.findall(content(part)):
                                self.handlers[route.rstrip('/')].append((identifier, ref(file, part)))
                records.append((file, node, identifier, package, imports, wildcards))
        for file, node, identifier, package, imports, wildcards in records:
            body = node.child_by_field_name('body')
            for item in body.named_children if body else []:
                if item.type == 'field_declaration':
                    slots = [item.child_by_field_name('type')]
                    relationship = 'declares_field_type'
                elif item.type == 'constructor_declaration':
                    params = item.child_by_field_name('parameters')
                    slots = [param.child_by_field_name('type') for param in params.named_children] if params else []
                    relationship = 'constructor_dependency'
                else:
                    continue
                for slot in slots:
                    for name in sorted(set(TYPES.findall(content(slot)))):
                        qualified = imports.get(name, f'{package}.{name}' if package and '.' not in name else name)
                        targets = registry.get(qualified, ())
                        if not targets and name not in imports and '.' not in name:
                            targets = [target for wildcard in sorted(wildcards)
                                       for target in registry.get(f'{wildcard}.{name}', ())]
                        if len(targets) == 1:
                            self.add_edge(identifier, targets[0], relationship, 'confirmed', [ref(file, slot)])
                        elif len(targets) > 1:
                            self.limit('ambiguous_java_type')

    def capability(self, identifier, kind, evidence):
        entries = self.nodes[identifier].setdefault('capabilities', [])
        if not any(item['type'] == kind for item in entries):
            entries.append({'type': kind, **evidence})

    def frontend(self, sources):
        grouped = {}
        for file, root in sources:
            directory, app = self.owner(file, 'frontend')
            if app is None:
                continue
            relative = Path(file).relative_to(directory)
            if len(relative.parts) < 2 or relative.parts[0] not in {'src', 'app', 'pages'}:
                continue
            parts = relative.parts
            group = parts[2] if len(parts) > 3 and parts[1] in {'features', 'modules'} else (
                parts[1] if len(parts) > 2 else 'Application entry')
            identifier = self.add_node(f'{directory}:{group}', group.replace('-', ' '), 'frontend_module', ref(file))
            if identifier:
                grouped[file] = (identifier, root)
                self.add_edge(app, identifier, 'contains', 'confirmed', [ref(file)])
        for file, (identifier, root) in grouped.items():
            constants = {}
            for node in root.named_children:
                if node.type != 'lexical_declaration' or not content(node).lstrip().startswith('const '):
                    continue
                for part in node.named_children:
                    name = content(part.child_by_field_name('name'))
                    value = part.child_by_field_name('value')
                    if IDENTIFIER.fullmatch(name) and value and value.type == 'string':
                        constants[name] = content(value).strip('\"\'')
            for node in walk(root):
                if node.type in {'import_statement', 'export_statement'}:
                    raw = content(node.child_by_field_name('source')).strip('\"\'')
                    if raw in WEB_CAPABILITIES:
                        self.capability(identifier, WEB_CAPABILITIES[raw], ref(file, node))
                    if not raw.startswith('.'):
                        continue
                    base = Path(os.path.normpath(str(Path(file).parent / raw)))
                    candidates = [base.as_posix(), *(str(base) + suffix for suffix in sorted(WEB)),
                                  *((base / ('index' + suffix)).as_posix() for suffix in sorted(WEB))]
                    targets = {grouped[path][0] for path in candidates if path in grouped}
                    if len(targets) == 1:
                        self.add_edge(identifier, next(iter(targets)), 'imports', 'confirmed', [ref(file, node)])
                    elif len(targets) > 1:
                        self.limit('ambiguous_frontend_import')
                elif node.type == 'call_expression' and content(node.child_by_field_name('function')) in {
                    'fetch', 'axios.get', 'axios.post', 'axios.put', 'axios.delete',
                }:
                    args = node.child_by_field_name('arguments')
                    target = args.named_children[0] if args and args.named_children else None
                    raw = content(target).strip('\"\'`')
                    raw = constants.get(raw, raw)
                    prefix = re.match(r'^\$\{([\w$]+)\}', raw)
                    if prefix and prefix[1] in constants:
                        raw = constants[prefix[1]] + raw[prefix.end():]
                    if not re.match(r'^/api(?:/|$)', raw):
                        continue
                    self.capability(identifier, 'api_client', ref(file, target))
                    matches = [(route, entries) for route, entries in self.handlers.items()
                               if raw == route or raw.startswith(route + '/')]
                    if matches:
                        _, entries = max(matches, key=lambda item: len(item[0]))
                        if len({row[0] for row in entries}) == 1:
                            controller, evidence = entries[0]
                            self.add_edge(identifier, controller, 'api_route_reference', 'inferred',
                                          [ref(file, target), evidence])
                        else:
                            self.limit('ambiguous_api_route')
                    else:
                        self.limit('unresolved_api_route')

    def result(self):
        partial = bool(self.diagnostics)
        return {
            'graph_type': 'system', 'status': 'partial' if self.nodes and partial else
            'complete' if self.nodes else 'unsupported',
            'nodes': list(self.nodes.values()), 'edges': list(self.edges.values()),
            'diagnostics': self.diagnostics,
            'coverage': {'detected_languages': sorted(self.detected), 'parsed_files': dict(self.parsed),
                         'skipped_files': self.skipped, 'limits': LIMITS.copy(),
                         'limitations': ['Static evidence only; no runtime call, deployment or API reachability proof.',
                                         'Only explicit Spring types, Maven/React manifests and local web imports are modeled.',
                                         'API links match literal route prefixes and are inferred; dynamic routes and aliases are omitted.']},
        }


def analyze_system(project_path):
    root = Path(project_path).resolve()
    graph = SystemGraph(root)
    if not root.is_dir():
        graph.limit('invalid_repository')
        return graph.result() | {'status': 'error'}
    java, web = [], []
    for file, suffix, text in graph.sources():
        if Path(file).name in {'pom.xml', 'package.json'}:
            graph.collect_manifest(file, text)
        elif ast := graph.parse(file, suffix, text):
            (java if suffix == '.java' else web).append((file, ast))
    graph.java(java)
    graph.frontend(web)
    return graph.result()
