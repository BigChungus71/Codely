"""Real scanner-to-checklist handoff, enabled with the existing native-test flag."""
import json
import os

import jsonschema
import pytest

from backend.app.analyzers.semgrep_adapter import ROOT, scan_repository
from backend.app.checklists import evaluate_repository


pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get('CODELY_RUN_SEMGREP_INTEGRATION') != '1',
    reason='Requires actual native Semgrep outside restricted sandbox')]


@pytest.fixture(scope='module')
def report():
    target = ROOT / 'fixtures/checklist_demo'
    scan = scan_repository(str(target))
    assert scan.status == 'complete' and scan.summary['total'] == 2
    result = evaluate_repository(str(target), scan)
    return result, scan


def test_real_scanner_checklist_handoff(report):
    result, scan = report
    assert result.coverage['status'] == 'complete'
    assert result.summary == {'PASS': 8, 'FAIL': 2, 'NEEDS_REVIEW': 1, 'NOT_APPLICABLE': 4}
    related = {identifier for check in result.checks for identifier in check['related_finding_ids']}
    assert related == {finding['id'] for finding in scan.findings}
    assert 'synthetic-demo-password' not in json.dumps(result.to_dict())


def test_representative_json_matches_real_deterministic_output(report):
    result, _scan = report
    expected = json.loads((ROOT / 'contracts/examples/checklist-v1.json').read_text())
    assert result.to_dict() == expected
    schema = json.loads((ROOT / 'contracts/checklist-v1.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(expected)
