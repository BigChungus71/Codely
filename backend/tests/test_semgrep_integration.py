"""Opt-in real Semgrep tests. No mocking and no execution of fixture source."""
import json
import os

import pytest

from backend.app.analyzers.semgrep_adapter import ROOT, scan_repository
from tools.validate_security_rules import validate_rules


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION') != '1',
    reason='Opt-in real Semgrep execution requires a working native process outside the sandbox')]
BASE = ROOT / 'fixtures/security_rules'
EXPECTED = json.loads((BASE / 'expectations.json').read_text())
RULE_IDS = sorted({entry['rule_id'] for entries in EXPECTED.values() for entry in entries})


@pytest.fixture(scope='module')
def real_scan():
    result = scan_repository(str(BASE))
    assert result.status == 'complete', result.diagnostics
    assert {'code': 'scanner_exit', 'exit_code': 0} in result.diagnostics
    assert {'code': 'scanner_coverage', 'files': len(EXPECTED)} in result.diagnostics
    return result


def test_native_rule_compilation():
    assert validate_rules() == 12


@pytest.mark.parametrize('rule_id', RULE_IDS)
def test_actual_rule_detections_and_safe_alternatives(real_scan, rule_id):
    expected = sorted((path, entry['line']) for path, entries in EXPECTED.items()
                      for entry in entries if entry['rule_id'] == rule_id)
    actual = sorted((finding['file'], finding['start_line']) for finding in real_scan.findings
                    if finding['rule_id'] == rule_id)
    assert actual == expected


def test_actual_nested_repository_contract(real_scan):
    expected = {(path, entry['rule_id'], entry['line']) for path, entries in EXPECTED.items()
                for entry in entries}
    assert {(f['file'], f['rule_id'], f['start_line']) for f in real_scan.findings} == expected
    assert real_scan.summary['total'] == len(expected)
    assert len({f['id'] for f in real_scan.findings}) == len(expected)
    for finding in real_scan.findings:
        assert set(finding) == {'id', 'rule_id', 'source', 'severity', 'title', 'file',
                                'start_line', 'end_line', 'message', 'cwe'}
        assert '\\' not in finding['file'] and finding['cwe']
    assert json.loads(json.dumps(real_scan.to_dict()))['status'] == 'complete'


def test_actual_safe_repository():
    result = scan_repository(str(BASE / 'safe'))
    assert result.status == 'complete', result.diagnostics
    assert result.findings == [] and result.summary['total'] == 0
    assert {'code': 'scanner_coverage', 'files': 12} in result.diagnostics


def test_actual_parse_error_is_partial(tmp_path):
    (tmp_path / 'valid.py').write_text('eval(user_input)\n')
    (tmp_path / 'broken.py').write_text('def broken(:\n')
    result = scan_repository(str(tmp_path))
    assert result.status == 'partial', result.diagnostics
    assert result.summary['total'] == 1
    assert {'code': 'python_syntax_error', 'file': 'broken.py'} in result.diagnostics


def test_actual_same_line_findings_are_distinct(tmp_path):
    (tmp_path / 'two.py').write_text('eval(first); eval(second)\n')
    result = scan_repository(str(tmp_path))
    assert result.status == 'complete', result.diagnostics
    assert len(result.findings) == len({f['id'] for f in result.findings}) == 2
