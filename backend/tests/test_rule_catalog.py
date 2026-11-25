import json
from pathlib import Path
import re

import jsonschema
from ruamel.yaml import YAML

from backend.app.analyzers.semgrep_adapter import ROOT, RULE
from tools.validate_security_rules import semgrep_package


def test_trusted_rule_catalog_and_offline_schema():
    yaml = YAML(typ='safe')
    pack = yaml.load(RULE.read_text(encoding='utf-8'))
    schema_file = semgrep_package().joinpath(
        'semgrep_interfaces/rule_schema_v1.yaml')
    jsonschema.Draft7Validator(yaml.load(schema_file.read_text())).validate(pack)
    rules = pack['rules']
    assert len(rules) == len({rule['id'] for rule in rules}) == 12
    for rule in rules:
        metadata = rule['metadata']
        assert rule['id'].startswith('codely.python.')
        assert rule['languages'] == ['python']
        for field in ('title', 'description', 'severity', 'cwe', 'remediation', 'references'):
            assert metadata[field]
        assert all(re.fullmatch(r'CWE-\d+', cwe) for cwe in metadata['cwe'])
        assert metadata['severity'] in {'HIGH', 'MEDIUM', 'LOW'}
        assert isinstance(metadata['owasp'], list)
        assert all(':2021 - ' in category for category in metadata['owasp'])
        assert all(url.startswith('https://') for url in metadata['references'])
        assert '$' not in rule['message']  # Never interpolate credentials/source into messages.
        assert 'validators' not in rule  # No live secret validation/API calls.


def test_every_rule_has_vulnerable_and_safe_fixtures():
    yaml = YAML(typ='safe')
    rules = yaml.load(RULE.read_text(encoding='utf-8'))['rules']
    base = ROOT / 'fixtures/security_rules'
    expected = json.loads((base / 'expectations.json').read_text())
    assert set(expected) == {p.relative_to(base).as_posix() for p in base.rglob('*')
                             if p.is_file() and p.suffix.lower() == '.py'}
    for rule in rules:
        name = rule['id'].removeprefix('codely.python.')
        assert expected[f'vulnerable/{name}/case.py'][0]['rule_id'] == rule['id']
        assert expected[f'safe/{name}/case.py'] == []
        # Parse text only; fixtures are never imported/compiled/executed by tests.
        assert (base / 'safe' / name / 'case.py').is_file()
