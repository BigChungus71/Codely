"""Strict Semgrep result normalization without changing the shared contract."""
import hashlib
from pathlib import Path, PureWindowsPath
import re


SEVERITIES = {'ERROR': 'HIGH', 'WARNING': 'MEDIUM', 'INFO': 'LOW',
              'CRITICAL': 'CRITICAL', 'HIGH': 'HIGH', 'MEDIUM': 'MEDIUM', 'LOW': 'LOW'}


def repository_relative_path(value, snapshot):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Invalid scanner path')
    # Treat backslashes as separators even when parsing Windows output on Linux.
    windows = PureWindowsPath(value)
    if windows.drive and not windows.is_absolute():
        raise ValueError('Drive-relative scanner path')
    if windows.is_absolute() and not Path(value).is_absolute():
        raise ValueError('Foreign absolute scanner path')
    if value.startswith(('\\\\', '//')):
        raise ValueError('Network scanner path')
    path = Path(value.replace('\\', '/'))
    if not path.is_absolute():
        path = snapshot / path
    return path.resolve().relative_to(snapshot.resolve()).as_posix()


def _position(position, key, default=None):
    value = position.get(key, default)
    if type(value) is not int or value < (0 if key == 'col' else 1):
        raise ValueError('Invalid source position')
    return value


def normalize_finding(raw, snapshot):
    relative = repository_relative_path(raw['path'], snapshot)
    extra = raw['extra']
    severity = SEVERITIES[extra['severity'].upper()]
    rule_id = raw['check_id']
    if not isinstance(rule_id, str) or not rule_id:
        raise ValueError('Invalid rule ID')
    start, end = _position(raw['start'], 'line'), _position(raw['end'], 'line')
    start_col, end_col = _position(raw['start'], 'col', 0), _position(raw['end'], 'col', 0)
    if end < start or (start == end and start_col and end_col and end_col < start_col):
        raise ValueError('Invalid source range')
    metadata = extra.get('metadata', {})
    cwe = metadata.get('cwe', [])
    if isinstance(cwe, str):
        cwe = [cwe]
    if not isinstance(cwe, list) or not all(isinstance(item, str) for item in cwe):
        raise ValueError('Invalid CWE metadata')
    message = extra['message']
    title = metadata.get('title', message)
    if not isinstance(message, str) or not isinstance(title, str):
        raise ValueError('Invalid finding text')
    identity = f'{rule_id}:{relative}:{start}:{start_col}:{end}:{end_col}'
    return {
        'id': 'finding_' + hashlib.sha256(identity.encode()).hexdigest()[:16],
        'rule_id': rule_id, 'source': 'semgrep', 'severity': severity,
        'title': title, 'file': relative, 'start_line': start, 'end_line': end,
        'message': message, 'cwe': sorted(set(re.findall(r'\bCWE-\d+\b', ' '.join(cwe)))),
    }
