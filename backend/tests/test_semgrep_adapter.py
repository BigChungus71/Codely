import json
import subprocess
from types import SimpleNamespace

import pytest

from backend.app.analyzers import semgrep_adapter as adapter


@pytest.fixture
def repository(tmp_path):
    (tmp_path / 'sample.py').write_text('eval(user_input)\n')
    return tmp_path


def scanner_json(path='sample.py', errors=None):
    return {'results': [{
        'check_id': 'local.eval', 'path': path,
        'start': {'line': 1}, 'end': {'line': 1},
        'extra': {'severity': 'WARNING', 'message': 'Review eval',
                  'metadata': {'title': 'Dynamic evaluation', 'cwe': ['CWE-95: eval']}}
    }], 'errors': errors or [], 'paths': {'scanned': ['sample.py']}}


def mock_run(monkeypatch, data, code=0):
    def run(command, **kwargs):
        assert kwargs['shell'] is False
        assert kwargs['timeout'] == 60
        assert kwargs['env']['PYTHONSAFEPATH'] == '1'
        assert 'PYTHONPATH' not in kwargs['env']
        assert kwargs['cwd'].joinpath('sample.py').read_text() == 'eval(user_input)\n'
        assert '--config' in command and str(adapter.RULE) in command
        assert '--no-rewrite-rule-ids' in command
        return SimpleNamespace(returncode=code, stdout=json.dumps(data).encode(),
                               stderr=b'potential secret never returned')
    monkeypatch.setattr(adapter.subprocess, 'run', run)


def test_normalization_and_stable_id(repository, monkeypatch):
    mock_run(monkeypatch, scanner_json())
    first = adapter.scan_repository(str(repository))
    second = adapter.scan_repository(str(repository))
    assert first.status == 'complete'
    assert first.findings == second.findings
    assert first.summary == {'total': 1, 'critical': 0, 'high': 0, 'medium': 1, 'low': 0}
    assert first.findings[0]['cwe'] == ['CWE-95']
    assert first.findings[0]['file'] == 'sample.py'
    assert 'potential secret' not in json.dumps(first.to_dict())


def test_error_with_findings_remains_partial(repository, monkeypatch):
    mock_run(monkeypatch, scanner_json(errors=[{'type': 'ParseError', 'message': 'secret'}]), 2)
    result = adapter.scan_repository(str(repository))
    assert result.status == 'partial' and result.summary['total'] == 1
    assert {'code': 'scanner_error', 'type': 'ParseError'} in result.diagnostics
    assert 'secret' not in json.dumps(result.to_dict())


def test_timeout(repository, monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired('semgrep', 60)
    monkeypatch.setattr(adapter.subprocess, 'run', run)
    result = adapter.scan_repository(str(repository))
    assert result.status == 'error'
    assert {'code': 'scanner_timeout', 'seconds': 60} in result.diagnostics


def test_invalid_json(repository, monkeypatch):
    monkeypatch.setattr(adapter.subprocess, 'run', lambda *a, **kw:
                        SimpleNamespace(returncode=2, stdout=b'<ERROR>', stderr=b''))
    result = adapter.scan_repository(str(repository))
    assert result.status == 'error'
    assert {'code': 'invalid_scanner_output'} in result.diagnostics


def test_external_finding_path_rejected(repository, monkeypatch):
    mock_run(monkeypatch, scanner_json('../outside.py'))
    result = adapter.scan_repository(str(repository))
    assert result.status == 'error' and not result.findings


def test_coverage_limits_are_visible(repository, monkeypatch):
    (repository / 'large.py').write_text('x' * 100)
    monkeypatch.setattr(adapter, 'MAX_FILE_BYTES', 50)
    mock_run(monkeypatch, scanner_json())
    result = adapter.scan_repository(str(repository))
    assert result.status == 'partial'
    assert {'code': 'coverage_limit', 'file': 'large.py'} in result.diagnostics


def test_empty_and_invalid_repository(tmp_path):
    assert adapter.scan_repository(str(tmp_path)).status == 'error'
    assert adapter.scan_repository(str(tmp_path / 'absent')).diagnostics == [
        {'code': 'invalid_repository'}]


def test_safe_scan_is_complete(repository, monkeypatch):
    data = scanner_json()
    data['results'] = []
    mock_run(monkeypatch, data)
    result = adapter.scan_repository(str(repository))
    assert result.status == 'complete' and result.summary['total'] == 0


def test_missing_executable(repository, monkeypatch):
    def run(*args, **kwargs):
        raise FileNotFoundError('scanner')
    monkeypatch.setattr(adapter.subprocess, 'run', run)
    result = adapter.scan_repository(str(repository))
    assert result.status == 'error'
    assert {'code': 'scanner_or_filesystem_unavailable'} in result.diagnostics


def test_uploaded_config_is_not_copied(repository, monkeypatch):
    (repository / '.semgrep.yaml').write_text('untrusted config')
    (repository / '.semgrepignore').write_text('sample.py')
    def run(*args, **kwargs):
        assert {p.name for p in kwargs['cwd'].iterdir()} == {'sample.py', '.semgrepignore'}
        assert kwargs['cwd'].joinpath('.semgrepignore').read_text() == ''
        return SimpleNamespace(returncode=0, stdout=json.dumps(scanner_json()).encode())
    monkeypatch.setattr(adapter.subprocess, 'run', run)
    assert adapter.scan_repository(str(repository)).status == 'complete'


def test_linked_files_are_skipped(repository, monkeypatch):
    (repository / 'linked.py').write_text('not to be read')
    original = adapter._linked
    monkeypatch.setattr(adapter, '_linked', lambda p:
                        p.name == 'linked.py' or original(p))
    mock_run(monkeypatch, scanner_json())
    result = adapter.scan_repository(str(repository))
    assert result.status == 'partial'
    assert {'code': 'linked_file_skipped', 'file': 'linked.py'} in result.diagnostics
