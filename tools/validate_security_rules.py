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
RULES = [
    ROOT / 'backend/app/rules/python-security.yaml',
    ROOT / 'backend/app/rules/java-security.yaml',
    ROOT / 'backend/app/rules/web-security.yaml',
]
RULE = RULES[0]


def validate_rules(rule_paths=None):
    target_rules = list(rule_paths) if rule_paths is not None else RULES
    yaml = YAML(typ='safe')
    package = importlib.resources.files('semgrep')
    schema = yaml.load(package.joinpath('semgrep_interfaces/rule_schema_v1.yaml').read_text())
    validator = jsonschema.Draft7Validator(schema)
    state = ROOT / '.semgrep-local'
    state.mkdir(exist_ok=True)
    total = 0
    with tempfile.TemporaryDirectory(prefix='rule-validation-', dir=state) as work:
        work = Path(work)
        lint = work / 'local-metachecks.yaml'
        lint.write_text(
            'rules:\n  - id: codely.local.invalid-marker\n'
            '    languages: [yaml]\n    severity: ERROR\n'
            '    message: Invalid local rule marker\n'
            '    pattern: "codely_invalid_rule: true"\n',
            encoding='utf-8',
        )
        core = package.joinpath('bin/semgrep-core.exe' if os.name == 'nt' else 'bin/semgrep-core')
        for rule_file in target_rules:
            pack = yaml.load(rule_file.read_text(encoding='utf-8'))
            validator.validate(pack)
            total += len(pack['rules'])
            completed = subprocess.run(
                [str(core), '-json', '-check_rules', str(lint), str(rule_file)],
                shell=False,
                timeout=60,
                capture_output=True,
                cwd=ROOT,
            )
            (state / f'rule-validation-{rule_file.stem}.json').write_bytes(completed.stdout)
            (state / f'rule-validation-{rule_file.stem}.stderr').write_bytes(completed.stderr)
            if completed.returncode:
                raise RuntimeError(f'Core rule validation exited {completed.returncode} for {rule_file.name}')
            lines = [line for line in completed.stdout.splitlines() if line.startswith(b'{')]
            if len(lines) != 1:
                raise RuntimeError(f'Missing or ambiguous core validation JSON for {rule_file.name}')
            data = json.loads(lines[0])
            if data.get('errors'):
                raise RuntimeError(f'Core rule validation reported errors for {rule_file.name}')
    return total


if __name__ == '__main__':
    print(f'PASS: offline schema and native core validation; {validate_rules()} rules across {len(RULES)} packs')
