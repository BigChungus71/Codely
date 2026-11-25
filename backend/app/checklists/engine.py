"""Deterministic, evidence-based checklist; never invokes a scanner or target code."""
import ast
from dataclasses import asdict, dataclass
import fnmatch
import json
from pathlib import Path
import re
import tomllib

import jsonschema
from packaging.requirements import InvalidRequirement, Requirement

from ..analyzers.finding_normalizer import repository_relative_path
from ..analyzers.semgrep_adapter import EXCLUDED, ROOT, ScanResult
from .inventory import evidence, inspect_repository, profile_repository, qualified, sensitive


CATALOG = Path(__file__).with_name('catalog-v1.json')
STATUSES = ('PASS', 'FAIL', 'NEEDS_REVIEW', 'NOT_APPLICABLE')


@dataclass
class ChecklistResult:
    catalog_version: str
    profile: dict
    coverage: dict
    summary: dict
    checks: list[dict]

    def to_dict(self):
        return asdict(self)


def _scan_input(scan_result, inventory):
    if scan_result is None:
        return 'not_provided', [], False
    payload = scan_result.to_dict() if isinstance(scan_result, ScanResult) else scan_result
    try:
        schema = json.loads((ROOT / 'contracts/security-scan.schema.json').read_text())
        jsonschema.Draft202012Validator(schema).validate(payload)
        findings = []
        for raw in payload['findings']:
            file = repository_relative_path(raw['file'], inventory.root)
            if raw['rule_id'].startswith(('codely.java.', 'codely.web.')) and Path(file).suffix.lower() != '.py':
                continue
            if file not in inventory.trees or raw['end_line'] < raw['start_line']:
                raise ValueError('Invalid finding location')
            if raw['end_line'] > len(inventory.texts[file].splitlines()):
                raise ValueError('Finding outside source')
            findings.append({'id': raw['id'], 'rule_id': raw['rule_id'], 'file': file,
                             'start_line': raw['start_line'], 'end_line': raw['end_line']})
        diagnostics = payload['diagnostics']
        known_pack = any(d.get('code') == 'coverage' and d.get('rule_set') == 'python-security-v2'
                         for d in diagnostics)
        process_ok = any(d.get('code') == 'scanner_exit' and d.get('exit_code') == 0
                         for d in diagnostics)
        complete = (payload['status'] == 'complete' and known_pack and process_ok
                    and not payload.get('errors')
                    and not any(d.get('code') in {'scanner_error', 'scanner_skipped_file',
                        'scanner_timeout', 'invalid_scanner_output'} for d in diagnostics))
        return payload['status'] if complete or payload['status'] != 'complete' else 'unverified', findings, complete
    except (jsonschema.ValidationError, ValueError, TypeError, KeyError, AttributeError):
        return 'invalid', [], False


def _literal(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_literal(element) for element in node.elts]
    return None


def _signals(inventory, aliases_by_file, profile):
    signals = {key: [] for key in ('environment', 'debug_true', 'debug_dynamic',
        'cors_open', 'cors_credentials', 'cors_allowlist', 'cors_dynamic', 'auth',
        'sql', 'command', 'dynamic_code')}
    for file, tree in sorted(inventory.trees.items()):
        aliases = aliases_by_file[file]
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = qualified(node.func, aliases)
                kwargs = {kw.arg: _literal(kw.value) for kw in node.keywords if kw.arg}
                if name in {'os.getenv', 'os.environ.get'}:
                    signals['environment'].append(evidence(file, 'environment_access', node))
                if name.rsplit('.', 1)[-1] in {'execute', 'executemany'}:
                    signals['sql'].append(evidence(file, 'sql_api_indicator', node))
                if name in {'os.system', 'os.popen'} or name.startswith('subprocess.'):
                    signals['command'].append(evidence(file, 'execution_api_indicator', node))
                if name in {'eval', 'exec', 'builtins.eval', 'builtins.exec'}:
                    signals['dynamic_code'].append(evidence(file, 'dynamic_code_indicator', node))
                if name == 'fastapi.FastAPI' and 'debug' in kwargs:
                    key = 'debug_true' if kwargs['debug'] is True else 'debug_dynamic'
                    if kwargs['debug'] is not False:
                        signals[key].append(evidence(file, key, node))
                middleware_names = {'fastapi.middleware.cors.CORSMiddleware',
                                    'starlette.middleware.cors.CORSMiddleware'}
                cors = name in middleware_names | {'flask_cors.CORS', 'flask_cors.cross_origin'}
                # add_middleware(CORSMiddleware, ...) has the middleware as its first argument.
                if name.endswith('.add_middleware') and node.args:
                    cors |= qualified(node.args[0], aliases) in middleware_names
                if cors:
                    origins = kwargs.get('allow_origins', kwargs.get('origins'))
                    credentials = kwargs.get('allow_credentials', kwargs.get('supports_credentials'))
                    broad = origins == '*' or (isinstance(origins, list) and '*' in origins)
                    if name in {'flask_cors.CORS', 'flask_cors.cross_origin'} and 'origins' not in kwargs:
                        broad = True
                    if kwargs.get('allow_origin_regex') in ('.*', '^.*$'):
                        broad = True
                    if broad:
                        key = 'cors_credentials' if credentials is True else 'cors_open'
                    elif ((isinstance(origins, list) and origins and all(
                            isinstance(origin, str) and origin and origin != '*' for origin in origins))
                            or (isinstance(origins, str) and origins and name.startswith('flask_cors.'))) and (
                            'allow_origin_regex' not in kwargs):
                        key = 'cors_allowlist'
                    else:
                        key = 'cors_dynamic'
                    signals[key].append(evidence(file, key, node))
            if isinstance(node, ast.Subscript) and qualified(node.value, aliases) == 'os.environ':
                signals['environment'].append(evidence(file, 'environment_access', node))
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if 'django' in profile['frameworks']:
                    for target in targets:
                        if isinstance(target, ast.Name) and target.id == 'DEBUG':
                            value = _literal(node.value)
                            if value is True:
                                signals['debug_true'].append(evidence(file, 'django_debug_true', node))
                            elif value is not False:
                                signals['debug_dynamic'].append(evidence(file, 'django_debug_dynamic', node))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    target = decorator.func if isinstance(decorator, ast.Call) else decorator
                    if qualified(target, aliases).rsplit('.', 1)[-1] in {
                            'login_required', 'permission_required', 'jwt_required', 'requires_auth'}:
                        signals['auth'].append(evidence(file, 'authentication_decorator_indicator', decorator))
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(
                    ('fastapi.security', 'django.contrib.auth', 'flask_login')):
                signals['auth'].append(evidence(file, 'authentication_import_indicator', node))
    for key in signals:
        signals[key] = sorted({json.dumps(item, sort_keys=True): item for item in signals[key]}.values(),
                              key=lambda item: (item['file'], item.get('start_line', 0), item['kind']))
    return signals


def _ignored(file, text):
    """Conservative root ignore-glob subset; unknown constructs require review."""
    ignored = False
    uncertain = False
    for line in text.splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith('#'):
            continue
        if '\\' in pattern or '[' in pattern:
            uncertain = True
            continue
        negative = pattern.startswith('!')
        pattern = pattern.removeprefix('!').lstrip('/')
        match = fnmatch.fnmatchcase(file, pattern) if '/' in pattern else fnmatch.fnmatchcase(Path(file).name, pattern)
        if match:
            ignored = not negative
    return ignored, uncertain


def _constraints(inventory, manifests):
    entries = []
    locations = []
    uncertain = False
    for file in manifests:
        text = inventory.texts.get(file)
        if text is None:
            uncertain = True
            continue
        if Path(file).name.lower().startswith('requirements'):
            for line_number, line in enumerate(text.splitlines(), 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                locations.append({'file': file, 'start_line': line_number, 'end_line': line_number,
                                  'kind': 'dependency_declaration'})
                if line.startswith('-') or line.endswith('\\'):
                    uncertain = True
                    continue
                entries.append(line.split(' #', 1)[0].split(' --hash=', 1)[0])
        elif Path(file).name == 'pyproject.toml':
            locations.append(evidence(file, 'dependency_manifest'))
            try:
                data = tomllib.loads(text)
                project = data.get('project', {})
                dependencies = project.get('dependencies', [])
                optional = project.get('optional-dependencies', {})
                if not isinstance(dependencies, list) or not isinstance(optional, dict):
                    raise ValueError('Malformed dependencies')
                entries.extend(dependencies)
                for group in optional.values():
                    if not isinstance(group, list):
                        raise ValueError('Malformed dependency group')
                    entries.extend(group)
                entries.extend(data.get('build-system', {}).get('requires', []))
                if project.get('dynamic') or 'poetry' in data.get('tool', {}):
                    uncertain = True
            except (ValueError, TypeError, AttributeError):
                uncertain = True
        else:
            uncertain = True
    for entry in entries:
        try:
            requirement = Requirement(entry)
            specs = list(requirement.specifier)
            pinned = any(spec.operator in {'==', '==='} and '*' not in spec.version for spec in specs)
            bounded = (any(spec.operator in {'>=', '>'} for spec in specs)
                       and any(spec.operator in {'<', '<='} for spec in specs)) or any(
                       spec.operator == '~=' for spec in specs)
            if requirement.url or not (pinned or bounded):
                uncertain = True
        except (InvalidRequirement, TypeError):
            uncertain = True
    return ('NEEDS_REVIEW' if uncertain or not entries else 'PASS'), locations


def _docker(inventory):
    files = [file for file in inventory.paths if Path(file).name.lower().startswith('dockerfile')]
    if not files:
        return 'NOT_APPLICABLE', [], 'no_dockerfile'
    overall = 'PASS'
    locations = []
    for file in files:
        text = inventory.texts.get(file)
        current = None
        unresolved = False
        for number, line in enumerate((text or '').splitlines(), 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            instruction = line.split(None, 1)
            op, value = instruction[0], instruction[1] if len(instruction) > 1 else ''
            if line.endswith('\\') or '$' in value:
                unresolved = True
            if op.upper() == 'FROM':
                current = None
            elif op.upper() == 'USER':
                current = (value.split('#', 1)[0].strip(), number)
                # Inheritance is conservative: only explicit final-stage USER is PASS.
        if text is None or current is None or unresolved:
            state = 'NEEDS_REVIEW'
            locations.append(evidence(file, 'docker_user_unresolved'))
        else:
            user, line = current
            if user.split(':')[0] in {'root', '0'}:
                state = 'FAIL'
            elif re.fullmatch(r'(?:[1-9]\d*|[a-z_][a-z0-9_-]*)(?::(?:\d+|[a-z_][a-z0-9_-]*))?', user):
                state = 'PASS'
            else:
                state = 'NEEDS_REVIEW'
            locations.append({'file': file, 'start_line': line, 'end_line': line,
                              'kind': {'FAIL': 'docker_root_user', 'PASS': 'docker_nonroot_declaration',
                                       'NEEDS_REVIEW': 'docker_user_unresolved'}[state]})
        if state == 'FAIL' or (state == 'NEEDS_REVIEW' and overall != 'FAIL'):
            overall = state
    return overall, locations, 'final_stage_user_declaration'


def evaluate_repository(project_path: str, scan_result=None) -> ChecklistResult:
    """Reuse a trusted current-repository ScanResult; never performs a scan itself."""
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    inventory = inspect_repository(project_path)
    profile, aliases = profile_repository(inventory)
    scanner_status, findings, scanner_complete = _scan_input(scan_result, inventory) if inventory.valid else ('invalid', [], False)
    signals = _signals(inventory, aliases, profile)
    technologies = set(profile['technologies'])
    python = 'python' in profile['languages']
    results = {}

    def record(key, status, locations=None, reason='', related=None):
        if not inventory.complete and status in {'PASS', 'NOT_APPLICABLE'}:
            status, reason = 'NEEDS_REVIEW', 'incomplete_static_inventory'
        unique = {json.dumps(item, sort_keys=True): item for item in (locations or [])}
        results[key] = {'status': status, 'reason': reason,
            'evidence': sorted(unique.values(), key=lambda item: (item['file'], item.get('start_line', 0), item['kind'])),
            'related_finding_ids': sorted(set(related or []))}

    def rule_check(key, suffixes, relevant):
        matched = [finding for finding in findings if finding['rule_id'] in {
            'codely.python.' + suffix for suffix in suffixes}]
        locations = [{**{k: finding[k] for k in ('file', 'start_line', 'end_line')},
                      'kind': 'semgrep_finding'} for finding in matched]
        if matched:
            state, reason = 'FAIL', 'supported_security_finding'
        elif not scanner_complete:
            state, reason = 'NEEDS_REVIEW', 'scanner_unavailable_or_incomplete'
        elif not relevant:
            state, reason = 'NOT_APPLICABLE', 'no_supported_technology_indicator'
        else:
            state, reason = 'PASS', 'no_supported_pattern_in_complete_scan'
        record(key, state, locations, reason, [finding['id'] for finding in matched])

    rule_check('hardcoded-credentials', ['hardcoded-credential'], python)
    env = signals['environment']
    record('environment-configuration', 'PASS' if env else ('NEEDS_REVIEW' if python else 'NOT_APPLICABLE'),
           env, 'environment_access_observed' if env else 'environment_configuration_not_observed')

    secret_paths = [file for file in inventory.paths if sensitive(Path(file))]
    ignore = inventory.texts.get('.gitignore')
    secret_evidence = [evidence(file, 'sensitive_filename_indicator') for file in secret_paths]
    if secret_paths:
        assessments = []
        for file in secret_paths:
            ignored, uncertain = _ignored(file, ignore or '')
            uncertain |= ignore is None and '.gitignore' in inventory.paths
            uncertain |= any(Path(candidate).name == '.gitignore' and Path(candidate).parent != Path('.')
                             and Path(file).is_relative_to(Path(candidate).parent)
                             for candidate in inventory.paths)
            assessments.append((ignored, uncertain))
        status = 'FAIL' if any(not ignored and not uncertain for ignored, uncertain in assessments) else 'NEEDS_REVIEW'
        record('sensitive-files-gitignore', status, secret_evidence, 'sensitive_files_require_tracking_review')
    elif ignore is None:
        record('sensitive-files-gitignore', 'NEEDS_REVIEW', reason='root_gitignore_not_observed')
    else:
        protections = [_ignored(name, ignore) for name in ('.env', '.env.production', 'private.key')]
        status = 'PASS' if all(ignored and not uncertain for ignored, uncertain in protections) else 'NEEDS_REVIEW'
        record('sensitive-files-gitignore', status, [evidence('.gitignore', 'root_ignore_configuration')],
               'bounded_root_ignore_policy')

    rule_check('production-debug', ['flask-debug'], bool(profile['frameworks']))
    if signals['debug_true']:
        previous = results['production-debug']
        record('production-debug', 'FAIL', previous['evidence'] + signals['debug_true'],
               'explicit_debug_enabled', previous['related_finding_ids'])
    elif signals['debug_dynamic'] and results['production-debug']['status'] != 'FAIL':
        record('production-debug', 'NEEDS_REVIEW', signals['debug_dynamic'], 'dynamic_debug_configuration')
    rule_check('tls-verification', ['tls-verification-disabled'], bool(technologies & {'requests', 'httpx', 'ssl'}))
    rule_check('unsafe-sql', ['sql-injection'], bool(signals['sql']))
    rule_check('unsafe-command', ['command-injection', 'dynamic-eval', 'dynamic-exec'],
               bool(signals['command'] or signals['dynamic_code']))
    rule_check('password-hashing', ['weak-password-hash'], 'hashlib' in technologies)
    rule_check('unsafe-deserialization', ['unsafe-pickle', 'unsafe-yaml'], bool(technologies & {'pickle', 'yaml'}))

    if signals['cors_credentials']:
        record('permissive-cors', 'FAIL', signals['cors_credentials'], 'wildcard_origin_with_credentials')
    elif signals['cors_open'] or signals['cors_dynamic']:
        record('permissive-cors', 'NEEDS_REVIEW', signals['cors_open'] + signals['cors_dynamic'], 'cors_policy_requires_review')
    elif signals['cors_allowlist']:
        record('permissive-cors', 'PASS', signals['cors_allowlist'], 'explicit_origin_allowlist_observed')
    else:
        record('permissive-cors', 'NEEDS_REVIEW' if profile['frameworks'] else 'NOT_APPLICABLE',
               reason='cors_policy_not_observed')
    record('authentication-indicators', 'NEEDS_REVIEW' if profile['frameworks'] else 'NOT_APPLICABLE',
           signals['auth'], 'authentication_coverage_cannot_be_proven_statically')
    manifests = profile['dependency_manifests']
    record('dependency-manifest', 'PASS' if manifests else ('NEEDS_REVIEW' if python else 'NOT_APPLICABLE'),
           [evidence(file, 'dependency_manifest') for file in manifests], 'manifest_presence_indicator')
    constraints, locations = _constraints(inventory, manifests)
    record('dependency-constraints', constraints if manifests else ('NEEDS_REVIEW' if python else 'NOT_APPLICABLE'),
           locations, 'bounded_version_declarations_only')
    tests = [file for file in inventory.paths if Path(file).suffix.lower() == '.py' and (
        Path(file).name.startswith('test_') or Path(file).stem.endswith('_test'))]
    record('test-presence', 'PASS' if tests else ('NEEDS_REVIEW' if python else 'NOT_APPLICABLE'),
           [evidence(file, 'test_filename_indicator') for file in tests], 'presence_does_not_prove_test_quality')
    state, locations, reason = _docker(inventory)
    record('docker-user', state, locations, reason)

    checks = [{**entry, **results[entry['key']]} for entry in catalog['checks']]
    summary = {state: sum(check['status'] == state for check in checks) for state in STATUSES}
    status = 'error' if not inventory.valid else ('complete' if inventory.complete and scanner_complete else 'partial')
    coverage = {'status': status, 'scanner_status': scanner_status,
        'inventoried_files': len(inventory.paths), 'parsed_python_files': len(inventory.trees),
        'diagnostics': inventory.diagnostics, 'excluded_directories': sorted(EXCLUDED),
        'limitations': catalog['limitations']}
    return ChecklistResult(catalog['version'], profile, coverage, summary, checks)
