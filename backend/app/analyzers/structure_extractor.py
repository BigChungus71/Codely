"""AST-only symbols, call syntax and framework indicators. Literal values stay private."""
import ast
import hashlib
from pathlib import PurePosixPath


def stable_id(kind, *parts):
    value = '\x00'.join(str(part) for part in parts)
    return kind + '_' + hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]


def location(file, node):
    return {'file': file, 'start_line': node.lineno,
            'end_line': getattr(node, 'end_lineno', node.lineno),
            'start_column': node.col_offset, 'end_column': getattr(node, 'end_col_offset', node.col_offset)}


def expression_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = expression_name(node.value)
        return base + '.' + node.attr if base else None
    if isinstance(node, ast.Subscript):
        base = expression_name(node.value)
        return base + '[...]' if base else None
    # Never unparse literals, forward-annotation strings, defaults or call arguments.
    return None


def assignment_names(node):
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [name for element in node.elts for name in assignment_names(element)]
    return []


FACTORIES = {'fastapi.FastAPI': ('fastapi', 'application'),
             'fastapi.APIRouter': ('fastapi', 'router'),
             'flask.Flask': ('flask', 'application'), 'flask.Blueprint': ('flask', 'blueprint')}
HTTP = {'get': 'GET', 'post': 'POST', 'put': 'PUT', 'patch': 'PATCH',
        'delete': 'DELETE', 'head': 'HEAD', 'options': 'OPTIONS', 'websocket': 'WEBSOCKET'}


class Extractor(ast.NodeVisitor):
    def __init__(self, file, module_id):
        self.file, self.module_id = file, module_id
        self.classes, self.functions, self.imports, self.symbols, self.calls = [], [], [], [], []
        self.frameworks, self.classifications = [], []
        self.route_records = []
        self.scopes = [(module_id, '', 'module')]
        self.aliases = [{}]
        self.objects = [{}]
        self.conditional = 0
        self.symbol_ordinals = {}

    def node_id(self, kind, node, name=''):
        if kind in {'class', 'function', 'symbol'}:
            key = (kind, name)
            ordinal = self.symbol_ordinals.get(key, 0)
            self.symbol_ordinals[key] = ordinal + 1
            return stable_id(kind, self.file, name, ordinal)
        return stable_id(kind, self.file, name, node.lineno, node.col_offset,
                         getattr(node, 'end_lineno', 0), getattr(node, 'end_col_offset', 0))

    def qualified(self, node):
        name = expression_name(node)
        if not name:
            return None
        first, _, tail = name.partition('.')
        for aliases in reversed(self.aliases):
            if first in aliases:
                base = aliases[first]
                return (base + ('.' + tail if tail else '')) if base else None
        return None  # Framework evidence requires an actual import binding.

    def known_object(self, name):
        for objects in reversed(self.objects):
            if name in objects:
                return objects[name]
        return None

    def classify(self, component, confidence, node=None, reason='filename_heuristic', symbol_id=None):
        entry = {'component': component, 'confidence': confidence, 'reason': reason,
                 'module_id': self.module_id, 'symbol_id': symbol_id,
                 'evidence': location(self.file, node) if node else {'file': self.file}}
        self.classifications.append(entry)

    def decorators(self, node, symbol_id):
        records = []
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            name = expression_name(target)
            records.append({'name': name, 'is_factory': isinstance(decorator, ast.Call),
                            **location(self.file, decorator)})
            if not isinstance(target, ast.Attribute) or not isinstance(decorator, ast.Call):
                continue
            receiver = expression_name(target.value)
            obj = self.known_object(receiver)
            method = target.attr
            if not obj or method not in {*HTTP, 'route', 'api_route'}:
                continue
            methods = [HTTP[method]] if method in HTTP else []
            for keyword in decorator.keywords:
                if keyword.arg == 'methods' and isinstance(keyword.value, (ast.List, ast.Tuple)):
                    methods = sorted({element.value for element in keyword.value.elts
                                      if isinstance(element, ast.Constant) and isinstance(element.value, str)
                                      and element.value in set(HTTP.values())})
            if obj[0] == 'flask' and method == 'route' and not methods:
                # Default can be affected by framework configuration; do not invent methods.
                methods = []
            is_lit_path = bool(decorator.args and isinstance(decorator.args[0], ast.Constant)
                               and isinstance(decorator.args[0].value, str))
            self.frameworks.append({'id': self.node_id('route', decorator, symbol_id),
                'framework': obj[0], 'kind': 'route', 'receiver': receiver,
                'receiver_kind': obj[1], 'symbol_id': symbol_id, 'methods': methods,
                'path_is_literal': is_lit_path,
                'path': '<redacted>', **location(self.file, decorator)})
            if is_lit_path and decorator.args[0].value.startswith('/'):
                raw_path = decorator.args[0].value.split('?', 1)[0].rstrip('/') or '/'
                self.route_records.append({'module_id': self.module_id, 'file': self.file, 'symbol_id': symbol_id,
                    'methods': methods, 'raw_pattern': raw_path, **location(self.file, decorator)})
            self.classify('controller', 'confirmed', decorator, 'framework_route_decorator', symbol_id)
        return records

    def parameters(self, args):
        result = []
        positional = args.posonlyargs + args.args
        default_at = len(positional) - len(args.defaults)
        groups = [(arg, 'positional_only' if index < len(args.posonlyargs) else 'positional', index >= default_at)
                  for index, arg in enumerate(positional)]
        if args.vararg:
            groups.append((args.vararg, 'var_positional', False))
        groups.extend((arg, 'keyword_only', default is not None)
                      for arg, default in zip(args.kwonlyargs, args.kw_defaults))
        if args.kwarg:
            groups.append((args.kwarg, 'var_keyword', False))
        for arg, kind, default in groups:
            result.append({'name': arg.arg, 'kind': kind, 'has_default': default,
                           'annotation': expression_name(arg.annotation), **location(self.file, arg)})
        return result

    def visit_FunctionDef(self, node):
        parent_id, parent_name, parent_kind = self.scopes[-1]
        qualname = parent_name + '.' + node.name if parent_name else node.name
        identifier = self.node_id('function', node, qualname)
        decorators = self.decorators(node, identifier)
        self.functions.append({'id': identifier, 'module_id': self.module_id, 'parent_id': parent_id,
            'name': node.name, 'qualified_name': qualname,
            'kind': 'method' if parent_kind == 'class' else 'function',
            'is_async': isinstance(node, ast.AsyncFunctionDef), 'parameters': self.parameters(node.args),
            'decorators': decorators, 'return_annotation': expression_name(node.returns),
            'extent_start_line': min([node.lineno] + [d.lineno for d in node.decorator_list]),
            **location(self.file, node)})
        for child in [*node.decorator_list, *node.args.defaults,
                      *[d for d in node.args.kw_defaults if d is not None],
                      *[arg.annotation for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                        if arg.annotation is not None],
                      *([node.returns] if node.returns is not None else [])]:
            self.visit(child)
        self.scopes.append((identifier, qualname, 'function'))
        self.aliases.append({arg['name']: None for arg in self.parameters(node.args)})
        self.objects.append({arg['name']: None for arg in self.parameters(node.args)})
        for child in node.body:
            self.visit(child)
        self.scopes.pop(); self.aliases.pop(); self.objects.pop()
        self.aliases[-1][node.name] = None
        self.objects[-1][node.name] = None

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        parent_id, parent_name, _ = self.scopes[-1]
        qualname = parent_name + '.' + node.name if parent_name else node.name
        identifier = self.node_id('class', node, qualname)
        bases = [{'name': expression_name(base), 'import_qualified_name': self.qualified(base),
                  'is_dynamic': expression_name(base) is None} for base in node.bases]
        self.classes.append({'id': identifier, 'module_id': self.module_id, 'parent_id': parent_id,
            'name': node.name, 'qualified_name': qualname, 'bases': bases,
            'decorators': self.decorators(node, identifier),
            'extent_start_line': min([node.lineno] + [d.lineno for d in node.decorator_list]),
            **location(self.file, node)})
        if any(base['import_qualified_name'] in {'django.db.models.Model', 'sqlmodel.SQLModel',
                'sqlalchemy.orm.DeclarativeBase'} for base in bases):
            self.classify('database_model', 'confirmed', node, 'explicit_framework_model_base', identifier)
        for child in [*node.decorator_list, *node.bases, *[k.value for k in node.keywords]]:
            self.visit(child)
        self.scopes.append((identifier, qualname, 'class')); self.aliases.append({}); self.objects.append({})
        for child in node.body:
            self.visit(child)
        self.scopes.pop(); self.aliases.pop(); self.objects.pop()
        self.aliases[-1][node.name] = None
        self.objects[-1][node.name] = None

    def visit_Import(self, node):
        self.import_statement(node, False)

    def visit_ImportFrom(self, node):
        self.import_statement(node, True)

    def import_statement(self, node, from_import):
        for index, alias in enumerate(node.names):
            binding = alias.asname or (alias.name if from_import else alias.name.split('.')[0])
            module = (node.module or '') if from_import else alias.name
            imported = alias.name if from_import else None
            self.imports.append({'id': self.node_id('import', node, str(index)),
                'module_id': self.module_id, 'scope_id': self.scopes[-1][0],
                'module': module, 'name': imported, 'alias': alias.asname,
                'binding': binding, 'level': node.level if from_import else 0,
                'kind': 'from' if from_import else 'import', 'conditional': bool(self.conditional),
                **location(self.file, node)})
            canonical = (module + '.' + alias.name) if from_import and not node.level else (
                alias.name if alias.asname else binding)
            self.aliases[-1][binding] = canonical if not (from_import and node.level) else None
            self.objects[-1][binding] = None
            framework = canonical.split('.')[0]
            if framework in {'fastapi', 'flask', 'django', 'sqlalchemy', 'sqlmodel'}:
                self.frameworks.append({'id': self.node_id('framework_import', node, canonical + ':' + binding),
                    'framework': framework, 'kind': 'import', 'binding': binding,
                    'symbol_id': self.scopes[-1][0], **location(self.file, node)})
            if canonical.startswith(('fastapi.security', 'django.contrib.auth', 'flask_login')):
                self.classify('authentication', 'confirmed', node, 'authentication_framework_import')

    def visit_Assign(self, node):
        self.assignment(node, node.targets, node.value)

    def visit_AnnAssign(self, node):
        self.assignment(node, [node.target], node.value)

    def assignment(self, node, targets, value):
        names = [name for target in targets for name in assignment_names(target)]
        canonical = self.qualified(value.func) if isinstance(value, ast.Call) else None
        for name in names:
            if self.scopes[-1][2] == 'module':
                self.symbols.append({'id': self.node_id('symbol', node, name), 'module_id': self.module_id,
                    'name': name, 'kind': 'assignment', 'has_annotation': isinstance(node, ast.AnnAssign),
                    'conditional': bool(self.conditional), **location(self.file, node)})
            self.aliases[-1][name] = None
            self.objects[-1][name] = FACTORIES.get(canonical)
            if canonical in FACTORIES:
                framework, kind = FACTORIES[canonical]
                self.frameworks.append({'id': self.node_id('framework', node, name),
                    'framework': framework, 'kind': kind, 'binding': name,
                    'symbol_id': self.scopes[-1][0], **location(self.file, node)})
                self.classify('router' if kind in {'router', 'blueprint'} else 'api_application',
                              'confirmed', node, 'explicit_framework_constructor')
        if value is not None:
            self.visit(value)

    def visit_Call(self, node):
        name = expression_name(node.func)
        canonical = self.qualified(node.func)
        self.calls.append({'id': self.node_id('call', node), 'module_id': self.module_id,
            'scope_id': self.scopes[-1][0], 'callee': name, 'import_qualified_name': canonical,
            'resolution': 'syntactic_only' if name and '[...]' not in name else 'dynamic_callable',
            **location(self.file, node)})
        if canonical in {'sqlite3.connect', 'sqlalchemy.create_engine', 'sqlalchemy.ext.asyncio.create_async_engine'}:
            self.classify('data_access', 'confirmed', node, 'explicit_database_api')
        if canonical in {'os.getenv', 'os.environ.get'}:
            self.classify('configuration', 'confirmed', node, 'environment_api_indicator')
        self.generic_visit(node)

    def visit_If(self, node):
        self.conditional += 1
        self.generic_visit(node)
        self.conditional -= 1

    visit_Try = visit_If
    visit_TryStar = visit_If
    visit_For = visit_If
    visit_AsyncFor = visit_If
    visit_While = visit_If
    visit_Match = visit_If

    def apply_heuristics(self):
        path = PurePosixPath(self.file)
        words = {part.lower() for part in path.parts} | {path.stem.lower(), *path.stem.lower().split('_')}
        mappings = {'service': {'service', 'services'}, 'controller': {'controller', 'controllers'},
                    'data_access': {'repository', 'repositories', 'database', 'db', 'dao'},
                    'database_model': {'model', 'models'}, 'configuration': {'config', 'settings'},
                    'authentication': {'auth', 'authentication', 'security'},
                    'utility': {'util', 'utils', 'utilities', 'helpers'}}
        confirmed = {entry['component'] for entry in self.classifications if entry['confidence'] == 'confirmed'}
        for component, candidates in mappings.items():
            if words & candidates and component not in confirmed:
                self.classify(component, 'inferred')
        if path.name.startswith('test_') or path.stem.endswith('_test') or 'tests' in words:
            self.classify('test', 'inferred')
