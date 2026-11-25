"""Static checklist tests using supplied scan envelopes, not mocked detection claims."""
import json
from pathlib import Path

import pytest

from backend.app.analyzers.semgrep_adapter import ScanResult
from backend.app.checklists import evaluate_repository
from backend.app.checklists import __main__ as cli
from backend.app.checklists import inventory


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'app.py').write_text('value = 1\n')
    return tmp_path


def scan(status='complete', rule=None, message='Static finding'):
    result = ScanResult(status)
    result.diagnostics = [{'code': 'coverage', 'rule_set': 'python-security-v2'},
                          {'code': 'scanner_exit', 'exit_code': 0}]
    if rule:
        result.findings = [{'id': 'finding_synthetic', 'rule_id': 'codely.python.' + rule,
            'source': 'semgrep', 'severity': 'HIGH', 'title': 'Static finding',
            'file': 'app.py', 'start_line': 1, 'end_line': 1, 'message': message, 'cwe': ['CWE-798']}]
        result.summary['total'] = result.summary['high'] = 1
    return result


def check(repo, key, supplied=None):
    result = evaluate_repository(str(repo), supplied if supplied is not None else scan())
    return next(item for item in result.checks if item['key'] == key)


def test_catalog_has_fifteen_versioned_checks(repo):
    result = evaluate_repository(str(repo), scan())
    assert result.catalog_version == '1.0.0'
    assert len({item['id'] for item in result.checks}) == len(result.checks) == 15
    assert sum(result.summary.values()) == 15
    assert result.coverage['status'] == 'complete'
    for item in result.checks:
        assert item['status'] in {'PASS', 'FAIL', 'NEEDS_REVIEW', 'NOT_APPLICABLE'}
        assert item['remediation'] and item['reference_urls'] and item['limitations']
        assert all(url.startswith('https://') for url in item['reference_urls'])


@pytest.mark.parametrize('status', ['partial', 'error'])
def test_incomplete_scan_is_never_passing(repo, status):
    assert check(repo, 'hardcoded-credentials', scan(status))['status'] == 'NEEDS_REVIEW'
    assert evaluate_repository(str(repo), scan(status)).coverage['status'] == 'partial'


def test_missing_scan_is_explicit_review(repo):
    result = evaluate_repository(str(repo))
    assert result.coverage['scanner_status'] == 'not_provided'
    assert next(c for c in result.checks if c['key'] == 'hardcoded-credentials')['status'] == 'NEEDS_REVIEW'


def test_unverified_pack_cannot_yield_pass(repo):
    data = scan()
    data.diagnostics = []
    assert check(repo, 'hardcoded-credentials', data)['status'] == 'NEEDS_REVIEW'


@pytest.mark.parametrize('value', [{}, [], {'status': 'complete'}, 42])
def test_invalid_scan_is_review_not_crash(repo, value):
    result = evaluate_repository(str(repo), value)
    assert result.coverage['scanner_status'] == 'invalid'


def test_related_findings_and_fail_survive_partial_scan(repo):
    item = check(repo, 'hardcoded-credentials', scan('partial', 'hardcoded-credential'))
    assert item['status'] == 'FAIL'
    assert item['related_finding_ids'] == ['finding_synthetic']
    assert item['evidence'] == [{'file': 'app.py', 'kind': 'semgrep_finding',
                                 'start_line': 1, 'end_line': 1}]


@pytest.mark.parametrize('rule,key', [
    ('hardcoded-credential','hardcoded-credentials'), ('flask-debug','production-debug'),
    ('tls-verification-disabled','tls-verification'), ('sql-injection','unsafe-sql'),
    ('command-injection','unsafe-command'), ('dynamic-eval','unsafe-command'),
    ('dynamic-exec','unsafe-command'), ('weak-password-hash','password-hashing'),
    ('unsafe-pickle','unsafe-deserialization'), ('unsafe-yaml','unsafe-deserialization')])
def test_existing_rule_findings_are_reused(repo, rule, key):
    assert check(repo, key, scan(rule=rule))['status'] == 'FAIL'


def test_tls_without_supported_library_is_not_applicable(repo):
    assert check(repo, 'tls-verification')['status'] == 'NOT_APPLICABLE'


def test_environment_access_has_line_evidence(repo):
    (repo / 'app.py').write_text('import os\nconfig = os.getenv("CONFIG")\n')
    item = check(repo, 'environment-configuration')
    assert item['status'] == 'PASS'
    assert item['evidence'][0]['start_line'] == 2


def test_missing_environment_configuration_needs_review(repo):
    assert check(repo, 'environment-configuration')['status'] == 'NEEDS_REVIEW'


@pytest.mark.parametrize('ignored,expected', [(False,'FAIL'), (True,'NEEDS_REVIEW')])
def test_sensitive_files_are_never_declared_safe(repo, ignored, expected):
    (repo / '.env').write_text('PASSWORD=synthetic-value-never-echoed')
    if ignored:
        (repo / '.gitignore').write_text('.env\n')
    assert check(repo, 'sensitive-files-gitignore')['status'] == expected


def test_sufficient_ignore_indicators_pass(repo):
    (repo / '.gitignore').write_text('.env\n.env.*\n*.key\n')
    assert check(repo, 'sensitive-files-gitignore')['status'] == 'PASS'


def test_ignore_negation_is_respected(repo):
    (repo / '.gitignore').write_text('.env*\n!.env\n*.key\n')
    (repo / '.env').write_text('TOKEN=not-real')
    assert check(repo, 'sensitive-files-gitignore')['status'] == 'FAIL'


@pytest.mark.parametrize('source', [
    'from fastapi import FastAPI\napp = FastAPI(debug=True)\n',
    'import django\nDEBUG = True\n'])
def test_explicit_additional_debug_configuration_fails(repo, source):
    (repo / 'app.py').write_text(source)
    assert check(repo, 'production-debug')['status'] == 'FAIL'


def test_dynamic_debug_configuration_is_review(repo):
    (repo / 'app.py').write_text('from fastapi import FastAPI\napp = FastAPI(debug=enabled)\n')
    assert check(repo, 'production-debug')['status'] == 'NEEDS_REVIEW'


@pytest.mark.parametrize('configuration,expected', [
    ('allow_origins=["*"], allow_credentials=True', 'FAIL'),
    ('allow_origins=["*"]', 'NEEDS_REVIEW'),
    ('allow_origins=["https://example.test"], allow_credentials=True', 'PASS'),
    ('allow_origins=dynamic_origins', 'NEEDS_REVIEW'),
    ('allow_origins=[dynamic_origin]', 'NEEDS_REVIEW'),
    ('allow_origins=["https://example.test"], allow_origin_regex=dynamic_regex', 'NEEDS_REVIEW')])
def test_cors_configuration_states(repo, configuration, expected):
    (repo / 'app.py').write_text('from fastapi import FastAPI\n'
        'from fastapi.middleware.cors import CORSMiddleware as Cors\napp = FastAPI()\n'
        f'app.add_middleware(Cors, {configuration})\n')
    assert check(repo, 'permissive-cors')['status'] == expected


def test_authentication_indicators_never_prove_coverage(repo):
    (repo / 'app.py').write_text('from flask import Flask\nfrom flask_login import login_required\n'
        '@login_required\ndef restricted():\n    return "value"\n')
    item = check(repo, 'authentication-indicators')
    assert item['status'] == 'NEEDS_REVIEW'
    assert item['evidence']


@pytest.mark.parametrize('requirement,expected', [
    ('flask==3.1.0','PASS'), ('flask>=3,<4','PASS'), ('flask~=3.1','PASS'),
    ('flask','NEEDS_REVIEW'), ('flask>=3','NEEDS_REVIEW'), ('-r external.txt','NEEDS_REVIEW'),
    ('flask @ https://example.test/flask.whl','NEEDS_REVIEW')])
def test_dependency_constraints(repo, requirement, expected):
    (repo / 'requirements.txt').write_text(requirement + '\n')
    assert check(repo, 'dependency-manifest')['status'] == 'PASS'
    assert check(repo, 'dependency-constraints')['status'] == expected


def test_pep621_dependencies(repo):
    (repo / 'pyproject.toml').write_text('[project]\nname="sample"\nversion="1.0"\n'
                                      'dependencies=["flask>=3,<4"]\n')
    assert check(repo, 'dependency-constraints')['status'] == 'PASS'


def test_invalid_toml_needs_review(repo):
    (repo / 'pyproject.toml').write_text('[project\n')
    assert check(repo, 'dependency-constraints')['status'] == 'NEEDS_REVIEW'


def test_setup_file_is_never_executed(repo):
    (repo / 'setup.py').write_text('raise RuntimeError("never run setup")\n')
    assert check(repo, 'dependency-manifest')['status'] == 'PASS'
    assert check(repo, 'dependency-constraints')['status'] == 'NEEDS_REVIEW'


def test_test_filename_presence_without_execution(repo):
    (repo / 'test_danger.py').write_text('raise RuntimeError("never run this")\n')
    assert check(repo, 'test-presence')['status'] == 'PASS'


@pytest.mark.parametrize('text,expected', [
    ('FROM python:3.11\nUSER root\n','FAIL'), ('FROM python:3.11\nUSER 0:0\n','FAIL'),
    ('FROM python:3.11\nUSER 10001\n','PASS'), ('FROM python:3.11\n','NEEDS_REVIEW'),
    ('FROM python:3.11\nUSER ${USER_ID}\n','NEEDS_REVIEW'),
    ('FROM python:3.11 AS build\nUSER 10001\nFROM python:3.11\n','NEEDS_REVIEW'),
    ('FROM python:3.11\nUSER 10001\nFROM python:3.11\nUSER root\n','FAIL')])
def test_final_docker_user(repo, text, expected):
    (repo / 'Dockerfile').write_text(text)
    assert check(repo, 'docker-user')['status'] == expected


def test_no_dockerfile_is_not_applicable(repo):
    assert check(repo, 'docker-user')['status'] == 'NOT_APPLICABLE'


@pytest.mark.parametrize('instruction,expected', [('USER', 'NEEDS_REVIEW'),
    ('USER -1', 'NEEDS_REVIEW'), ('USER\t10001', 'PASS')])
def test_docker_user_syntax_is_conservative(repo, instruction, expected):
    (repo / 'Dockerfile').write_text('FROM python:3.11\n' + instruction + '\n')
    assert check(repo, 'docker-user')['status'] == expected


def test_nested_ignore_policies_require_review(repo):
    nested = repo / 'config'
    nested.mkdir()
    (nested / '.env').write_text('TOKEN=synthetic-value')
    (nested / '.gitignore').write_text('.env\n')
    assert check(repo, 'sensitive-files-gitignore')['status'] == 'NEEDS_REVIEW'


def test_missing_manifest_is_review(repo):
    assert check(repo, 'dependency-manifest')['status'] == 'NEEDS_REVIEW'


def test_inventory_size_limit_is_partial(repo, monkeypatch):
    monkeypatch.setattr(inventory, 'MAX_FILE_BYTES', 1)
    result = evaluate_repository(str(repo), scan())
    assert result.coverage['status'] == 'partial'
    assert {'code': 'file_size_limit', 'file': 'app.py'} in result.coverage['diagnostics']


def test_static_profile_and_alias_evidence(repo):
    (repo / 'app.py').write_text('import flask as web\nfrom requests import get\n')
    result = evaluate_repository(str(repo), scan())
    assert result.profile['frameworks'] == ['flask']
    assert result.profile['technologies'] == ['flask', 'requests']
    assert result.profile['evidence'][0]['file'] == 'app.py'


def test_syntax_gap_downgrades_static_pass(repo):
    (repo / 'broken.py').write_text('def broken(:\n')
    (repo / 'requirements.txt').write_text('flask==3.1.0\n')
    assert check(repo, 'dependency-manifest')['status'] == 'NEEDS_REVIEW'
    assert evaluate_repository(str(repo), scan()).coverage['status'] == 'partial'


@pytest.mark.parametrize('value', ['', None, 42, 'does-not-exist'])
def test_invalid_repository_output_is_explicit(value):
    result = evaluate_repository(value)
    assert result.coverage['status'] == 'error'
    assert all(item['status'] == 'NEEDS_REVIEW' for item in result.checks)


def test_secret_redaction_and_determinism(repo, monkeypatch):
    secret = 'synthetic-UNIQUE-secret-never-in-output'
    (repo / '.env').write_text('PASSWORD=' + secret)
    (repo / 'app.py').write_text('import os\npassword = "' + secret + '"\n')
    (repo / 'requirements.txt').write_text('pkg @ https://user:' + secret + '@example.test/a.whl\n')
    original_open = Path.open
    def guarded_open(path, *args, **kwargs):
        assert path.name != '.env', 'Sensitive file contents must not be read'
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded_open)
    supplied = scan(rule='hardcoded-credential', message=secret)
    first = evaluate_repository(str(repo), supplied).to_dict()
    second = evaluate_repository(str(repo), supplied).to_dict()
    assert first == second
    serialized = json.dumps(first, sort_keys=True)
    assert secret not in serialized and str(repo) not in serialized


def test_evaluator_never_invokes_scanner(repo, monkeypatch):
    from backend.app.analyzers import semgrep_adapter
    monkeypatch.setattr(semgrep_adapter, 'scan_repository', lambda path: pytest.fail('Duplicate scan'))
    assert evaluate_repository(str(repo), scan()).catalog_version == '1.0.0'


def test_cli_reuses_json_without_scanning(repo, monkeypatch, capsys):
    path = repo / 'scan.json'
    path.write_text(json.dumps(scan().to_dict()))
    monkeypatch.setattr(cli, 'scan_repository', lambda path: pytest.fail('Duplicate scan'))
    assert cli.main([str(repo), '--scan-result', str(path)]) == 0
    assert json.loads(capsys.readouterr().out)['catalog_version'] == '1.0.0'


def test_cli_scans_exactly_once(repo, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, 'scan_repository', lambda path: calls.append(path) or scan())
    assert cli.main([str(repo)]) == 0
    assert calls == [str(repo)]
    capsys.readouterr()
