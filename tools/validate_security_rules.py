"""Offline rule validation using the installed Semgrep schema and core parser.

Semgrep 1.187.0's CLI --validate fetches registry metachecks. Use a local minimal
metacheck pack instead, so validation needs no registry/API access.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import jsonschema
from ruamel.yaml import YAML


ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / 'backend/app/rules/python-security.yaml'


def semgrep_package():
    executable = os.getenv('CODELY_SEMGREP_EXECUTABLE')
    python = Path(executable).expanduser().absolute().parent / ('python.exe' if os.name == 'nt' else 'python') if executable else Path(sys.executable)
    code = "from importlib.resources import files; print(files('semgrep'))"
    result = subprocess.run([str(python), '-I', '-c', code], check=True, capture_output=True, text=True, timeout=10)
    return Path(result.stdout.strip())


def validate_rules(rule_path=RULE):
    yaml = YAML(typ='safe')
    pack = yaml.load(rule_path.read_text(encoding='utf-8'))
    package = semgrep_package()
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
        completed = subprocess.run([str(core), '-json', '-check_rules', str(lint), str(rule_path)],
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
    paths = [RULE, RULE.with_name('java-security.yaml'), RULE.with_name('web-security.yaml')]
    print(f'PASS: offline schema and native core validation; {sum(map(validate_rules, paths))} rules')
