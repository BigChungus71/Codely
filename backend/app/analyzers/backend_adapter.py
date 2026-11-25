"""Compatibility hook for the teammate backend's CODELY_SCANNER_ADAPTER seam."""
from .semgrep_adapter import scan_repository as _scan_repository


def scan_repository(project_path: str) -> dict:
    result = _scan_repository(project_path)
    payload = result.to_dict()
    # The teammate backend checks errors before caching a completed result.
    payload['errors'] = [] if result.status == 'complete' else [
        {'code': 'security_scan_incomplete', 'status': result.status}]
    return payload
