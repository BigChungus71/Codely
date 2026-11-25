"""Mocked boundary tests; these do not establish native detection coverage."""
from copy import deepcopy
import json
from pathlib import PureWindowsPath
import subprocess
from types import SimpleNamespace

import pytest

from backend.app.analyzers import semgrep_adapter as adapter
from backend.app.analyzers.finding_normalizer import normalize_finding
from backend.tests.test_semgrep_adapter import scanner_json


@pytest.fixture
def repository(tmp_path):
    (tmp_path / 'sample.py').write_text('eval(value)\n')
    return tmp_path


def output(monkeypatch, payload, exit_code=0):
    monkeypatch.setattr(adapter.subprocess, 'run', lambda *args, **kwargs:
        SimpleNamespace(returncode=exit_code, stdout=payload, stderr=b'secret diagnostics'))


@pytest.mark.parametrize('payload', [b'', b'not-json', b'null', b'[]', b'"string"',
    b'{}', b'{"results":{},"errors":[],"paths":{"scanned":[]}}',
    b'{"results":[],"errors":[1],"paths":{"scanned":[]}}',
    b'{"results":[],"errors":[],"paths":{"scanned":"sample.py"}}'])
def test_malformed_output_is_never_success(repository, monkeypatch, payload):
    output(monkeypatch, payload)
    result = adapter.scan_repository(str(repository))
    assert result.status == 'error' and not result.findings
    assert {'code': 'invalid_scanner_output'} in result.diagnostics


@pytest.mark.parametrize('exit_code', [2, 7, -9])
def test_failed_scanner_without_findings_is_error(repository, monkeypatch, exit_code):
    data = scanner_json()
    data['results'] = []
    output(monkeypatch, json.dumps(data).encode(), exit_code)
    result = adapter.scan_repository(str(repository))
    assert result.status == 'error'
    assert {'code': 'scanner_exit', 'exit_code': exit_code} in result.diagnostics


def test_partial_errors_without_findings_are_not_clean(repository, monkeypatch):
    data = scanner_json(errors=[{'type': 'Timeout', 'message': 'source must not leak'}])
    data['results'] = []
    output(monkeypatch, json.dumps(data).encode())
    result = adapter.scan_repository(str(repository))
    assert result.status == 'partial' and result.summary['total'] == 0
    assert 'source must not leak' not in json.dumps(result.to_dict())


def test_incomplete_scanner_inventory(repository, monkeypatch):
    data = scanner_json()
    data['results'] = []
    data['paths']['scanned'] = []
    output(monkeypatch, json.dumps(data).encode())
    assert adapter.scan_repository(str(repository)).status == 'partial'


def test_duplicates_are_counted_once(repository, monkeypatch):
    data = scanner_json()
    data['results'] *= 3
    output(monkeypatch, json.dumps(data).encode())
    result = adapter.scan_repository(str(repository))
    assert result.status == 'complete'
    assert len(result.findings) == result.summary['total'] == 1
    assert {'code': 'duplicate_findings_removed', 'count': 2} in result.diagnostics


def test_conflicting_duplicates_are_not_silently_merged(repository, monkeypatch):
    data = scanner_json()
    second = deepcopy(data['results'][0])
    second['extra']['severity'] = 'ERROR'
    data['results'].append(second)
    output(monkeypatch, json.dumps(data).encode())
    assert adapter.scan_repository(str(repository)).status == 'error'


def test_distinct_columns_have_distinct_ids(repository):
    raw = scanner_json()['results'][0]
    raw['start']['col'] = 1
    first = normalize_finding(raw, repository)
    raw['start']['col'] = 15
    assert normalize_finding(raw, repository)['id'] != first['id']


def test_windows_relative_path_normalization(repository):
    raw = scanner_json(r'nested\module.py')['results'][0]
    assert normalize_finding(raw, repository)['file'] == 'nested/module.py'
    assert not PureWindowsPath(normalize_finding(raw, repository)['file']).is_absolute()


@pytest.mark.parametrize('path', ['../outside.py', r'..\outside.py', r'C:relative.py',
                                r'\\server\share\file.py', '', 'file\x00.py'])
def test_unsafe_scanner_paths_are_rejected(repository, path):
    with pytest.raises(ValueError):
        normalize_finding(scanner_json(path)['results'][0], repository)


@pytest.mark.parametrize('change', [
    {'start': {'line': 0}}, {'start': {'line': True}}, {'end': {'line': -1}},
    {'extra': {'severity': 'UNKNOWN', 'message': 'x'}},
    {'extra': {'severity': 'WARNING', 'message': 'x', 'metadata': {'cwe': None}}},
])
def test_malformed_finding_never_reports_clean(repository, monkeypatch, change):
    data = scanner_json()
    data['results'][0].update(deepcopy(change))
    output(monkeypatch, json.dumps(data).encode())
    assert adapter.scan_repository(str(repository)).status == 'error'


@pytest.mark.parametrize('value', ['', '   ', None, 42, 'path\x00invalid'])
def test_invalid_repository_arguments(value):
    result = adapter.scan_repository(value)
    assert result.status == 'error'
    assert result.diagnostics == [{'code': 'invalid_repository'}]


def test_unsupported_only_repository_is_not_clean(tmp_path, monkeypatch):
    (tmp_path / 'sample.go').write_text('package sample')
    def unexpected(*args, **kwargs):
        pytest.fail('Scanner should not run without supported files')
    monkeypatch.setattr(adapter.subprocess, 'run', unexpected)
    result = adapter.scan_repository(str(tmp_path))
    assert result.status == 'error'
    assert {'code': 'no_supported_files'} in result.diagnostics
    assert next(d for d in result.diagnostics if d['code'] == 'coverage')['unsupported_files'] == 1


def test_nested_windows_paths_are_normalized(tmp_path, monkeypatch):
    path = tmp_path / 'nested package' / 'deep' / 'sample.py'
    path.parent.mkdir(parents=True)
    path.write_text('eval(value)\n')
    data = scanner_json(r'nested package\deep\sample.py')
    data['paths']['scanned'] = [r'nested package\deep\sample.py']
    output(monkeypatch, json.dumps(data).encode())
    result = adapter.scan_repository(str(tmp_path))
    assert result.status == 'complete'
    assert result.findings[0]['file'] == 'nested package/deep/sample.py'


def test_syntax_error_is_coverage_gap(repository, monkeypatch):
    (repository / 'broken.py').write_text('def broken(:\n')
    output(monkeypatch, json.dumps(scanner_json()).encode())
    result = adapter.scan_repository(str(repository))
    assert result.status == 'partial'
    assert {'code': 'python_syntax_error', 'file': 'broken.py'} in result.diagnostics


@pytest.mark.parametrize('severity, expected', [('ERROR', 'HIGH'), ('WARNING', 'MEDIUM'),
    ('INFO', 'LOW'), ('CRITICAL', 'CRITICAL'), ('high', 'HIGH')])
def test_severity_mapping(repository, severity, expected):
    raw = scanner_json()['results'][0]
    raw['extra']['severity'] = severity
    assert normalize_finding(raw, repository)['severity'] == expected
