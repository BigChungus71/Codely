"""Local, deterministic Python scanning. Uploaded code is only read as text."""
from dataclasses import asdict, dataclass, field
import ast
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

from .finding_normalizer import normalize_finding as _normalize, repository_relative_path


ROOT = Path(__file__).resolve().parents[3]
RULE = ROOT / 'backend/app/rules/python-security.yaml'
EXCLUDED = {'.git', '.venv', 'venv', '__pycache__', 'node_modules',
            '.semgrep-local', 'reference', 'dist', 'build'}
MAX_FILES = 5000
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024


def _linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0)
                                    & stat.FILE_ATTRIBUTE_REPARSE_POINT)


@dataclass
class ScanResult:
    status: str
    summary: dict = field(default_factory=lambda: dict.fromkeys(
        ('total', 'critical', 'high', 'medium', 'low'), 0))
    findings: list[dict] = field(default_factory=list)
    diagnostics: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def scan_repository(project_path: str) -> ScanResult:
    """Scan a bounded Python snapshot with trusted rules and a 60-second limit.

    Status is complete, partial, or error. Diagnostics deliberately omit source
    text and raw stderr, which may contain secrets. This supports Python only.
    """
    result = ScanResult('error')
    incomplete = False
    try:
        if not isinstance(project_path, str) or not project_path.strip() or '\x00' in project_path:
            result.diagnostics.append({'code': 'invalid_repository'})
            return result
        requested = Path(project_path)
        if not requested.is_dir() or _linked(requested):
            result.diagnostics.append({'code': 'invalid_repository'})
            return result
        project = requested.resolve()
        state = ROOT / '.semgrep-local'
        if state.exists() and _linked(state):
            result.diagnostics.append({'code': 'invalid_scanner_state'})
            return result
        state.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='scan-', dir=state) as work:
            work = Path(work)
            snapshot = work / 'repository'
            snapshot.mkdir()
            # Override Semgrep's default ignore template with a trusted empty one.
            # Uploaded ignore files and inline suppression comments cannot hide coverage.
            (snapshot / '.semgrepignore').write_text('', encoding='utf-8')
            count = size = 0
            copied = set()
            unsupported = 0

            def walk_error(_error):
                nonlocal incomplete
                incomplete = True
                result.diagnostics.append({'code': 'directory_unreadable'})

            for folder, dirs, files in os.walk(project, followlinks=False,
                                               onerror=walk_error):
                dirs.sort()
                for directory in dirs[:]:
                    path = Path(folder) / directory
                    if directory in EXCLUDED:
                        dirs.remove(directory)
                    elif _linked(path):
                        dirs.remove(directory)
                        incomplete = True
                        result.diagnostics.append({'code': 'linked_directory_skipped',
                            'file': path.relative_to(project).as_posix()})
                for name in sorted(files):
                    if Path(name).suffix.lower() != '.py':
                        unsupported += 1
                        continue
                    path = Path(folder) / name
                    relative = path.relative_to(project)
                    if _linked(path) or not path.resolve().is_relative_to(project):
                        incomplete = True
                        result.diagnostics.append({'code': 'linked_file_skipped',
                                                   'file': relative.as_posix()})
                        continue
                    try:
                        with path.open('rb') as source:
                            content = source.read(MAX_FILE_BYTES + 1)
                        if (len(content) > MAX_FILE_BYTES or count >= MAX_FILES
                                or size + len(content) > MAX_TOTAL_BYTES):
                            incomplete = True
                            result.diagnostics.append({'code': 'coverage_limit',
                                                       'file': relative.as_posix()})
                            continue
                        text = content.decode('utf-8-sig')
                        try:
                            ast.parse(text, filename=relative.as_posix())
                        except (SyntaxError, ValueError, RecursionError):
                            incomplete = True
                            result.diagnostics.append({'code': 'python_syntax_error',
                                                       'file': relative.as_posix()})
                            continue
                        target = snapshot / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content)
                        copied.add(relative.as_posix())
                        count += 1
                        size += len(content)
                    except (OSError, UnicodeError):
                        incomplete = True
                        result.diagnostics.append({'code': 'file_unreadable_or_non_utf8',
                                                   'file': relative.as_posix()})
            result.diagnostics.append({'code': 'coverage', 'language': 'python',
                'snapshot_files': count, 'excluded_directories': sorted(EXCLUDED),
                'unsupported_files': unsupported, 'rule_set': 'python-security-v2'})
            if count == 0:
                result.diagnostics.append({'code': 'no_supported_files'})
                return result
            env = os.environ.copy()
            env.pop('PYTHONPATH', None)
            env.pop('PYTHONHOME', None)
            env.update(SEMGREP_LOG_FILE=str(work / 'scanner.log'),
                SEMGREP_SETTINGS_FILE=str(work / 'settings.yaml'),
                SEMGREP_VERSION_CACHE_PATH=str(work / 'version'),
                SEMGREP_SEND_METRICS='off', SEMGREP_ENABLE_VERSION_CHECK='0',
                PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONSAFEPATH='1')
            scanner = Path(sys.executable).parent / ('semgrep.exe' if os.name == 'nt'
                                                     else 'semgrep')
            command = [str(scanner), 'scan', '--config', str(RULE), '--json',
                       '--metrics=off', '--disable-version-check', '--no-git-ignore',
                       '--no-rewrite-rule-ids', '--disable-nosem',
                       '--novcs', '--project-root', str(snapshot),
                       '--scan-unknown-extensions', '--jobs', '1', '.']
            # Unknown-extension scanning applies only to explicit targets. Windows
            # accepts .PY; provide those targets explicitly with a safe argv budget.
            argument_size = sum(len(argument) + 3 for argument in command)
            for relative in sorted(copied):
                if Path(relative).suffix != '.py':
                    argument_size += len(relative) + 3
                    if argument_size < 28000:
                        command.append(relative)
                    else:
                        incomplete = True
                        result.diagnostics.append({'code': 'target_argument_limit', 'file': relative})
            process = subprocess.run(command, cwd=snapshot, env=env, shell=False,
                                     timeout=60, capture_output=True)
            result.diagnostics.append({'code': 'scanner_exit',
                                       'exit_code': process.returncode})
            try:
                data = json.loads(process.stdout)
                raw_findings = data['results']
                errors = data['errors']
                if (not isinstance(raw_findings, list) or not isinstance(errors, list)
                        or not isinstance(data.get('paths', {}).get('scanned'), list)):
                    raise ValueError('Invalid scanner arrays')
                if not all(isinstance(error, dict) for error in errors):
                    raise ValueError('Invalid scanner errors')
                normalized = [_normalize(finding, snapshot) for finding in raw_findings]
                if any(finding['file'] not in copied for finding in normalized):
                    raise ValueError('Finding references a file outside the snapshot inventory')
                unique = {}
                for finding in normalized:
                    previous = unique.get(finding['id'])
                    if previous is not None and previous != finding:
                        raise ValueError('Conflicting duplicate finding')
                    unique[finding['id']] = finding
                result.findings = list(unique.values())
                if len(normalized) != len(result.findings):
                    result.diagnostics.append({'code': 'duplicate_findings_removed',
                        'count': len(normalized) - len(result.findings)})
                for error in errors:
                    result.diagnostics.append({'code': 'scanner_error',
                        'type': error.get('type', 'unknown')})
                scanned = set()
                for scanned_path in data.get('paths', {}).get('scanned', []):
                    scanned.add(repository_relative_path(scanned_path, snapshot))
                result.diagnostics.append({'code': 'scanner_coverage', 'files': len(scanned)})
                for missing in sorted(copied - scanned):
                    result.diagnostics.append({'code': 'scanner_skipped_file', 'file': missing})
                incomplete |= bool(errors) or scanned != copied
            except (ValueError, KeyError, TypeError, AttributeError):
                result.findings = []
                result.diagnostics.append({'code': 'invalid_scanner_output'})
                return result
            if process.returncode != 0:
                result.status = 'partial' if result.findings else 'error'
            else:
                result.status = 'partial' if incomplete else 'complete'
    except subprocess.TimeoutExpired:
        result.diagnostics.append({'code': 'scanner_timeout', 'seconds': 60})
    except (OSError, ValueError, TypeError):
        result.diagnostics.append({'code': 'scanner_or_filesystem_unavailable'})
    result.findings.sort(key=lambda f: (f['file'], f['start_line'], f['rule_id'], f['id']))
    for finding in result.findings:
        result.summary['total'] += 1
        result.summary[finding['severity'].lower()] += 1
    return result
