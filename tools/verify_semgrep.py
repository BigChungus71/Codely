"""Verify the installed scanner against local static fixtures; never import them."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    state = root / '.semgrep-local'
    state.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        SEMGREP_LOG_FILE=str(state / 'semgrep.log'),
        SEMGREP_SETTINGS_FILE=str(state / 'settings.yaml'),
        SEMGREP_VERSION_CACHE_PATH=str(state / 'version'),
        SEMGREP_SEND_METRICS='off', SEMGREP_ENABLE_VERSION_CHECK='0',
        PYTHONUTF8='1', PYTHONIOENCODING='utf-8',
    )
    command = [
        str(Path(sys.executable).parent / ('semgrep.exe' if os.name == 'nt' else 'semgrep')), 'scan',
        '--config', 'backend/app/rules/compatibility-smoke.yaml',
        '--json', '--metrics=off', '--disable-version-check', '--no-git-ignore',
        'fixtures/semgrep_compatibility',
    ]
    result = subprocess.run(command, cwd=root, env=env, shell=False,
                            timeout=60, capture_output=True)
    (state / 'verification.json').write_bytes(result.stdout)
    (state / 'verification.stderr').write_bytes(result.stderr)
    if result.returncode:
        raise SystemExit(f'Scanner exited {result.returncode}; see {state}')
    data = json.loads(result.stdout)
    expected = 'backend.app.rules.codely.compatibility.python-eval'
    findings = data['results']
    scanned = {p.replace('\\', '/') for p in data['paths']['scanned']}
    prefix = 'fixtures/semgrep_compatibility/'
    if data['errors'] or scanned != {prefix + 'safe.py', prefix + 'vulnerable.py'}:
        raise SystemExit('Scanner errors or incomplete fixture coverage')
    if len(findings) != 1 or findings[0]['check_id'] != expected:
        raise SystemExit('Unexpected findings')
    finding = findings[0]
    if (finding['path'].replace('\\', '/') != prefix + 'vulnerable.py'
            or finding['start']['line'] != 3):
        raise SystemExit('Unexpected finding evidence')
    print('PASS: JSON parsed; both fixtures scanned; vulnerable=1, safe=0; errors=0')


if __name__ == '__main__':
    main()
