"""Teammate hooks are synchronous Python callables selected by module:function.

Scanner(path: str) -> ScanResult-compatible dict
Architecture(path: str) -> {nodes: [...], edges: [...]}
Explanation(finding: dict, context: dict) -> Explanation-compatible dict
Hooks own their I/O timeouts. The built-in scanner has a process timeout.
"""
import hashlib
import importlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from fastapi import HTTPException
from .repository import SKIP


def hook(variable: str):
    spec = os.getenv(variable)
    if not spec: return None
    try:
        module, name = spec.split(':', 1)
        return getattr(importlib.import_module(module), name)
    except (ImportError, AttributeError, ValueError):
        raise HTTPException(503, f'{variable} adapter could not be loaded')


def scan_repository(project_path: str):
    custom = hook('CODELY_SCANNER_ADAPTER')
    if custom: return custom(project_path)
    executable = shutil.which('semgrep')
    config = os.getenv('SEMGREP_CONFIG')
    if not config and executable:
        from .teammate_services import scan_python
        return scan_python(project_path)
    if not executable or not config:
        raise HTTPException(503, 'Scanner unavailable: provide CODELY_SCANNER_ADAPTER or install Semgrep and set SEMGREP_CONFIG')
    command = [executable, 'scan', '--json', '--metrics=off', '--disable-version-check', '--strict', '--config', config]
    for directory in sorted(SKIP): command.extend(['--exclude', directory])
    command.append('.')
    try:
        result = subprocess.run(command, cwd=project_path, capture_output=True, text=True, timeout=90, check=False)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, 'Security scan exceeded 90 seconds')
    except OSError:
        raise HTTPException(503, 'Scanner could not start')
    if result.returncode != 0:
        raise HTTPException(502, 'Semgrep scan failed; check scanner configuration locally')
    data = json.loads(result.stdout)
    findings = []
    for item in data['results']:
        extra = item['extra']
        file = item['path']
        path = Path(file)
        if path.is_absolute(): file = path.relative_to(Path(project_path)).as_posix()
        identity = f"{item['check_id']}:{file}:{item['start']['line']}:{item['end']['line']}"
        cwe = extra.get('metadata', {}).get('cwe', [])
        findings.append({
            'id': hashlib.sha256(identity.encode()).hexdigest()[:20],
            'rule_id': item['check_id'], 'source': 'semgrep',
            'severity': {'ERROR': 'HIGH', 'WARNING': 'MEDIUM', 'INFO': 'INFO'}.get(extra.get('severity'), 'UNKNOWN'),
            'title': item['check_id'], 'file': file,
            'start_line': item['start']['line'], 'end_line': item['end']['line'],
            'message': extra['message'], 'cwe': [cwe] if isinstance(cwe, str) else cwe,
            'evidence': item,
        })
    return {'findings': findings, 'errors': data.get('errors', [])}


def architecture(project_path: str):
    custom = hook('CODELY_ARCHITECTURE_ADAPTER')
    if custom:
        return custom(project_path)
    from .teammate_services import project_graph
    return project_graph(project_path)


def explain(finding: dict, context: dict):
    custom = hook('CODELY_EXPLANATION_ADAPTER')
    if custom:
        return custom(finding, {key: context[key] for key in ('file', 'start_line', 'content')})
    from .teammate_services import review_finding
    return review_finding(context['project_id'], context['root'], finding)
