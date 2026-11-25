"""Tree-sitter structural extractors for Java, JavaScript, TypeScript, JSX and TSX.

Outputs normalized dictionaries matching the RepositoryStructure contract without
executing target code or retaining literal secrets/values.
"""
from pathlib import PurePosixPath
import re

from .structure_extractor import stable_id


HTTP_METHODS = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options', 'all', 'use'}
SPRING_ROUTE_ANNOTATIONS = {
    'GetMapping': ['GET'],
    'PostMapping': ['POST'],
    'PutMapping': ['PUT'],
    'PatchMapping': ['PATCH'],
    'DeleteMapping': ['DELETE'],
    'RequestMapping': [],
}
NEST_ROUTE_DECORATORS = {
    'Get': ['GET'],
    'Post': ['POST'],
    'Put': ['PUT'],
    'Patch': ['PATCH'],
    'Delete': ['DELETE'],
    'All': [],
}
JS_DB_PACKAGES = {'prisma', '@prisma/client', 'mongoose', 'typeorm', 'sequelize', 'pg', 'mysql2', 'sqlite3', 'better-sqlite3'}
JS_AUTH_PACKAGES = {'passport', 'jsonwebtoken', 'next-auth', '@nestjs/jwt', 'bcrypt', 'bcryptjs'}


def _normalize_route_pattern(raw_literal: str) -> str | None:
    """Normalize static URL route literals for safe non-plaintext API matching."""
    text = raw_literal.strip().strip('"\'`')
    if not text.startswith('/'):
        return None
    # Strip query strings and normalize path parameters (:id, {id}, [id], ${id})
    path_only = text.split('?', 1)[0].rstrip('/') or '/'
    normalized = re.sub(r'(\$\{[^}]+\}|\[[^]]+\]|\{[^}]+\}|:[A-Za-z_][A-Za-z0-9_]*)', '{param}', path_only)
    return normalized


class _BaseTsExtractor:
    def __init__(self, file: str, module_id: str, language: str, source_bytes: bytes):
        self.file = file
        self.module_id = module_id
        self.language = language
        self.source = source_bytes
        self.classes: list[dict] = []
        self.functions: list[dict] = []
        self.symbols: list[dict] = []
        self.imports: list[dict] = []
        self.calls: list[dict] = []
        self.frameworks: list[dict] = []
        self.classifications: list[dict] = []
        self.exports: set[str] = set()
        self.route_records: list[dict] = []
        self.api_client_calls: list[dict] = []
        self.component_references: list[dict] = []
        self.package_name: str | None = None
        self._ordinals: dict[tuple[str, str], int] = {}

    def text(self, node) -> str:
        if node is None:
            return ''
        return self.source[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

    def loc(self, node) -> dict:
        return {
            'file': self.file,
            'start_line': node.start_point[0] + 1,
            'end_line': node.end_point[0] + 1,
            'start_column': node.start_point[1],
            'end_column': node.end_point[1],
        }

    def node_id(self, kind: str, node, name: str = '') -> str:
        if kind in {'class', 'function', 'symbol'}:
            key = (kind, name)
            ordinal = self._ordinals.get(key, 0)
            self._ordinals[key] = ordinal + 1
            return stable_id(kind, self.file, name, ordinal)
        return stable_id(
            kind,
            self.file,
            name,
            node.start_point[0] + 1,
            node.start_point[1],
            node.end_point[0] + 1,
            node.end_point[1],
        )

    def classify(self, component: str, confidence: str, node=None, reason: str = 'filename_heuristic', symbol_id=None):
        self.classifications.append(
            {
                'component': component,
                'confidence': confidence,
                'reason': reason,
                'module_id': self.module_id,
                'symbol_id': symbol_id,
                'evidence': self.loc(node) if node is not None else {'file': self.file},
            }
        )

    def apply_filename_heuristics(self, extra_mappings: dict[str, set[str]]) -> None:
        path = PurePosixPath(self.file)
        stem_tokens = {tok.lower() for tok in re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z]|$)', path.stem)}
        words = {part.lower() for part in path.parts} | {path.stem.lower()} | stem_tokens
        mappings = {
            'service': {'service', 'services'},
            'controller': {'controller', 'controllers', 'handler', 'handlers'},
            'data_access': {'repository', 'repositories', 'database', 'db', 'dao'},
            'database_model': {'model', 'models', 'entity', 'entities', 'schema', 'schemas'},
            'configuration': {'config', 'configuration', 'settings'},
            'authentication': {'auth', 'authentication', 'security'},
            'utility': {'util', 'utils', 'utilities', 'helper', 'helpers'},
        }
        for key, vals in extra_mappings.items():
            mappings.setdefault(key, set()).update(vals)
        confirmed = {entry['component'] for entry in self.classifications if entry['confidence'] == 'confirmed'}
        for component, candidates in mappings.items():
            if words & candidates and component not in confirmed:
                self.classify(component, 'inferred')
        if (
            path.stem.lower().endswith(('test', 'tests', 'spec'))
            or '.test.' in path.name.lower()
            or '.spec.' in path.name.lower()
            or 'test' in {p.lower() for p in path.parts}
            or 'tests' in {p.lower() for p in path.parts}
            or '__tests__' in {p.lower() for p in path.parts}
        ):
            self.classify('test', 'inferred')


class JavaStructureAdapter(_BaseTsExtractor):
    def extract(self, root_node) -> None:
        self._walk(root_node, parent_id=self.module_id, parent_name='', in_conditional=False)
        self.apply_filename_heuristics({})

    def _annotations(self, decl_node) -> list[dict]:
        anns = []
        for child in decl_node.children:
            if child.type == 'modifiers':
                for sub in child.children:
                    if sub.type in {'annotation', 'marker_annotation'}:
                        name_node = sub.child_by_field_name('name')
                        name = self.text(name_node) if name_node is not None else self.text(sub).lstrip('@').split('(', 1)[0].strip()
                        anns.append(
                            {
                                'name': name,
                                'is_factory': sub.type == 'annotation',
                                'raw_args': self.text(sub.child_by_field_name('arguments')) if sub.type == 'annotation' else '',
                                **self.loc(sub),
                            }
                        )
        return anns

    def _parameters(self, params_node) -> list[dict]:
        result = []
        if params_node is None:
            return result
        for child in params_node.children:
            if child.type in {'formal_parameter', 'spread_parameter'}:
                name_node = child.child_by_field_name('name')
                if name_node is None:
                    # spread_parameter has variable_declarator child
                    for sub in child.children:
                        if sub.type == 'variable_declarator':
                            name_node = sub.child_by_field_name('name')
                            break
                type_node = child.child_by_field_name('type')
                param_name = self.text(name_node) if name_node is not None else 'arg'
                result.append(
                    {
                        'name': param_name,
                        'kind': 'var_positional' if child.type == 'spread_parameter' else 'positional',
                        'has_default': False,
                        'annotation': self.text(type_node) if type_node is not None else None,
                        **self.loc(child),
                    }
                )
        return result

    def _extract_bases(self, class_node) -> list[dict]:
        bases = []
        for child in class_node.children:
            if child.type == 'superclass':
                for sub in child.children:
                    if sub.type in {'type_identifier', 'scoped_type_identifier', 'generic_type'}:
                        raw = self.text(sub).split('<', 1)[0].strip()
                        bases.append({'name': raw, 'import_qualified_name': None, 'is_dynamic': False, 'relation': 'extends'})
            elif child.type in {'super_interfaces', 'extends_interfaces'}:
                for sub in child.children:
                    if sub.type == 'type_list':
                        for item in sub.children:
                            if item.type in {'type_identifier', 'scoped_type_identifier', 'generic_type'}:
                                raw = self.text(item).split('<', 1)[0].strip()
                                bases.append(
                                    {
                                        'name': raw,
                                        'import_qualified_name': None,
                                        'is_dynamic': False,
                                        'relation': 'implements' if child.type == 'super_interfaces' else 'extends',
                                    }
                                )
        return bases

    def _walk(self, node, *, parent_id: str, parent_name: str, in_conditional: bool, pending_decs: list[dict] | None = None) -> None:
        ntype = node.type
        pending_decs = pending_decs or []
        if ntype == 'package_declaration':
            raw = self.text(node).removeprefix('package').rstrip(';').strip()
            if raw:
                self.package_name = raw
            return
        if ntype == 'import_declaration':
            raw = self.text(node).removeprefix('import').strip().rstrip(';').strip()
            is_static = False
            if raw.startswith('static '):
                is_static = True
                raw = raw.removeprefix('static').strip()
            parts = raw.rsplit('.', 1)
            mod_part = parts[0] if len(parts) == 2 else raw
            name_part = parts[1] if len(parts) == 2 else None
            binding = name_part or raw
            self.imports.append(
                {
                    'id': self.node_id('import', node, raw),
                    'module_id': self.module_id,
                    'scope_id': parent_id,
                    'module': mod_part,
                    'name': name_part,
                    'alias': None,
                    'binding': binding,
                    'level': 0,
                    'kind': 'java_static' if is_static else 'java_import',
                    'conditional': in_conditional,
                    **self.loc(node),
                }
            )
            if raw.startswith('org.springframework.boot'):
                self.frameworks.append({'id': self.node_id('framework_import', node, raw), 'framework': 'spring_boot', 'kind': 'import', 'binding': binding, 'symbol_id': parent_id, **self.loc(node)})
            elif raw.startswith('org.springframework.web'):
                self.frameworks.append({'id': self.node_id('framework_import', node, raw), 'framework': 'spring_mvc', 'kind': 'import', 'binding': binding, 'symbol_id': parent_id, **self.loc(node)})
            elif raw.startswith('org.springframework.security'):
                self.classify('authentication', 'confirmed', node, 'spring_security_import')
            elif raw.startswith(('jakarta.persistence', 'javax.persistence', 'org.springframework.data')):
                self.frameworks.append({'id': self.node_id('framework_import', node, raw), 'framework': 'jpa', 'kind': 'import', 'binding': binding, 'symbol_id': parent_id, **self.loc(node)})
            return

        if ntype in {'class_declaration', 'interface_declaration', 'enum_declaration', 'record_declaration'}:
            name_node = node.child_by_field_name('name')
            cname = self.text(name_node) if name_node is not None else 'Anonymous'
            qual = f'{parent_name}.{cname}' if parent_name else cname
            cid = self.node_id('class', node, qual)
            anns = self._annotations(node)
            bases = self._extract_bases(node)
            loc = self.loc(node)
            extent_start = min([loc['start_line']] + [a['start_line'] for a in anns])
            self.classes.append(
                {
                    'id': cid,
                    'module_id': self.module_id,
                    'parent_id': parent_id,
                    'name': cname,
                    'qualified_name': qual,
                    'kind_detail': ntype.removesuffix('_declaration'),
                    'bases': bases,
                    'decorators': [{'name': a['name'], 'is_factory': a['is_factory'], 'file': a['file'], 'start_line': a['start_line'], 'end_line': a['end_line'], 'start_column': a['start_column'], 'end_column': a['end_column']} for a in anns],
                    'extent_start_line': extent_start,
                    **loc,
                }
            )
            if parent_id == self.module_id:
                self.exports.add(cname)
            class_prefix = ''
            for ann in anns:
                short = ann['name'].split('.')[-1]
                if short == 'SpringBootApplication':
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'spring_boot', 'kind': 'application', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('api_application', 'confirmed', node, 'spring_boot_application', cid)
                elif short in {'RestController', 'Controller'}:
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'spring_mvc', 'kind': 'controller', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('controller', 'confirmed', node, 'spring_controller_annotation', cid)
                elif short == 'RequestMapping':
                    m = re.search(r'"([^"]+)"', ann['raw_args'])
                    if m:
                        class_prefix = m.group(1)
                elif short == 'Service':
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'spring', 'kind': 'service', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('service', 'confirmed', node, 'spring_service_annotation', cid)
                elif short == 'Repository':
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'spring', 'kind': 'repository', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('data_access', 'confirmed', node, 'spring_repository_annotation', cid)
                elif short in {'Entity', 'Table'}:
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'jpa', 'kind': 'entity', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('database_model', 'confirmed', node, 'jpa_entity_annotation', cid)
                elif short in {'Configuration', 'ConfigurationProperties'}:
                    self.classify('configuration', 'confirmed', node, 'spring_configuration_annotation', cid)
            body = node.child_by_field_name('body')
            if body is not None:
                self._walk_children(body, parent_id=cid, parent_name=qual, in_conditional=in_conditional, class_prefix=class_prefix)
            return

        if ntype in {'method_declaration', 'constructor_declaration'}:
            name_node = node.child_by_field_name('name')
            fname = self.text(name_node) if name_node is not None else parent_name.rsplit('.', 1)[-1]
            qual = f'{parent_name}.{fname}' if parent_name else fname
            fid = self.node_id('function', node, qual)
            anns = self._annotations(node)
            params = self._parameters(node.child_by_field_name('parameters'))
            ret_node = node.child_by_field_name('type')
            loc = self.loc(node)
            extent_start = min([loc['start_line']] + [a['start_line'] for a in anns])
            self.functions.append(
                {
                    'id': fid,
                    'module_id': self.module_id,
                    'parent_id': parent_id,
                    'name': fname,
                    'qualified_name': qual,
                    'kind': 'method',
                    'is_constructor': ntype == 'constructor_declaration',
                    'is_async': False,
                    'parameters': params,
                    'decorators': [{'name': a['name'], 'is_factory': a['is_factory'], 'file': a['file'], 'start_line': a['start_line'], 'end_line': a['end_line'], 'start_column': a['start_column'], 'end_column': a['end_column']} for a in anns],
                    'return_annotation': self.text(ret_node) if ret_node is not None else None,
                    'extent_start_line': extent_start,
                    **loc,
                }
            )
            for ann in anns:
                short = ann['name'].split('.')[-1]
                if short in SPRING_ROUTE_ANNOTATIONS:
                    methods = list(SPRING_ROUTE_ANNOTATIONS[short])
                    m = re.search(r'"([^"]+)"', ann['raw_args'])
                    raw_path = m.group(1) if m else ''
                    self.frameworks.append(
                        {
                            'id': self.node_id('route', node, fid),
                            'framework': 'spring_mvc',
                            'kind': 'route',
                            'receiver': parent_name or 'controller',
                            'receiver_kind': 'controller',
                            'symbol_id': fid,
                            'methods': methods,
                            'path_is_literal': bool(m),
                            'path': '<redacted>',
                            **loc,
                        }
                    )
                    self.classify('controller', 'confirmed', node, 'spring_route_mapping', fid)
                    norm = _normalize_route_pattern(raw_path)
                    if norm:
                        self.route_records.append({'module_id': self.module_id, 'file': self.file, 'symbol_id': fid, 'methods': methods, 'normalized_path': norm, **loc})
                elif short in {'PreAuthorize', 'Secured', 'RolesAllowed'}:
                    self.classify('authentication', 'confirmed', node, 'spring_security_annotation', fid)
            body = node.child_by_field_name('body')
            if body is not None:
                self._walk_children(body, parent_id=fid, parent_name=qual, in_conditional=in_conditional)
            return

        if ntype in {'method_invocation', 'object_creation_expression'}:
            if ntype == 'method_invocation':
                obj_node = node.child_by_field_name('object')
                name_node = node.child_by_field_name('name')
                callee = (f'{self.text(obj_node)}.{self.text(name_node)}' if obj_node is not None else self.text(name_node))
            else:
                type_node = node.child_by_field_name('type')
                callee = self.text(type_node).split('<', 1)[0].strip()
            self.calls.append(
                {
                    'id': self.node_id('call', node, callee),
                    'module_id': self.module_id,
                    'scope_id': parent_id,
                    'callee': callee,
                    'import_qualified_name': None,
                    'resolution': 'syntactic_only' if callee else 'dynamic_callable',
                    **self.loc(node),
                }
            )
            if callee.endswith(('getConnection', 'createQuery', 'prepareStatement', 'executeQuery')):
                self.classify('data_access', 'confirmed', node, 'jdbc_database_api')
            if callee in {'System.getenv', 'env.getProperty'}:
                self.classify('configuration', 'confirmed', node, 'environment_api_indicator')

        cond = in_conditional or ntype in {'if_statement', 'try_statement', 'for_statement', 'enhanced_for_statement', 'while_statement', 'switch_expression'}
        self._walk_children(node, parent_id=parent_id, parent_name=parent_name, in_conditional=cond)

    def _walk_children(self, node, *, parent_id: str, parent_name: str, in_conditional: bool, class_prefix: str = '') -> None:
        base_route_count = len(self.route_records)
        for child in node.children:
            self._walk(child, parent_id=parent_id, parent_name=parent_name, in_conditional=in_conditional)
        if class_prefix and len(self.route_records) > base_route_count:
            prefix = class_prefix.rstrip('/')
            for rec in self.route_records[base_route_count:]:
                if not rec['normalized_path'].startswith(prefix):
                    rec['normalized_path'] = (prefix + '/' + rec['normalized_path'].lstrip('/')).rstrip('/') or '/'


class JsTsStructureAdapter(_BaseTsExtractor):
    def __init__(self, file: str, module_id: str, language: str, source_bytes: bytes):
        super().__init__(file, module_id, language, source_bytes)
        self.import_bindings: dict[str, tuple[str, str | None]] = {}
        self.factory_bindings: dict[str, tuple[str, str]] = {}
        self.has_react_import = False
        self.has_next_import = False
        self.has_jsx = False

    def extract(self, root_node) -> None:
        self._walk(root_node, parent_id=self.module_id, parent_name='', in_conditional=False)
        if self.has_next_import and PurePosixPath(self.file).stem in {'page', 'layout', 'route'} or 'pages' in PurePosixPath(self.file).parts:
            self.classify('router', 'confirmed', reason='nextjs_app_router_convention')
        self.apply_filename_heuristics({'frontend_component': {'component', 'components', 'page', 'pages', 'view', 'views'}})

    def _decorators(self, node) -> list[dict]:
        decs = []
        for child in node.children:
            if child.type == 'decorator':
                expr = self.text(child).lstrip('@').strip()
                name = expr.split('(', 1)[0].strip()
                decs.append({'name': name, 'is_factory': '(' in expr, 'raw': expr, **self.loc(child)})
        return decs

    def _parameters(self, params_node) -> list[dict]:
        result = []
        if params_node is None:
            return result
        for child in params_node.children:
            if child.type in {'identifier', 'required_parameter', 'optional_parameter', 'rest_parameter', 'object_pattern', 'array_pattern', 'assignment_pattern'}:
                if child.type == 'identifier':
                    pname, kind, has_def, ann = self.text(child), 'positional', False, None
                elif child.type == 'assignment_pattern':
                    left = child.child_by_field_name('left')
                    pname, kind, has_def, ann = (self.text(left) if left else 'param'), 'positional', True, None
                elif child.type == 'rest_parameter':
                    pname, kind, has_def, ann = self.text(child).lstrip('.').split(':', 1)[0].strip(), 'var_positional', False, None
                else:
                    pat = child.child_by_field_name('pattern') or child.child_by_field_name('name') or child
                    pname = self.text(pat).split(':', 1)[0].split('=', 1)[0].strip()
                    has_def = child.type == 'optional_parameter' or child.child_by_field_name('value') is not None
                    type_node = child.child_by_field_name('type')
                    ann = self.text(type_node).lstrip(':').strip() if type_node is not None else None
                    kind = 'var_positional' if self.text(child).lstrip().startswith('...') else 'positional'
                result.append({'name': pname or 'param', 'kind': kind, 'has_default': bool(has_def), 'annotation': ann, **self.loc(child)})
        return result

    def _record_import(self, node, source_mod: str, name: str | None, alias: str | None, binding: str, kind: str, in_conditional: bool) -> None:
        self.imports.append(
            {
                'id': self.node_id('import', node, f'{source_mod}:{binding}'),
                'module_id': self.module_id,
                'scope_id': self.module_id,
                'module': source_mod,
                'name': name,
                'alias': alias,
                'binding': binding,
                'level': 0,
                'kind': kind,
                'conditional': in_conditional,
                **self.loc(node),
            }
        )
        self.import_bindings[binding] = (source_mod, name)
        pkg_root = source_mod if not source_mod.startswith('@') else '/'.join(source_mod.split('/')[:2])
        if pkg_root == 'react' or pkg_root.startswith('react/'):
            self.has_react_import = True
            self.frameworks.append({'id': self.node_id('framework_import', node, source_mod), 'framework': 'react', 'kind': 'import', 'binding': binding, 'symbol_id': self.module_id, **self.loc(node)})
        elif pkg_root == 'next' or pkg_root.startswith('next/'):
            self.has_next_import = True
            self.frameworks.append({'id': self.node_id('framework_import', node, source_mod), 'framework': 'nextjs', 'kind': 'import', 'binding': binding, 'symbol_id': self.module_id, **self.loc(node)})
        elif pkg_root == 'express':
            self.frameworks.append({'id': self.node_id('framework_import', node, source_mod), 'framework': 'express', 'kind': 'import', 'binding': binding, 'symbol_id': self.module_id, **self.loc(node)})
        elif pkg_root.startswith('@nestjs/'):
            self.frameworks.append({'id': self.node_id('framework_import', node, source_mod), 'framework': 'nestjs', 'kind': 'import', 'binding': binding, 'symbol_id': self.module_id, **self.loc(node)})
        elif pkg_root in JS_DB_PACKAGES:
            self.classify('data_access', 'confirmed', node, 'database_package_import')
        elif pkg_root in JS_AUTH_PACKAGES:
            self.classify('authentication', 'confirmed', node, 'authentication_package_import')
        elif pkg_root == 'dotenv':
            self.classify('configuration', 'confirmed', node, 'environment_package_import')

    def _walk(self, node, *, parent_id: str, parent_name: str, in_conditional: bool, pending_decs: list[dict] | None = None) -> None:
        ntype = node.type
        pending_decs = pending_decs or []
        if ntype == 'import_statement':
            src_node = node.child_by_field_name('source')
            if src_node is None:
                return
            source_mod = self.text(src_node).strip('"\'`')
            clause = next((c for c in node.children if c.type == 'import_clause'), None)
            if clause is None:
                self._record_import(node, source_mod, None, None, source_mod, 'side_effect_import', in_conditional)
                return
            emitted = False
            for child in clause.children:
                if child.type == 'identifier':
                    self._record_import(node, source_mod, 'default', None, self.text(child), 'es_default', in_conditional)
                    emitted = True
                elif child.type == 'namespace_import':
                    ident = next((c for c in child.children if c.type == 'identifier'), None)
                    if ident is not None:
                        self._record_import(node, source_mod, '*', self.text(ident), self.text(ident), 'es_namespace', in_conditional)
                        emitted = True
                elif child.type == 'named_imports':
                    for spec in child.children:
                        if spec.type == 'import_specifier':
                            orig = spec.child_by_field_name('name')
                            alias = spec.child_by_field_name('alias')
                            orig_txt = self.text(orig) if orig else ''
                            alias_txt = self.text(alias) if alias else None
                            self._record_import(node, source_mod, orig_txt, alias_txt, alias_txt or orig_txt, 'es_named', in_conditional)
                            emitted = True
            if not emitted:
                self._record_import(node, source_mod, None, None, source_mod, 'es_import', in_conditional)
            return

        if ntype == 'export_statement':
            src_node = node.child_by_field_name('source')
            if src_node is not None:
                source_mod = self.text(src_node).strip('"\'`')
                self._record_import(node, source_mod, '*', None, source_mod, 'es_reexport', in_conditional)
                return
            export_decs = self._decorators(node)
            for child in node.children:
                if child.type in {'class_declaration', 'function_declaration', 'interface_declaration', 'lexical_declaration', 'variable_declaration'}:
                    self._walk(child, parent_id=parent_id, parent_name=parent_name, in_conditional=in_conditional, pending_decs=export_decs)
            return

        if ntype in {'class_declaration', 'interface_declaration'}:
            name_node = node.child_by_field_name('name')
            cname = self.text(name_node) if name_node is not None else 'Anonymous'
            qual = f'{parent_name}.{cname}' if parent_name else cname
            cid = self.node_id('class', node, qual)
            decs = pending_decs + self._decorators(node)
            bases = []
            for child in node.children:
                if child.type == 'class_heritage':
                    for clause in child.children:
                        if clause.type in {'extends_clause', 'implements_clause'}:
                            rel = 'implements' if clause.type == 'implements_clause' else 'extends'
                            for sub in clause.children:
                                if sub.type in {'identifier', 'type_identifier', 'member_expression', 'generic_type'}:
                                    raw = self.text(sub).split('<', 1)[0].strip()
                                    if raw not in {'extends', 'implements'}:
                                        bases.append({'name': raw, 'import_qualified_name': None, 'is_dynamic': False, 'relation': rel})
                elif child.type == 'extends_type_clause':
                    for sub in child.children:
                        if sub.type in {'type_identifier', 'generic_type'}:
                            bases.append({'name': self.text(sub).split('<', 1)[0].strip(), 'import_qualified_name': None, 'is_dynamic': False, 'relation': 'extends'})
            loc = self.loc(node)
            extent_start = min([loc['start_line']] + [d['start_line'] for d in decs])
            self.classes.append(
                {
                    'id': cid,
                    'module_id': self.module_id,
                    'parent_id': parent_id,
                    'name': cname,
                    'qualified_name': qual,
                    'kind_detail': 'interface' if ntype == 'interface_declaration' else 'class',
                    'bases': bases,
                    'decorators': [{'name': d['name'], 'is_factory': d['is_factory'], 'file': d['file'], 'start_line': d['start_line'], 'end_line': d['end_line'], 'start_column': d['start_column'], 'end_column': d['end_column']} for d in decs],
                    'extent_start_line': extent_start,
                    **loc,
                }
            )
            if parent_id == self.module_id:
                self.exports.add(cname)
            class_prefix = ''
            for d in decs:
                if d['name'] == 'Controller':
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'nestjs', 'kind': 'controller', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('controller', 'confirmed', node, 'nestjs_controller_decorator', cid)
                    m = re.search(r'["\']([^"\']+)["\']', d['raw'])
                    if m:
                        class_prefix = m.group(1)
                elif d['name'] == 'Injectable':
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'nestjs', 'kind': 'service', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('service', 'confirmed', node, 'nestjs_injectable_decorator', cid)
                elif d['name'] == 'Module':
                    self.frameworks.append({'id': self.node_id('framework', node, cname), 'framework': 'nestjs', 'kind': 'application', 'binding': cname, 'symbol_id': cid, **loc})
                    self.classify('api_application', 'confirmed', node, 'nestjs_module_decorator', cid)
            body = node.child_by_field_name('body')
            if body is not None:
                self._walk_children(body, parent_id=cid, parent_name=qual, in_conditional=in_conditional, class_prefix=class_prefix)
            return

        if ntype in {'function_declaration', 'generator_function_declaration', 'method_definition'}:
            name_node = node.child_by_field_name('name')
            fname = self.text(name_node) if name_node is not None else 'anonymous'
            qual = f'{parent_name}.{fname}' if parent_name else fname
            fid = self.node_id('function', node, qual)
            decs = pending_decs + self._decorators(node)
            params = self._parameters(node.child_by_field_name('parameters'))
            loc = self.loc(node)
            extent_start = min([loc['start_line']] + [d['start_line'] for d in decs])
            is_async = 'async' in {self.text(c) for c in node.children if not c.is_named}
            self.functions.append(
                {
                    'id': fid,
                    'module_id': self.module_id,
                    'parent_id': parent_id,
                    'name': fname,
                    'qualified_name': qual,
                    'kind': 'method' if ntype == 'method_definition' else 'function',
                    'is_constructor': fname == 'constructor' and ntype == 'method_definition',
                    'is_async': is_async,
                    'parameters': params,
                    'decorators': [{'name': d['name'], 'is_factory': d['is_factory'], 'file': d['file'], 'start_line': d['start_line'], 'end_line': d['end_line'], 'start_column': d['start_column'], 'end_column': d['end_column']} for d in decs],
                    'return_annotation': None,
                    'extent_start_line': extent_start,
                    **loc,
                }
            )
            if parent_id == self.module_id:
                self.exports.add(fname)
            for d in decs:
                if d['name'] in NEST_ROUTE_DECORATORS:
                    methods = list(NEST_ROUTE_DECORATORS[d['name']])
                    m = re.search(r'["\']([^"\']+)["\']', d['raw'])
                    self.frameworks.append({'id': self.node_id('route', node, fid), 'framework': 'nestjs', 'kind': 'route', 'receiver': parent_name or 'controller', 'receiver_kind': 'controller', 'symbol_id': fid, 'methods': methods, 'path_is_literal': bool(m), 'path': '<redacted>', **loc})
                    self.classify('controller', 'confirmed', node, 'nestjs_route_decorator', fid)
                    if m and (norm := _normalize_route_pattern(m.group(1))):
                        self.route_records.append({'module_id': self.module_id, 'file': self.file, 'symbol_id': fid, 'methods': methods, 'normalized_path': norm, **loc})
            body = node.child_by_field_name('body')
            before_jsx = self._count_jsx(body) if body is not None else False
            if before_jsx and fname[:1].isupper() and parent_id == self.module_id:
                self.frameworks.append({'id': self.node_id('react_comp', node, fid), 'framework': 'react', 'kind': 'component', 'binding': fname, 'symbol_id': fid, **loc})
                self.classify('frontend_component', 'confirmed', node, 'react_jsx_component', fid)
            if body is not None:
                self._walk_children(body, parent_id=fid, parent_name=qual, in_conditional=in_conditional)
            return

        if ntype in {'lexical_declaration', 'variable_declaration'} and parent_id == self.module_id:
            for decl in node.children:
                if decl.type == 'variable_declarator':
                    name_node = decl.child_by_field_name('name')
                    val_node = decl.child_by_field_name('value')
                    if name_node is not None and name_node.type == 'identifier':
                        vname = self.text(name_node)
                        self.exports.add(vname)
                        self.symbols.append({'id': self.node_id('symbol', decl, vname), 'module_id': self.module_id, 'name': vname, 'kind': 'assignment', 'has_annotation': False, 'conditional': in_conditional, **self.loc(decl)})
                        if val_node is not None and val_node.type == 'call_expression':
                            callee = self.text(val_node.child_by_field_name('function'))
                            if callee in {'express', 'express.Router', 'Router'}:
                                fkind = 'router' if 'Router' in callee else 'application'
                                self.factory_bindings[vname] = ('express', fkind)
                                self.frameworks.append({'id': self.node_id('framework', decl, vname), 'framework': 'express', 'kind': fkind, 'binding': vname, 'symbol_id': self.module_id, **self.loc(decl)})
                                self.classify('router' if fkind == 'router' else 'api_application', 'confirmed', decl, 'express_factory')
                            elif callee == 'require':
                                args = val_node.child_by_field_name('arguments')
                                if args is not None:
                                    m = re.search(r'["\']([^"\']+)["\']', self.text(args))
                                    if m:
                                        self._record_import(decl, m.group(1), 'default', None, vname, 'commonjs_require', in_conditional)
                        elif val_node is not None and val_node.type in {'arrow_function', 'function_expression', 'function'}:
                            fid = self.node_id('function', val_node, vname)
                            loc = self.loc(val_node)
                            is_async = 'async' in {self.text(c) for c in val_node.children if not c.is_named}
                            self.functions.append({'id': fid, 'module_id': self.module_id, 'parent_id': parent_id, 'name': vname, 'qualified_name': vname, 'kind': 'function', 'is_async': is_async, 'parameters': self._parameters(val_node.child_by_field_name('parameters')), 'decorators': [], 'return_annotation': None, 'extent_start_line': loc['start_line'], **loc})
                            body = val_node.child_by_field_name('body')
                            if body is not None and self._count_jsx(body) and vname[:1].isupper():
                                self.frameworks.append({'id': self.node_id('react_comp', val_node, fid), 'framework': 'react', 'kind': 'component', 'binding': vname, 'symbol_id': fid, **loc})
                                self.classify('frontend_component', 'confirmed', val_node, 'react_jsx_component', fid)
                            if body is not None:
                                self._walk_children(body, parent_id=fid, parent_name=vname, in_conditional=in_conditional)
                            continue
                    if val_node is not None:
                        self._walk(val_node, parent_id=parent_id, parent_name=parent_name, in_conditional=in_conditional)
            return

        if ntype in {'jsx_element', 'jsx_self_closing_element'}:
            self.has_jsx = True
            open_node = node.child_by_field_name('open_tag') if ntype == 'jsx_element' else node
            name_node = open_node.child_by_field_name('name') if open_node is not None else None
            tag = self.text(name_node) if name_node is not None else ''
            if tag and tag[:1].isupper():
                root_ident = tag.split('.', 1)[0]
                self.component_references.append({'source_module_id': self.module_id, 'component': root_ident, **self.loc(node)})

        if ntype == 'call_expression':
            fn_node = node.child_by_field_name('function')
            callee = self.text(fn_node) if fn_node is not None else ''
            self.calls.append({'id': self.node_id('call', node, callee), 'module_id': self.module_id, 'scope_id': parent_id, 'callee': callee or None, 'import_qualified_name': None, 'resolution': 'syntactic_only' if callee else 'dynamic_callable', **self.loc(node)})
            if callee == 'require':
                args = node.child_by_field_name('arguments')
                if args is not None:
                    m = re.search(r'^\(\s*["\']([^"\']+)["\']\s*\)$', self.text(args).strip())
                    if m:
                        self._record_import(node, m.group(1), None, None, m.group(1), 'commonjs_require', in_conditional)
            if '.' in callee:
                recv, method = callee.rsplit('.', 1)
                if recv in self.factory_bindings and method in HTTP_METHODS:
                    args = node.child_by_field_name('arguments')
                    arg_txt = self.text(args) if args is not None else ''
                    m = re.search(r'["\']([^"\']+)["\']', arg_txt)
                    methods = [method.upper()] if method not in {'all', 'use'} else []
                    loc = self.loc(node)
                    self.frameworks.append({'id': self.node_id('route', node, parent_id), 'framework': 'express', 'kind': 'route', 'receiver': recv, 'receiver_kind': self.factory_bindings[recv][1], 'symbol_id': parent_id, 'methods': methods, 'path_is_literal': bool(m), 'path': '<redacted>', **loc})
                    self.classify('controller', 'confirmed', node, 'express_route_registration', parent_id)
                    if m and (norm := _normalize_route_pattern(m.group(1))):
                        self.route_records.append({'module_id': self.module_id, 'file': self.file, 'symbol_id': parent_id, 'methods': methods, 'normalized_path': norm, **loc})
            # Frontend HTTP client call indicators (fetch('/api/...'), axios.get('/api/...'))
            if callee == 'fetch' or callee.startswith('axios.'):
                args = node.child_by_field_name('arguments')
                arg_txt = self.text(args) if args is not None else ''
                m = re.search(r'["\'`]((?:/|https?://[^/]+/)[^"\'`\s]+)["\'`]', arg_txt)
                if m:
                    raw_url = m.group(1)
                    if raw_url.startswith('http'):
                        raw_url = '/' + raw_url.split('://', 1)[1].split('/', 1)[-1]
                    norm = _normalize_route_pattern(raw_url)
                    if norm:
                        method = callee.split('.', 1)[1].upper() if '.' in callee else 'GET'
                        self.api_client_calls.append({'module_id': self.module_id, 'file': self.file, 'method': method, 'normalized_path': norm, **self.loc(node)})

        if ntype == 'member_expression' and self.text(node) == 'process.env':
            self.classify('configuration', 'confirmed', node, 'node_process_env')

        cond = in_conditional or ntype in {'if_statement', 'try_statement', 'for_statement', 'for_in_statement', 'while_statement', 'switch_statement'}
        self._walk_children(node, parent_id=parent_id, parent_name=parent_name, in_conditional=cond)

    def _walk_children(self, node, *, parent_id: str, parent_name: str, in_conditional: bool, class_prefix: str = '') -> None:
        base_route_count = len(self.route_records)
        buffered_decs: list[dict] = []
        for child in node.children:
            if child.type == 'decorator':
                expr = self.text(child).lstrip('@').strip()
                name = expr.split('(', 1)[0].strip()
                buffered_decs.append({'name': name, 'is_factory': '(' in expr, 'raw': expr, **self.loc(child)})
                continue
            self._walk(child, parent_id=parent_id, parent_name=parent_name, in_conditional=in_conditional, pending_decs=buffered_decs)
            buffered_decs = []
        if class_prefix and len(self.route_records) > base_route_count:
            prefix = '/' + class_prefix.strip('/')
            for rec in self.route_records[base_route_count:]:
                if not rec['normalized_path'].startswith(prefix):
                    rec['normalized_path'] = (prefix.rstrip('/') + '/' + rec['normalized_path'].lstrip('/')).rstrip('/') or '/'

    def _count_jsx(self, node) -> bool:
        stack = [node]
        while stack:
            cur = stack.pop()
            if cur.type in {'jsx_element', 'jsx_self_closing_element'}:
                return True
            stack.extend(cur.children)
        return False
