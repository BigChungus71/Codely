"""Offline rule validation using the installed Semgrep schema and core parser.

Semgrep 1.187.0's CLI --validate fetches registry metachecks. Use a local minimal
metacheck pack instead, so validation needs no registry/API access.
"""
import importlib.resources
import json
import os
from pathlib import Path
import subprocess
import tempfile

import jsonschema
from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / 'backend/app/rules/python-security.yaml'


def validate_rules():
    yaml = YAML(typ='safe')
    pack = yaml.load(RULE.read_text(encoding='utf-8'))
    package = importlib.resources.files('semgrep')
    schema = yaml.load(package.joinpath('semgrep_interfaces/rule_schema_v1.yaml').read_text())
    jsonschema.Draft7Validator(schema).validate(pack)
    state = ROOT / '.semgrep-local'
    state.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rule-validation-', dir=state) as work:
        work = Path(work)
        lint = work / 'local-metachecks.yaml'
        lint.write_text('rules:\n  - id: codely.local.invalid-marker\n'
                        '    languages: [yaml]\n    severity: ERROR\n'
                        '    message: Invalid local rule marker\n'
                        '    pattern: "codely_invalid_rule: true"\n', encoding='utf-8')
        core = package.joinpath('bin/semgrep-core.exe' if os.name == 'nt' else 'bin/semgrep-core')
        completed = subprocess.run([str(core), '-json', '-check_rules', str(lint), str(RULE)],
                                   shell=False, timeout=60, capture_output=True, cwd=ROOT)
        (state / 'rule-validation.json').write_bytes(completed.stdout)
        (state / 'rule-validation.stderr').write_bytes(completed.stderr)
        if completed.returncode:
            raise RuntimeError(f'Core rule validation exited {completed.returncode}; see {state}')
        # The core's check_rules mode emits a progress dot before its JSON.
        lines = [line for line in completed.stdout.splitlines() if line.startswith(b'{')]
        if len(lines) != 1:
            raise RuntimeError('Missing or ambiguous core validation JSON')
        data = json.loads(lines[0])
        if data.get('errors'):
            raise RuntimeError('Core rule validation reported errors')
    return len(pack['rules'])


if __name__ == '__main__':
    print(f'PASS: offline schema and native core validation; {validate_rules()} rules')
